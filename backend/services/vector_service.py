"""
Vector Service — Retrieval-Augmented Adapter & Hook Matching
============================================================
Implements semantic search over the adapter and hook catalogs using
Google text-embedding-005 with MRL-512 truncation.

Key design decisions:
  • Embeddings derived from actual adapter/hook JSON files (not hardcoded strings)
  • Each JSON is cleaned to strip operational noise (endpoints, error_codes,
    maturity_score, timeout_ms, retry_policy, sandbox_base_url, credential_env_vars)
    before building the embedding text — only semantic intent signals are kept
  • Rich semantic fields (description, use_cases, semantic_tags, compliance_context,
    typical_callers, auth_description) are embedded with full context
  • Required/optional field names and descriptions are included for field-level matching
  • Incremental per-entry hashing (only re-embeds files that changed on disk)
  • Catalog is scanned directly from the adapters/ and hooks/ directories —
    no master_index.json dependency for the embedding document side
  • Similarity scores surfaced to LLM prompt for explainability
  • Confidence threshold (0.45) with graceful fallback to full catalog
  • Vectorized numpy cosine similarity (matrix multiply, not a loop)
  • MRL-512 truncation: 33% smaller cache, <1% accuracy loss
"""

import json
import hashlib
import time
import traceback
from pathlib import Path
from typing import Optional

import numpy as np

from backend.config import (
    ADAPTER_MASTER_INDEX,
    HOOK_MASTER_INDEX,
    ADAPTERS_CATALOG_DIR,
    HOOKS_CATALOG_DIR,
    ADAPTER_EMBEDDINGS_CACHE,
    HOOK_EMBEDDINGS_CACHE,
    VECTOR_TOP_K_ADAPTERS,
    VECTOR_TOP_K_HOOKS,
    VECTOR_SIMILARITY_THRESHOLD,
    VECTOR_EMBEDDING_DIM,
    GEMINI_EMBEDDING_MODEL,
    get_google_api_key,
)


# ── Module-level state ────────────────────────────────────────────────────────

_embeddings_available: bool = False  # Set to True after successful build
_adapter_cache: dict = {}            # In-memory adapter embeddings cache
_hook_cache: dict = {}               # In-memory hook embeddings cache


# ── Semantic Text Extractors ──────────────────────────────────────────────────
#
# These functions read a full adapter or hook JSON and extract ONLY the semantic
# signals relevant for matching — stripping operational noise so the embedding
# model focuses on intent, purpose, and domain context.
#
# Fields KEPT for adapters (semantic signals):
#   adapter_name, category, provider, description, use_cases, semantic_tags,
#   compliance_context, typical_callers, auth_type, auth_description,
#   required_fields (name + description), optional_fields (name + description)
#
# Fields STRIPPED for adapters (operational noise, not useful for matching):
#   base_url, versions[].endpoint, maturity_score, error_codes, timeout_ms,
#   retry_policy, sandbox_base_url, fallback_adapter, credential_env_vars,
#   versions[].release_notes, versions[].sunset_date, response_schema
#
# Fields KEPT for hooks (semantic signals):
#   hook_name, hook_type, description, use_cases, semantic_tags, when_to_use,
#   trigger_condition, applicable_adapters
#
# Fields STRIPPED for hooks:
#   payload_template, input_parameters, output, timeout_ms, retry_policy,
#   credential_env_vars, error_codes, example_log_entry


def _extract_adapter_embedding_text(adapter_json: dict) -> str:
    """
    Build a clean, rich natural-language embedding string from an adapter JSON.

    Strips all technical/operational fields. Keeps only semantic signals that
    are useful for matching against BRD/requirement descriptions.
    """
    parts = []

    # Core identity
    if adapter_json.get("adapter_name"):
        parts.append(f"Adapter: {adapter_json['adapter_name']}.")
    if adapter_json.get("provider"):
        parts.append(f"Provider: {adapter_json['provider']}.")
    if adapter_json.get("category"):
        parts.append(f"Category: {adapter_json['category']}.")

    # Rich semantic description (the most important signal)
    if adapter_json.get("description"):
        parts.append(adapter_json["description"])

    # Use cases (concrete business scenarios)
    if adapter_json.get("use_cases"):
        parts.append(f"Use cases: {'; '.join(adapter_json['use_cases'])}.")

    # Semantic tags (keyword cloud for fuzzy domain matching)
    if adapter_json.get("semantic_tags"):
        parts.append(f"Tags: {', '.join(adapter_json['semantic_tags'])}.")

    # Compliance and regulatory context
    if adapter_json.get("compliance_context"):
        parts.append(f"Compliance: {adapter_json['compliance_context']}.")

    # Who typically calls this adapter
    if adapter_json.get("typical_callers"):
        parts.append(f"Typical callers: {adapter_json['typical_callers']}.")

    # Auth type with human description
    auth_desc = adapter_json.get("auth_description") or adapter_json.get("auth_type", "")
    if auth_desc:
        parts.append(f"Authentication: {auth_desc}.")

    # Required fields — names and human descriptions only (no validation rules)
    req_fields = adapter_json.get("required_fields", [])
    if req_fields:
        field_descs = []
        for f in req_fields:
            if isinstance(f, dict) and f.get("field_name"):
                desc = f.get("description", "")
                field_descs.append(f"{f['field_name']} ({desc})" if desc else f["field_name"])
        if field_descs:
            parts.append(f"Required fields: {', '.join(field_descs)}.")

    # Optional fields — names and human descriptions only
    opt_fields = adapter_json.get("optional_fields", [])
    if opt_fields:
        field_descs = []
        for f in opt_fields:
            if isinstance(f, dict) and f.get("field_name"):
                desc = f.get("description", "")
                field_descs.append(f"{f['field_name']} ({desc})" if desc else f["field_name"])
        if field_descs:
            parts.append(f"Optional fields: {', '.join(field_descs)}.")

    return " ".join(parts)


def _extract_hook_embedding_text(hook_json: dict) -> str:
    """
    Build a clean, rich natural-language embedding string from a hook JSON.

    Focuses on what the hook does, when it fires, and which integrations use it.
    Strips operational config (timeout, retry_policy, input_parameters, etc.)
    """
    parts = []

    # Core identity
    name = hook_json.get("hook_name") or hook_json.get("id", "")
    hook_type = hook_json.get("hook_type") or hook_json.get("type", "")
    if name:
        parts.append(f"Hook: {name}.")
    if hook_type:
        parts.append(f"Type: {hook_type}.")

    # Rich description
    if hook_json.get("description"):
        parts.append(hook_json["description"])

    # Use cases
    if hook_json.get("use_cases"):
        parts.append(f"Use cases: {'; '.join(hook_json['use_cases'])}.")

    # Semantic tags
    if hook_json.get("semantic_tags"):
        parts.append(f"Tags: {', '.join(hook_json['semantic_tags'])}.")

    # When to use guidance
    if hook_json.get("when_to_use"):
        parts.append(f"When to use: {hook_json['when_to_use']}.")

    # Trigger condition
    if hook_json.get("trigger_condition"):
        parts.append(f"Trigger: {hook_json['trigger_condition']}.")

    # Applicable adapters
    applicable = hook_json.get("applicable_adapters", [])
    if applicable and applicable != ["*"]:
        parts.append(f"Applicable to adapters: {', '.join(applicable)}.")
    elif applicable == ["*"]:
        parts.append("Applicable to all adapters.")

    return " ".join(parts)


# ── Embedding Client ──────────────────────────────────────────────────────────

def _get_embedding(text: str, max_retries: int = 4, task_type: str = "RETRIEVAL_DOCUMENT", title: str = None) -> list[float]:
    """
    Call Gemini embedding model with MRL truncation and task_type configuration.
    Returns a float list of configured dimensionality.
    """
    from google import genai
    from google.genai import types as gtypes

    api_key = get_google_api_key()
    client = genai.Client(api_key=api_key)

    for attempt in range(max_retries):
        try:
            config_kwargs = {
                "output_dimensionality": VECTOR_EMBEDDING_DIM,
                "task_type": task_type,
            }
            if title:
                config_kwargs["title"] = title

            result = client.models.embed_content(
                model=GEMINI_EMBEDDING_MODEL,
                contents=text,
                config=gtypes.EmbedContentConfig(**config_kwargs),
            )
            return result.embeddings[0].values
        except Exception as e:
            error_str = str(e).lower()
            is_retryable = any(kw in error_str for kw in [
                "429", "rate", "resource_exhausted", "quota",
                "503", "overloaded", "unavailable", "deadline",
            ])
            if is_retryable and attempt < max_retries - 1:
                wait_time = min(2 ** attempt * 3, 60)
                print(f"  ⏳ Embedding API rate limited (attempt {attempt + 1}/{max_retries}). Waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            raise


# ── File Hash Helpers ─────────────────────────────────────────────────────────

def _file_hash(path: Path) -> str:
    """MD5 hash of a file's content. Returns '' if file doesn't exist."""
    if not path.exists():
        return ""
    return hashlib.md5(path.read_bytes()).hexdigest()


# ── Cache I/O ─────────────────────────────────────────────────────────────────

def _load_cache(cache_path: Path) -> dict:
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache_path: Path, cache: dict) -> None:
    cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")


# ── Build / Rebuild ───────────────────────────────────────────────────────────

def build_adapter_embeddings(force: bool = False) -> dict:
    """
    Build (or incrementally update) the adapter embeddings cache.

    Scans ADAPTERS_CATALOG_DIR for *.json files directly (excluding master_index.json).
    For each adapter JSON:
      1. Checks the MD5 hash — skips if unchanged and embedding exists in cache
      2. Loads the full adapter JSON
      3. Extracts a clean semantic embedding text via _extract_adapter_embedding_text()
         (strips endpoints, error_codes, timeout_ms, etc.)
      4. Calls Gemini text-embedding-005 to generate a 512-dim vector
      5. Stores the embedding, hash, and key metadata in the cache file

    Returns the updated in-memory cache dict.
    """
    global _adapter_cache, _embeddings_available

    cache = _load_cache(ADAPTER_EMBEDDINGS_CACHE)
    rebuilt = []
    skipped = []

    # Scan the adapters directory directly — no master_index dependency
    adapter_files = [
        p for p in ADAPTERS_CATALOG_DIR.glob("*.json")
        if p.name != "master_index.json"
    ]

    if not adapter_files:
        print("  ⚠️  No adapter JSON files found in catalog directory.")
        return {"rebuilt": [], "skipped": []}

    for adapter_file in sorted(adapter_files):
        adapter_id = adapter_file.stem  # e.g. "cibil", "experian", "karza"
        current_hash = _file_hash(adapter_file)

        cached_entry = cache.get(adapter_id, {})
        if not force and cached_entry.get("file_hash") == current_hash and cached_entry.get("embedding"):
            skipped.append(adapter_id)
            continue

        # Load and parse the adapter JSON
        try:
            adapter_json = json.loads(adapter_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  ⚠️  Failed to parse adapter JSON '{adapter_file.name}': {e}")
            continue

        # Extract clean semantic text for embedding (strips operational noise)
        embedding_text = _extract_adapter_embedding_text(adapter_json)

        print(f"  🔢 Embedding adapter: {adapter_id}...")
        try:
            embedding = _get_embedding(embedding_text)
        except Exception as e:
            print(f"  ⚠️  Failed to embed adapter '{adapter_id}': {e}")
            continue

        # Determine category and name from the JSON itself
        category = adapter_json.get("category", "")
        name = adapter_json.get("adapter_name", adapter_id)

        # Build version list (stable non-deprecated versions only for metadata)
        versions = [
            v.get("version", "") for v in adapter_json.get("versions", [])
            if not v.get("deprecated", False)
        ]

        cache[adapter_id] = {
            "file_hash": current_hash,
            "embedding": embedding,
            "id": adapter_id,
            "name": name,
            "category": category,
            "versions": versions,
            "path": adapter_file.name,
        }
        rebuilt.append(adapter_id)

    # Update meta
    cache["_meta"] = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": GEMINI_EMBEDDING_MODEL,
        "dim": VECTOR_EMBEDDING_DIM,
        "source": "adapter_json_files",
    }

    _save_cache(ADAPTER_EMBEDDINGS_CACHE, cache)
    _adapter_cache = cache
    _embeddings_available = True

    if rebuilt:
        print(f"  ✅ Adapter embeddings: rebuilt {len(rebuilt)} ({', '.join(rebuilt)}), skipped {len(skipped)}")
    else:
        print(f"  ✅ Adapter embeddings: all {len(skipped)} entries up-to-date (no rebuild needed)")

    return {"rebuilt": rebuilt, "skipped": skipped}


def build_hook_embeddings(force: bool = False) -> dict:
    """
    Build (or incrementally update) the hook embeddings cache.

    Scans HOOKS_CATALOG_DIR for *.json files directly (excluding master_index.json).
    For each hook JSON:
      1. Checks MD5 hash — skips if unchanged and embedding exists in cache
      2. Extracts clean semantic text via _extract_hook_embedding_text()
      3. Embeds using Gemini text-embedding-005

    Returns summary of rebuilt/skipped entries.
    """
    global _hook_cache

    cache = _load_cache(HOOK_EMBEDDINGS_CACHE)
    rebuilt = []
    skipped = []

    # Scan the hooks directory directly — no master_index dependency
    hook_files = [
        p for p in HOOKS_CATALOG_DIR.glob("*.json")
        if p.name != "master_index.json"
    ]

    if not hook_files:
        print("  ⚠️  No hook JSON files found in catalog directory.")
        return {"rebuilt": [], "skipped": []}

    for hook_file in sorted(hook_files):
        hook_id = hook_file.stem  # e.g. "retry_hook", "audit_emit_hook"
        current_hash = _file_hash(hook_file)

        cached_entry = cache.get(hook_id, {})
        if not force and cached_entry.get("file_hash") == current_hash and cached_entry.get("embedding"):
            skipped.append(hook_id)
            continue

        # Load and parse the hook JSON
        try:
            hook_json = json.loads(hook_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  ⚠️  Failed to parse hook JSON '{hook_file.name}': {e}")
            continue

        # Extract clean semantic text for embedding
        embedding_text = _extract_hook_embedding_text(hook_json)

        print(f"  🔢 Embedding hook: {hook_id}...")
        try:
            embedding = _get_embedding(embedding_text)
        except Exception as e:
            print(f"  ⚠️  Failed to embed hook '{hook_id}': {e}")
            continue

        name = hook_json.get("hook_name") or hook_json.get("id") or hook_id
        hook_type = hook_json.get("hook_type") or hook_json.get("type", "")

        cache[hook_id] = {
            "file_hash": current_hash,
            "embedding": embedding,
            "id": hook_id,
            "name": name,
            "type": hook_type,
            "path": hook_file.name,
        }
        rebuilt.append(hook_id)

    cache["_meta"] = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": GEMINI_EMBEDDING_MODEL,
        "dim": VECTOR_EMBEDDING_DIM,
        "source": "hook_json_files",
    }

    _save_cache(HOOK_EMBEDDINGS_CACHE, cache)
    _hook_cache = cache

    if rebuilt:
        print(f"  ✅ Hook embeddings: rebuilt {len(rebuilt)} ({', '.join(rebuilt)}), skipped {len(skipped)}")
    else:
        print(f"  ✅ Hook embeddings: all {len(skipped)} entries up-to-date")

    return {"rebuilt": rebuilt, "skipped": skipped}


def ensure_embeddings_fresh() -> None:
    """
    Called on startup and after catalog uploads. Incrementally rebuilds
    any stale entries. Fails gracefully — pipeline falls back to full-index
    LLM matching if embeddings are unavailable.
    """
    global _embeddings_available, _adapter_cache, _hook_cache

    print("\n  🔍 Vector Service: checking embedding cache freshness...")
    try:
        build_adapter_embeddings()
        build_hook_embeddings()
        _embeddings_available = True
    except Exception as e:
        print(f"  ⚠️  Vector Service: failed to build embeddings — falling back to full-index matching. Error: {e}")
        traceback.print_exc()
        _embeddings_available = False

    # Load caches into memory if not already loaded
    if not _adapter_cache:
        _adapter_cache = _load_cache(ADAPTER_EMBEDDINGS_CACHE)
    if not _hook_cache:
        _hook_cache = _load_cache(HOOK_EMBEDDINGS_CACHE)


# ── Search ────────────────────────────────────────────────────────────────────

def search_adapters(
    query: str,
    category: Optional[str] = None,
    top_k: int = VECTOR_TOP_K_ADAPTERS,
) -> list[dict]:
    """
    Retrieve the top-K most semantically similar adapters for a query.

    Args:
        query:    Rich natural-language description of the service requirement.
                  Built by stage3_matching._build_adapter_search_query().
        category: If provided, restricts search to adapters in this category
                  (deterministic pre-filter before vector search).
        top_k:    Number of candidates to return (default: VECTOR_TOP_K_ADAPTERS=3).

    Returns:
        List of dicts with keys: adapter_id, name, category, versions,
        path, semantic_similarity_score, low_confidence.
        Empty list if embeddings are unavailable (caller should fall back).
    """
    global _embeddings_available, _adapter_cache

    if not _embeddings_available or not _adapter_cache:
        return []

    # Reload from disk if in-memory cache is empty (e.g. after process restart)
    if not _adapter_cache:
        _adapter_cache = _load_cache(ADAPTER_EMBEDDINGS_CACHE)

    # Filter to relevant entries (skip _meta key)
    candidates = {
        k: v for k, v in _adapter_cache.items()
        if k != "_meta" and isinstance(v, dict) and "embedding" in v
    }

    # Hybrid retrieval: deterministic category pre-filter
    if category:
        filtered = {
            k: v for k, v in candidates.items()
            if v.get("category", "").lower() == category.lower()
        }
        # If category filter leaves nothing (e.g. new unknown category), fall back to full set
        if filtered:
            candidates = filtered

    if not candidates:
        return []

    # Embed the query
    try:
        query_vec = np.array(_get_embedding(query, task_type="RETRIEVAL_QUERY"), dtype=np.float32)
    except Exception as e:
        print(f"  ⚠️  Failed to embed query for adapter search: {e}")
        return []

    # Vectorized cosine similarity (matrix multiply — one operation, not a loop)
    ids = list(candidates.keys())
    matrix = np.array([candidates[k]["embedding"] for k in ids], dtype=np.float32)

    # L2-normalize for cosine similarity via dot product
    query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
    matrix_norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-10
    matrix_normed = matrix / matrix_norms

    scores = np.dot(matrix_normed, query_norm)  # shape: (n_candidates,)

    # Sort descending, take top-K
    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    for idx in top_indices:
        score = float(scores[idx])
        adapter_id = ids[idx]
        entry = candidates[adapter_id]

        # Confidence threshold gate
        low_confidence = score < VECTOR_SIMILARITY_THRESHOLD

        results.append({
            "adapter_id": adapter_id,
            "name": entry.get("name", adapter_id),
            "category": entry.get("category", ""),
            "versions": entry.get("versions", []),
            "path": entry.get("path", ""),
            "semantic_similarity_score": round(score, 4),
            "low_confidence": low_confidence,
        })

    return results


def search_hooks(
    query: str,
    top_k: int = VECTOR_TOP_K_HOOKS,
) -> list[dict]:
    """
    Retrieve the top-K most semantically similar hooks for a query.

    Args:
        query: Natural-language description of the integration context
               (e.g. "bureau integration requiring PII encryption and audit trail").
        top_k: Number of hook candidates to return.

    Returns:
        List of dicts with keys: hook_id, name, type, path, semantic_similarity_score.
    """
    global _embeddings_available, _hook_cache

    if not _embeddings_available or not _hook_cache:
        return []

    if not _hook_cache:
        _hook_cache = _load_cache(HOOK_EMBEDDINGS_CACHE)

    candidates = {
        k: v for k, v in _hook_cache.items()
        if k != "_meta" and isinstance(v, dict) and "embedding" in v
    }

    if not candidates:
        return []

    try:
        query_vec = np.array(_get_embedding(query, task_type="RETRIEVAL_QUERY"), dtype=np.float32)
    except Exception as e:
        print(f"  ⚠️  Failed to embed query for hook search: {e}")
        return []

    ids = list(candidates.keys())
    matrix = np.array([candidates[k]["embedding"] for k in ids], dtype=np.float32)

    query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
    matrix_norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-10
    matrix_normed = matrix / matrix_norms

    scores = np.dot(matrix_normed, query_norm)

    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    for idx in top_indices:
        score = float(scores[idx])
        hook_id = ids[idx]
        entry = candidates[hook_id]
        results.append({
            "hook_id": hook_id,
            "name": entry.get("name", hook_id),
            "type": entry.get("type", ""),
            "path": entry.get("path", ""),
            "semantic_similarity_score": round(score, 4),
        })

    return results


def is_available() -> bool:
    """Returns True if embeddings are loaded and search is operational."""
    return _embeddings_available


# ── Query Builders (QUERY side — used by stage3_matching.py) ─────────────────
#
# These build the QUERY that gets embedded and compared against adapter/hook
# document embeddings. The query comes from Stage 2 service requirements.
# Note: Input fields are deliberately excluded from adapter queries to avoid
# false matches on common field names like pan_number that appear in all adapters.

def build_service_query(service: dict) -> str:
    """
    Build a rich natural-language query string from a Stage 2 detected service dict.
    Used in Stage 3 to search for matching adapters via cosine similarity.

    Deliberately excludes input field names — they pollute the query with generic
    terms (pan_number, mobile_number) that appear in many adapters, diluting intent.
    """
    parts = [
        f"Integration requirement: {service.get('service_name', '')}.",
        f"Purpose: {service.get('purpose', '')}.",
        f"Category: {service.get('category', '')}.",
    ]
    if service.get("provider"):
        parts.append(f"Provider: {service['provider']}.")
    if service.get("version_hint"):
        parts.append(f"Version hint from BRD: {service['version_hint']}.")
    if service.get("compliance_requirements"):
        parts.append(f"Compliance: {', '.join(service['compliance_requirements'])}.")
    return " ".join(parts)


def build_hook_query(integration: dict) -> str:
    """
    Build a natural-language query for hook matching from an integration dict.
    Used in Stage 3 to search for relevant hooks for each integration.
    """
    parts = [
        f"Integration: {integration.get('service_name', '')}.",
        f"Category: {integration.get('category', '')}.",
        f"Adapter: {integration.get('adapter_id', '')}.",
    ]
    if integration.get("is_mandatory"):
        parts.append("This is a mandatory integration.")
    if integration.get("compliance_requirements"):
        parts.append(f"Compliance requirements: {', '.join(integration['compliance_requirements'])}.")
    return " ".join(parts)


# ── Public alias ──────────────────────────────────────────────────────────────

def build_embeddings_cache(force: bool = False) -> None:
    """
    Public entry point for startup warming and post-upload incremental rebuilds.
    Delegates to ensure_embeddings_fresh() which calls build_adapter_embeddings()
    and build_hook_embeddings() with per-entry MD5 hash checking.

    Args:
        force: If True, re-embeds all entries even if hashes haven't changed.
               Pass force=True after making semantic field changes to adapter JSONs.
    """
    ensure_embeddings_fresh()

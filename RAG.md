# FinSpark RAG Architecture — Complete Technical Reference

> **Document version:** 2.0 (Post-refactor — JSON-driven embeddings)
> **Last updated:** May 2026

---

## Table of Contents

1. [Overview](#1-overview)
2. [RAG Source: Adapter & Hook JSON Files](#2-rag-source-adapter--hook-json-files)
3. [Semantic Fields in Adapter JSONs](#3-semantic-fields-in-adapter-jsons)
4. [Semantic Fields in Hook JSONs](#4-semantic-fields-in-hook-jsons)
5. [JSON Cleaning: What Gets Stripped](#5-json-cleaning-what-gets-stripped)
6. [Semantic Text Extraction](#6-semantic-text-extraction)
7. [Vector Embedding Generation](#7-vector-embedding-generation)
8. [Incremental Embedding Cache](#8-incremental-embedding-cache)
9. [Stage 3: Adapter Matching Pipeline](#9-stage-3-adapter-matching-pipeline)
10. [Stage 3: Hook Matching Pipeline](#10-stage-3-hook-matching-pipeline)
11. [Full End-to-End Flow](#11-full-end-to-end-flow)
12. [File Map](#12-file-map)

---

## 1. Overview

FinSpark's RAG system enables the pipeline to match a BRD (Business Requirements Document) against 500+ API adapters and lifecycle hooks using semantic vector search — even when the BRD uses vague domain language without naming any specific APIs.

### The Core Problem

A BRD might say:
> *"We need to verify the creditworthiness of borrowers based on their repayment history and outstanding debts."*

No mention of "CIBIL". No mention of "credit bureau". The RAG engine must bridge this gap purely through semantic similarity.

### Solution Architecture

```
BRD (PDF/DOCX)
    │
    ▼
Stage 1: Document Extraction
    │
    ▼
Stage 2: Service Requirement Detection (LLM)
    │   Extracts: service_name, purpose, category, provider, version_hint
    ▼
Stage 3: Adapter Matching via Vector Search
    │   1. Build NL search query from Stage 2 output
    │   2. Embed query → 512-dim vector (text-embedding-005)
    │   3. Cosine similarity vs adapter embeddings cache
    │   4. Top-3 candidates → LLM chooses best
    │   5. Load full adapter JSON for chosen adapter
    │
    ▼
Stage 4-7: Config Generation, Enrichment, Simulation, Deployment
```

---

## 2. RAG Source: Adapter & Hook JSON Files

### Previous Architecture (Deprecated)

Previously, the system used hardcoded Python strings in `vector_service.py` like:

```python
_ADAPTER_DESCRIPTIONS = {
    "cibil": "TransUnion CIBIL Bureau — A credit bureau adapter...",
    ...
}
```

**Problems:**
- Descriptions were static and could drift from the actual adapter's capabilities
- New adapters added to the catalog didn't automatically get embeddings
- Hook descriptions were similarly hardcoded

### New Architecture (Current)

**Each adapter and hook JSON file IS the RAG source.** The vector service reads the JSON files directly from:

- **Adapters:** `backend/catalogs/adapters/*.json` (12 files)
- **Hooks:** `backend/catalogs/hooks/*.json` (13 files, excluding master_index.json)

This means:
- Updating an adapter JSON automatically updates its embedding on next startup
- Adding a new `my_adapter.json` to the adapters folder automatically gets embedded
- The source of truth for both the pipeline AND the RAG engine is the same file

### Adapter Files

| File | Adapter | Category |
|------|---------|----------|
| `cibil.json` | TransUnion CIBIL | bureau |
| `experian.json` | Experian Credit Score | bureau |
| `karza.json` | Karza KYC | kyc |
| `digilocker.json` | DigiLocker | document |
| `gst.json` | GSTN API | gst |
| `pennydrop.json` | Penny Drop Verify | banking |
| `perfios.json` | Perfios Account Aggregator | banking |
| `razorpay.json` | Razorpay Payments | payment |
| `stripe_payment_adapter.json` | Stripe Payments | payment |
| `riskguard.json` | RiskGuard Analytics | fraud |
| `twilio.json` | Twilio SMS | messaging |
| `Aarogya_Health_API.json` | Aarogya Health API | health_records |

### Hook Files

| File | Hook | Type |
|------|------|------|
| `retry_hook.json` | retry_hook | retry |
| `audit_emit_hook.json` | audit_emit_hook | audit |
| `logging_hook.json` | logging_hook | post_call |
| `credential_resolve_hook.json` | credential_resolve_hook | pre-call |
| `field_encryption_hook.json` | field_encryption_hook | pre-call |
| `on_failure_alert_hook.json` | on_failure_alert_hook | on-failure |
| `post_schema_validation_hook.json` | post_schema_validation_hook | validation |
| `post_transform_hook.json` | post_transform_hook | post-call |
| `pre_auth_hook.json` | pre_auth_hook | pre-call |
| `pre_validation_hook.json` | pre_validation_hook | validation |
| `rate_limit_guard_hook.json` | rate_limit_guard_hook | pre-call |
| `simulation_intercept_hook.json` | simulation_intercept_hook | pre-call |
| `version_compatibility_hook.json` | version_compatibility_hook | pre-call |

---

## 3. Semantic Fields in Adapter JSONs

Every adapter JSON was enriched with the following fields specifically for RAG quality. These are what the embedding model "reads":

### `description` (string)
Rich, multi-sentence natural language description of the adapter's purpose, typical use cases, domain context, authentication type, and regulatory context. Written to match BRD language — e.g., mentions "borrower creditworthiness" not just "credit score". This is the **single highest-impact field** for retrieval accuracy.

**Example (cibil.json):**
```json
"description": "TransUnion CIBIL Bureau — Retrieves a borrower's CIBIL credit score and full bureau report. Used in lending pipelines for assessing creditworthiness, borrower eligibility, and risk-based pricing. The credit score reflects repayment history, outstanding loan balances, credit inquiries, defaults, and settlement flags. Required for RBI-regulated credit underwriting processes..."
```

### `use_cases` (array of strings)
Concrete, business-language use case descriptions. Each entry is a complete sentence describing a specific scenario where this adapter is used.

```json
"use_cases": [
    "Checking CIBIL score before personal loan approval",
    "Assessing creditworthiness for high-risk borrower segments",
    "Bureau pull for co-borrower eligibility in home loans"
]
```

### `semantic_tags` (array of strings)
A keyword cloud covering all domain terms, synonyms, and related concepts that a BRD might use to refer to this adapter. Includes technical terms, compliance keywords, and industry jargon.

```json
"semantic_tags": [
    "credit score", "CIBIL", "bureau", "credit report", "creditworthiness",
    "borrower risk", "RBI", "repayment history", "credit inquiry", "NPA"
]
```

### `compliance_context` (string)
Regulatory and compliance requirements associated with this adapter. Critical for matching BRDs that specify compliance needs.

```json
"compliance_context": "RBI-regulated credit information company. Data shared under CICRA 2005. Consent required before every bureau pull."
```

### `typical_callers` (string)
Describes the types of organizations and systems that commonly use this adapter. Helps match industry-specific BRDs.

```json
"typical_callers": "Retail lenders, NBFCs, microfinance institutions, fintech lending platforms, housing finance companies"
```

### `auth_description` (string)
Human-readable description of how authentication works. Useful for BRDs that mention specific auth requirements.

### `required_fields` and `optional_fields` (arrays)
Each field has `field_name` and `description`. The descriptions are embedded as semantic context (e.g., "pan_number (Borrower's 10-character alphanumeric PAN card identifier)").

---

## 4. Semantic Fields in Hook JSONs

Hook JSONs were enriched with parallel semantic fields:

### `description` (string)
Explains what the hook does, when it fires, and why it's important. Written in operational language that matches integration config requirements.

### `use_cases` (array of strings)
Specific scenarios where this hook is applied.

### `semantic_tags` (array of strings)
Domain keywords for the hook's function (e.g., "retry", "backoff", "429 handling", "rate limit").

### `when_to_use` (string)
Prescriptive guidance on which adapters and integration types should attach this hook. Helps the LLM reason about hook selection.

### `trigger_condition` (string)
Precisely when in the integration lifecycle this hook fires.

---

## 5. JSON Cleaning: What Gets Stripped

Before building the embedding text, `vector_service.py` calls `_extract_adapter_embedding_text()` which deliberately **excludes** these fields:

| Stripped Field | Reason |
|----------------|--------|
| `base_url` | Technical endpoint — not useful for intent matching |
| `versions[].endpoint` | URL paths — pollute the embedding with noise |
| `versions[].release_notes` | Implementation detail, not semantic intent |
| `versions[].sunset_date` | Operational, not semantic |
| `versions[].maturity_score` | Internal scoring metric |
| `error_codes` | HTTP error codes — noise for intent matching |
| `timeout_ms` | Config parameter, not semantic |
| `retry_policy` | Config parameter |
| `sandbox_base_url` | Technical URL |
| `fallback_adapter` | Operational fallback logic |
| `credential_env_vars` | Environment variable names |
| `response_schema` | Response structure definition |

**Why this matters:** If we embed `endpoint: /v3/commercial/creditReport`, the embedding model might associate the adapter with words like "commercial" or "report" for the wrong reasons. We want the model to associate it with "bureau", "credit score", "borrower eligibility" — the semantic intent.

---

## 6. Semantic Text Extraction

**File:** `backend/services/vector_service.py`
**Functions:** `_extract_adapter_embedding_text()`, `_extract_hook_embedding_text()`

### Adapter Extraction Logic

```python
def _extract_adapter_embedding_text(adapter_json: dict) -> str:
    parts = []
    parts.append(f"Adapter: {adapter_json['adapter_name']}.")
    parts.append(f"Provider: {adapter_json['provider']}.")
    parts.append(f"Category: {adapter_json['category']}.")
    parts.append(adapter_json["description"])  # Full rich description
    parts.append(f"Use cases: {'; '.join(adapter_json['use_cases'])}.")
    parts.append(f"Tags: {', '.join(adapter_json['semantic_tags'])}.")
    parts.append(f"Compliance: {adapter_json['compliance_context']}.")
    parts.append(f"Typical callers: {adapter_json['typical_callers']}.")
    parts.append(f"Authentication: {adapter_json['auth_description']}.")
    # Required fields — name + description only, no validation rules
    # Optional fields — name + description only
    return " ".join(parts)
```

### Hook Extraction Logic

```python
def _extract_hook_embedding_text(hook_json: dict) -> str:
    parts = []
    parts.append(f"Hook: {hook_json['hook_name']}.")
    parts.append(f"Type: {hook_json['hook_type']}.")
    parts.append(hook_json["description"])
    parts.append(f"Use cases: {'; '.join(hook_json['use_cases'])}.")
    parts.append(f"Tags: {', '.join(hook_json['semantic_tags'])}.")
    parts.append(f"When to use: {hook_json['when_to_use']}.")
    parts.append(f"Trigger: {hook_json['trigger_condition']}.")
    return " ".join(parts)
```

### Example: CIBIL Embedding Text

The actual text sent to the embedding model for `cibil.json` looks like:

```
Adapter: TransUnion CIBIL Bureau. Provider: TransUnion CIBIL Ltd. Category: bureau.
TransUnion CIBIL Bureau — Retrieves a borrower's CIBIL credit score and full bureau
report including repayment history, outstanding loan balances, credit inquiries,
defaults, and settlement flags... Use cases: Checking CIBIL score before personal
loan approval; Assessing creditworthiness for high-risk borrower segments...
Tags: credit score, CIBIL, bureau, credit report, creditworthiness, borrower risk,
RBI, repayment history... Compliance: RBI-regulated credit information company...
Authentication: OAuth 2.0 client credentials flow. Client ID and secret required...
Required fields: pan_number (Borrower's 10-character PAN card), full_name (Legal name),
date_of_birth (Date of birth for identity verification)...
```

---

## 7. Vector Embedding Generation

**Model:** `text-embedding-005` (Google Gemini)
**Dimensionality:** 512 (MRL truncation from 768)
**Config:** `VECTOR_EMBEDDING_DIM = 512` in `backend/config.py`

### Why text-embedding-005?

- Specifically designed for semantic retrieval (not just classification)
- MRL (Matryoshka Representation Learning) allows truncating to 512 dims with <1% accuracy loss
- Better than `text-embedding-004` on financial and regulatory domain text
- 33% smaller cache with the 512-dim truncation vs full 768-dim

### Embedding API Call

```python
result = client.models.embed_content(
    model="models/text-embedding-005",
    contents=embedding_text,           # The cleaned semantic text
    config=gtypes.EmbedContentConfig(
        output_dimensionality=512,     # MRL truncation
    ),
)
embedding_vector = result.embeddings[0].values  # 512 float values
```

### Retry Logic

The `_get_embedding()` function includes exponential backoff for:
- `429` (rate limit / resource exhausted)
- `503` (service overloaded)

Up to 4 attempts with `min(2^attempt × 3, 60)` second delays.

---

## 8. Incremental Embedding Cache

**Adapter cache file:** `backend/data/adapter_embeddings.json`
**Hook cache file:** `backend/data/hook_embeddings.json`

### Cache Structure

```json
{
  "_meta": {
    "built_at": "2026-05-09T10:20:00Z",
    "model": "models/text-embedding-005",
    "dim": 512,
    "source": "adapter_json_files"
  },
  "cibil": {
    "file_hash": "3f2a8d1c...",          // MD5 of cibil.json at time of embedding
    "embedding": [0.021, -0.043, ...],  // 512 floats
    "id": "cibil",
    "name": "TransUnion CIBIL Bureau",
    "category": "bureau",
    "versions": ["v3"],
    "path": "cibil.json"
  },
  "experian": { ... },
  ...
}
```

### Incremental Update Logic

```python
for adapter_file in ADAPTERS_CATALOG_DIR.glob("*.json"):
    current_hash = md5(adapter_file.read_bytes())
    cached_entry = cache.get(adapter_id, {})
    
    if cached_entry.get("file_hash") == current_hash:
        # File unchanged — skip re-embedding (saves API quota)
        continue
    
    # File changed — re-embed
    adapter_json = json.loads(adapter_file.read_text())
    embedding_text = _extract_adapter_embedding_text(adapter_json)
    embedding = _get_embedding(embedding_text)
    cache[adapter_id] = { "file_hash": current_hash, "embedding": embedding, ... }
```

### When Does Re-Embedding Trigger?

| Event | Re-embed? |
|-------|-----------|
| Adapter JSON unchanged | ❌ Skip (uses cached embedding) |
| Adapter JSON updated (e.g., new use_case added) | ✅ Re-embeds that file only |
| New adapter JSON added to catalog | ✅ Embeds new file only |
| Adapter JSON deleted | ✅ Old cache entry orphaned (cleaned on next forced rebuild) |
| `force=True` passed to `build_embeddings_cache()` | ✅ Re-embeds all files |

---

## 9. Stage 3: Adapter Matching Pipeline

**File:** `backend/agents/stage3_matching.py`

### Step 1: Build Semantic Search Query

From the Stage 2 service requirement, a targeted NL query is built:

```python
query = (
    "Integration requirement: credit bureau check. "
    "Purpose: assess borrower creditworthiness and repayment history. "
    "Category: bureau. "
    "Compliance: RBI CICRA."
)
```

**Critical design decision:** Input field names (pan_number, aadhaar, mobile_number) are **deliberately excluded** from the search query. These terms appear in many adapters (CIBIL, Karza, DigiLocker all require PAN) and would dilute the intent signal. The query focuses on *purpose* and *domain context*, not data fields.

### Step 2: Embed the Query

```python
query_vec = np.array(_get_embedding(query), dtype=np.float32)  # 512 dims
```

### Step 3: Cosine Similarity vs Adapter Cache

```python
# L2-normalize both vectors
query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
matrix_normed = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-10)

# Vectorized dot product = cosine similarity for all adapters at once
scores = np.dot(matrix_normed, query_norm)  # shape: (n_adapters,)
```

### Step 4: Top-3 Candidates

The top 3 adapters by cosine similarity are returned with their scores:

```json
[
  { "adapter_id": "cibil", "semantic_similarity_score": 0.912, "low_confidence": false },
  { "adapter_id": "experian", "semantic_similarity_score": 0.874, "low_confidence": false },
  { "adapter_id": "karza", "semantic_similarity_score": 0.631, "low_confidence": false }
]
```

If `score < VECTOR_SIMILARITY_THRESHOLD (0.45)`, `low_confidence: true` is flagged for the LLM.

### Step 5: LLM Selection

The top-3 candidates and the original service requirement are sent to Gemini. The LLM selects the single best adapter, explaining its reasoning:

```
Given the service requirement "credit bureau — borrower creditworthiness",
the following adapters were retrieved (similarity scores shown):
1. cibil (0.912) — bureau
2. experian (0.874) — bureau
3. karza (0.631) — kyc

Select the most appropriate adapter and explain why.
```

### Step 6: Load Full Adapter JSON

Once the LLM selects (e.g., "cibil"), the **full `cibil.json`** is loaded from disk:

```python
adapter_json = json.loads(
    (ADAPTERS_CATALOG_DIR / f"{chosen_adapter_id}.json").read_text()
)
```

This complete JSON — with endpoints, required fields, versions, auth config — is passed to Stage 4 (Config Generation). The full context is available at this point; the cleaning only happens on the embedding side.

---

## 10. Stage 3: Hook Matching Pipeline

For each identified integration (after adapter selection), hooks are also matched semantically.

### Hook Search Query

```python
hook_query = (
    "Integration: CIBIL bureau credit check. "
    "Category: bureau. "
    "Adapter: cibil. "
    "Compliance requirements: RBI CICRA, KYC."
)
```

### Matching Process

Same cosine similarity approach as adapters. Top-K hooks (configurable, default varies) are returned. The LLM then selects which hooks to attach to the integration config.

For a bureau integration, expected top hooks would be:
1. `credential_resolve_hook` — resolve CIBIL API key before call
2. `pre_validation_hook` — validate PAN, DOB before sending
3. `field_encryption_hook` — encrypt Aadhaar/PAN in transit
4. `pre_auth_hook` — inject OAuth2 bearer token
5. `audit_emit_hook` — write regulatory audit trail
6. `retry_hook` — retry on CIBIL 429/5xx

---

## 11. Full End-to-End Flow

```
1. User uploads BRD (PDF/DOCX)
       │
       ▼
2. Stage 1: Document text extracted
       │
       ▼
3. Stage 2: LLM extracts service requirements
   → { service_name, purpose, category, provider, version_hint, compliance_requirements }
       │
       ▼
4. Stage 3: For each service requirement:
   a. build_service_query() → NL query string
   b. _get_embedding(query) → 512-dim query vector
   c. cosine_similarity(query_vec, adapter_matrix) → scores
   d. top-3 candidates → LLM selects best
   e. ADAPTERS_CATALOG_DIR/chosen_id.json → full adapter JSON loaded
   f. build_hook_query() → hook NL query
   g. cosine_similarity(hook_query_vec, hook_matrix) → top hooks
   h. LLM selects relevant hooks
       │
       ▼
5. Stage 4: Config Builder generates integration config
   (uses full adapter JSON for endpoints, required_fields, auth_type, versions)
       │
       ▼
6. Stage 5-6: Enrichment & Review
       │
       ▼
7. Stage 7: Simulation (simulation_intercept_hook replaces real calls with mocks)
       │
       ▼
8. Stage 8: Deployment
```

---

## 12. File Map

| File | Role |
|------|------|
| `backend/services/vector_service.py` | Core RAG engine — embedding generation, cache management, cosine search |
| `backend/catalogs/adapters/*.json` | **RAG source documents** — 12 adapter JSONs (semantic fields + operational config) |
| `backend/catalogs/hooks/*.json` | **RAG source documents** — 13 hook JSONs (semantic fields + operational config) |
| `backend/data/adapter_embeddings.json` | Embedding cache (auto-generated, gitignored) |
| `backend/data/hook_embeddings.json` | Hook embedding cache (auto-generated, gitignored) |
| `backend/config.py` | Constants: `GEMINI_EMBEDDING_MODEL`, `VECTOR_EMBEDDING_DIM`, `VECTOR_SIMILARITY_THRESHOLD`, `VECTOR_TOP_K_ADAPTERS` |
| `backend/agents/stage3_matching.py` | Calls `search_adapters()`, `search_hooks()`, `build_service_query()` |

### Key Constants (backend/config.py)

| Constant | Value | Description |
|----------|-------|-------------|
| `GEMINI_EMBEDDING_MODEL` | `"models/text-embedding-005"` | Gemini embedding model |
| `VECTOR_EMBEDDING_DIM` | `512` | MRL truncation dimension |
| `VECTOR_SIMILARITY_THRESHOLD` | `0.45` | Min score before "low confidence" flag |
| `VECTOR_TOP_K_ADAPTERS` | `3` | Top-K adapters returned to LLM |
| `VECTOR_TOP_K_HOOKS` | varies | Top-K hooks returned per integration |
| `ADAPTERS_CATALOG_DIR` | `backend/catalogs/adapters` | Adapter JSON source directory |
| `HOOKS_CATALOG_DIR` | `backend/catalogs/hooks` | Hook JSON source directory |
| `ADAPTER_EMBEDDINGS_CACHE` | `backend/data/adapter_embeddings.json` | Adapter embedding cache path |
| `HOOK_EMBEDDINGS_CACHE` | `backend/data/hook_embeddings.json` | Hook embedding cache path |

---

*This document describes the production RAG architecture. For implementation details, refer to `backend/services/vector_service.py` which is the canonical source of truth.*

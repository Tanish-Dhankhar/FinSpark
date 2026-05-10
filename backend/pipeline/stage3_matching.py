"""
Stage 3 — Retrieval-Augmented Catalog Matching & Config Enrichment
==================================================================
Processes each integration ONE-BY-ONE (serial, not batched):

For each detected service:
  3a: Build search query from purpose/category/provider (NOT input fields)
      → vector search → top-3 adapter candidates
  3b: LLM picks the best adapter from top-3
  3c: Fetch FULL adapter JSON (e.g. cibil.json)
  3d: LLM fills config + field mapping for THIS service using:
      - Stage 2 extraction (all BRD fields for this service)
      - Full adapter JSON (endpoints, auth, fields, versions, etc.)

For each integration (after adapters are matched):
  3e: Build hook search query → vector search → top-5 hook candidates
  3f: LLM picks hooks for THIS integration
  3g: Fetch full hook JSONs → LLM fills hook config for THIS integration
"""
import json
from pathlib import Path
from typing import Dict, List, Optional

from backend.config import (
    ADAPTER_MASTER_INDEX, HOOK_MASTER_INDEX,
    ADAPTERS_CATALOG_DIR, HOOKS_CATALOG_DIR,
    VECTOR_TOP_K_ADAPTERS, VECTOR_TOP_K_HOOKS,
)
from backend.services.llm_service import call_llm_json
from backend.services.audit_service import emit_audit_event
from backend.services.project_service import get_latest_config, save_config
from backend.services import vector_service
from backend.services.vector_service import (
    search_adapters, search_hooks,
    is_available as vector_is_available,
)


# ── Prompt Templates ────────────────────────────────────────────────────────

ADAPTER_PICK_SYSTEM = """You are an enterprise integration adapter selector.
You receive semantically retrieved adapter candidates for ONE service.
Pick the SINGLE best adapter using these priority rules:

1. EXACT MATCH FIRST: If the BRD names a specific provider (e.g. 'CIBIL', 'Razorpay', 'Karza'),
   prefer the candidate whose adapter_id or name exactly matches that provider. Ignore similarity score.
2. CATEGORY ALIGNMENT: The adapter category must match the service category.
3. SEMANTIC SCORE: Among remaining candidates, pick the highest semantic_similarity_score.
4. VERSION: When selecting a version, prefer the latest STABLE, non-deprecated version.
   Never select a beta or deprecated version unless it is the only option.
5. NEVER invent adapter IDs. Only use IDs exactly as listed in the candidates.

If no candidate is a reasonable match (score below 0.3 and no name match), set adapter_id to "unmatched"."""

ADAPTER_PICK_PROMPT = """Service requirement from BRD:
{service_info}

Adapter candidates (ranked by semantic similarity):
{candidates}

Select the single best adapter. Respond ONLY with this JSON (no extra text):
{{
  "adapter_id": "exact adapter_id string from candidates list above",
  "recommended_version": "latest stable non-deprecated version string (e.g. 'v2', 'v3')",
  "match_confidence": "high/medium/low",
  "semantic_similarity_score": 0.0,
  "reason": "one sentence: why this adapter and version"
}}

If no candidate fits, set adapter_id to "unmatched" and explain in reason."""

INTEGRATION_FILL_SYSTEM = """You are an enterprise integration configuration engine.
You receive the FULL adapter catalog JSON for ONE matched adapter and the service requirements from the BRD.
Fill the integration config entry precisely.

Core rules:
- Copy exact values from the adapter JSON: endpoints, auth_type, timeout_ms, retry_policy, sandbox_base_url.
- Prefix ALL credential references with $: e.g. "$KARZA_API_KEY", never bare variable names.
- endpoint_url = adapter base_url + selected version's endpoint path.
- For field_mapping, map EVERY required_field from the adapter JSON:
    * If a BRD input field covers it (same concept, possibly different name) → mapping_type="rename" or "direct"
    * If a BRD field needs type/format conversion → mapping_type="computed"
    * If NO BRD field covers it → mapping_type="missing", user_field="N/A"
      DO NOT use null or "null" string for user_field — use the string "N/A".
- For transformation_rules: generate encrypt rules for all PII fields (PAN, Aadhaar, DOB, phone, account_number).
- DO NOT select a deprecated version. If the version marked for selection is deprecated, use the
  latest stable version from the versions list and explain in _version_reason.
- Include _mapping_reason and _adapter_reason/_version_reason annotations."""

INTEGRATION_FILL_PROMPT = """Fill the integration config for this ONE service.

SERVICE INFO FROM BRD:
{service_info}

CHOSEN ADAPTER (full catalog entry):
{adapter_json}

CHOSEN VERSION: {chosen_version}
MATCH REASON: {match_reason}

Return a SINGLE JSON object with EXACTLY this structure:
{{
  "integration_id": "keep the existing integration_id value",
  "service_name": "keep the existing service_name value",
  "adapter_id": "{adapter_id}",
  "category": "copy category from adapter JSON",
  "is_mandatory": true,
  "status": "adapter_matched",
  "selected_version": "{chosen_version}",
  "endpoint_url": "adapter base_url + selected version endpoint path, e.g. https://api.cibil.com/v3/consumer/score",
  "auth_type": "copy auth_type from adapter JSON exactly",
  "credential_env_vars": ["$EACH_VAR from adapter credential_env_vars, prefixed with $"],
  "timeout_ms": "copy timeout_ms from adapter JSON (integer)",
  "retry_policy": {{"max_retries": 0, "backoff_strategy": "fixed"}},
  "sandbox_url": "copy sandbox_base_url from adapter JSON",
  "fallback_adapter": "copy fallback_adapter from adapter JSON or null",
  "deprecated": false,
  "sunset_date": null,
  "field_mapping": [
    {{
      "user_field": "BRD field name if mapped, or 'N/A' if missing from BRD",
      "api_field": "required_field or optional_field name from adapter JSON",
      "mapping_type": "direct | rename | computed | missing",
      "description": "short description of this mapping",
      "_mapping_reason": "why this specific mapping was chosen"
    }}
  ],
  "transformation_rules": [
    {{
      "source_field": "BRD field name",
      "target_field": "API field name",
      "rule_type": "encrypt | format | type_cast | compute",
      "rule": "description of the transformation",
      "example": "concrete before/after example"
    }}
  ],
  "hooks": [],
  "_adapter_reason": "why this adapter was selected",
  "_version_reason": "why this specific version was chosen (and if auto-upgraded from deprecated, explain)"
}}

FIELD MAPPING RULES (apply in order):
1. For EVERY field in adapter required_fields:
   a. Find the BRD input field with the same or semantically equivalent meaning.
   b. If found: mapping_type="direct" (same name) or "rename" (different name).
   c. If no BRD field covers it: mapping_type="missing", user_field="N/A".
      Add a _mapping_reason explaining which upstream service should provide this field at runtime.
2. For adapter optional_fields: include mappings if BRD mentions those fields.
3. For PII fields (PAN, Aadhaar, phone, DOB, bank account): add an encrypt entry in transformation_rules.

Return ONLY the JSON object (no markdown, no explanation outside the JSON)."""

HOOK_PICK_SYSTEM = """You are a hook selection engine for enterprise integration pipelines.
You receive semantically retrieved hook candidates for ONE integration.
Select the appropriate hooks by applying these rules:

MANDATORY for ALL integrations (include if present in candidates):
  - credential_resolve_hook: required before any auth injection
  - pre_auth_hook: required for any authenticated call
  - retry_hook: required for any external HTTP adapter
  - on_failure_alert_hook: required for all mandatory integrations

ADDITIONAL rules by category:
  - KYC / bureau / banking: also include field_encryption_hook (PII data must be encrypted)
  - fraud / bureau: also include post_schema_validation_hook if present
  - Any adapter with compliance_requirements: also include audit_emit_hook if present

Always use hook_id values EXACTLY as they appear in the candidates list.
Do NOT invent hook IDs. If a mandatory hook is not in the candidates list, still list it —
the caller will handle missing candidates gracefully."""

HOOK_PICK_PROMPT = """Integration context:
{integration_info}

Available hook candidates (ranked by semantic similarity):
{candidates}

Select all appropriate hooks for this integration. Respond ONLY with this JSON:
{{
  "assigned_hooks": ["hook_id_1", "hook_id_2"]
}}

Apply the mandatory hook rules from your system instructions.
Only include hook_ids that appear in the candidates list above."""

HOOK_FILL_SYSTEM = """You are a hook configuration engine.
For each assigned hook, return a complete hook object using fields from the hook catalog JSON.
Set lifecycle_state to 'registered' for all hooks.
Prefix ALL credential_env_vars with $ (e.g. "$CLIENT_ENCRYPTION_KEY")."""

HOOK_FILL_PROMPT = """Integration:
{integration_info}

Assigned hook IDs: {hook_ids}

Full hook catalog data:
{hook_details}

Return ONLY a JSON array. Each element is one hook object populated from the catalog data above.
Use this exact structure for each hook (copy all values from the catalog):
[
  {{
    "hook_id": "from catalog hook_id field",
    "hook_name": "from catalog hook_name field",
    "hook_type": "from catalog hook_type field",
    "description": "from catalog description field",
    "use_cases": ["from catalog use_cases array"],
    "semantic_tags": ["from catalog semantic_tags array"],
    "when_to_use": "from catalog when_to_use field",
    "trigger_condition": "from catalog trigger_condition field",
    "applicable_adapters": ["from catalog applicable_adapters array"],
    "lifecycle_state": "registered",
    "execution_order": 0,
    "is_blocking": true,
    "payload_template": {{}},
    "input_parameters": [],
    "output": {{}},
    "timeout_ms": 1000,
    "retry_policy": {{}},
    "credential_env_vars": ["$PREFIXED from catalog credential_env_vars"],
    "audit_on_trigger": true
  }}
]

Return ONLY the JSON array. No markdown fences, no explanation."""


# ── Helpers ──────────────────────────────────────────────────────────────────

def _build_adapter_search_query(service: dict) -> str:
    """
    Build a natural-language search query for vector search.
    Only uses purpose/category/provider signals — NOT input fields or
    field names, which are irrelevant for finding the right adapter.
    """
    parts = []

    # Core: what the service does and why
    if service.get("purpose"):
        parts.append(f"Purpose: {service['purpose']}.")

    # Provider name is the strongest signal (e.g. "CIBIL", "Razorpay")
    if service.get("provider"):
        parts.append(f"Provider: {service['provider']}.")

    # Exact API name from BRD (strongest signal if available)
    if service.get("exact_api_name_from_doc"):
        parts.append(f"API name from document: {service['exact_api_name_from_doc']}.")

    # Service name
    if service.get("service_name"):
        parts.append(f"Service: {service['service_name']}.")

    # Category for pre-filtering
    if service.get("category"):
        parts.append(f"Category: {service['category']}.")

    # Compliance/regulatory context helps (e.g. "RBI KYC" → bureau/kyc adapters)
    if service.get("compliance_requirements"):
        parts.append(f"Compliance: {', '.join(service['compliance_requirements'][:3])}.")

    # Auth type hint
    if service.get("auth_type_hint"):
        parts.append(f"Auth: {service['auth_type_hint']}.")

    return " ".join(parts) if parts else service.get("service_name", "unknown service")


def _build_hook_search_query(integration: dict) -> str:
    """Build a search query for hook matching from an integration dict."""
    parts = [
        f"Integration: {integration.get('service_name', '')}.",
        f"Category: {integration.get('category', '')}.",
        f"Adapter: {integration.get('adapter_id', '')}.",
    ]
    if integration.get("is_mandatory"):
        parts.append("This is a mandatory integration.")
    # Compliance context strengthens hook matching (e.g. RBI → audit_emit, field_encryption)
    compliance = integration.get("compliance_requirements") or []
    if compliance:
        parts.append(f"Compliance requirements: {', '.join(compliance)}.")
    # Auth type informs pre_auth_hook relevance
    auth = integration.get("auth_type")
    if auth:
        parts.append(f"Authentication: {auth}.")
    return " ".join(parts)


def _slim_service_info(service: dict) -> dict:
    """Return a compact service info dict for LLM prompts to stay within token limits."""
    return {
        "service_name": service.get("service_name"),
        "provider": service.get("provider"),
        "exact_api_name": service.get("exact_api_name_from_doc"),
        "category": service.get("category"),
        "purpose": service.get("purpose"),
        "version_hint": service.get("version_hint"),
        "version_is_explicit": service.get("version_is_explicit", False),
        "auth_type_hint": service.get("auth_type_hint"),
        "input_fields_mentioned": service.get("input_fields_mentioned", []),
        "output_fields_mentioned": service.get("output_fields_mentioned", []),
        "compliance_requirements": service.get("compliance_requirements", []),
        "hook_signals": service.get("hook_signals", []),
        "confidence": service.get("confidence"),
        "additional_context": service.get("additional_context"),
    }


def _slim_integration_info(integration: dict) -> dict:
    """Return a compact integration info dict for hook prompts."""
    return {
        "integration_id": integration.get("integration_id"),
        "service_name": integration.get("service_name"),
        "adapter_id": integration.get("adapter_id"),
        "category": integration.get("category"),
        "is_mandatory": integration.get("is_mandatory"),
        "status": integration.get("status"),
    }


def _load_hook_index(hook_index_cache: Optional[dict] = None) -> dict:
    """Load hook master index (cached across calls within one Stage 3 run)."""
    if hook_index_cache is not None:
        return hook_index_cache
    return json.loads(HOOK_MASTER_INDEX.read_text(encoding="utf-8"))


# ── Main Entry Point ─────────────────────────────────────────────────────────

def run_stage3(client_id: str, requirements: dict) -> dict:
    """
    Execute Stage 3 — Catalog Matching & Config Enrichment.

    Each service is processed independently (not batched) so each gets
    the full adapter JSON and precise field mapping.

    Args:
        client_id: The client folder ID
        requirements: Output from Stage 2

    Returns:
        The enriched config dict
    """
    print(f"\n{'='*60}")
    print(f"  Stage 3 — Catalog Matching & Config Enrichment")
    print(f"{'='*60}")

    services_detected = requirements.get("services_detected", [])
    using_vector = vector_is_available()

    # Build adapter path lookup by scanning the directory directly.
    # This ensures newly added adapter JSONs are found without updating master_index,
    # and that IDs always match file stems (same as vector_service.py).
    adapter_id_to_path: dict = {
        p.stem: p.name
        for p in ADAPTERS_CATALOG_DIR.glob("*.json")
        if p.name != "master_index.json" and p.name != "embeddings_cache.json"
    }

    # Also load master_index for fallback candidate list (when vector search fails)
    adapter_index = json.loads(ADAPTER_MASTER_INDEX.read_text(encoding="utf-8"))

    low_confidence_services: list = []

    # ── Per-service loop: 3a → 3b → 3c → 3d ─────────────────────────────
    for service in services_detected:
        svc_name = service.get("service_name", "unknown")
        print(f"\n  {'─'*55}")
        print(f"  🔧 Processing service: {svc_name}")

        # ── 3a: Build search query & run vector search ────────────────
        print(f"     🔍 3a: Vector search for best adapter...")
        search_query = _build_adapter_search_query(service)
        print(f"        Query: \"{search_query[:120]}...\"" if len(search_query) > 120
              else f"        Query: \"{search_query}\"")

        if using_vector:
            candidates = search_adapters(
                query=search_query,
                category=service.get("category"),
                top_k=VECTOR_TOP_K_ADAPTERS,
            )
            if not candidates:
                # Fallback: provide all adapters in category or full index
                print(f"        ⚠️  No vector hits — falling back to full adapter index")
                candidates = [
                    {
                        "adapter_id": a["id"],
                        "name": a["name"],
                        "category": a.get("category", ""),
                        "versions": a.get("versions", []),
                        "maturity_score": a.get("maturity_score", 0),
                        "path": a.get("path", ""),
                        "semantic_similarity_score": 0.0,
                        "low_confidence": True,
                    }
                    for a in adapter_index.get("adapters", [])[:VECTOR_TOP_K_ADAPTERS]
                ]
        else:
            # Fallback: take first N adapters from index matching the category
            print(f"        📦 Fallback: vector service unavailable")
            all_adapters = adapter_index.get("adapters", [])
            cat = (service.get("category") or "").lower()
            filtered = [a for a in all_adapters if a.get("category", "").lower() == cat]
            pool = filtered[:VECTOR_TOP_K_ADAPTERS] if filtered else all_adapters[:VECTOR_TOP_K_ADAPTERS]
            candidates = [
                {
                    "adapter_id": a["id"],
                    "name": a["name"],
                    "category": a.get("category", ""),
                    "versions": a.get("versions", []),
                    "maturity_score": a.get("maturity_score", 0),
                    "path": a.get("path", ""),
                    "semantic_similarity_score": 0.0,
                    "low_confidence": True,
                }
                for a in pool
            ]

        # Log candidates
        for c in candidates:
            flag = " ⚠️LOW" if c.get("low_confidence") else ""
            print(f"        → {c['adapter_id']} (score={c.get('semantic_similarity_score', 0):.3f}){flag}")

        if candidates and candidates[0].get("low_confidence"):
            low_confidence_services.append(svc_name)

        # ── 3b: LLM picks the best adapter from top-3 ────────────────
        print(f"     🤖 3b: LLM selecting best adapter...")
        pick_prompt = ADAPTER_PICK_PROMPT.format(
            service_info=json.dumps(_slim_service_info(service), indent=2),
            candidates=json.dumps(candidates, indent=2),
        )
        pick_result = call_llm_json(
            prompt=pick_prompt,
            system_instruction=ADAPTER_PICK_SYSTEM,
        )
        chosen_adapter_id = pick_result.get("adapter_id", "unmatched")
        chosen_version = pick_result.get("recommended_version", "")
        match_reason = pick_result.get("reason", "")
        print(f"        ✅ Chosen: {chosen_adapter_id} v{chosen_version}")
        print(f"           Reason: {match_reason[:100]}")

        # ── 3c: Fetch FULL adapter JSON ───────────────────────────────
        adapter_json = None
        if chosen_adapter_id != "unmatched" and chosen_adapter_id in adapter_id_to_path:
            adapter_file = ADAPTERS_CATALOG_DIR / adapter_id_to_path[chosen_adapter_id]
            if adapter_file.exists():
                adapter_json = json.loads(adapter_file.read_text(encoding="utf-8"))
                print(f"     📄 3c: Loaded full adapter: {adapter_file.name}")
            else:
                print(f"     ⚠️  3c: Adapter file not found: {adapter_file}")
        else:
            print(f"     ⚠️  3c: Adapter '{chosen_adapter_id}' not in catalog — config will be partial")

        # ── 3d: LLM fills config for this service ────────────────────
        print(f"     📝 3d: Filling config + field mapping for {svc_name}...")
        current_config = get_latest_config(client_id)

        if adapter_json is not None:
            fill_prompt = INTEGRATION_FILL_PROMPT.format(
                service_info=json.dumps(_slim_service_info(service), indent=2),
                adapter_json=json.dumps(adapter_json, indent=2),
                chosen_version=chosen_version,
                match_reason=match_reason,
                adapter_id=chosen_adapter_id,
            )
            filled_integration = call_llm_json(
                prompt=fill_prompt,
                system_instruction=INTEGRATION_FILL_SYSTEM,
            )

            # If LLM returned a list, take first item
            if isinstance(filled_integration, list):
                filled_integration = filled_integration[0] if filled_integration else {}
        else:
            # No adapter JSON — build a minimal integration entry
            filled_integration = {
                "adapter_id": chosen_adapter_id,
                "status": "adapter_matched" if chosen_adapter_id != "unmatched" else "unmatched",
                "selected_version": chosen_version,
                "_adapter_reason": match_reason,
                "_version_reason": "No adapter file found in catalog",
            }

        # Deterministic enforcement: deprecated + sunset_date from adapter JSON
        if adapter_json and chosen_version:
            for ver_entry in adapter_json.get("versions", []):
                if ver_entry.get("version") == chosen_version:
                    filled_integration["deprecated"] = ver_entry.get("deprecated", False)
                    filled_integration["sunset_date"] = ver_entry.get("sunset_date", None)
                    break
            else:
                filled_integration.setdefault("deprecated", False)
                filled_integration.setdefault("sunset_date", None)

        # Merge into the integration that matches this service
        for integ in current_config.get("integrations", []):
            if integ.get("service_name") == svc_name or integ.get("integration_id") == service.get("integration_id"):
                integ.update(filled_integration)
                # Always enforce adapter_id from step 3b (LLM can't override)
                integ["adapter_id"] = chosen_adapter_id
                integ["selected_version"] = chosen_version
                break
        else:
            # Service not found in current config (shouldn't happen) — append
            filled_integration.setdefault("integration_id", svc_name.lower().replace(" ", "_"))
            filled_integration.setdefault("service_name", svc_name)
            filled_integration.setdefault("category", service.get("category", ""))
            filled_integration.setdefault("is_mandatory", service.get("is_mandatory", True))
            filled_integration.setdefault("hooks", [])
            filled_integration.setdefault("field_mapping", [])
            filled_integration.setdefault("transformation_rules", [])
            current_config.setdefault("integrations", []).append(filled_integration)

        save_config(client_id, current_config)
        print(f"        ✅ Config updated for {svc_name}")

    # Store low-confidence flags for Stage 4 reasoning report
    requirements["_low_confidence_matches"] = low_confidence_services

    emit_audit_event(
        client_id=client_id,
        stage="stage_3_matching",
        action=f"Adapter matching complete: {len(services_detected)} services processed"
               f" (vector={'yes' if using_vector else 'fallback'},"
               f" low_confidence={len(low_confidence_services)})",
        agent="gemini_flash_lite",
        input_data=json.dumps({"services": [s.get("service_name") for s in services_detected]}),
        output_data=json.dumps({"low_confidence": low_confidence_services}),
    )

    # ── Per-integration hook loop: 3e → 3f → 3g ──────────────────────────
    print(f"\n  {'='*55}")
    print(f"  🪝 Hook Matching — per integration")

    hook_index = json.loads(HOOK_MASTER_INDEX.read_text(encoding="utf-8"))

    # Build hook path lookup by scanning the directory directly.
    # This avoids the master_index ID↔file-stem mismatch (e.g. "datadog_logging" → logging_hook.json).
    # File stem is the canonical hook ID (same as vector_service.py).
    hook_id_to_path: dict = {
        p.stem: p.name
        for p in HOOKS_CATALOG_DIR.glob("*.json")
        if p.name != "master_index.json" and p.name != "embeddings_cache.json"
    }
    all_hook_ids_assigned: set = set()

    current_config = get_latest_config(client_id)

    for integration in current_config.get("integrations", []):
        integ_id = integration.get("integration_id") or integration.get("service_name", "unknown")
        print(f"\n  {'─'*55}")
        print(f"  🪝 Hooks for: {integ_id}")

        # ── 3e: Build hook search query & vector search ───────────────
        print(f"     🔍 3e: Searching relevant hooks...")
        hook_query = _build_hook_search_query(integration)

        if vector_is_available():
            hook_candidates = search_hooks(query=hook_query, top_k=VECTOR_TOP_K_HOOKS)
        else:
            # Fallback: use all hooks from catalog directory (not master_index)
            # so IDs (file stems) are consistent with what vector search returns.
            hook_candidates = [
                {
                    "hook_id": p.stem,
                    "name": p.stem.replace("_", " ").title(),
                    "type": "",
                    "path": p.name,
                    "semantic_similarity_score": 0.0,
                }
                for p in sorted(HOOKS_CATALOG_DIR.glob("*.json"))
                if p.name not in ("master_index.json", "embeddings_cache.json")
            ][:VECTOR_TOP_K_HOOKS]

        hook_ids_preview = [c.get("hook_id", c.get("id", "?")) for c in hook_candidates]
        print(f"        Candidates: {', '.join(hook_ids_preview)}")

        # ── 3f: LLM picks hooks for this integration ──────────────────
        print(f"     🤖 3f: LLM selecting hooks...")
        hook_pick_prompt = HOOK_PICK_PROMPT.format(
            integration_info=json.dumps(_slim_integration_info(integration), indent=2),
            candidates=json.dumps(hook_candidates, indent=2),
        )
        hook_pick_result = call_llm_json(
            prompt=hook_pick_prompt,
            system_instruction=HOOK_PICK_SYSTEM,
        )
        assigned_hook_ids = hook_pick_result.get("assigned_hooks", [])
        print(f"        ✅ Assigned: {', '.join(assigned_hook_ids)}")
        all_hook_ids_assigned.update(assigned_hook_ids)

        # ── 3g: Fetch full hook JSONs & fill hook config ──────────────
        print(f"     📄 3g: Loading hook files and filling config...")
        hook_details = {}
        for hid in assigned_hook_ids:
            if hid in hook_id_to_path:
                hook_file = HOOKS_CATALOG_DIR / hook_id_to_path[hid]
                if hook_file.exists():
                    hook_details[hid] = json.loads(hook_file.read_text(encoding="utf-8"))
                else:
                    print(f"        ⚠️  Hook file not found: {hook_file}")
            else:
                print(f"        ⚠️  Hook '{hid}' not in catalog index")

        if hook_details:
            hook_fill_prompt = HOOK_FILL_PROMPT.format(
                integration_info=json.dumps(_slim_integration_info(integration), indent=2),
                hook_ids=json.dumps(assigned_hook_ids),
                hook_details=json.dumps(hook_details, indent=2),
            )
            filled_hooks = call_llm_json(
                prompt=hook_fill_prompt,
                system_instruction=HOOK_FILL_SYSTEM,
            )
            if isinstance(filled_hooks, list):
                integration["hooks"] = filled_hooks
            elif isinstance(filled_hooks, dict) and "hooks" in filled_hooks:
                integration["hooks"] = filled_hooks["hooks"]
            else:
                # Minimal fallback: build hook stubs from catalog data
                integration["hooks"] = [
                    {
                        "hook_id": hid,
                        "hook_name": hook_details[hid].get("hook_name", hid),
                        "hook_type": hook_details[hid].get("hook_type", ""),
                        "lifecycle_state": "registered",
                        "execution_order": hook_details[hid].get("execution_order", 99),
                        "is_blocking": hook_details[hid].get("is_blocking", False),
                        "trigger_condition": hook_details[hid].get("trigger_condition", ""),
                        "timeout_ms": hook_details[hid].get("timeout_ms", 5000),
                    }
                    for hid in assigned_hook_ids if hid in hook_details
                ]
        else:
            integration["hooks"] = []

        # Re-read config and update just this integration's hooks
        current_config = get_latest_config(client_id)
        for cfg_integ in current_config.get("integrations", []):
            cfg_id = cfg_integ.get("integration_id") or cfg_integ.get("service_name")
            if cfg_id == integ_id:
                cfg_integ["hooks"] = integration["hooks"]
                break
        save_config(client_id, current_config)
        print(f"        ✅ Hooks saved for {integ_id}: {len(integration['hooks'])} hooks")

    emit_audit_event(
        client_id=client_id,
        stage="stage_3_matching",
        action=f"Hook assignment complete: {len(all_hook_ids_assigned)} unique hooks"
               f" across {len(current_config.get('integrations', []))} integrations",
        agent="gemini_flash_lite",
    )

    final_config = get_latest_config(client_id)

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n  {'='*55}")
    print(f"  ✅ Stage 3 complete")
    total_mappings = sum(len(i.get("field_mapping", [])) for i in final_config.get("integrations", []))
    total_rules = sum(len(i.get("transformation_rules", [])) for i in final_config.get("integrations", []))
    total_hooks = sum(len(i.get("hooks", [])) for i in final_config.get("integrations", []))
    print(f"     Integrations: {len(final_config.get('integrations', []))}")
    print(f"     Field mappings: {total_mappings}")
    print(f"     Transformation rules: {total_rules}")
    print(f"     Hooks: {total_hooks}")

    return final_config

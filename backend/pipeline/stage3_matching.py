"""
Stage 3 — Catalog Matching & Config Enrichment
6 sub-steps with selective file fetching:
  3a: Adapter Matching (1 LLM) → matched adapter IDs
  3b: Selective File Fetch (code) → load only matched adapter JSONs
  3c: Config Fill (1 LLM) → enriched config
  3d: Hook Matching (1 LLM) → matched hook IDs
  3e: Hook Fetch + Fill (1 LLM) → config with hooks
  3f: Field Mapping (1 LLM) → field_mapping[] + transformation_rules[]
"""
import json
from pathlib import Path
from typing import Dict, List

from backend.config import (
    ADAPTER_MASTER_INDEX, HOOK_MASTER_INDEX,
    ADAPTERS_CATALOG_DIR, HOOKS_CATALOG_DIR,
)
from backend.services.llm_service import call_llm_json
from backend.services.audit_service import emit_audit_event
from backend.services.project_service import get_latest_config, save_config


# ── Prompt Templates ────────────────────────────────────────────────────────

ADAPTER_MATCH_SYSTEM = """You are an enterprise integration adapter matcher.
Given integration requirements and a catalog of available adapters, select the best-fit adapter for each detected service.
Only match adapters that are actually relevant. Consider version deprecation status and maturity scores."""

ADAPTER_MATCH_PROMPT = """Here are the extracted integration requirements:
{requirements}

Here is the adapter catalog master index:
{adapter_index}

For each service detected in the requirements, match it to the best adapter from the catalog.
Consider:
- Service name and category alignment
- Version hints from the BRD (if any)
- Prefer non-deprecated versions
- Prefer higher maturity scores
- If no adapter matches a service, omit it

Return JSON:
{{
  "matched_adapters": [
    {{
      "service_name": "name from requirements",
      "adapter_id": "id from catalog",
      "recommended_version": "best version to use",
      "match_confidence": "high/medium/low",
      "reason": "why this adapter was selected"
    }}
  ]
}}
"""

CONFIG_FILL_SYSTEM = """You are an enterprise integration configuration engine.
Your job is to enrich a configuration file with detailed adapter information.
Fill in endpoints, auth types, credential references, timeout, retry policies from the adapter catalog data.
Use $ENV_VAR_NAME format for all credential references — never put actual API keys.
IMPORTANT: For every decision, add reasoning annotations as described below."""

CONFIG_FILL_PROMPT = """Here is the current config:
{current_config}

Here are the matched adapter details (full catalog entries):
{adapter_details}

Here are the requirements:
{requirements}

For each integration in the config's "integrations" array, enrich it with the matched adapter data:
- Set adapter_id to the matched adapter's id
- Set selected_version to the recommended version
- Set endpoint_url to the full URL (base_url + version endpoint)
- Set auth_type from the adapter
- Set credential_env_vars from the adapter (as $VAR_NAME references)
- Set timeout_ms from the adapter
- Set retry_policy from the adapter
- Set sandbox_url from the adapter
- Set fallback_adapter from the adapter
- Set deprecated to the boolean "deprecated" field from the selected version entry in the adapter catalog
- Set sunset_date to the "sunset_date" string (or null) from the selected version entry in the adapter catalog
- Set status to "adapter_matched"

**REASONING ANNOTATIONS (required for every integration):**
- Add "_adapter_reason": a short string explaining WHY this adapter was chosen for this service (e.g. "Best category match for credit bureau; highest maturity score").
- Add "_version_reason": a short string explaining WHY this version was selected. If a version mentioned in the BRD document is deprecated, explain that you selected the newer non-deprecated version instead (e.g. "BRD requested v1 but it is deprecated with sunset 2025-06-01; auto-upgraded to v2 which is stable").
- If an API or service from the requirements has NO matching adapter in the catalog, still include the integration entry with adapter_id set to "unmatched" and add "_adapter_reason": "No matching adapter found in catalog for this service".

If an integration doesn't have a matched adapter, leave it unchanged.

Return the COMPLETE updated config JSON with all fields preserved."""

HOOK_MATCH_SYSTEM = """You are a hook selection engine for enterprise integrations.
Select the most appropriate hooks for each integration based on the hook catalog and integration context."""

HOOK_MATCH_PROMPT = """Here is the hook catalog master index:
{hook_index}

Here are the integrations currently in the config:
{integrations}

For each integration, select appropriate hooks from the catalog. Consider:
- Every integration needs: credential_resolve_hook, pre_auth_hook, retry_hook, on_failure_alert_hook
- Bureau/KYC integrations additionally need: field_encryption_hook, post_schema_validation_hook
- All integrations benefit from: post_transform_hook, audit_emit_hook
- Simulation mode needs: simulation_intercept_hook

Return JSON:
{{
  "hook_assignments": [
    {{
      "integration_id": "the integration id",
      "adapter_id": "the adapter id", 
      "assigned_hooks": ["hook_id_1", "hook_id_2", ...]
    }}
  ]
}}
"""

HOOK_FILL_SYSTEM = """You are a hook configuration engine.
Populate hook entries in the integration config with details from the hook catalog files.
Each hook should have lifecycle_state set to 'registered'."""

HOOK_FILL_PROMPT = """Here is the current config:
{current_config}

Here are the hook assignments:
{hook_assignments}

Here are the full hook catalog entries for assigned hooks:
{hook_details}

For each integration in the config, populate its "hooks" array with the assigned hooks. Each hook entry should include:
{{
  "hook_id": "from catalog",
  "hook_name": "from catalog",
  "hook_type": "from catalog",
  "lifecycle_state": "registered",
  "execution_order": from catalog,
  "is_blocking": from catalog,
  "trigger_condition": "from catalog",
  "timeout_ms": from catalog
}}

Return the COMPLETE updated config JSON."""

FIELD_MAPPING_SYSTEM = """You are a field mapping and transformation rule engine.
Map user-side fields from BRD documents to API-side fields from adapter schemas.
Generate transformation rules for type conversions, encryptions, and computed fields.
IMPORTANT: For every mapping decision, add a reasoning annotation. For missing required fields, mark them clearly."""

FIELD_MAPPING_PROMPT = """Here is the current config:
{current_config}

Here are the requirements with detected fields:
{requirements}

Here are the adapter schemas for matched integrations:
{adapter_schemas}

For each integration in the config, generate:

1. field_mapping[] — maps user fields to API fields:
   {{
     "user_field": "field name from BRD/user",
     "api_field": "field name expected by the API",
     "mapping_type": "direct/rename/computed/missing",
     "description": "why this mapping exists",
     "_mapping_reason": "Explain why this mapping was chosen. For 'missing' type, explain why the field could not be mapped."
   }}

   **IMPORTANT for missing fields:**
   - If a REQUIRED field from the adapter schema cannot be mapped to any user field from the BRD, set mapping_type to "missing" and set user_field to "" (empty).
   - In the _mapping_reason, explain: "Required API field '<field_name>' has no corresponding data in the BRD document. This must be provided at runtime."
   - This ensures the reviewer knows which required fields are NOT covered by the BRD.

2. transformation_rules[] — data transformations needed:
   {{
     "source_field": "input field",
     "target_field": "output field",  
     "rule_type": "type_cast/encrypt/format/compute",
     "rule": "description of the transformation",
     "example": "e.g. encrypt(pan_number) → tax_identifier_encrypted"
   }}

Important: 
- Map ALL required fields from the adapter schema — if a required field can't be mapped, include it with mapping_type "missing"
- Generate transformation rules where types don't match directly
- PII fields (PAN, Aadhaar, etc.) should have encryption transformation rules

Return the COMPLETE updated config JSON with field_mapping and transformation_rules filled for each integration."""


def run_stage3(client_id: str, requirements: dict) -> dict:
    """
    Execute Stage 3 — Catalog Matching & Config Enrichment.
    
    6 sub-steps as specified.
    
    Args:
        client_id: The client folder ID
        requirements: Output from Stage 2
        
    Returns:
        The enriched config dict
    """
    print(f"\n{'='*60}")
    print(f"  Stage 3 — Catalog Matching & Config Enrichment")
    print(f"{'='*60}")

    adapter_index = json.loads(ADAPTER_MASTER_INDEX.read_text(encoding="utf-8"))
    hook_index = json.loads(HOOK_MASTER_INDEX.read_text(encoding="utf-8"))

    # ── 3a: Adapter Matching ──────────────────────────────────────────────
    print(f"\n  🔍 Step 3a: Matching adapters...")

    match_prompt = ADAPTER_MATCH_PROMPT.format(
        requirements=json.dumps(requirements, indent=2),
        adapter_index=json.dumps(adapter_index, indent=2),
    )

    match_result = call_llm_json(
        prompt=match_prompt,
        system_instruction=ADAPTER_MATCH_SYSTEM,
    )

    matched = match_result.get("matched_adapters", [])
    print(f"     ✅ Matched {len(matched)} adapters:")
    for m in matched:
        print(f"        • {m['service_name']} → {m['adapter_id']} ({m['recommended_version']})")

    emit_audit_event(
        client_id=client_id,
        stage="stage_3_matching",
        action=f"Adapter matching: {len(matched)} adapters matched",
        agent="gemini_flash_lite",
        input_data=json.dumps(requirements)[:200],
        output_data=json.dumps(match_result)[:200],
    )

    # ── 3b: Selective File Fetch ──────────────────────────────────────────
    print(f"\n  📂 Step 3b: Fetching matched adapter files...")

    adapter_details = {}
    adapter_id_to_path = {a["id"]: a["path"] for a in adapter_index.get("adapters", [])}

    for m in matched:
        aid = m["adapter_id"]
        if aid in adapter_id_to_path:
            adapter_file = ADAPTERS_CATALOG_DIR / adapter_id_to_path[aid]
            if adapter_file.exists():
                adapter_details[aid] = json.loads(adapter_file.read_text(encoding="utf-8"))
                print(f"     📄 Loaded {adapter_file.name}")
            else:
                print(f"     ⚠️  Adapter file not found: {adapter_file}")
        else:
            print(f"     ⚠️  Adapter ID not in index: {aid}")

    # ── 3c: Config Fill ───────────────────────────────────────────────────
    print(f"\n  📝 Step 3c: Enriching config with adapter details...")

    current_config = get_latest_config(client_id)
    fill_prompt = CONFIG_FILL_PROMPT.format(
        current_config=json.dumps(current_config, indent=2),
        adapter_details=json.dumps(adapter_details, indent=2),
        requirements=json.dumps(requirements, indent=2),
    )

    enriched_config = call_llm_json(
        prompt=fill_prompt,
        system_instruction=CONFIG_FILL_SYSTEM,
    )

    # Validate and fallback
    if isinstance(enriched_config, list):
        generated_integrations = enriched_config
    elif isinstance(enriched_config, dict):
        generated_integrations = enriched_config.get("integrations", [])
    else:
        generated_integrations = []

    for old_integ in current_config.get("integrations", []):
        old_id = old_integ.get("integration_id") or old_integ.get("service_name")
        for new_integ in generated_integrations:
            new_id = new_integ.get("integration_id") or new_integ.get("service_name")
            if old_id and new_id and old_id == new_id:
                old_integ.update(new_integ)
                break
        
        # Enforce exact adapter_id from step 3a matching
        for m in matched:
            if m.get("service_name") == old_integ.get("service_name"):
                old_integ["adapter_id"] = m.get("adapter_id")
                if not old_integ.get("selected_version"):
                    old_integ["selected_version"] = m.get("recommended_version")

    enriched_config = current_config

    # ── Deterministic enforcement: deprecated + sunset_date ───────────
    # LLM may omit these fields; force-set them from adapter catalog data.
    for integ in enriched_config.get("integrations", []):
        aid = integ.get("adapter_id", "")
        sel_ver = integ.get("selected_version", "")
        if aid in adapter_details:
            for ver_entry in adapter_details[aid].get("versions", []):
                if ver_entry.get("version") == sel_ver:
                    integ["deprecated"] = ver_entry.get("deprecated", False)
                    integ["sunset_date"] = ver_entry.get("sunset_date", None)
                    break
            else:
                # Version not found — default to not deprecated
                integ.setdefault("deprecated", False)
                integ.setdefault("sunset_date", None)
        else:
            integ.setdefault("deprecated", False)
            integ.setdefault("sunset_date", None)

    save_config(client_id, enriched_config)
    print(f"     ✅ Config enriched with adapter details (incl. deprecated + sunset_date)")

    emit_audit_event(
        client_id=client_id,
        stage="stage_3_matching",
        action="Config enriched with adapter endpoints, auth, and retry policies",
        agent="gemini_flash_lite",
    )

    # ── 3d: Hook Matching ─────────────────────────────────────────────────
    print(f"\n  🪝 Step 3d: Matching hooks for integrations...")

    current_config = get_latest_config(client_id)
    hook_match_prompt = HOOK_MATCH_PROMPT.format(
        hook_index=json.dumps(hook_index, indent=2),
        integrations=json.dumps(current_config.get("integrations", []), indent=2),
    )

    hook_match_result = call_llm_json(
        prompt=hook_match_prompt,
        system_instruction=HOOK_MATCH_SYSTEM,
    )

    hook_assignments = hook_match_result.get("hook_assignments", [])
    print(f"     ✅ Hook assignments for {len(hook_assignments)} integrations")

    # ── 3e: Hook Fetch + Fill ─────────────────────────────────────────────
    print(f"\n  🪝 Step 3e: Fetching and filling hook details...")

    # Collect all unique hook IDs
    all_hook_ids = set()
    for ha in hook_assignments:
        for hid in ha.get("assigned_hooks", []):
            all_hook_ids.add(hid)

    hook_id_to_path = {h["id"]: h["path"] for h in hook_index.get("hooks", [])}
    hook_details = {}
    for hid in all_hook_ids:
        if hid in hook_id_to_path:
            hook_file = HOOKS_CATALOG_DIR / hook_id_to_path[hid]
            if hook_file.exists():
                hook_details[hid] = json.loads(hook_file.read_text(encoding="utf-8"))
                print(f"     📄 Loaded {hook_file.name}")

    current_config = get_latest_config(client_id)
    hook_fill_prompt = HOOK_FILL_PROMPT.format(
        current_config=json.dumps(current_config, indent=2),
        hook_assignments=json.dumps(hook_assignments, indent=2),
        hook_details=json.dumps(hook_details, indent=2),
    )

    config_with_hooks = call_llm_json(
        prompt=hook_fill_prompt,
        system_instruction=HOOK_FILL_SYSTEM,
    )

    if isinstance(config_with_hooks, list):
        generated_integrations = config_with_hooks
    elif isinstance(config_with_hooks, dict):
        generated_integrations = config_with_hooks.get("integrations", [])
    else:
        generated_integrations = []

    for old_integ in current_config.get("integrations", []):
        old_id = old_integ.get("integration_id") or old_integ.get("service_name")
        for new_integ in generated_integrations:
            new_id = new_integ.get("integration_id") or new_integ.get("service_name")
            if old_id and new_id and old_id == new_id:
                if "hooks" in new_integ:
                    old_integ["hooks"] = new_integ["hooks"]
                break
    config_with_hooks = current_config

    save_config(client_id, config_with_hooks)
    print(f"     ✅ Hooks populated in config")

    emit_audit_event(
        client_id=client_id,
        stage="stage_3_matching",
        action=f"Hooks assigned: {len(all_hook_ids)} unique hooks across {len(hook_assignments)} integrations",
        agent="gemini_flash_lite",
    )

    # ── 3f: Field Mapping + Transformation Rules ─────────────────────────
    print(f"\n  🗺️  Step 3f: Generating field mappings and transformation rules...")

    current_config = get_latest_config(client_id)
    
    # Build adapter schemas for matched integrations
    adapter_schemas = {}
    for integration in current_config.get("integrations", []):
        aid = integration.get("adapter_id", "")
        if aid in adapter_details:
            adapter_schemas[aid] = {
                "required_fields": adapter_details[aid].get("required_fields", []),
                "optional_fields": adapter_details[aid].get("optional_fields", []),
                "response_schema": adapter_details[aid].get("response_schema", {}),
            }

    mapping_prompt = FIELD_MAPPING_PROMPT.format(
        current_config=json.dumps(current_config, indent=2),
        requirements=json.dumps(requirements, indent=2),
        adapter_schemas=json.dumps(adapter_schemas, indent=2),
    )

    config_with_mappings = call_llm_json(
        prompt=mapping_prompt,
        system_instruction=FIELD_MAPPING_SYSTEM,
    )

    if isinstance(config_with_mappings, list):
        generated_integrations = config_with_mappings
    elif isinstance(config_with_mappings, dict):
        generated_integrations = config_with_mappings.get("integrations", [])
    else:
        generated_integrations = []

    for old_integ in current_config.get("integrations", []):
        old_id = old_integ.get("integration_id") or old_integ.get("service_name")
        for new_integ in generated_integrations:
            new_id = new_integ.get("integration_id") or new_integ.get("service_name")
            if old_id and new_id and old_id == new_id:
                if "field_mapping" in new_integ:
                    old_integ["field_mapping"] = new_integ["field_mapping"]
                if "transformation_rules" in new_integ:
                    old_integ["transformation_rules"] = new_integ["transformation_rules"]
                break
    config_with_mappings = current_config

    save_config(client_id, config_with_mappings)

    # Count total mappings
    total_mappings = sum(
        len(i.get("field_mapping", []))
        for i in config_with_mappings.get("integrations", [])
    )
    total_rules = sum(
        len(i.get("transformation_rules", []))
        for i in config_with_mappings.get("integrations", [])
    )
    print(f"     ✅ Generated {total_mappings} field mappings and {total_rules} transformation rules")

    emit_audit_event(
        client_id=client_id,
        stage="stage_3_matching",
        action=f"Field mapping complete: {total_mappings} mappings, {total_rules} transformation rules",
        agent="gemini_flash_lite",
    )

    print(f"\n  ✅ Stage 3 complete")
    return config_with_mappings

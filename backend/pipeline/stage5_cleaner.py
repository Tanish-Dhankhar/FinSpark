"""
Stage 5 — Cleaner Agent
Removes unnecessary fields from the config that shouldn't be in production.
Ensures no actual API keys leaked into the config (replaces with $ENV_VAR references).
Validates JSON structural integrity.
"""
import json
import re

from backend.services.llm_service import call_llm_json
from backend.services.audit_service import emit_audit_event
from backend.services.project_service import get_latest_config, save_config


CLEANER_SYSTEM = """You are a production configuration cleaner for enterprise integration systems.
Your job is to sanitize a configuration file to make it production-ready.

Rules:
1. Remove any actual API keys, secrets, tokens, or passwords — replace them with $ENV_VAR_NAME references
2. Remove any development/debug artifacts that shouldn't be in production
3. Remove any TODO comments or placeholder text like "to be filled" or "TBD"
4. Ensure all credential references use the $ENV_VAR_NAME format (e.g., "$CIBIL_API_KEY")
5. Remove any empty or null arrays/objects that serve no purpose
6. Keep all structural fields even if empty — don't remove the schema structure
7. Ensure consistent formatting
8. DO NOT remove any integrations, hooks, field mappings, or transformation rules
9. DO NOT change endpoint URLs, version selections, or business logic
10. REMOVE all keys ending in "_reason" (e.g., "_adapter_reason", "_version_reason", "_mapping_reason") — these are pipeline annotations that MUST NOT appear in production config
11. Remove any key named "mapping_reason" inside field_mapping arrays
12. For every integration's "integration_id" field: if the value contains any of
    these indicator substrings — "existing", "keep", "placeholder", "value",
    "integration_id", "to be", "tbd" — the field value is a leaked instruction
    artifact. Replace the entire value with null and add the integration's
    service_name to a top-level "cleanup_warnings" list.
13. Scan ALL string field values (not just keys). If any string value appears to
    be a verbatim copy of a prompt instruction (e.g., it reads like an imperative
    sentence, contains "keep the existing", "copy from", "use the value from"),
    clear that field to null and log it in cleanup_warnings.
14. Return the complete cleaned config as valid JSON
15. HOOK FIELDS PROTECTION — within each hook object, NEVER remove or nullify:
    input_parameters, output, payload_template, timeout_ms, retry_policy,
    execution_order, is_blocking, lifecycle_state, credential_env_vars.
    These are runtime-required schema fields. Only remove _reason annotation keys.
16. DO NOT modify the "environment" field on any integration — leave it exactly
    as it was. This field is controlled by the deployment promotion gate, not the cleaner.
17. DO NOT change integration "status" values — statuses like "adapter_matched",
    "unmatched", "simulation_passed" are pipeline state markers, not dev artifacts.
18. DO NOT remove "mapping_type", "user_field", "api_field", or "description" from
    field_mapping entries. These are schema-structural fields, not annotations."""

CLEANER_PROMPT = """Clean this integration configuration for production readiness:

{config}

Specific checks:
- Scan for any string that looks like an API key (long alphanumeric strings, base64 tokens, etc.) and replace with $ENV_VAR references
- Remove empty placeholder strings like "" where they serve no purpose in metadata fields
- Ensure every credential_env_vars entry is in $VARIABLE_NAME format
- Clean up any LLM artifacts (like instructional text that might have leaked from prompts)

Return the complete cleaned configuration as valid JSON."""


def _post_process_clean(config: dict, original_config: dict) -> dict:
    """
    Programmatic post-processing after LLM cleaning.
    Catches things the LLM might have missed and restores protected fields.
    """
    # [FIX C4] Restore environment and status from original — these are gated fields
    # that the cleaner must NEVER modify. Only the deployment promotion gate changes them.
    PROTECTED_INTEGRATION_FIELDS = {"environment", "status"}
    orig_integ_map = {
        (i.get("integration_id") or i.get("service_name", "")): i
        for i in original_config.get("integrations", [])
    }
    for integ in config.get("integrations", []):
        key = integ.get("integration_id") or integ.get("service_name", "")
        orig = orig_integ_map.get(key)
        if orig:
            for field in PROTECTED_INTEGRATION_FIELDS:
                if field in orig:
                    integ[field] = orig[field]  # always restore from pre-clean snapshot

    # [FIX H11] Restore hook runtime fields that the LLM may have stripped.
    # These are schema-structural fields required at execution time.
    PROTECTED_HOOK_FIELDS = {
        "input_parameters", "output", "payload_template",
        "timeout_ms", "retry_policy", "execution_order",
        "is_blocking", "lifecycle_state", "credential_env_vars",
    }
    orig_hooks_by_id: dict = {}
    for oi in original_config.get("integrations", []):
        for oh in oi.get("hooks", []):
            hid = oh.get("hook_id") or oh.get("hook_name", "")
            if hid:
                orig_hooks_by_id[hid] = oh

    for integ in config.get("integrations", []):
        for hook in integ.get("hooks", []):
            hid = hook.get("hook_id") or hook.get("hook_name", "")
            orig_hook = orig_hooks_by_id.get(hid)
            if orig_hook:
                for field in PROTECTED_HOOK_FIELDS:
                    if field in orig_hook and field not in hook:
                        hook[field] = orig_hook[field]
                        print(f"     🔧 Restored hook field '{field}' on '{hid}' (cleaner had stripped it)")

    # Ensure pipeline_run status fields are clean
    if "metadata" in config and "pipeline_run" in config["metadata"]:
        pr = config["metadata"]["pipeline_run"]
        if "overall_status" not in pr:
            pr["overall_status"] = "draft"

    # [FIX M12] Restore all structural pipeline_run fields from original
    if "metadata" in original_config and "pipeline_run" in original_config["metadata"]:
        orig_pr = original_config["metadata"]["pipeline_run"]
        if "metadata" not in config:
            config["metadata"] = {}
        if "pipeline_run" not in config["metadata"]:
            config["metadata"]["pipeline_run"] = {}
        pr = config["metadata"]["pipeline_run"]
        for pr_field in ("stages_completed", "current_stage", "started_at", "last_updated"):
            if pr_field in orig_pr and pr_field not in pr:
                pr[pr_field] = orig_pr[pr_field]

    # Fix 9B: Deterministic integration_id placeholder detection
    # Catches leaked prompt instruction text the LLM cleaner may have missed.
    PLACEHOLDER_SIGNALS = {"existing", "keep", "placeholder", "tbd", "to be", "integration_id value"}
    warnings = config.setdefault("cleanup_warnings", [])

    for integ in config.get("integrations", []):
        iid = integ.get("integration_id") or ""
        iid_lower = iid.lower()
        if any(signal in iid_lower for signal in PLACEHOLDER_SIGNALS):
            svc = integ.get("service_name", "unknown")
            print(f"     Cleared placeholder integration_id for '{svc}': '{iid}'")
            warnings.append({
                "field": "integration_id",
                "service": svc,
                "original_value": iid,
                "action": "cleared -- contained prompt instruction text",
            })
            integ["integration_id"] = None

    return config


def strip_reason_fields(obj):
    """
    Recursively remove all keys ending with '_reason' from dicts,
    including inside arrays. This is a hard programmatic guarantee
    that no _reason annotations leak into the production config.
    """
    if isinstance(obj, dict):
        keys_to_remove = [
            k for k in obj
            if k.endswith("_reason") or k == "mapping_reason"
        ]
        for k in keys_to_remove:
            del obj[k]
        for v in obj.values():
            strip_reason_fields(v)
    elif isinstance(obj, list):
        for item in obj:
            strip_reason_fields(item)
    return obj


def run_stage5(client_id: str) -> dict:
    """
    Execute Stage 5 — Config Cleaning.
    
    Args:
        client_id: The client folder ID
        
    Returns:
        The cleaned config dict
    """
    print(f"\n{'='*60}")
    print(f"  Stage 5 — Cleaner Agent")
    print(f"{'='*60}")

    current_config = get_latest_config(client_id)
    if not current_config:
        raise ValueError(f"No config found for client {client_id}")

    print(f"\n  🧹 Cleaning config for production readiness...")

    prompt = CLEANER_PROMPT.format(config=json.dumps(current_config, indent=2))

    cleaned_config = call_llm_json(
        prompt=prompt,
        system_instruction=CLEANER_SYSTEM,
    )

    # Validate structure preservation
    if "integrations" not in cleaned_config:
        print(f"     ⚠️  Cleaner removed integrations — restoring from original")
        cleaned_config["integrations"] = current_config.get("integrations", [])
    if "metadata" not in cleaned_config:
        cleaned_config["metadata"] = current_config.get("metadata", {})

    # ── Restore ANY dropped fields in integrations ──────
    for orig_integ in current_config.get("integrations", []):
        key = orig_integ.get("integration_id") or orig_integ.get("adapter_id") or orig_integ.get("service_name", "")
        if not key:
            continue
        for cleaned_integ in cleaned_config.get("integrations", []):
            ckey = cleaned_integ.get("integration_id") or cleaned_integ.get("adapter_id") or cleaned_integ.get("service_name", "")
            if ckey == key:
                # Restore hooks specifically to print a message
                if "hooks" in orig_integ and "hooks" not in cleaned_integ:
                    print(f"     🧲 Restored hooks for '{key}' (cleaner dropped them)")
                # Restore all missing fields
                for k, v in orig_integ.items():
                    if k.endswith("_reason") or k == "mapping_reason":
                        continue
                    if k not in cleaned_integ:
                        cleaned_integ[k] = v
                break

    # [FIX C5] Missing-field production gate — warn loudly for every missing mapping.
    # Downstream Stage 6 and production gating systems will use this to block deployments.
    missing_field_count = 0
    for integ in cleaned_config.get("integrations", []):
        svc_name = integ.get("service_name", integ.get("integration_id", "unknown"))
        for fm in integ.get("field_mapping", []):
            if fm.get("mapping_type") == "missing":
                missing_field_count += 1
                print(f"     ⚠️  MISSING FIELD [{svc_name}] → '{fm.get('api_field')}' — must be resolved before production")
    if missing_field_count:
        print(f"     🔴 PRODUCTION GATE: {missing_field_count} missing field mapping(s) detected. Set to 'blocked' in pipeline_run.")
        if "metadata" in cleaned_config and "pipeline_run" in cleaned_config["metadata"]:
            pr = cleaned_config["metadata"]["pipeline_run"]
            pr["missing_field_count"] = missing_field_count
            pr["production_gate"] = "blocked" if missing_field_count > 0 else "clear"

    # Post-process (pass original for protected field restoration)
    cleaned_config = _post_process_clean(cleaned_config, current_config)

    # Count what was cleaned
    original_str = json.dumps(current_config)
    cleaned_str = json.dumps(cleaned_config)
    size_diff = len(original_str) - len(cleaned_str)

    save_config(client_id, cleaned_config)

    # ── Hard guarantee: strip all _reason fields programmatically ──────
    strip_reason_fields(cleaned_config)
    save_config(client_id, cleaned_config)

    print(f"     ✅ Config cleaned (size delta: {size_diff:+d} chars)")
    print(f"     Integrations preserved: {len(cleaned_config.get('integrations', []))}")

    emit_audit_event(
        client_id=client_id,
        stage="stage_5_cleaner",
        action=f"Config cleaned for production (size delta: {size_diff:+d} chars)",
        agent="qwen_local",
        input_data=original_str[:200],
        output_data=cleaned_str[:200],
    )

    print(f"\n  ✅ Stage 5 complete")
    return cleaned_config

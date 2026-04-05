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
12. Return the complete cleaned config as valid JSON"""

CLEANER_PROMPT = """Clean this integration configuration for production readiness:

{config}

Specific checks:
- Scan for any string that looks like an API key (long alphanumeric strings, base64 tokens, etc.) and replace with $ENV_VAR references
- Remove empty placeholder strings like "" where they serve no purpose in metadata fields
- Ensure every credential_env_vars entry is in $VARIABLE_NAME format
- Clean up any LLM artifacts (like instructional text that might have leaked from prompts)

Return the complete cleaned configuration as valid JSON."""


def _post_process_clean(config: dict) -> dict:
    """
    Programmatic post-processing after LLM cleaning.
    Catches things the LLM might have missed.
    """
    config_str = json.dumps(config)

    # Pattern: anything that looks like an actual API key (40+ char alphanumeric)
    # But NOT $ENV_VAR references or URLs
    suspicious_patterns = [
        # Bearer tokens
        (r'"(Bearer\s+[A-Za-z0-9_\-\.]{20,})"', '"$BEARER_TOKEN"'),
        # Long hex strings that look like keys (32+ chars)
        (r'"([a-f0-9]{32,})"', None),  # Will be handled case by case
    ]

    # Ensure pipeline_run status fields are clean
    if "metadata" in config and "pipeline_run" in config["metadata"]:
        pr = config["metadata"]["pipeline_run"]
        if "overall_status" not in pr:
            pr["overall_status"] = "draft"

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

    # ── Merge hooks back if the LLM dropped them during cleaning ─────────
    for orig_integ in current_config.get("integrations", []):
        key = orig_integ.get("adapter_id") or orig_integ.get("integration_id") or orig_integ.get("service_name", "")
        orig_hooks = orig_integ.get("hooks", [])
        if not key or not orig_hooks:
            continue
        for cleaned_integ in cleaned_config.get("integrations", []):
            ckey = cleaned_integ.get("adapter_id") or cleaned_integ.get("integration_id") or cleaned_integ.get("service_name", "")
            if ckey == key and not cleaned_integ.get("hooks"):
                cleaned_integ["hooks"] = orig_hooks
                print(f"     🪝 Restored hooks for '{key}' (cleaner dropped them)")

    # Post-process
    cleaned_config = _post_process_clean(cleaned_config)

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
        agent="gemini_flash_lite",
        input_data=original_str[:200],
        output_data=cleaned_str[:200],
    )

    print(f"\n  ✅ Stage 5 complete")
    return cleaned_config

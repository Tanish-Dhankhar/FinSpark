"""
Stage 2 — Requirement Parsing Engine (Simplified)
Single LLM call: full document text + master_index → structured requirements summary.
Then template fill: requirements + config → populated config.
"""
import json
from typing import Dict

from backend.config import ADAPTER_MASTER_INDEX, HOOK_MASTER_INDEX
from backend.services.llm_service import call_llm, call_llm_json
from backend.services.audit_service import emit_audit_event
from backend.services.project_service import get_latest_config, save_config


EXTRACTION_SYSTEM_PROMPT = """You are an enterprise integration requirements analyst. 
Your job is to extract all integration-related signals from business requirement documents.
You are precise, exhaustive, and structured in your output.
You never hallucinate services that aren't mentioned in the document."""

EXTRACTION_PROMPT_TEMPLATE = """Analyze the following enterprise document(s) and extract ALL integration requirements.

Here is the catalog of available adapters for context (these are the ONLY adapters that can be matched):
{adapter_index}

Here is the catalog of available hooks:
{hook_index}

---
DOCUMENT TEXT:
{document_text}
---

Extract and return a JSON object with this exact structure:
{{
  "services_detected": [
    {{
      "service_name": "Name of the service/API",
      "provider": "Provider name",
      "category": "bureau/kyc/payment/banking/gst/fraud/messaging/document",
      "is_mandatory": true,
      "confidence": "high/medium/low",
      "version_hint": "any version mentioned in docs or null",
      "endpoint_hints": ["any endpoint URLs mentioned"],
      "purpose": "brief description of why this service is needed",
      "fields_mentioned": ["list of data field names mentioned in context of this service"],
      "data_types_mentioned": ["list of data types mentioned"],
      "hook_signals": ["any webhook/hook/callback mentions related to this service"]
    }}
  ],
  "general_requirements": {{
    "industry_vertical": "detected industry",
    "region": "detected region/country",
    "security_requirements": ["list of security needs mentioned"],
    "compliance_requirements": ["list of compliance needs mentioned"],
    "data_fields_global": ["all data field names mentioned across the entire document"]
  }}
}}

Be thorough. Extract every service, field, and integration signal. Only include services that are ACTUALLY mentioned or clearly implied in the document.
"""

TEMPLATE_FILL_SYSTEM_PROMPT = """You are an enterprise integration configuration engine.
Your job is to populate a JSON configuration template with information extracted from requirement documents.
Rules:
1. Fill every field you can CONFIDENTLY populate from the provided requirements.
2. Do NOT remove or restructure any fields from the template.
3. Leave unfillable fields exactly as they are in the template.
4. For the integrations array, create one entry per detected service with as much detail as possible.
5. Return ONLY valid JSON — the complete config with filled fields."""

TEMPLATE_FILL_PROMPT = """Here are the extracted integration requirements:
{requirements_summary}

Here is the current configuration template:
{current_config}

Fill the configuration template with information from the requirements. For each detected service, create an integration entry in the "integrations" array with this structure:
{{
  "integration_id": "unique_id",
  "service_name": "service name",
  "adapter_id": "",
  "category": "category",
  "is_mandatory": true/false,
  "status": "detected",
  "selected_version": "",
  "endpoint_url": "",
  "auth_type": "",
  "credential_env_vars": [],
  "field_mapping": [],
  "transformation_rules": [],
  "hooks": [],
  "timeout_ms": null,
  "retry_policy": {{}},
  "sandbox_url": "",
  "fallback_adapter": null
}}

Also fill in the metadata fields: industry_vertical, region, uploaded_documents list.
Return the COMPLETE config JSON with all fields preserved.
"""


def run_stage2(client_id: str, extracted_texts: Dict[str, str]) -> dict:
    """
    Execute Stage 2 — Requirement Parsing.
    
    1. Single LLM call: full document text + catalog indexes → structured requirements
    2. Template fill LLM call: requirements + config → populated config
    
    Args:
        client_id: The client folder ID
        extracted_texts: Dict of filename → extracted text from Stage 1
        
    Returns:
        The requirements summary dict
    """
    print(f"\n{'='*60}")
    print(f"  Stage 2 — Requirement Parsing Engine")
    print(f"{'='*60}")

    # Combine all document texts
    combined_text = ""
    for filename, text in extracted_texts.items():
        combined_text += f"\n\n===== {filename} =====\n\n{text}"

    # Load catalog indexes for context
    adapter_index = json.loads(ADAPTER_MASTER_INDEX.read_text(encoding="utf-8"))
    hook_index = json.loads(HOOK_MASTER_INDEX.read_text(encoding="utf-8"))

    # ── Step 1: Extract requirements (single LLM call) ────────────────────
    print(f"\n  🔍 Step 1: Extracting integration requirements...")
    print(f"     Document length: {len(combined_text)} characters")

    extraction_prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        adapter_index=json.dumps(adapter_index, indent=2),
        hook_index=json.dumps(hook_index, indent=2),
        document_text=combined_text,
    )

    requirements = call_llm_json(
        prompt=extraction_prompt,
        system_instruction=EXTRACTION_SYSTEM_PROMPT,
    )

    services = requirements.get("services_detected", [])
    print(f"     ✅ Detected {len(services)} integration services:")
    for svc in services:
        mandatory = "MANDATORY" if svc.get("is_mandatory") else "optional"
        print(f"        • {svc['service_name']} ({svc.get('category', '?')}) [{mandatory}]")

    emit_audit_event(
        client_id=client_id,
        stage="stage_2_parsing",
        action=f"Extracted requirements: {len(services)} services detected",
        agent="gemini_flash_lite",
        input_data=combined_text[:200],
        output_data=json.dumps(requirements)[:200],
    )

    # ── Step 2: Fill config template ──────────────────────────────────────
    print(f"\n  📝 Step 2: Filling config template with extracted requirements...")

    current_config = get_latest_config(client_id)
    if not current_config:
        raise ValueError(f"No config found for client {client_id}")

    # Add document metadata
    current_config["metadata"]["uploaded_documents"] = [
        {"filename": fname, "type": fname.split(".")[-1].upper()}
        for fname in extracted_texts.keys()
    ]

    fill_prompt = TEMPLATE_FILL_PROMPT.format(
        requirements_summary=json.dumps(requirements, indent=2),
        current_config=json.dumps(current_config, indent=2),
    )

    filled_config = call_llm_json(
        prompt=fill_prompt,
        system_instruction=TEMPLATE_FILL_SYSTEM_PROMPT,
    )

    # Validate basic structure
    if "metadata" not in filled_config or "integrations" not in filled_config:
        print(f"     ⚠️  LLM returned incomplete config structure, merging with template...")
        # Merge: keep template structure, overlay LLM output
        for key in filled_config:
            if key in current_config:
                current_config[key] = filled_config[key]
        filled_config = current_config

    # Save updated config
    save_config(client_id, filled_config)
    integrations_count = len(filled_config.get("integrations", []))
    print(f"     ✅ Config populated with {integrations_count} integrations")

    emit_audit_event(
        client_id=client_id,
        stage="stage_2_parsing",
        action=f"Config template filled with {integrations_count} integrations",
        agent="gemini_flash_lite",
        input_data=json.dumps(requirements)[:200],
        output_data=json.dumps(filled_config)[:200],
    )

    print(f"\n  ✅ Stage 2 complete")
    return requirements

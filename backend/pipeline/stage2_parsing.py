"""
Stage 2 — Requirement Extraction Engine
========================================
Single LLM call: full document text → exhaustive structured extraction.
Then template fill: requirements + config → populated config skeleton.

Design principles:
  • Stage 2 is ONLY an extractor — it never filters, ranks, or matches adapters.
  • It captures EVERYTHING the BRD mentions: specific API names, exact versions
    (even if not in our catalog), all input/output fields, endpoint hints,
    auth types, compliance requirements, and hook/webhook signals.
  • Stage 3 will use this rich extraction to do vector-based catalog matching.
"""
import json
from typing import Dict

from backend.services.llm_service import call_llm, call_llm_json
from backend.services.audit_service import emit_audit_event
from backend.services.project_service import get_latest_config, save_config


# Known service categories — used only so Stage 2 can classify what type of
# service was mentioned. Actual catalog matching happens in Stage 3.
KNOWN_ADAPTER_CATEGORIES = (
    "bureau, kyc, payment, banking, gst, fraud, messaging, document, health_records, other"
)

EXTRACTION_SYSTEM_PROMPT = """You are an enterprise integration requirements analyst.
Your job is to exhaustively extract every integration signal from business requirement documents.

Critical rules:
1. Extract EVERY service or API mentioned — even if you have never heard of it.
2. If the BRD names a specific API provider or product (e.g. "TransUnion CIBIL v2", "Razorpay", "DigiLocker"),
   capture the exact name and version. Do NOT generalize or omit it.
3. If a specific version is mentioned (e.g. "v2", "version 3.1", "2024 API"), capture it exactly.
4. If a service is only vaguely described (e.g. "a credit scoring API"), still extract it with
   confidence="low" and your best guess at category and purpose.
5. Capture ALL input/output fields mentioned anywhere in the document for each adapter.
6. Capture ALL endpoint URLs, auth types, and webhook/callback mentions.
7. DO NOT hallucinate services not mentioned. Only extract what is actually there.
8. Be exhaustive — it is better to extract too much than to miss anything."""

EXTRACTION_PROMPT_TEMPLATE = """Analyze the following enterprise document(s) and extract ALL integration requirements.

Known categories to classify each detected service into:
{known_categories}

Use category "other" if a service doesn't fit any known category.

---
DOCUMENT TEXT:
{document_text}
---

Extract and return a JSON object with this EXACT structure.
Leave fields as null if not mentioned — never fabricate information.

{{
  "services_detected": [
    {{
      "service_name": "Exact name as mentioned in the document (e.g. 'TransUnion CIBIL', 'Razorpay Payment Gateway')",
      "provider": "Provider/vendor name if mentioned, else null",
      "category": "one of the known categories above",
      "is_mandatory": true,
      "confidence": "high (explicitly named) / medium (clearly implied) / low (vaguely described)",
      "exact_api_name_from_doc": "Copy the exact string used in the document to name this API, if any",
      "version_hint": "Exact version string mentioned (e.g. 'v2', '3.1', '2024') or null if not mentioned",
      "version_is_explicit": true,
      "endpoint_hints": ["Any endpoint URLs or paths literally mentioned in the document"],
      "auth_type_hint": "Any auth type mentioned (OAuth2, API Key, Basic Auth) or null",
      "purpose": "Why is this service needed? What business problem does it solve?",
      "input_fields_mentioned": [
        {{
          "field_name": "exact field name from doc",
          "field_type": "string/integer/date/boolean/etc if mentioned, else null",
          "is_pii": true,
          "notes": "any validation rules, formats, or constraints mentioned"
        }}
      ],
      "output_fields_mentioned": ["list of response/output field names mentioned"],
      "compliance_requirements": ["RBI, KYC, AML, GDPR, etc. — only if explicitly linked to this service"],
      "hook_signals": ["Any webhook, callback, event, or notification mentions for this specific service"],
      "additional_context": "Any other relevant detail about this service from the document"
    }}
  ],
  "general_requirements": {{
    "industry_vertical": "detected industry (e.g. lending, insurance, payments)",
    "region": "country/region if mentioned",
    "security_requirements": ["encryption, HTTPS, mTLS, etc."],
    "compliance_requirements": ["all compliance standards mentioned globally"],
    "data_fields_global": ["every data field name mentioned anywhere in the entire document"],
    "global_hook_signals": ["any webhook/event/notification mentions not tied to a specific service"],
    "non_catalog_apis": ["list any APIs mentioned that seem custom or non-standard"]
  }}
}}

IMPORTANT: If the BRD mentions a specific API by name (even one you don't recognize),
always include it. The downstream matching engine will decide if it's in our catalog.
"""

TEMPLATE_FILL_SYSTEM_PROMPT = """You are an enterprise integration configuration engine.
Your job is to populate a JSON configuration template skeleton with information
extracted from requirement documents.

Rules:
1. Fill every field you can CONFIDENTLY populate from the provided requirements.
2. Do NOT remove or restructure any fields from the template.
3. Leave unfillable fields exactly as they are in the template.
4. For the integrations array, create one skeleton entry per detected service.
   Leave adapter_id, endpoint_url, auth_type, field_mapping EMPTY — Stage 3 will fill these.
5. Populate: integration_id, service_name, category, is_mandatory, status="detected",
   and any version_hint from the BRD.
6. Return ONLY valid JSON — the complete config with filled fields."""

TEMPLATE_FILL_PROMPT = """Here are the extracted integration requirements:
{requirements_summary}

Here is the current configuration template:
{current_config}

Create one integration skeleton entry per detected service in the "integrations" array:
{{
  "integration_id": "unique_id based on service name",
  "service_name": "service name from requirements",
  "adapter_id": "",
  "category": "category from requirements",
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
  "fallback_adapter": null,
  "_brd_version_hint": "version string from BRD if any, else null",
  "_brd_purpose": "purpose extracted from BRD",
  "_brd_input_fields": []
}}

Also fill in metadata: industry_vertical, region, uploaded_documents.
Return the COMPLETE config JSON with all fields preserved.
"""


def run_stage2(client_id: str, extracted_texts: Dict[str, str]) -> dict:
    """
    Execute Stage 2 — Requirement Extraction.

    1. Exhaustive extraction: full document text → structured requirements
       (captures specific APIs/versions even if not in catalog)
    2. Template skeleton fill: requirements → integration stubs in config
       (Stage 3 will enrich each stub with adapter data)

    Args:
        client_id: The client folder ID
        extracted_texts: Dict of filename → extracted text from Stage 1

    Returns:
        The requirements summary dict (passed to Stage 3)
    """
    print(f"\n{'='*60}")
    print(f"  Stage 2 — Requirement Extraction Engine")
    print(f"{'='*60}")

    # Combine all document texts
    combined_text = ""
    for filename, text in extracted_texts.items():
        combined_text += f"\n\n===== {filename} =====\n\n{text}"

    # ── Step 1: Exhaustive requirement extraction ─────────────────────────
    print(f"\n  🔍 Step 1: Extracting all integration signals from documents...")
    print(f"     Document length: {len(combined_text)} characters")

    extraction_prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        known_categories=KNOWN_ADAPTER_CATEGORIES,
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
        version_str = f" [v={svc.get('version_hint')}]" if svc.get("version_hint") else ""
        explicit_str = " (explicit)" if svc.get("version_is_explicit") else ""
        fields_count = len(svc.get("input_fields_mentioned", []))
        print(f"        • {svc['service_name']} ({svc.get('category', '?')}) "
              f"[{mandatory}]{version_str}{explicit_str} — {fields_count} input fields")

    emit_audit_event(
        client_id=client_id,
        stage="stage_2_parsing",
        action=f"Extracted requirements: {len(services)} services detected",
        agent="gemini_flash_lite",
        input_data=combined_text[:200],
        output_data=json.dumps(requirements)[:200],
    )

    # ── Step 2: Fill config skeleton ──────────────────────────────────────
    print(f"\n  📝 Step 2: Creating integration stubs in config template...")

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

    # Validate basic structure — merge if LLM returned incomplete
    if "metadata" not in filled_config or "integrations" not in filled_config:
        print(f"     ⚠️  LLM returned incomplete config structure, merging with template...")
        for key in filled_config:
            if key in current_config:
                current_config[key] = filled_config[key]
        filled_config = current_config

    # Save updated config
    save_config(client_id, filled_config)
    integrations_count = len(filled_config.get("integrations", []))
    print(f"     ✅ Config skeleton created with {integrations_count} integration stubs")
    print(f"        (Stage 3 will enrich each stub via vector search + adapter JSON)")

    emit_audit_event(
        client_id=client_id,
        stage="stage_2_parsing",
        action=f"Config skeleton filled with {integrations_count} integration stubs",
        agent="gemini_flash_lite",
        input_data=json.dumps(requirements)[:200],
        output_data=json.dumps(filled_config)[:200],
    )

    print(f"\n  ✅ Stage 2 complete")
    return requirements

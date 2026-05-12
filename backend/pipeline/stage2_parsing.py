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
2. Capture exact names and versions as literally written. Do NOT generalize or omit.
3. If a specific version is mentioned (e.g. "v2", "version 3.1", "2024 API"), capture it exactly.
   If no version is mentioned, set version_hint to null and version_is_explicit to false.
4. If a service is only vaguely described (e.g. "a credit scoring API"), still extract it with
   confidence="low" and your best guess at category and purpose.
5. For input_fields_mentioned: ONLY capture fields explicitly named in the BRD for this service.
   Do NOT include fields you think the API might need — that is the downstream engine's job.
6. Mark is_mandatory=true ONLY if the BRD explicitly states the service is a REQUIRED
   INTEGRATION that the system sends data TO and receives a decision-driving response FROM.

   MANDATORY OVERRIDE — always set is_mandatory=false AND role="mentioned_only" when
   ALL of the following structural signals are present for a service:
     a. The BRD describes the system PUSHING events/notifications TO the service
        (e.g., "alert via", "notify via", "send SMS to", "trigger webhook on").
     b. The service returns no response that drives any business decision.
     c. The BRD explicitly states or implies failures are non-blocking
        (e.g., "must not block", "best effort", "notify at each step",
        "failures should not delay", "alert team if").

   These services are hook targets, not integration requirements. They must NOT
   receive an integration skeleton in Stage 3.

7. CRITICAL — Assign the role field. Before assigning, apply this single discriminating test:

   TEST: Does the system receive a RESPONSE from this service that it uses to make a business decision?
   • YES → the service drives logic (score returned, status returned, verification result returned)
             → role = "primary" or "fallback" (see below)
   • NO  → the system only pushes data outward; no response consumed to drive logic
             → role = "mentioned_only"

   role = "primary" when:
   • The BRD lists the service as an explicit, numbered, named integration requirement.
   • The service follows a request-response model: the system sends data AND uses the response
     to drive a business outcome (a decision, approval, verification, or transaction).
   • Linguistic signals: "SHALL use", "MUST integrate", "required", "mandatory integration",
     "the platform uses [service] for [purpose]".

   role = "fallback" when:
   • The document explicitly positions this service as a contingency only triggered when
     a named primary service is unavailable or fails.
   • Linguistic signals: "fallback to", "if [primary] fails", "in case [primary] is unavailable",
     "alternative if", "backup", "secondary provider", "failover to", "retry with".

   role = "mentioned_only" when ANY of these structural signals are present:
   • The document describes the service as a RECIPIENT of outbound events the system generates:
     the system SENDS notifications/alerts/events TO the service; the service returns nothing
     that the system consumes. BRD patterns: "alert [audience] via [service]",
     "notify [channel] when [event]", "send [event] to [service] on [trigger]",
     "[service] webhook on [condition]", "monitoring via", "operational alert to".
     These are hook signals, NOT integration requirements.
   • The service has no named input fields in the BRD and no named output fields — the document
     only says the system will POST to it or trigger it, never what data the system reads back.
   • The service is mentioned purely for comparison, background, or future consideration.
   • The document explicitly excludes it: "out of scope", "not required", "do NOT integrate".

   Tie-breaking rules:
   • Uncertain between primary and fallback → prefer "primary".
   • Uncertain between primary and mentioned_only → apply the TEST above.
     If no response drives any business logic → choose "mentioned_only".
   • A service that only RECEIVES outbound calls from the system is NEVER primary.


8. For hook_signals: you MUST scan the ENTIRE document including all prose sections,
   not just the field tables. For each service, ask:
     "Does the BRD describe what happens when THIS service fails, returns a specific
      value, or meets a threshold condition?"
   If yes, capture that as a hook_signal with the EXACT condition stated.

   Common prose patterns to look for:
     - "If [service] returns [value/status], then [action]"
     - "Route to [queue/team] when [condition]"
     - "If [service] fails, [retry/escalate/skip]"
     - "Allow up to N re-attempts"
     - "Treat as [state] if [service] returns no record"
     - "Notify [recipient] on [event]"

   Capture the FULL condition, not just "webhook mentioned".
   Example: "Route to manual review queue if identity verification fails" — NOT "manual review webhook".
9. DO NOT hallucinate services not mentioned. Only extract what is in the document.
10. Be exhaustive — it is better to extract too much than to miss anything.

CATEGORY DISAMBIGUATION — apply before assigning any category:

  "bureau" = services that return a credit history, credit score, or repayment
             track record for a person or entity. The service is operated by a
             regulated credit information company. Signals: "credit score",
             "credit report", "bureau check", "credit history", "CIBIL",
             "Experian", "CRIF", "Equifax".

  "fraud"  = services that score real-time transaction or behavioural risk,
             detect AML patterns, or flag suspicious activity. They do NOT
             return credit history. Signals: "fraud score", "risk score",
             "AML", "transaction monitoring", "device fingerprint", "velocity check".

  A credit bureau is NEVER category "fraud". When uncertain between the two,
  check: does the service return a credit score or repayment history? If yes → "bureau"."""

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
      "service_name": "Exact name of the service/API as written in the document — do not paraphrase or generalize",
      "provider": "Provider/vendor name if mentioned, else null",
      "category": "one of the known categories above",
      "is_mandatory": "true if BRD explicitly says required/mandatory, false for optional/conditional, true by default if unclear",
      "role": "primary | fallback | mentioned_only — see system rules. This field is MANDATORY.",
      "fallback_for": "If role=fallback: the service_name of the PRIMARY service this is a fallback for. Else null.",
      "confidence": "high (explicitly named API) / medium (clearly implied but not named) / low (vaguely described)",
      "exact_api_name_from_doc": "Copy the EXACT string the document uses to name this API or service — do not paraphrase",
      "version_hint": "Exact version string if mentioned (e.g. 'v2', '3.1', 'Latest stable') or null. Do not guess.",
      "version_is_explicit": "true only if a specific version number was stated, false otherwise",
      "endpoint_hints": ["Any endpoint URLs or paths literally quoted in the document"],
      "auth_type_hint": "Auth type if explicitly mentioned (e.g. 'OAuth2', 'API Key', 'Bearer token') or null",
      "purpose": "Concise explanation: what business problem does this service solve in THIS project?",
      "input_fields_mentioned": [
        {{
          "field_name": "ONLY fields explicitly named in the BRD for THIS service — do not add assumed fields",
          "field_type": "string/integer/date/boolean — from document only, else null",
          "is_pii": "true if name/Aadhaar/PAN/phone/DOB/account/address, else false",
          "notes": "validation rules, formats, value constraints mentioned for this field"
        }}
      ],
      "output_fields_mentioned": ["response/output field names explicitly mentioned in the BRD for this service"],
      "compliance_requirements": ["RBI, KYC, PMLA, DPDP, GDPR, etc. — ONLY if explicitly linked to this specific service"],
      "hook_signals": [
        "Capture ALL conditional triggers: e.g. 'Route to Fraud Investigation Queue if risk score >= 75'.",
        "Include the threshold or condition exactly as stated.",
        "Also capture: callbacks, webhooks, event notifications, post-call actions."
      ],
      "additional_context": "Any other relevant constraints, dependencies, or SLA requirements for this service"
    }}
  ],
  "general_requirements": {{
    "industry_vertical": "detected industry (e.g. lending, insurance, payments)",
    "region": "country/region if mentioned",
    "security_requirements": ["all encryption, HTTPS, mTLS, certificate pinning mentions"],
    "compliance_requirements": ["ALL compliance standards mentioned anywhere in the document"],
    "data_fields_global": ["every data field name mentioned anywhere in the entire document"],
    "global_hook_signals": ["webhook/event/notification mentions not tied to a single specific service"],
    "non_catalog_apis": ["APIs or services that seem custom-built, internal, or non-standard"]
  }}
}}

CRITICAL:
- If the BRD names a specific API or provider, always include it — even if unfamiliar.
  The downstream matching engine will handle catalog lookup.
- Do NOT add input fields that you think an API would need. Only capture what the BRD explicitly states.
- hook_signals must capture the business trigger condition (score threshold, event type), not just
  'webhook mentioned'.
"""

TEMPLATE_FILL_SYSTEM_PROMPT = """You are an enterprise integration configuration engine.
Your job is to populate a JSON configuration template skeleton with information
extracted from requirement documents.

Rules:
1. Fill every field you can CONFIDENTLY populate from the provided requirements.
2. Do NOT remove or restructure any fields from the template.
3. Leave unfillable fields as empty strings or empty arrays — never remove them.
4. CRITICAL: Only create integration skeleton entries for services where role == "primary".
   Services with role=="fallback" or role=="mentioned_only" must NOT get their own integration stub.
   Fallback services will be referenced in the fallback_adapter field of the primary integration by Stage 3.
5. Populate these fields from the extracted requirements:
   - integration_id: snake_case unique ID derived from the service_name
     Pattern: take key words from service_name, lowercase, join with underscores, suffix _001.
     (e.g. "Acme Credit Score API v3" → "acme_credit_score_001"; "FooBar KYC Engine" → "foobar_kyc_001")

   - service_name: exact name from extraction
   - category: from extraction
   - is_mandatory: from extraction (true/false)
   - status: always "detected" at this stage
   - _brd_version_hint: copy version_hint from extraction (even if null)
   - _brd_purpose: copy purpose from extraction
   - _brd_input_fields: copy only the field_name values from input_fields_mentioned
   - _brd_fallback_hint: if the BRD names a fallback for this service, capture the fallback's service name here
6. Return ONLY valid JSON — the COMPLETE config with ALL fields preserved."""

TEMPLATE_FILL_PROMPT = """Here are the extracted integration requirements:
{requirements_summary}

Here is the current configuration template:
{current_config}

For each service in "services_detected" where role == "primary", create ONE integration skeleton entry:
{{
  "integration_id": "snake_case_unique_id derived from service_name (lowercase, underscores, suffix _001)",
  "service_name": "exact service_name from extraction",
  "adapter_id": "",
  "category": "category from extraction",
  "is_mandatory": true,
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
  "_brd_version_hint": "copy version_hint from this service's extraction — string like 'v2' or 'Latest stable', or null",
  "_brd_purpose": "copy purpose from this service's extraction",
  "_brd_input_fields": ["copy only the field_name strings from input_fields_mentioned for this service"],
  "_brd_fallback_hint": "service name of the fallback provider if BRD names one, else null"
}}

Also populate these metadata fields from general_requirements:
- metadata.client.industry_vertical
- metadata.client.region
- metadata.uploaded_documents (already set, do not change)

CRITICAL RULES:
- ONLY include services with role=="primary" in the integrations array.
- Do NOT create stubs for fallback or mentioned_only services.
- Do NOT merge multiple services into one integration entry.
- Return the COMPLETE config JSON. Do not remove any existing top-level keys.
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

    # Safety cap: Stage 2 system prompt + schema takes ~1400 tokens.
    # At 4 chars/token, 12000 chars ≈ 3000 tokens of BRD text.
    # Total input stays under ~4500 tokens, leaving 11k+ output budget on a 16k context.
    BRD_TEXT_CAP = 12000
    if len(combined_text) > BRD_TEXT_CAP:
        print(f"     ⚠️  BRD text capped at {BRD_TEXT_CAP} chars to fit context window "
              f"(original: {len(combined_text)} chars)")
        combined_text = combined_text[:BRD_TEXT_CAP] + "\n\n... [document truncated — first section only]"

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

    # ── DETERMINISTIC ROLE FILTER ──────────────────────────────────────────
    # Uses only structural signals already extracted by the LLM — no hardcoded
    # service names, category strings, or domain-specific terms.
    # This is deterministic Python code; it does NOT rely on the LLM following instructions.

    role_lookup: dict = {}           # service_name (lower) → role string
    input_fields_lookup: dict = {}   # service_name (lower) → count of input_fields_mentioned
    output_fields_lookup: dict = {}  # service_name (lower) → count of output_fields_mentioned
    hook_mentioned_names: set = set()  # service names appearing ONLY in other services' hook_signals

    for svc in requirements.get("services_detected", []):
        name = (svc.get("service_name") or "").strip().lower()
        role = (svc.get("role") or "primary").strip().lower()
        role_lookup[name] = role
        input_fields_lookup[name] = len(svc.get("input_fields_mentioned", []))
        output_fields_lookup[name] = len(svc.get("output_fields_mentioned", []))

    # Collect service names that appear only as hook/event targets in other services.
    # A service with no BRD fields that is only a hook target is structurally outbound-only.
    for svc in requirements.get("services_detected", []):
        for hook in svc.get("hook_signals", []):
            hook_lower = hook.lower()
            for candidate_name in role_lookup:
                if candidate_name in hook_lower:
                    hook_mentioned_names.add(candidate_name)

    # Filter integration stubs — ONLY keep services classified as "primary"
    original_stubs = filled_config.get("integrations", [])
    primary_stubs = []
    filtered_out = []

    for stub in original_stubs:
        stub_name = (stub.get("service_name") or "").strip().lower()
        # Default to "primary" if the LLM didn't classify this service at all
        role = role_lookup.get(stub_name, "primary")

        # ── Structural safety net (domain-agnostic) ────────────────────────
        # Demote to mentioned_only if ALL three signals hold:
        #   1. Zero BRD input fields (the system sends no structured data to it), AND
        #   2. Zero BRD output fields (the system reads nothing back from it), AND
        #   3. It appears in other services' hook_signals (it is a notification target).
        # This pattern matches any outbound-only channel regardless of name or industry.
        if role == "primary":
            has_no_inputs  = input_fields_lookup.get(stub_name, -1) == 0
            has_no_outputs = output_fields_lookup.get(stub_name, -1) == 0
            is_hook_target = stub_name in hook_mentioned_names
            if has_no_inputs and has_no_outputs and is_hook_target:
                role = "mentioned_only"
                print(f"     ⚡ Safety net: demoted '{stub.get('service_name')}' "
                      f"(0 BRD input fields, 0 output fields, hook target only) → mentioned_only")

        if role in ("fallback", "mentioned_only"):
            filtered_out.append((stub.get("service_name", "unknown"), role))
        else:
            primary_stubs.append(stub)

    filled_config["integrations"] = primary_stubs


    if filtered_out:
        print(f"     🔽 Filtered out {len(filtered_out)} non-primary stubs:")
        for name, role in filtered_out:
            print(f"        • [{role.upper()}] {name}")

    # Save updated config
    save_config(client_id, filled_config)
    integrations_count = len(filled_config.get("integrations", []))
    print(f"     ✅ Config skeleton created with {integrations_count} primary integration stubs")
    print(f"        (Stage 3 will enrich each stub via vector search + adapter JSON)")

    emit_audit_event(
        client_id=client_id,
        stage="stage_2_parsing",
        action=f"Config skeleton filled with {integrations_count} stubs ({len(filtered_out)} fallbacks/mentioned-only filtered)",
        agent="gemini_flash_lite",
        input_data=json.dumps(requirements)[:200],
        output_data=json.dumps(filled_config)[:200],
    )

    print(f"\n  ✅ Stage 2 complete")
    return requirements


"""
Stage 4 — Reasoning Document Generator
Reads the annotated config (with _reason fields from Stage 3) and the raw BRD text
from Stage 1, then generates a comprehensive markdown reasoning report explaining
all pipeline decisions.
"""
import json
from pathlib import Path

from backend.config import CLIENTS_DIR
from backend.services.llm_service import call_llm
from backend.services.audit_service import emit_audit_event
from backend.services.project_service import get_latest_config


# ── Prompt Templates ────────────────────────────────────────────────────────

REASONING_SYSTEM = """You are a documentation engine for an enterprise AI integration pipeline.
Your job is to produce a clear, well-structured markdown reasoning report that explains every
decision the pipeline made. This report will be shown to a human reviewer alongside the
integration config so they can understand WHY things were set up the way they are.

Write in professional, concise English. Use markdown headers, bullet points, tables, and
warning callouts to make the document scannable. Be factual — reference specific adapter IDs,
version numbers, and field names. Be actionable — for every gap or warning, provide a clear
next step the reviewer should take."""

REASONING_PROMPT = """You are given two inputs:

1. **Annotated Integration Config** — a JSON config where each integration has `_adapter_reason`,
   `_version_reason` fields, and each field mapping may have `_mapping_reason` and `mapping_type: "missing"` entries.

2. **Raw BRD Text** — the original business requirement document text submitted by the client.

---

**Annotated Config:**
```json
{annotated_config}
```

---

**Raw BRD Text:**
```
{brd_text}
```

---

Generate a **Reasoning Report** in markdown format.

**CRITICAL — follow this order before writing any section:**
1. First, scan the BRD text and count all services/APIs mentioned.
2. Cross-reference that list against the integrations array.
3. Use the cross-reference result to write accurate coverage counts in EVERY section.
   Never state "all services matched" if the cross-reference reveals unmatched services.

Cover ALL of the following sections:

## 1. Adapter Selection Rationale
For each integration, explain:
- Which adapter was chosen and why (use the `_adapter_reason` from the config)
- The match confidence level and semantic similarity score if available
- If no adapter was matched (`adapter_id: "unmatched"`), add a ⚠️ warning with the service name
- **Integration ID validation**: for each integration, verify that `integration_id` follows
  `snake_case_with_suffix_001` format (all lowercase, underscores, no hyphens, no uppercase).
  If any integration_id violates this format (e.g., `INT-CIBIL-001`, `karza-kyc-001`), add a
  ⚠️ **ID FORMAT WARNING** block noting the non-compliant ID and what it should be corrected to.

## 2. Version Selection & Deprecation Notices
For each integration, explain:
- Which version was selected and why (use `_version_reason`)
- If a version was auto-upgraded because the BRD-requested version is deprecated, explain clearly:
  - Old requested version → new selected version → sunset date of old version
- If the selected version is itself deprecated or beta, add a ⚠️ deprecation warning with the sunset date

## 3. Missing Required Fields
Look through ALL field_mapping entries with `mapping_type: "missing"` across all integrations.
For each missing field, create a table row:

| Integration | Missing Field | API Requirement | Suggested Source |
|-------------|---------------|-----------------|------------------|
| e.g. cibil  | mobile_number | Required for identity match | Source from upstream KYC service response |

**IMPORTANT for Suggested Source column:**
- First check if the missing field exists anywhere in the BRD (look in raw BRD text).
  If it does: write "Already in BRD global fields — wire from applicant data payload at runtime."
  Do NOT say "add to intake form" if the field already exists in the BRD.
- If the field genuinely does not appear anywhere in the BRD, check if another integration
  in this config could provide it (e.g., KYC service providing PAN to Bureau).
- Only suggest "Add to applicant intake form" if the field is absent from both the BRD
  and all upstream service responses.

After the table, add a ⚠️ callout: "These fields must be resolved before production deployment."

## 4. Unmatched APIs / Services
Cross-reference the BRD text against the integrations array:
- List any API or service mentioned in the BRD that has NO matched integration entry
- For each unmatched service, suggest: (a) whether a similar adapter exists in common catalogs,
  (b) whether a new adapter JSON should be created in `backend/catalogs/adapters/`
- If all BRD services are fully covered, state that explicitly with ✅
- **Use the count from this section to write the Coverage line in Section 6.**

## 5. Field Mapping Summary
For each integration, independently derive:
- Total field_mapping entries: X mapped (direct/rename/computed) + Y missing
- PII fields: list ONLY fields where is_pii=true from THIS integration's OWN field_mapping.
  DO NOT copy PII fields from any other integration's section.
- Format conversion fields: list fields with transformation_rules of rule_type="format"
- Each integration's PII list MUST be derived from its own field_mapping entries only.
  If an integration has no PII fields in its field_mapping, state "No PII fields mapped."

## 6. Overall Assessment
Provide a structured assessment. Use the unmatched count derived in Section 4.

**Coverage**: [X/Y integrations fully matched based on Section 4 cross-reference, Z with missing fields]
**Confidence**: [High / Medium / Low — justify briefly]
**Critical Actions Required** (⚠️ must fix before production):
1. [action 1]
2. [action 2]

**Recommended Actions** (nice to have):
- [recommendation 1]

---

Output ONLY the markdown document. Do not wrap in code fences. Start with a title:
# Integration Reasoning Report
"""


def run_stage4(client_id: str, extracted_texts: dict) -> str:
    """
    Execute Stage 4 — Reasoning Document Generator.

    Reads the annotated config and BRD text, calls the LLM to produce
    a reasoning_report.md file.

    Args:
        client_id: The client folder ID
        extracted_texts: Dict mapping filename → extracted text (from Stage 1)

    Returns:
        The markdown reasoning report string
    """
    print(f"\n{'='*60}")
    print(f"  Stage 4 — Reasoning Document Generator")
    print(f"{'='*60}")

    # ── Load annotated config ─────────────────────────────────────────────
    annotated_config = get_latest_config(client_id)
    if not annotated_config:
        raise ValueError(f"No config found for client {client_id}")

    # ── Combine all BRD texts ─────────────────────────────────────────────
    brd_text = "\n\n---\n\n".join(
        f"### {filename}\n{text}"
        for filename, text in extracted_texts.items()
    )

    # Truncate BRD if too long (keep first 15K chars)
    if len(brd_text) > 15000:
        brd_text = brd_text[:15000] + "\n\n... [truncated for length]"

    # ── Build compact reasoning-only config summary ───────────────────────
    # Extract only the fields the LLM needs — avoids 30K truncation cutting off integrations
    compact_integrations = []
    for integ in annotated_config.get("integrations", []):
        compact_integrations.append({
            "integration_id": integ.get("integration_id"),
            "service_name": integ.get("service_name"),
            "adapter_id": integ.get("adapter_id"),
            "status": integ.get("status"),
            "selected_version": integ.get("selected_version"),
            "deprecated": integ.get("deprecated"),
            "sunset_date": integ.get("sunset_date"),
            "is_mandatory": integ.get("is_mandatory"),
            "fallback_adapter": integ.get("fallback_adapter"),
            "_adapter_reason": integ.get("_adapter_reason"),
            "_version_reason": integ.get("_version_reason"),
            "_brd_version_hint": integ.get("_brd_version_hint"),
            "field_mapping": integ.get("field_mapping", []),  # includes _mapping_reason
        })

    compact_config = {
        "metadata": {
            "client": annotated_config.get("metadata", {}).get("client", {}),
            "uploaded_documents": annotated_config.get("metadata", {}).get("uploaded_documents", []),
        },
        "integrations": compact_integrations,
    }
    config_str = json.dumps(compact_config, indent=2)
    # Safety cap: 40K chars (compact view is much smaller so this rarely triggers)
    if len(config_str) > 40000:
        config_str = config_str[:40000] + "\n... [truncated]"

    # ── Generate reasoning report via LLM ─────────────────────────────────
    print(f"\n  📝 Generating reasoning report...")

    prompt = REASONING_PROMPT.format(
        annotated_config=config_str,
        brd_text=brd_text,
    )

    reasoning_md = call_llm(
        prompt=prompt,
        system_instruction=REASONING_SYSTEM,
        expect_json=False,
    )

    # ── Save reasoning report ─────────────────────────────────────────────
    report_path = CLIENTS_DIR / client_id / "reasoning_report.md"
    report_path.write_text(reasoning_md, encoding="utf-8")

    print(f"     ✅ Reasoning report saved ({len(reasoning_md)} chars)")
    print(f"     📄 {report_path}")

    # ── Audit ─────────────────────────────────────────────────────────────
    # Count key metrics for the audit event
    integrations = annotated_config.get("integrations", [])
    missing_fields = sum(
        1 for integ in integrations
        for fm in integ.get("field_mapping", [])
        if fm.get("mapping_type") == "missing"
    )
    unmatched = sum(
        1 for integ in integrations
        if integ.get("adapter_id") == "unmatched"
    )

    emit_audit_event(
        client_id=client_id,
        stage="stage_4_reasoning",
        action=f"Reasoning report generated: {len(integrations)} integrations analyzed, "
               f"{missing_fields} missing fields flagged, {unmatched} unmatched services",
        agent="qwen_local",
        output_data=reasoning_md[:200],
    )

    print(f"\n  ✅ Stage 4 complete")
    return reasoning_md

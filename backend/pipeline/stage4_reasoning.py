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
version numbers, and field names."""

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

Generate a **Reasoning Report** in markdown format covering ALL of the following sections:

## 1. Adapter Selection Rationale
For each integration, explain:
- Which adapter was chosen and why (use the `_adapter_reason` from the config)
- If no adapter was matched, flag it as a ⚠️ warning

## 2. Version Selection & Deprecation Notices
For each integration, explain:
- Which version was selected and why (use `_version_reason`)
- If a version was auto-upgraded because the BRD-requested version is deprecated, explain clearly with the old version, new version, and sunset date
- If the selected version is itself deprecated, add a ⚠️ deprecation warning

## 3. Missing Required Fields
Look through all field_mapping entries with `mapping_type: "missing"`:
- List each missing required field by integration
- Explain why it couldn't be mapped (use `_mapping_reason`)
- Add a ⚠️ warning that these must be provided at runtime

## 4. Unmatched APIs / Services
Cross-reference the BRD text against the integrations:
- If the BRD mentions any APIs, services, or integrations that are NOT present in the config (no matching adapter was found), list them here
- If all BRD services are covered, state that explicitly

## 5. Field Mapping Summary
For each integration, provide a summary table or list:
- Total fields mapped vs total required
- Any computed or transformed fields
- Any fields with special notes (encryption, format conversion, etc.)

## 6. Overall Assessment
Provide a brief overall assessment:
- How complete is the integration coverage?
- Any critical gaps the reviewer should address?
- Confidence level: High / Medium / Low

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

    # Truncate if too long (keep first 15K chars to stay within LLM context)
    if len(brd_text) > 15000:
        brd_text = brd_text[:15000] + "\n\n... [truncated for length]"

    # Truncate config for LLM context
    config_str = json.dumps(annotated_config, indent=2)
    if len(config_str) > 30000:
        config_str = config_str[:30000] + "\n... [truncated]"

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
        agent="gemini_flash_lite",
        output_data=reasoning_md[:200],
    )

    print(f"\n  ✅ Stage 4 complete")
    return reasoning_md

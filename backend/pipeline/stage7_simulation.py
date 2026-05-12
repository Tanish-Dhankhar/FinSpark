"""
Stage 7 — Simulation & Testing Framework (Single-Version)
Loads mock responses, runs simulation, generates report with confidence score.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from backend.config import CLIENTS_DIR, MOCKS_DIR
from backend.services.llm_service import call_llm_json
from backend.services.audit_service import emit_audit_event
from backend.services.project_service import get_latest_config, save_config


REPORT_SYSTEM = """You are a simulation report generator for enterprise API integrations.
Analyze the field_mapping data and produce a structured quality report.

SCORING FORMULA -- apply this EXACTLY for each integration:

  Step 1: Count fields
    mapped_count  = count of field_mapping entries where mapping_type != "missing"
    missing_count = count of field_mapping entries where mapping_type == "missing"
    total_fields  = mapped_count + missing_count

  Step 2: Calculate score
    base_score       = (mapped_count / total_fields) * 100
                       [if total_fields == 0: base_score = 100, skip to Step 3]
    missing_penalty  = missing_count * 15
    confidence_score = max(0, round(base_score - missing_penalty))

  Worked example:
    field_mapping has 7 entries: 5 mapped, 2 missing
    base_score       = (5 / 7) * 100 = 71.4
    missing_penalty  = 2 * 15 = 30
    confidence_score = max(0, round(71.4 - 30)) = 41  -> status: "failed"

  Step 3: Assign status
    "passed"  -- confidence_score >= 75 AND missing_count == 0
    "warning" -- confidence_score >= 50 AND missing_count == 0
    "failed"  -- confidence_score < 50 OR missing_count > 0

  Step 4: Determine overall_passed (set LAST, after all statuses are assigned)
    overall_passed = true  ONLY IF  count(status == "failed") == 0
    overall_passed = false IF  count(status == "failed") >= 1
    Warning status does NOT make overall_passed false.

FORBIDDEN PENALTIES -- never apply a penalty for:
  - Having zero transformation_rules
  - Having fewer hooks than expected
  - Any condition not listed in Steps 1-3 above

For missing_mandatory_fields: list the api_field value for every entry where
mapping_type == "missing". Do not leave this array empty if such entries exist.

Use EXACT status values: "passed", "warning", "failed", "skipped" -- no other values."""


REPORT_PROMPT = """Here is the integration config:
{config}

Here are the simulation results for each integration:
{simulation_results}

Generate a simulation report as JSON:
{{
  "report_id": "sim_{random_id}",
  "generated_at": "{timestamp}",
  "overall_confidence_score": <number 0-100, average of all integration confidence_scores>,
  "overall_passed": <true if no integration has status=\"failed\", false otherwise>,
  "total_integrations_tested": <number>,
  "passed_count": <count of status=\"passed\">,
  "failed_count": <count of status=\"failed\">,
  "human_readable_summary": "Clear paragraph: how many passed/warned/failed and why",
  "recommended_actions": ["specific actions for each failed/warning integration"],
  "integration_results": [
    {{
      "integration_id": "id from config",
      "adapter_id": "adapter_id from config",
      "version_tested": "selected_version from config",
      "status": "passed | warning | failed — apply rules from system instructions",
      "confidence_score": <0-100 integer>,
      "fields_mapped_correctly": <count of field_mapping entries NOT mapping_type=\"missing\">,
      "total_required_fields": <total field_mapping entries>,
      "type_mismatches": ["any field type or format issues found"],
      "missing_mandatory_fields": ["api_field names where mapping_type=\"missing\""],
      "transformation_rule_failures": ["any transformation rules that cannot be applied"],
      "notes": "one sentence summary for this integration"
    }}
  ]
}}

IMPORTANT: Apply the pass/warning/fail rules from the system instruction exactly.
Do not mark an integration as failed just because optional fields are missing.
"""


def _load_mock_response(adapter_id: str, version: str) -> dict:
    """Load a mock response JSON for a given adapter and version."""
    # Guard: version may be None for unmatched adapters
    if version:
        # Try exact version match first
        mock_file = MOCKS_DIR / adapter_id / f"{version}_success.json"
        if mock_file.exists():
            return json.loads(mock_file.read_text(encoding="utf-8"))

        # Try normalising: strip leading 'v' then re-add it
        clean_version = version.lstrip("v")
        mock_file = MOCKS_DIR / adapter_id / f"v{clean_version}_success.json"
        if mock_file.exists():
            return json.loads(mock_file.read_text(encoding="utf-8"))

    # Try the adapter directory for any available mock (version-agnostic fallback)
    adapter_mock_dir = MOCKS_DIR / adapter_id
    if adapter_mock_dir.exists():
        mock_files = list(adapter_mock_dir.glob("*_success.json"))
        if mock_files:
            return json.loads(mock_files[0].read_text(encoding="utf-8"))

    # Return a generic placeholder mock
    return {
        "_mock": True,
        "_note": f"No mock file found for {adapter_id}/{version}",
        "status": "simulated",
        "response_code": 200,
    }



def _simulate_integration(integration: dict) -> dict:
    """Simulate a single integration using mock responses."""
    adapter_id = integration.get("adapter_id", "unknown")
    version = integration.get("selected_version", "v1")
    
    mock_response = _load_mock_response(adapter_id, version)
    field_mapping = integration.get("field_mapping", [])
    transformation_rules = integration.get("transformation_rules", [])

    # Check field mapping coverage
    mapped_fields = [m.get("api_field", "") for m in field_mapping]
    response_fields = list(mock_response.keys()) if isinstance(mock_response, dict) else []
    
    return {
        "integration_id": integration.get("integration_id", "unknown"),
        "adapter_id": adapter_id,
        "version": version,
        "mock_response": mock_response,
        "mapped_fields_count": len(field_mapping),
        "transformation_rules_count": len(transformation_rules),
        "response_fields": response_fields,
        "mock_available": not mock_response.get("_mock", False),
    }


def run_stage7(client_id: str) -> dict:
    """
    Execute Stage 7 — Simulation & Testing.
    Single-version simulation with mock responses.
    """
    print(f"\n{'='*60}")
    print(f"  Stage 7 — Simulation & Testing Framework")
    print(f"{'='*60}")

    config = get_latest_config(client_id)
    if not config:
        raise ValueError(f"No config found for client {client_id}")

    integrations = config.get("integrations", [])

    # ── Split: simulatable vs unmatched stubs ─────────────────────────────
    simulatable = [i for i in integrations if i.get("adapter_id", "unknown") != "unmatched"]
    unmatched_stubs = [i for i in integrations if i.get("adapter_id", "unknown") == "unmatched"]


    if unmatched_stubs:
        names = ", ".join(s.get("service_name", "?") for s in unmatched_stubs)
        print(f"\n  ⚠️  Skipping {len(unmatched_stubs)} unmatched stub(s) — no adapter in catalog: {names}")

    print(f"\n  🧪 Simulating {len(simulatable)} matched integrations...")

    # Run simulations only on matched integrations
    sim_results = []
    for integration in simulatable:
        aid = integration.get("adapter_id", "unknown")
        ver = integration.get("selected_version") or "unknown"
        print(f"     🔄 Simulating {aid} ({ver})...")

        result = _simulate_integration(integration)
        sim_results.append(result)

        mock_status = "✅ mock loaded" if result["mock_available"] else "⚠️  generic mock"
        print(f"        {mock_status}, {result['mapped_fields_count']} field mappings")

    # ── Build compact config view for LLM (avoids 118KB context overflow) ──
    compact_integrations = []
    for intg in simulatable:
        field_mapping = intg.get("field_mapping", [])
        compact_integrations.append({
            "integration_id": intg.get("integration_id"),
            "adapter_id": intg.get("adapter_id"),
            "selected_version": intg.get("selected_version"),
            "is_mandatory": intg.get("is_mandatory", True),
            "status": intg.get("status"),
            "field_mapping": [
                {
                    "api_field": m.get("api_field"),
                    "mapping_type": m.get("mapping_type"),
                    "user_field": m.get("user_field"),
                }
                for m in field_mapping
            ],
            "transformation_rules_count": len(intg.get("transformation_rules", [])),
        })
    compact_config = {"integrations": compact_integrations}

    # Generate report via LLM
    print(f"\n  📊 Generating simulation report...")

    timestamp = datetime.now(timezone.utc).isoformat()
    report_prompt = REPORT_PROMPT.format(
        config=json.dumps(compact_config, indent=2),
        simulation_results=json.dumps(sim_results, indent=2),
        random_id=uuid.uuid4().hex[:8],
        timestamp=timestamp,
    )


    report = call_llm_json(
        prompt=report_prompt,
        system_instruction=REPORT_SYSTEM,
    )

    # ── Enforce mathematical correctness post-LLM ──────────────────────────
    integration_results = report.get("integration_results", [])

    # Append skipped entries for unmatched stubs (pre-populated, no LLM needed)
    for stub in unmatched_stubs:
        integration_results.append({
            "integration_id": stub.get("integration_id", "unknown"),
            "adapter_id": "unmatched",
            "version_tested": None,
            "status": "skipped",
            "confidence_score": 0,
            "fields_mapped_correctly": 0,
            "total_required_fields": 0,
            "type_mismatches": [],
            "missing_mandatory_fields": [],
            "transformation_rule_failures": [],
            "notes": f"No adapter found in catalog for '{stub.get('service_name', '?')}'. Manual integration required.",
        })
    report["integration_results"] = integration_results

    if integration_results:
        passed_count = sum(
            1 for ir in integration_results
            if ir.get("status", "").lower() in ("passed", "warning")
        )
        failed_count = sum(
            1 for ir in integration_results
            if ir.get("status", "").lower() == "failed"
        )
        skipped_count = sum(
            1 for ir in integration_results
            if ir.get("status", "").lower() == "skipped"
        )
        scored_results = [ir for ir in integration_results if ir.get("status", "").lower() != "skipped"]
        total_score = sum(ir.get("confidence_score", 0) for ir in scored_results)

        report["passed_count"] = passed_count
        report["failed_count"] = failed_count
        report["skipped_count"] = skipped_count
        report["total_integrations_tested"] = len(integration_results)
        report["overall_passed"] = (failed_count == 0)
        report["overall_confidence_score"] = round(total_score / len(scored_results)) if scored_results else 0
    else:
        report["overall_confidence_score"] = 0
        report["passed_count"] = 0
        report["failed_count"] = 0
        report["skipped_count"] = len(unmatched_stubs)
        report["total_integrations_tested"] = len(unmatched_stubs)
        report["overall_passed"] = False


    # Save report
    reports_dir = CLIENTS_DIR / client_id / "simulation_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_filename = f"simulation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path = reports_dir / report_filename
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Update config with simulation results
    config["simulation_report"] = report
    config["simulation_report"]["report_file_path"] = str(report_path)
    config["metadata"]["pipeline_run"]["overall_status"] = "completed"
    config["metadata"]["pipeline_run"]["completed_at"] = timestamp
    config["metadata"]["status"] = "production-ready"
    save_config(client_id, config)

    # Print summary
    confidence = report.get("overall_confidence_score", 0)
    passed = report.get("passed_count", 0)
    failed = report.get("failed_count", 0)
    
    print(f"\n  📈 Simulation Results:")
    print(f"     Confidence Score: {confidence}%")
    print(f"     Passed: {passed}, Failed: {failed}")
    print(f"     Report saved: {report_filename}")

    emit_audit_event(
        client_id=client_id,
        stage="stage_7_simulation",
        action=f"Simulation complete: {confidence}% confidence, {passed} passed, {failed} failed",
        agent="gemini_flash_lite",
        output_data=json.dumps(report)[:200],
    )

    print(f"\n  ✅ Stage 7 complete")
    return report

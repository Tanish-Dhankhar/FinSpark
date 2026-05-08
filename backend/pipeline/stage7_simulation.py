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


REPORT_SYSTEM = """You are a simulation report generator for enterprise integrations.
Analyze simulation results and produce a structured quality report.
Be precise about field mapping correctness and identify any issues."""

REPORT_PROMPT = """Here is the integration config:
{config}

Here are the simulation results for each integration:
{simulation_results}

Generate a simulation report as JSON:
{{
  "report_id": "sim_{random_id}",
  "generated_at": "{timestamp}",
  "overall_confidence_score": <number 0-100>,
  "overall_passed": <boolean>,
  "total_integrations_tested": <number>,
  "passed_count": <number>,
  "failed_count": <number>,
  "human_readable_summary": "A clear paragraph summarizing results",
  "recommended_actions": ["list of actions to take"],
  "integration_results": [
    {{
      "integration_id": "id",
      "adapter_id": "adapter",
      "version_tested": "version",
      "status": "passed/failed/warning",
      "confidence_score": <0-100>,
      "fields_mapped_correctly": <number>,
      "total_required_fields": <number>,
      "type_mismatches": ["list of mismatches"],
      "missing_mandatory_fields": ["list"],
      "transformation_rule_failures": ["list"],
      "notes": "any additional notes"
    }}
  ]
}}

Confidence score formula: (correctly_resolved / total_required) * 100, with -10 penalty per mandatory field failure.
"""


def _load_mock_response(adapter_id: str, version: str) -> dict:
    """Load a mock response JSON for a given adapter and version."""
    # Try exact version match
    mock_file = MOCKS_DIR / adapter_id / f"{version}_success.json"
    if mock_file.exists():
        return json.loads(mock_file.read_text(encoding="utf-8"))
    
    # Try without 'v' prefix
    clean_version = version.lstrip("v")
    mock_file = MOCKS_DIR / adapter_id / f"v{clean_version}_success.json"
    if mock_file.exists():
        return json.loads(mock_file.read_text(encoding="utf-8"))

    # Try the adapter directory for any available mock
    adapter_mock_dir = MOCKS_DIR / adapter_id
    if adapter_mock_dir.exists():
        mock_files = list(adapter_mock_dir.glob("*_success.json"))
        if mock_files:
            return json.loads(mock_files[0].read_text(encoding="utf-8"))

    # Return a generic mock
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
    print(f"\n  🧪 Simulating {len(integrations)} integrations...")

    # Run simulations
    sim_results = []
    for integration in integrations:
        aid = integration.get("adapter_id", "unknown")
        ver = integration.get("selected_version", "?")
        print(f"     🔄 Simulating {aid} ({ver})...")
        
        result = _simulate_integration(integration)
        sim_results.append(result)
        
        mock_status = "✅ mock loaded" if result["mock_available"] else "⚠️ generic mock"
        print(f"        {mock_status}, {result['mapped_fields_count']} field mappings")

    # Generate report via LLM
    print(f"\n  📊 Generating simulation report...")
    
    timestamp = datetime.now(timezone.utc).isoformat()
    report_prompt = REPORT_PROMPT.format(
        config=json.dumps(config, indent=2),
        simulation_results=json.dumps(sim_results, indent=2),
        random_id=uuid.uuid4().hex[:8],
        timestamp=timestamp,
    )

    report = call_llm_json(
        prompt=report_prompt,
        system_instruction=REPORT_SYSTEM,
    )

    # ── Enforce mathematical correctness (LLMs are bad at math) ──
    integration_results = report.get("integration_results", [])
    if integration_results:
        passed_count = sum(1 for ir in integration_results if ir.get("status", "").lower() == "passed")
        failed_count = len(integration_results) - passed_count
        total_score = sum(ir.get("confidence_score", 0) for ir in integration_results)
        
        report["passed_count"] = passed_count
        report["failed_count"] = failed_count
        report["total_integrations_tested"] = len(integration_results)
        report["overall_passed"] = (failed_count == 0)
        report["overall_confidence_score"] = round(total_score / len(integration_results))
    else:
        report["overall_confidence_score"] = 0
        report["passed_count"] = 0
        report["failed_count"] = 0
        report["total_integrations_tested"] = 0
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

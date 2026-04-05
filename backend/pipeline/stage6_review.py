"""
Stage 6 — Human-in-the-Loop Review
Pipeline pauses here for human approval or change requests.
Max 3 correction iterations, then escalation.
"""
import json
from datetime import datetime, timezone

from backend.services.llm_service import call_llm_json
from backend.services.audit_service import emit_audit_event
from backend.services.project_service import (
    get_latest_config, save_config, get_current_version_number
)
from backend.config import MAX_CORRECTION_ITERATIONS


CORRECTOR_SYSTEM = (
    "You are an integration configuration corrector. "
    "Apply the reviewer's natural language changes precisely. "
    "Preserve all structure. Keep $ENV_VAR credential references. "
    "Return complete valid JSON."
)

CORRECTOR_PROMPT = """Current config:
{config}

Reviewer requested:
"{feedback}"

Apply changes and return the complete updated config JSON."""


def pause_for_review(client_id: str) -> dict:
    """Pause pipeline at Stage 6 for human review."""
    print(f"\n{'='*60}")
    print(f"  Stage 6 — Human-in-the-Loop Review")
    print(f"{'='*60}")

    config = get_latest_config(client_id)
    if not config:
        raise ValueError(f"No config found for {client_id}")

    config["metadata"]["pipeline_run"]["overall_status"] = "awaiting_review"
    config["metadata"]["pipeline_run"]["human_review_status"] = "pending"
    save_config(client_id, config)

    version = get_current_version_number(client_id)
    iterations = config["metadata"]["pipeline_run"].get("correction_iterations", 0)

    print(f"\n  ⏸️  Pipeline paused — awaiting human review")
    print(f"     Config version: v{version}")
    print(f"     Corrections used: {iterations}/{MAX_CORRECTION_ITERATIONS}")

    emit_audit_event(
        client_id=client_id,
        stage="stage_6_review",
        action="Pipeline paused for human review",
        agent="stage6_review",
        responsible="system",
    )

    return {
        "status": "awaiting_review",
        "config_version": f"v{version}",
        "correction_iterations": iterations,
        "max_iterations": MAX_CORRECTION_ITERATIONS,
        "integrations_count": len(config.get("integrations", [])),
    }


def approve_config(client_id: str, reviewer: str = "human_reviewer") -> dict:
    """Approve current config, allowing Stage 7 to proceed."""
    config = get_latest_config(client_id)
    if not config:
        raise ValueError(f"No config found for {client_id}")

    config["metadata"]["pipeline_run"]["overall_status"] = "approved"
    config["metadata"]["pipeline_run"]["human_review_status"] = "approved"
    config["metadata"]["pipeline_run"]["human_reviewer"] = reviewer
    config["metadata"]["status"] = "approved"
    save_config(client_id, config)

    version = get_current_version_number(client_id)
    print(f"\n  ✅ Config v{version} APPROVED by {reviewer}")

    emit_audit_event(
        client_id=client_id,
        stage="stage_6_review",
        action=f"Config v{version} approved",
        agent="stage6_review",
        responsible=reviewer,
    )

    return {
        "status": "approved",
        "config_version": f"v{version}",
        "message": "Config approved. Proceeding to simulation.",
    }


def request_changes(client_id: str, feedback: str, reviewer: str = "human_reviewer") -> dict:
    """Process change request via Corrector Agent LLM."""
    config = get_latest_config(client_id)
    if not config:
        raise ValueError(f"No config found for {client_id}")

    current_iterations = config["metadata"]["pipeline_run"].get("correction_iterations", 0)

    # Check limit
    if current_iterations >= MAX_CORRECTION_ITERATIONS:
        config["metadata"]["pipeline_run"]["overall_status"] = "escalated"
        config["metadata"]["pipeline_run"]["human_review_status"] = "escalated"
        save_config(client_id, config)

        emit_audit_event(
            client_id=client_id,
            stage="stage_6_review",
            action=f"Config ESCALATED after {MAX_CORRECTION_ITERATIONS} iterations",
            agent="stage6_review",
            responsible=reviewer,
        )

        return {
            "status": "escalated",
            "message": f"Max {MAX_CORRECTION_ITERATIONS} iterations reached. Escalated.",
            "iterations_used": current_iterations,
        }

    print(f"\n  ✏️  Correction {current_iterations + 1}/{MAX_CORRECTION_ITERATIONS}...")

    prompt = CORRECTOR_PROMPT.format(
        config=json.dumps(config, indent=2),
        feedback=feedback,
    )

    corrected = call_llm_json(prompt=prompt, system_instruction=CORRECTOR_SYSTEM)

    # Validate
    if "integrations" not in corrected:
        corrected["integrations"] = config.get("integrations", [])
    if "metadata" not in corrected:
        corrected["metadata"] = config.get("metadata", {})

    corrected.pop("_correction_notes", None)
    corrected["metadata"]["pipeline_run"]["correction_iterations"] = current_iterations + 1
    corrected["metadata"]["pipeline_run"]["overall_status"] = "awaiting_review"
    corrected["metadata"]["pipeline_run"]["review_notes"] = feedback

    new_version = get_current_version_number(client_id) + 1
    save_config(client_id, corrected, version=new_version)

    print(f"     ✅ Changes applied → config_v{new_version}.json")

    emit_audit_event(
        client_id=client_id,
        stage="stage_6_review",
        action=f"Correction {current_iterations + 1} applied, saved as v{new_version}",
        agent="gemini_flash_lite",
        responsible=reviewer,
        input_data=feedback[:200],
    )

    return {
        "status": "changes_applied",
        "config_version": f"v{new_version}",
        "iterations_used": current_iterations + 1,
        "iterations_remaining": MAX_CORRECTION_ITERATIONS - (current_iterations + 1),
        "message": f"Changes applied. Config v{new_version} ready for review.",
    }

"""
Pipeline Orchestrator
Coordinates all pipeline stages sequentially: 1→2→3→4→5→pause at 6→7 after approval.
"""
import json
import traceback
from datetime import datetime, timezone

from backend.services.audit_service import emit_audit_event
from backend.services.project_service import get_latest_config, save_config
from backend.pipeline.stage1_ingestion import run_stage1
from backend.pipeline.stage2_parsing import run_stage2
from backend.pipeline.stage3_matching import run_stage3
from backend.pipeline.stage4_reasoning import run_stage4
from backend.pipeline.stage5_cleaner import run_stage5
from backend.pipeline.stage6_review import pause_for_review
from backend.pipeline.stage7_simulation import run_stage7


# Global dict tracking pipeline progress per client (in-memory)
_pipeline_progress = {}


def get_progress(client_id: str) -> dict:
    """Get current pipeline progress for a client."""
    return _pipeline_progress.get(client_id, {
        "stage": "idle",
        "status": "idle",
        "message": "No pipeline running",
        "progress_percent": 0,
    })


def _update_progress(client_id: str, stage: str, status: str, message: str, percent: int):
    """Update in-memory pipeline progress."""
    _pipeline_progress[client_id] = {
        "stage": stage,
        "status": status,
        "message": message,
        "progress_percent": percent,
    }
    print(f"  [{percent}%] {message}")


def run_pipeline_stages_1_to_5(client_id: str) -> dict:
    """
    Run pipeline stages 1 through 5, then pause at stage 6 for review.
    
    Args:
        client_id: The client folder ID
        
    Returns:
        Status dict with review info
    """
    print(f"\n{'#'*60}")
    print(f"  PIPELINE START — Client: {client_id}")
    print(f"  Time: {datetime.now(timezone.utc).isoformat()}")
    print(f"{'#'*60}")

    emit_audit_event(
        client_id=client_id,
        stage="pipeline",
        action="Pipeline execution started (stages 1-5)",
        agent="orchestrator",
    )

    try:
        # ── Stage 1: Document Ingestion ────────────────────────────────
        _update_progress(client_id, "stage_1", "running", "Stage 1: Extracting documents...", 5)
        extracted_texts = run_stage1(client_id)
        _update_progress(client_id, "stage_1", "complete", f"Stage 1: Extracted {len(extracted_texts)} documents", 15)

        # ── Stage 2: Requirement Parsing ───────────────────────────────
        _update_progress(client_id, "stage_2", "running", "Stage 2: Parsing requirements...", 20)
        requirements = run_stage2(client_id, extracted_texts)
        services_count = len(requirements.get("services_detected", []))
        _update_progress(client_id, "stage_2", "complete", f"Stage 2: Detected {services_count} services", 35)

        # ── Stage 3: Catalog Matching ──────────────────────────────────
        _update_progress(client_id, "stage_3", "running", "Stage 3: Matching adapters & hooks...", 40)
        enriched_config = run_stage3(client_id, requirements)
        _update_progress(client_id, "stage_3", "complete", "Stage 3: Config enriched with adapters, hooks, mappings", 60)

        # ── Stage 4: Reasoning Document ───────────────────────────────
        _update_progress(client_id, "stage_4", "running", "Stage 4: Generating reasoning report...", 65)
        run_stage4(client_id, extracted_texts)
        _update_progress(client_id, "stage_4", "complete", "Stage 4: Reasoning report generated", 75)

        # ── Stage 5: Cleaner Agent ─────────────────────────────────────
        _update_progress(client_id, "stage_5", "running", "Stage 5: Cleaning config...", 80)
        run_stage5(client_id)
        _update_progress(client_id, "stage_5", "complete", "Stage 5: Config cleaned for production", 85)

        # ── Stage 6: Pause for Review ──────────────────────────────────
        _update_progress(client_id, "stage_6", "awaiting_review", "Stage 6: Awaiting human review", 90)
        review_status = pause_for_review(client_id)

        emit_audit_event(
            client_id=client_id,
            stage="pipeline",
            action="Pipeline paused at Stage 6 for human review",
            agent="orchestrator",
        )

        return review_status

    except Exception as e:
        error_msg = f"Pipeline failed: {str(e)}"
        _update_progress(client_id, "error", "failed", error_msg, 0)
        print(f"\n  ❌ {error_msg}")
        traceback.print_exc()

        emit_audit_event(
            client_id=client_id,
            stage="pipeline",
            action=f"Pipeline FAILED: {str(e)[:200]}",
            agent="orchestrator",
            details=traceback.format_exc()[:500],
        )

        # Update config status
        try:
            config = get_latest_config(client_id)
            if config:
                config["metadata"]["pipeline_run"]["overall_status"] = "failed"
                save_config(client_id, config)
        except Exception:
            pass

        raise


def run_pipeline_stage_7(client_id: str) -> dict:
    """
    Run Stage 7 (simulation) after human approval.
    
    Args:
        client_id: The client folder ID
        
    Returns:
        Simulation report dict
    """
    print(f"\n{'#'*60}")
    print(f"  PIPELINE RESUME — Stage 7 Simulation — Client: {client_id}")
    print(f"{'#'*60}")

    emit_audit_event(
        client_id=client_id,
        stage="pipeline",
        action="Pipeline resumed for Stage 7 simulation",
        agent="orchestrator",
    )

    try:
        _update_progress(client_id, "stage_7", "running", "Stage 7: Running simulation...", 92)
        report = run_stage7(client_id)

        confidence = report.get("overall_confidence_score", 0)
        _update_progress(
            client_id, "completed", "completed",
            f"Pipeline complete — Confidence: {confidence}%", 100
        )

        emit_audit_event(
            client_id=client_id,
            stage="pipeline",
            action=f"Pipeline COMPLETED — confidence score: {confidence}%",
            agent="orchestrator",
        )

        return report

    except Exception as e:
        error_msg = f"Stage 7 failed: {str(e)}"
        _update_progress(client_id, "error", "failed", error_msg, 90)
        print(f"\n  ❌ {error_msg}")
        traceback.print_exc()

        emit_audit_event(
            client_id=client_id,
            stage="pipeline",
            action=f"Stage 7 FAILED: {str(e)[:200]}",
            agent="orchestrator",
        )
        raise

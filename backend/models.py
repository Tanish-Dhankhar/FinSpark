"""
FinSpark Pydantic Models
Request/Response schemas for the API layer.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ── Enums ───────────────────────────────────────────────────────────────────

class PipelineStage(str, Enum):
    INGESTION = "stage_1_ingestion"
    PARSING = "stage_2_parsing"
    MATCHING = "stage_3_matching"
    REASONING = "stage_4_reasoning"
    CLEANER = "stage_5_cleaner"
    REVIEW = "stage_6_review"
    SIMULATION = "stage_7_simulation"
    COMPLETED = "completed"


class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    APPROVED = "approved"
    ESCALATED = "escalated"
    COMPLETED = "completed"
    FAILED = "failed"


class ReviewAction(str, Enum):
    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"


# ── Request Models ──────────────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    client_name: str = Field(..., min_length=1, max_length=200, description="Name of the client/company")


class ReviewRequest(BaseModel):
    action: ReviewAction
    feedback_text: Optional[str] = Field(None, description="Natural language correction instructions (required for request_changes)")


# ── Response Models ─────────────────────────────────────────────────────────

class ProjectSummary(BaseModel):
    client_id: str
    client_name: str
    created_at: str
    current_config_version: str
    pipeline_status: PipelineStatus
    active_integrations_count: int = 0


class ProjectDetail(BaseModel):
    client_id: str
    client_name: str
    created_at: str
    current_config_version: str
    pipeline_status: PipelineStatus
    current_stage: Optional[str] = None
    active_integrations_count: int = 0
    config_versions: List[str] = []
    diff_files: List[str] = []
    simulation_reports: List[str] = []
    input_documents: List[str] = []
    correction_iterations: int = 0


class PipelineProgressResponse(BaseModel):
    client_id: str
    stage: str
    status: PipelineStatus
    message: str
    progress_percent: int = 0


class AuditEntry(BaseModel):
    timestamp: str
    stage: str
    action: str
    agent: str = "system"
    responsible: str = "system"
    input_hash: Optional[str] = None
    output_hash: Optional[str] = None
    details: Optional[str] = None


class ReviewResponse(BaseModel):
    status: str
    message: str
    config_version: Optional[str] = None
    iterations_remaining: Optional[int] = None

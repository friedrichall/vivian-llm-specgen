"""Pydantic models_funcspec for backend job state."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError


class JobStatus(str, Enum):
    """Finite set of lifecycle states for a backend job."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobPhase(str, Enum):
    """Current phase of pipeline execution for one job."""

    QUEUED = "QUEUED"
    PREPARING_INPUT = "PREPARING_INPUT"
    ANALYZING_SCENE = "ANALYZING_SCENE"
    AWAITING_SCENE_CONFIRMATION = "AWAITING_SCENE_CONFIRMATION"
    PLANNING_INTERACTIONS = "PLANNING_INTERACTIONS"
    GENERATING_SPECS_INTERACTION_ELEMENTS = "GENERATING_SPECS_INTERACTION_ELEMENTS"
    GENERATING_SPECS_VISUALIZATION_ELEMENTS = "GENERATING_SPECS_VISUALIZATION_ELEMENTS"
    GENERATING_SPECS_STATES = "GENERATING_SPECS_STATES"
    GENERATING_SPECS_TRANSITIONS = "GENERATING_SPECS_TRANSITIONS"
    GENERATING_SPECS = "GENERATING_SPECS"
    REVIEWING_CONSISTENCY = "REVIEWING_CONSISTENCY"
    GENERATING_FIX_PLAN = "GENERATING_FIX_PLAN"
    DETERMINING_RETRY_SCOPE = "DETERMINING_RETRY_SCOPE"
    VALIDATING_OUTPUT = "VALIDATING_OUTPUT"
    PUBLISHING = "PUBLISHING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class SceneReviewState(str, Enum):
    """Lifecycle state of the scene review subflow."""

    PENDING = "PENDING"
    PROCESSING_FEEDBACK = "PROCESSING_FEEDBACK"
    CONFIRMED = "CONFIRMED"


class JobInfo(BaseModel):
    """In-memory representation of a single job."""

    job_id: str
    status: JobStatus
    phase: JobPhase
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    log_path: str
    output_path: str | None
    successful_attempt: int | None
    error: str | None


class StartJobRequest(BaseModel):
    """Input required to start one backend pipeline job."""

    model_config = ConfigDict(extra="forbid")

    group_path: str = Field(min_length=1)
    start_pipeline: bool = True
    only_scene_analysis: bool = False
    use_mock_scene_analysis: bool = False
    interaction_description: str | None = None
    screens_dir: str | None = None

    @field_validator("group_path")
    @classmethod
    def reject_blank_group_path(cls, value: str) -> str:
        """Require a non-blank group_path."""
        if not value.strip():
            raise PydanticCustomError(
                "group_path_blank",
                "group_path must not be blank.",
            )
        return value


class StartJobResponse(BaseModel):
    """Response returned immediately after accepting a job."""

    job_id: str
    status: JobStatus


class JobStatusResponse(BaseModel):
    """State response for status polling."""

    job_id: str
    status: JobStatus
    phase: JobPhase
    error: str | None


class JobLogsResponse(BaseModel):
    """Incremental log chunk response."""

    job_id: str
    status: JobStatus
    chunk: str
    next_offset: int


class JobResultResponse(BaseModel):
    """Final result contract for finished jobs."""

    job_id: str
    status: JobStatus
    success: bool
    successful_attempt: int | None
    output_path: str | None
    error: str | None


class CancelJobResponse(BaseModel):
    """Response sent after cancellation is requested."""

    job_id: str
    status: JobStatus
    message: str


class SceneReviewPayload(BaseModel):
    """Snapshot returned to clients for review/confirmation."""

    revision: int = Field(ge=1)
    summary: str
    scene_understanding: dict[str, Any]
    interaction_plan: dict[str, Any] | None = None
    updated_at: datetime


class SceneReviewResponse(BaseModel):
    """Current scene-review state for one job."""

    job_id: str
    status: JobStatus
    phase: JobPhase
    review_state: SceneReviewState | None
    scene_review: SceneReviewPayload | None
    error: str | None


class SceneReviewDecisionRequest(BaseModel):
    """User decision payload for one scene review revision."""

    revision: int = Field(ge=1)
    confirmed: bool
    feedback: str | None = None

    @model_validator(mode="after")
    def validate_feedback_requirement(self) -> "SceneReviewDecisionRequest":
        """Require non-empty feedback when not confirming."""
        if self.confirmed:
            return self
        feedback = (self.feedback or "").strip()
        if not feedback:
            raise PydanticCustomError(
                "feedback_required",
                "feedback is required when confirmed is false.",
            )
        return self


class SceneReviewDecisionResponse(BaseModel):
    """Acknowledgement returned when a scene-review decision is accepted."""

    job_id: str
    status: JobStatus
    phase: JobPhase
    review_state: SceneReviewState
    accepted_revision: int
    message: str

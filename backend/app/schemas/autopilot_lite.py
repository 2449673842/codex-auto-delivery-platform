from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.browser_ai_pool import (
    BrowserAiPoolJobPreview,
    BrowserAiPoolProviderRequest,
)
from app.schemas.mastermind_review import (
    MastermindReviewGatePreviewResponse,
    MastermindReviewPacketPreviewRequest,
    MastermindReviewPacketPreviewResponse,
)


AutoPilotMode = Literal["review_batch", "repair_planning", "delivery_check"]


class AutoPilotLitePreviewRequest(BaseModel):
    mode: AutoPilotMode = "review_batch"
    prompt: str = ""
    providers: list[BrowserAiPoolProviderRequest] = Field(default_factory=list)
    include_task_context: bool = True
    include_project_memory: bool = True
    include_evidence_board: bool = True
    include_timeline: bool = True
    include_mastermind_review: bool = True
    run_gate_preview: bool = True
    max_total_concurrency: int = Field(default=2, ge=1, le=6)
    per_provider_concurrency: int = Field(default=1, ge=1, le=3)
    prompt_budget: int = Field(default=12000, ge=1000, le=30000)
    mastermind_packet: MastermindReviewPacketPreviewRequest = Field(
        default_factory=MastermindReviewPacketPreviewRequest
    )


class AutoPilotLiteStepPreview(BaseModel):
    key: str
    title: str
    status: str
    summary: str = ""
    blocking_reasons: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    source_ids: dict[str, Any] = Field(default_factory=dict)


class AutoPilotLitePreviewResponse(BaseModel):
    task_id: int
    project_id: int
    mode: AutoPilotMode = "review_batch"
    status: str
    autopilot_state: str
    recommendation: str
    steps: list[AutoPilotLiteStepPreview] = Field(default_factory=list)
    provider_jobs: list[BrowserAiPoolJobPreview] = Field(default_factory=list)
    pool_overall_status: str = ""
    synthesis_status: str = ""
    mastermind_packet_preview: MastermindReviewPacketPreviewResponse | None = None
    gate_preview: MastermindReviewGatePreviewResponse | None = None
    recommended_actions: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    read_only: bool = True
    persisted: bool = False
    advisory_only: bool = True
    human_confirmation_required: bool = True
    no_auto_merge: bool = True

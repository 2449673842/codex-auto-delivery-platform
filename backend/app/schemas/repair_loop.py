from pydantic import BaseModel, Field


REPAIR_FAILURE_TYPES = {
    "sandbox_failed",
    "sandbox_gate_blocked",
    "verification_failed",
    "ci_failed",
    "sonar_failed",
    "review_blocked",
    "browser_ai_failed",
    "multi_ai_evidence_partial",
}


class FailureEvidenceSource(BaseModel):
    agent_run_id: int | None = None
    artifact_id: int | None = None
    dispatch_batch_id: int | None = None
    dispatch_job_id: int | None = None


class FailureEvidencePreviewRequest(BaseModel):
    task_id: int
    failure_type: str
    source: FailureEvidenceSource = Field(default_factory=FailureEvidenceSource)
    max_excerpt_chars: int = Field(default=4000, ge=200, le=12000)


class FailureEvidenceRedactionStatus(BaseModel):
    redaction_applied: bool = True
    truncated: bool = False
    max_chars: int = 4000


class FailureEvidencePacketResponse(BaseModel):
    task_id: int
    project_id: int
    failure_type: str
    failed_step: str
    failed_command_summary: str = ""
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""
    blocked_reasons: list[str] = Field(default_factory=list)
    related_agent_run_ids: list[int] = Field(default_factory=list)
    related_artifact_ids: list[int] = Field(default_factory=list)
    related_dispatch_batch_id: int | None = None
    related_dispatch_job_ids: list[int] = Field(default_factory=list)
    source_commit_hint: str = "verify_current_master_before_acting"
    safety_notes: list[str] = Field(default_factory=list)
    redaction_status: FailureEvidenceRedactionStatus
    read_only: bool = True
    persisted: bool = False

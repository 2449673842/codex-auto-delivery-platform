from pydantic import BaseModel, Field

from app.schemas.multi_ai_evidence_run import MultiAiEvidenceRoleRequest


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


class RepairPacketGenerateRequest(BaseModel):
    task_id: int
    failure_evidence: FailureEvidencePacketResponse
    analysis_mode: str = "broadcast"
    providers: list[str] = Field(default_factory=list)
    roles: list[MultiAiEvidenceRoleRequest] = Field(default_factory=list)
    max_attempts: int = Field(default=1, ge=1, le=3)


class RepairEvidenceBySource(BaseModel):
    source: str
    summary: str
    artifact_ids: list[int] = Field(default_factory=list)
    agent_run_ids: list[int] = Field(default_factory=list)
    dispatch_batch_id: int | None = None
    dispatch_job_ids: list[int] = Field(default_factory=list)


class RepairPacketResponse(BaseModel):
    task_id: int
    project_id: int
    failure_summary: str = ""
    suspected_root_causes: list[str] = Field(default_factory=list)
    evidence_by_source: list[RepairEvidenceBySource] = Field(default_factory=list)
    multi_ai_findings: list[str] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)
    recommended_fix_strategy: str = ""
    files_likely_involved: list[str] = Field(default_factory=list)
    commands_to_verify: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    human_decision_required: bool = True
    codex_handoff_prompt: str = ""
    max_attempts: int = 1
    do_not_do: list[str] = Field(default_factory=list)
    repair_packet_artifact_id: int | None = None
    source_failure_type: str
    source_artifact_ids: list[int] = Field(default_factory=list)
    source_agent_run_ids: list[int] = Field(default_factory=list)
    source_dispatch_batch_id: int | None = None
    source_dispatch_job_ids: list[int] = Field(default_factory=list)
    analysis_dispatch_batch_id: int | None = None
    analysis_status: str = ""
    read_only: bool = False
    persisted: bool = True
    safety_notes: list[str] = Field(default_factory=list)

from pydantic import BaseModel, Field


class AnswerSynthesisPreviewRequest(BaseModel):
    task_id: int
    dispatch_batch_id: int | None = None
    include_artifacts: bool = True
    max_artifact_chars: int = Field(default=2000, ge=0, le=20000)


class ArtifactSummary(BaseModel):
    artifact_id: int
    filename: str | None = None
    artifact_type: str
    summary: str = ""
    is_truncated: bool = False


class AnswerSynthesisPreviewResponse(BaseModel):
    task_id: int
    dispatch_batch_id: int | None = None
    synthesis_status: str
    job_count: int = 0
    succeeded_jobs: int = 0
    failed_jobs: int = 0
    blocked_jobs: int = 0
    common_findings: list[str] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    next_questions: list[str] = Field(default_factory=list)
    artifact_summaries: list[ArtifactSummary] = Field(default_factory=list)
    source_job_ids: list[int] = Field(default_factory=list)
    source_agent_run_ids: list[int] = Field(default_factory=list)
    source_artifact_ids: list[int] = Field(default_factory=list)
    confidence: float = 0.0
    safety_notes: list[str] = Field(default_factory=list)
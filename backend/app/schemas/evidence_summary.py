from pydantic import BaseModel, Field


class EvidenceLinkedIds(BaseModel):
    agent_run_id: int | None = None
    artifact_id: int | None = None
    dispatch_batch_id: int | None = None
    dispatch_job_id: int | None = None
    repair_attempt_id: int | None = None


class TimelineItem(BaseModel):
    time: str
    type: str
    title: str
    status: str
    source: str
    linked_ids: EvidenceLinkedIds = Field(default_factory=EvidenceLinkedIds)
    summary: str = ""
    safety_flags: list[str] = Field(default_factory=list)


class TimelineResponse(BaseModel):
    task_id: int
    project_id: int
    items: list[TimelineItem] = Field(default_factory=list)
    read_only: bool = True
    persisted: bool = False


class EvidenceRedactionStatus(BaseModel):
    redaction_applied: bool = True
    truncated: bool = False
    max_chars: int = 2000


class EvidenceBoardFilters(BaseModel):
    evidence_type: list[str] = Field(default_factory=list)
    source: list[str] = Field(default_factory=list)
    status: list[str] = Field(default_factory=list)
    provider: list[str] = Field(default_factory=list)
    role: list[str] = Field(default_factory=list)


class EvidenceBoardItem(BaseModel):
    evidence_type: str
    source: str
    status: str
    provider: str = ""
    role: str = ""
    artifact_id: int | None = None
    agent_run_id: int | None = None
    dispatch_batch_id: int | None = None
    dispatch_job_id: int | None = None
    repair_attempt_id: int | None = None
    summary: str = ""
    raw_excerpt: str = ""
    safety_notes: list[str] = Field(default_factory=list)
    redaction_status: EvidenceRedactionStatus = Field(default_factory=EvidenceRedactionStatus)


class EvidenceBoardResponse(BaseModel):
    task_id: int
    project_id: int
    filters: EvidenceBoardFilters
    items: list[EvidenceBoardItem] = Field(default_factory=list)
    read_only: bool = True
    persisted: bool = False

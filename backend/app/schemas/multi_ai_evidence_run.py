from pydantic import BaseModel, Field


EVIDENCE_RUN_MODES = {"broadcast", "routed"}
EVIDENCE_PROMPT_SOURCES = {"task_goal", "handoff_packet", "answer_synthesis", "custom_prompt"}


class MultiAiEvidenceRoleRequest(BaseModel):
    role: str
    provider: str = "custom"
    prompt: str = ""


class MultiAiEvidenceRunRequest(BaseModel):
    task_id: int
    mode: str = "broadcast"
    providers: list[str] = Field(default_factory=list)
    roles: list[MultiAiEvidenceRoleRequest] = Field(default_factory=list)
    prompt_source: str = "task_goal"
    custom_prompt: str = ""
    concurrency_limit: int = Field(default=2, ge=1, le=8)
    timeout_seconds: int | None = None
    target_url: str = ""
    input_selector: str = ""
    send_selector: str = ""
    response_selector: str = ""
    scroll_container_selector: str = ""
    copy_button_selector: str = ""
    login_hint_selector: str = ""


class MultiAiEvidenceSafetyGate(BaseModel):
    mode_valid: bool = False
    prompt_source_valid: bool = False
    providers_known: bool = False
    providers_allowed: bool = False
    job_count_ok: bool = False
    browser_ai_enabled: bool = False
    gate_passed: bool = False
    blocked_reasons: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)


class MultiAiEvidenceJobResponse(BaseModel):
    dispatch_job_id: int | None = None
    sequence_no: int
    provider: str
    role: str = "general"
    status: str = "preview"
    prompt_source: str = "task_goal"
    prompt_hash: str = ""
    question: str = ""
    error_message: str | None = None
    agent_run_id: int | None = None
    artifact_id: int | None = None
    artifact_ids: list[int] = Field(default_factory=list)
    answer_preview: str = ""


class MultiAiEvidenceRunResponse(BaseModel):
    evidence_run_id: int | None = None
    dispatch_batch_id: int | None = None
    task_id: int
    mode: str
    prompt_source: str = "task_goal"
    providers: list[str] = Field(default_factory=list)
    jobs: list[MultiAiEvidenceJobResponse] = Field(default_factory=list)
    estimated_job_count: int = 0
    concurrency_limit: int = 2
    concurrency_note: str = "bounded concurrency is planned; current MVP executes jobs sequentially"
    overall_status: str = "preview"
    safety_gate: MultiAiEvidenceSafetyGate
    read_only: bool = False
    persisted: bool = False
    synthesis_refreshed: bool = False
    synthesis_status: str = ""
    source_artifact_ids: list[int] = Field(default_factory=list)
    error_message: str = ""

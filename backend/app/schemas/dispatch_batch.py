from pydantic import BaseModel, Field


VALID_BATCH_MODES = {"broadcast", "routed", "pipeline"}


class DispatchJobRequest(BaseModel):
    question: str
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    mode: str = "review"
    module_name: str = ""
    task_type: str = ""


class DispatchBatchRequest(BaseModel):
    task_id: int
    task_goal: str = ""
    batch_mode: str = "routed"
    jobs: list[DispatchJobRequest] = Field(default_factory=list)


class DispatchJobPreview(BaseModel):
    dispatch_job_id: int | None = None
    sequence_no: int = 1
    question: str
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    mode: str = "review"
    status: str = "preview"
    prompt_hash: str = ""
    context_packet_hash: str = ""
    expected_artifact_type: str = ""
    safety_boundary: dict = Field(default_factory=dict)
    agent_run_id: int | None = None
    artifact_ids: list[int] = Field(default_factory=list)
    error_message: str | None = None


class DispatchBatchPreviewResponse(BaseModel):
    dispatch_batch_id: int | None = None
    task_id: int
    batch_mode: str
    status: str = "preview"
    task_goal: str = ""
    jobs: list[DispatchJobPreview] = Field(default_factory=list)
    would_execute: bool = False


class DispatchBatchResponse(BaseModel):
    dispatch_batch_id: int
    task_id: int
    batch_mode: str
    status: str
    task_goal: str = ""
    jobs: list[DispatchJobPreview] = Field(default_factory=list)
    summary: dict = Field(default_factory=dict)

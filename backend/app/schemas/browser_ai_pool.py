from typing import Any

from pydantic import BaseModel, Field


class BrowserAiPoolProviderRequest(BaseModel):
    provider: str = "custom"
    role: str = "reviewer"
    display_name: str = ""
    target_url: str = ""
    prompt_selector: str = ""
    submit_selector: str = ""
    response_selector: str = ""
    scroll_container_selector: str = ""
    copy_button_selector: str = ""
    login_hint_selector: str = ""
    stable_response_timeout_seconds: int | None = Field(default=120, ge=1, le=600)
    stable_polls: int = Field(default=3, ge=1, le=50)
    stable_interval_ms: int = Field(default=1000, ge=100, le=10000)
    enabled: bool = True


class BrowserAiPoolRequest(BaseModel):
    prompt: str = ""
    providers: list[BrowserAiPoolProviderRequest] = Field(default_factory=list)
    max_total_concurrency: int = Field(default=1, ge=1, le=6)
    per_provider_concurrency: int = Field(default=1, ge=1, le=3)
    save_artifacts: bool = True
    artifact_prefix: str = "browser_ai_pool_answer"
    include_task_context: bool = True
    include_project_memory: bool = True
    include_evidence_board: bool = True
    prompt_budget: int = Field(default=12000, ge=1000, le=30000)


class BrowserAiPoolRedactionStatus(BaseModel):
    redaction_applied: bool = True
    truncated: bool = False
    max_chars: int = 4000


class BrowserAiPoolJobPreview(BaseModel):
    provider: str
    role: str
    display_name: str = ""
    enabled: bool = True
    status: str = "ready"
    prompt_hash: str = ""
    prompt_excerpt: str = ""
    target_url: str = ""
    prompt_selector: str = ""
    submit_selector: str = ""
    response_selector: str = ""
    stable_response_timeout_seconds: int | None = None
    stable_polls: int = 3
    stable_interval_ms: int = 1000
    safety_notes: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)


class BrowserAiPoolPreviewResponse(BaseModel):
    task_id: int
    project_id: int
    overall_status: str
    jobs: list[BrowserAiPoolJobPreview] = Field(default_factory=list)
    max_total_concurrency: int = 1
    per_provider_concurrency: int = 1
    read_only: bool = True
    persisted: bool = False
    advisory_only: bool = True
    human_confirmation_required: bool = True
    no_auto_merge: bool = True
    safety_notes: list[str] = Field(default_factory=list)


class BrowserAiPoolJobResult(BaseModel):
    provider: str
    role: str
    display_name: str = ""
    status: str
    agent_run_id: int | None = None
    artifact_id: int | None = None
    answer_excerpt: str = ""
    failure_reason: str = ""
    manual_login_required: bool = False
    redaction_status: BrowserAiPoolRedactionStatus = Field(default_factory=BrowserAiPoolRedactionStatus)
    safety_notes: list[str] = Field(default_factory=list)


class BrowserAiPoolExecuteResponse(BaseModel):
    task_id: int
    project_id: int
    pool_run_id: int | None = None
    overall_status: str
    jobs: list[BrowserAiPoolJobResult] = Field(default_factory=list)
    read_only: bool = False
    persisted: bool = True
    advisory_only: bool = True
    human_confirmation_required: bool = True
    no_auto_merge: bool = True
    safety_notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

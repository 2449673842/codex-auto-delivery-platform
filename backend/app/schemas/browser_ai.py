from pydantic import BaseModel, Field


class BrowserAiSafetyGate(BaseModel):
    browser_ai_enabled: bool = False
    provider_allowed: bool = False
    provider_valid: bool = False
    selectors_present: bool = False
    target_url_present: bool = False
    timeout_ok: bool = False
    gate_passed: bool = False
    blocked_reasons: list[str] = Field(default_factory=list)


class BrowserAiRequest(BaseModel):
    project_id: int
    task_id: int
    provider: str = "custom"
    target_url: str = ""
    prompt_source: str = "task_goal"
    custom_prompt: str = ""
    input_selector: str = ""
    send_selector: str = ""
    response_selector: str = ""
    timeout_seconds: int | None = None


class BrowserAiResponse(BaseModel):
    status: str
    provider: str = "custom"
    prompt_hash: str = ""
    answer_preview: str = ""
    agent_run_id: int | None = None
    artifact_id: int | None = None
    error_message: str | None = None
    safety_gate: BrowserAiSafetyGate
    browser_opened: bool = False
    persisted: bool = False

from pydantic import BaseModel, Field


class AiDispatchRequest(BaseModel):
    task_goal: str = ""
    module_name: str = ""
    task_type: str = ""
    mode: str = "planning"
    task_id: int | None = None
    project_id: int = 1


class SafetyGateInfo(BaseModel):
    execution_enabled: bool = False
    openai_key_present: bool = False
    provider_allowed: bool = False
    mode_valid: bool = False
    budget_ok: bool = True
    gate_passed: bool = False


class AiDispatchDryRunResponse(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    mode: str = ""
    prompt_hash: str = ""
    context_packet_hash: str = ""
    estimated_tokens: int = 0
    safety_gate: SafetyGateInfo
    would_dispatch: bool = False


class AiExecuteStep(BaseModel):
    step: str
    status: str
    details: str | None = None


class AiDispatchExecuteResponse(BaseModel):
    agent_run_id: int = 0
    task_id: int | None = None
    status: str = ""
    output_summary: str | None = None
    output_diff: str | None = None
    artifacts: list[dict] = Field(default_factory=list)
    events: list[dict] = Field(default_factory=list)
    sandbox_applied: bool = False
    sandbox_gate_passed: bool = False
    sandbox_gate_blocked_reasons: list[str] = Field(default_factory=list)
    prompt_hash: str = ""
    context_packet_hash: str = ""
    token_usage: dict = Field(default_factory=dict)
    steps: list[AiExecuteStep] = Field(default_factory=list)

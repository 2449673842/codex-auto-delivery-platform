from pydantic import BaseModel, Field


class OrchestrationStatusResponse(BaseModel):
    task_id: int
    task_status: str
    next_action: str | None
    can_auto_continue: bool
    blocked_reasons: list[str] = Field(default_factory=list)
    latest_agent_run_id: int | None
    latest_agent_review_id: int | None
    latest_approval_decision_id: int | None


class OrchestrationStepResponse(BaseModel):
    task_id: int
    before_status: str
    after_status: str
    action_taken: str | None
    events_created: list[str] = Field(default_factory=list)
    stopped: bool
    stop_reason: str | None = None


class OrchestrationRunRequest(BaseModel):
    max_steps: int = Field(default=10, ge=1, le=50)
    actor: str | None = "system"


class OrchestrationRunResponse(BaseModel):
    task_id: int
    steps_executed: int
    final_status: str
    stopped: bool
    stop_reason: str | None = None
    actions: list[str] = Field(default_factory=list)

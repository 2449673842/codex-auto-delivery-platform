from pydantic import BaseModel, Field


class SandboxGateBlockedReason(BaseModel):
    reason: str
    detail: str | None = None


class SandboxGateDecision(BaseModel):
    passed: bool
    blocked_reasons: list[SandboxGateBlockedReason] = Field(default_factory=list)
    can_prepare_pr: bool = False
    message: str = "Sandbox gate evaluation complete"

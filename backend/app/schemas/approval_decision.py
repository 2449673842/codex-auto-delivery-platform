from datetime import datetime
from pydantic import BaseModel, Field


class ApprovalEvaluationRequest(BaseModel):
    agent_run_id: int | None = None
    agent_review_id: int | None = None
    policy_id: int | None = None
    tests_passed: bool | None = None
    sonar_passed: bool | None = None
    security_issues_found: bool | None = None
    changed_files: str | None = None
    diff_summary: str | None = None
    actor: str | None = None
    message: str | None = None


class AutoApproveRequest(BaseModel):
    approval_decision_id: int
    actor: str | None = None
    message: str | None = None


class ApprovalEvaluationResponse(BaseModel):
    id: int
    task_id: int
    risk_level: str
    risk_reasons: list[str] = []
    auto_approve_allowed: bool
    human_required: bool
    decision_reason: str | None
    blocked_reasons: list[str] = []
    tests_passed: bool | None
    security_issues_found: bool | None

    model_config = {"from_attributes": True}


class ApprovalDecisionResponse(BaseModel):
    id: int
    task_id: int
    agent_run_id: int | None
    agent_review_id: int | None
    policy_id: int | None
    risk_level: str
    auto_approve_allowed: bool
    human_required: bool
    decision_reason: str | None
    blocked_reasons_json: str | None
    policy_snapshot_json: str | None
    created_at: datetime

    model_config = {"from_attributes": True}

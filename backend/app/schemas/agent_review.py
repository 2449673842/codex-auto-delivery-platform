from datetime import datetime
from pydantic import BaseModel, Field


class AgentReviewCreate(BaseModel):
    reviewer_agent_id: int
    decision: str = Field(..., pattern=r'^(approved|changes_requested|rejected|human_required)$')
    risk_level: str = "low"
    comments: str | None = None
    issues_json: str | None = None
    confidence_score: float | None = Field(None, ge=0.0, le=1.0)


class AgentReviewResponse(BaseModel):
    id: int
    task_id: int
    agent_run_id: int
    reviewer_agent_id: int
    decision: str
    risk_level: str
    comments: str | None
    issues_json: str | None
    confidence_score: float | None
    created_at: datetime

    model_config = {"from_attributes": True}

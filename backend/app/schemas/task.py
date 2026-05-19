from datetime import datetime

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    project_id: int
    title: str = Field(..., min_length=1, max_length=256)
    description: str | None = None
    priority: str = "medium"
    source: str = "manual"
    planner: str | None = None
    executor: str | None = None
    reviewer: str | None = None
    human_approver: str | None = None
    target_branch: str | None = None


class TaskStatusTransition(BaseModel):
    actor: str | None = None
    message: str | None = None


class TaskResponse(BaseModel):
    id: int
    project_id: int
    title: str
    description: str | None
    status: str
    priority: str
    source: str
    planner: str | None
    executor: str | None
    reviewer: str | None
    human_approver: str | None
    ticket_content: str | None
    result_summary: str | None
    pr_url: str | None
    ci_url: str | None
    deploy_url: str | None
    target_branch: str | None
    created_at: datetime
    updated_at: datetime
    project_name: str = ""

    model_config = {"from_attributes": True}

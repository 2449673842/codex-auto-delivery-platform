from datetime import datetime

from pydantic import BaseModel, Field


class ReviewCreate(BaseModel):
    reviewer: str | None = None
    decision: str = Field(..., pattern=r"^(approved|rejected|changes_requested)$")
    comments: str | None = None
    issues: str | None = None
    linter_passed: bool | None = None


class ReviewResponse(BaseModel):
    id: int
    task_id: int
    reviewer: str | None
    decision: str
    comments: str | None
    issues: str | None
    linter_passed: bool | None
    sonar_passed: bool | None
    ci_passed: bool | None
    created_at: datetime

    model_config = {"from_attributes": True}

from datetime import datetime
from pydantic import BaseModel, Field


class AgentRunCreate(BaseModel):
    agent_id: int
    run_type: str = Field(..., pattern=r'^(plan|execute|review|test|remediate)$')
    input_prompt: str | None = None
    branch: str | None = None
    commit_sha: str | None = None
    attempt_no: int = 1


class AgentRunUpdate(BaseModel):
    status: str | None = None
    output_summary: str | None = None
    output_diff: str | None = None
    output_log: str | None = None
    branch: str | None = None
    commit_sha: str | None = None
    pr_url: str | None = None
    risk_level: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    error_message: str | None = None
    raw_result_json: str | None = None


class SubmitResultRequest(BaseModel):
    status: str = Field(..., pattern=r'^(succeeded|failed)$')
    output_summary: str | None = None
    output_diff: str | None = None
    output_log: str | None = None
    raw_result_json: str | None = None
    duration_ms: int | None = None
    error_message: str | None = None


class AgentRunResponse(BaseModel):
    id: int
    task_id: int
    project_id: int
    agent_id: int
    run_type: str
    status: str
    input_prompt: str | None
    output_summary: str | None
    output_diff: str | None
    output_log: str | None
    branch: str | None
    commit_sha: str | None
    pr_url: str | None
    risk_level: str
    attempt_no: int
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    error_message: str | None
    raw_result_json: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

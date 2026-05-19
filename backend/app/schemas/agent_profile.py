from datetime import datetime
from pydantic import BaseModel, Field


class AgentProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    agent_type: str = Field(..., pattern=r'^(planner|executor|reviewer|test)$')
    provider: str = Field(..., pattern=r'^(codex|openai|claude|local|manual)$')
    model_name: str | None = None
    secret_ref: str | None = None
    enabled: bool = True
    max_runtime_seconds: int = 300
    max_attempts: int = 3
    allowed_projects: str | None = None


class AgentProfileUpdate(BaseModel):
    name: str | None = None
    agent_type: str | None = Field(None, pattern=r'^(planner|executor|reviewer|test)$')
    provider: str | None = Field(None, pattern=r'^(codex|openai|claude|local|manual)$')
    model_name: str | None = None
    secret_ref: str | None = None
    enabled: bool | None = None
    max_runtime_seconds: int | None = None
    max_attempts: int | None = None
    allowed_projects: str | None = None


class AgentProfileResponse(BaseModel):
    id: int
    name: str
    agent_type: str
    provider: str
    model_name: str | None
    secret_ref: str | None
    enabled: bool
    max_runtime_seconds: int
    max_attempts: int
    allowed_projects: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

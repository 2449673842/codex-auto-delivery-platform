from typing import Any

from pydantic import BaseModel, Field


class AiHandoffPreviewRequest(BaseModel):
    project_id: int
    task_id: int | None = None
    include_recent_batches: bool = True
    include_answer_synthesis: bool = True
    include_safety_rules: bool = True
    max_chars: int = Field(default=12000, ge=1000, le=30000)


class AiHandoffSourceIds(BaseModel):
    project_id: int
    task_id: int | None = None
    dispatch_batch_ids: list[int] = Field(default_factory=list)
    dispatch_job_ids: list[int] = Field(default_factory=list)
    agent_run_ids: list[int] = Field(default_factory=list)
    artifact_ids: list[int] = Field(default_factory=list)


class AiHandoffPreviewResponse(BaseModel):
    project_id: int
    task_id: int | None = None
    handoff_status: str
    project_snapshot: dict[str, Any] = Field(default_factory=dict)
    current_task_summary: dict[str, Any] = Field(default_factory=dict)
    recent_capabilities: list[str] = Field(default_factory=list)
    current_master_commit_hint: str
    current_pr_summary: dict[str, Any] = Field(default_factory=dict)
    recent_dispatch_summary: dict[str, Any] = Field(default_factory=dict)
    answer_synthesis_summary: dict[str, Any] = Field(default_factory=dict)
    safety_rules: list[str] = Field(default_factory=list)
    next_recommended_steps: list[str] = Field(default_factory=list)
    next_ai_prompt: str
    source_ids: AiHandoffSourceIds
    redaction_applied: bool = True
    safety_notes: list[str] = Field(default_factory=list)

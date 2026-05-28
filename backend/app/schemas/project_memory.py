from typing import Any

from pydantic import BaseModel, Field


class ProjectMemorySourceRef(BaseModel):
    source_type: str
    path: str | None = None
    section: str | None = None
    pr_number: int | None = None
    note: str | None = None


class ProjectMemoryRedactionStatus(BaseModel):
    redaction_applied: bool = True
    truncated: bool = False
    max_chars: int = 4000


class ProjectMemoryItem(BaseModel):
    memory_id: str
    project_id: int
    memory_type: str
    title: str
    summary: str
    content: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[ProjectMemorySourceRef] = Field(default_factory=list)
    confidence: str
    stale: bool = False
    updated_at: str
    redaction_status: ProjectMemoryRedactionStatus = Field(default_factory=ProjectMemoryRedactionStatus)


class ProjectMemoryFilters(BaseModel):
    memory_type: list[str] = Field(default_factory=list)
    confidence: list[str] = Field(default_factory=list)
    stale: list[bool] = Field(default_factory=list)


class ProjectMemoryResponse(BaseModel):
    project_id: int
    items: list[ProjectMemoryItem] = Field(default_factory=list)
    filters: ProjectMemoryFilters
    read_only: bool = True
    persisted: bool = False
    safety_notes: list[str] = Field(default_factory=list)


class ProjectMemorySummaryResponse(BaseModel):
    project_id: int
    summary: str
    memory_count: int
    memory_types: list[str] = Field(default_factory=list)
    stale_count: int = 0
    high_confidence_count: int = 0
    read_only: bool = True
    persisted: bool = False
    safety_notes: list[str] = Field(default_factory=list)

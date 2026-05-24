from typing import Any

from pydantic import BaseModel, Field


class McpToolDescriptor(BaseModel):
    name: str
    description: str
    read_only: bool = True
    dry_run_only: bool = False
    safety_notes: list[str] = Field(default_factory=list)


class McpCallRequest(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class McpCallResponse(BaseModel):
    tool: str
    status: str
    data: dict[str, Any] = Field(default_factory=dict)
    error_message: str = ""
    read_only: bool = True
    persisted: bool = False
    safety_notes: list[str] = Field(default_factory=list)

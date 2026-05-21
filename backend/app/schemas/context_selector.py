from pydantic import BaseModel, Field


class ContextSelectorRequest(BaseModel):
    task_goal: str = ""
    module_name: str = ""
    task_type: str = ""


class ContextSelectorMatch(BaseModel):
    name: str = ""
    type: str = ""
    description: str = ""
    files: dict = Field(default_factory=dict)
    api: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)


class ContextSelectorResponse(BaseModel):
    matched_modules: list[ContextSelectorMatch] = Field(default_factory=list)
    recommended_files: list[str] = Field(default_factory=list)
    recommended_tests: list[str] = Field(default_factory=list)
    recommended_api: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    task_hints_used: list[str] = Field(default_factory=list)
    confidence: str = "low"
    warnings: list[str] = Field(default_factory=list)

from pydantic import BaseModel, Field


class CodeContextFile(BaseModel):
    path: str
    content: str
    language: str | None = None


class CodeContextBundle(BaseModel):
    files: list[CodeContextFile] = Field(default_factory=list)


class CodeContextCreateRequest(BaseModel):
    files: list[CodeContextFile] = Field(default_factory=list, min_length=1)


class CodeContextResponse(BaseModel):
    files: list[CodeContextFile] = Field(default_factory=list)
    artifact_id: int | None = None
    task_id: int
    file_count: int = 0
    total_size_bytes: int = 0

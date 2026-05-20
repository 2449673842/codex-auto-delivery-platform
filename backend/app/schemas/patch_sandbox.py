from pydantic import BaseModel, Field


class ChangedFileEntry(BaseModel):
    path: str
    status: str
    additions: int = 0
    deletions: int = 0
    before_sha256: str | None = None
    after_sha256: str | None = None


class PatchApplyReport(BaseModel):
    applied: bool
    changed_files: list[ChangedFileEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class PatchApplyResult(BaseModel):
    success: bool
    report: PatchApplyReport
    message: str
    before_after_previews: dict[str, dict[str, str]] = Field(default_factory=dict)

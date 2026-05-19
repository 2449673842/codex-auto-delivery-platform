from datetime import datetime

from pydantic import BaseModel, Field


class ArtifactCreate(BaseModel):
    artifact_type: str = Field(..., pattern=r"^(execution_log|diff|review_note|ci_log|screenshot)$")
    content: str | None = None
    filename: str | None = None
    metadata_json: str | None = None


class ArtifactResponse(BaseModel):
    id: int
    task_id: int
    artifact_type: str
    storage_type: str
    content: str | None
    file_path: str | None
    filename: str | None
    size_bytes: int | None
    sha256: str | None
    is_truncated: bool
    metadata_json: str | None
    created_at: datetime

    model_config = {"from_attributes": True}

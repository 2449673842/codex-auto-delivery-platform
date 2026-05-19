from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.artifact import ArtifactCreate, ArtifactResponse
from app.schemas.common import ApiEnvelope
from app.services import artifact_service

router = APIRouter(tags=["artifacts"])


@router.post("/api/tasks/{task_id}/artifacts", status_code=201)
async def upload_artifact(
    task_id: int, body: ArtifactCreate, db: AsyncSession = Depends(get_session)
):
    artifact = await artifact_service.upload_artifact(db, task_id, body)
    return ApiEnvelope(
        data=ArtifactResponse.model_validate(artifact, from_attributes=True)
    )


@router.get("/api/tasks/{task_id}/artifacts")
async def list_artifacts(
    task_id: int, db: AsyncSession = Depends(get_session)
):
    artifacts = await artifact_service.list_artifacts(db, task_id)
    return ApiEnvelope(
        data=[
            ArtifactResponse.model_validate(a, from_attributes=True)
            for a in artifacts
        ]
    )


@router.get("/api/tasks/{task_id}/artifacts/{artifact_id}")
async def get_artifact(
    task_id: int, artifact_id: int, db: AsyncSession = Depends(get_session)
):
    artifact = await artifact_service.get_artifact(db, artifact_id)
    return ApiEnvelope(
        data=ArtifactResponse.model_validate(artifact, from_attributes=True)
    )


@router.delete("/api/tasks/{task_id}/artifacts/{artifact_id}")
async def delete_artifact(
    task_id: int, artifact_id: int, db: AsyncSession = Depends(get_session)
):
    await artifact_service.delete_artifact(db, artifact_id)
    return ApiEnvelope(data=None, message="Artifact deleted")

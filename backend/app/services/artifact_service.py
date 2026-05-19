import hashlib

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.models.task_artifact import TaskArtifact
from app.schemas.artifact import ArtifactCreate
from app.services.event_service import create_event


async def upload_artifact(
    db: AsyncSession, task_id: int, data: ArtifactCreate
) -> TaskArtifact:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status == "archived":
        raise HTTPException(
            status_code=409, detail="Cannot upload artifact to archived task"
        )

    content = data.content or ""
    sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
    size_bytes = len(content.encode("utf-8"))

    artifact = TaskArtifact(
        task_id=task_id,
        artifact_type=data.artifact_type,
        content=content,
        filename=data.filename,
        size_bytes=size_bytes,
        sha256=sha256,
        metadata_json=data.metadata_json,
    )
    db.add(artifact)
    await db.flush()
    await db.refresh(artifact)

    await create_event(
        db,
        task_id=task_id,
        event_type="artifact_uploaded",
        actor=None,
        message=f"Artifact uploaded: {data.artifact_type} ({size_bytes} bytes)",
    )
    return artifact


async def list_artifacts(
    db: AsyncSession, task_id: int
) -> list[TaskArtifact]:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    result = await db.execute(
        select(TaskArtifact)
        .where(TaskArtifact.task_id == task_id)
        .order_by(TaskArtifact.created_at.desc())
    )
    return list(result.scalars().all())


async def get_artifact(db: AsyncSession, artifact_id: int) -> TaskArtifact:
    artifact = await db.get(TaskArtifact, artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return artifact


async def delete_artifact(db: AsyncSession, artifact_id: int) -> None:
    artifact = await get_artifact(db, artifact_id)
    await db.delete(artifact)
    await db.flush()

"""Code Context Service — safely provides file content to AI providers.

This service:
- Stores code context as TaskArtifacts
- Only uses API-provided file content, never reads local paths
- No shell execution or OS commands
- No git operations
- No secret material access
"""

import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.models.task_artifact import TaskArtifact
from app.schemas.code_context import CodeContextCreateRequest, CodeContextResponse, CodeContextFile
from app.services.event_service import create_event


async def set_code_context(
    db: AsyncSession, task_id: int, data: CodeContextCreateRequest
) -> CodeContextResponse:
    """Store code context for a task as TaskArtifacts.

    Creates a single bundle artifact (code_context_bundle) containing all files.
    Does NOT access local paths or file system.
    """
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status == "archived":
        raise HTTPException(
            status_code=409, detail="Cannot add code context to archived task"
        )

    bundle = {
        "files": [
            {"path": f.path, "content": f.content, "language": f.language}
            for f in data.files
        ]
    }
    content_json = json.dumps(bundle, ensure_ascii=False)
    total_size = len(content_json.encode("utf-8"))
    sha256 = hashlib.sha256(content_json.encode("utf-8")).hexdigest()

    artifact = TaskArtifact(
        task_id=task_id,
        artifact_type="code_context_bundle",
        content=content_json,
        filename=f"code_context_bundle_{task_id}.json",
        size_bytes=total_size,
        sha256=sha256,
        metadata_json=json.dumps({"file_count": len(data.files), "total_size_bytes": total_size}),
    )
    db.add(artifact)
    await db.flush()
    await db.refresh(artifact)

    await create_event(
        db, task_id=task_id, event_type="artifact_uploaded",
        actor="code_context_service",
        message=f"Code context uploaded: {len(data.files)} files ({total_size} bytes)",
    )

    return CodeContextResponse(
        files=list(data.files),
        artifact_id=artifact.id,
        task_id=task_id,
        file_count=len(data.files),
        total_size_bytes=total_size,
    )


async def get_code_context(
    db: AsyncSession, task_id: int
) -> CodeContextResponse:
    """Retrieve the latest code context bundle for a task."""
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    result = await db.execute(
        select(TaskArtifact)
        .where(
            TaskArtifact.task_id == task_id,
            TaskArtifact.artifact_type == "code_context_bundle",
        )
        .order_by(TaskArtifact.id.desc())
        .limit(1)
    )
    artifact = result.scalar_one_or_none()
    if not artifact or not artifact.content:
        raise HTTPException(status_code=404, detail="No code context found for this task")

    try:
        bundle = json.loads(artifact.content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Stored code context is corrupted")

    files_raw = bundle.get("files", [])
    files = [CodeContextFile(**f) for f in files_raw]

    return CodeContextResponse(
        files=files,
        artifact_id=artifact.id,
        task_id=task_id,
        file_count=len(files),
        total_size_bytes=artifact.size_bytes or 0,
    )


async def load_code_context_dict(
    db: AsyncSession, task_id: int
) -> dict | None:
    """Load code context as a dict for AI provider use.
    
    Returns None if no code context exists. Does NOT raise on missing context.
    """
    result = await db.execute(
        select(TaskArtifact)
        .where(
            TaskArtifact.task_id == task_id,
            TaskArtifact.artifact_type == "code_context_bundle",
        )
        .order_by(TaskArtifact.id.desc())
        .limit(1)
    )
    artifact = result.scalar_one_or_none()
    if not artifact or not artifact.content:
        return None
    try:
        return json.loads(artifact.content)
    except json.JSONDecodeError:
        return None

"""Code Context API Router — provides code context for AI providers.

This router:
- POST /api/tasks/{task_id}/code-context — Upload code context files
- GET /api/tasks/{task_id}/code-context — Get latest code context
- No local file system access
- No shell execution
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.code_context import CodeContextCreateRequest
from app.schemas.common import ApiEnvelope
from app.services import code_context_service

router = APIRouter(tags=["code_context"])


@router.post("/api/tasks/{task_id}/code-context", status_code=201)
async def set_code_context(
    task_id: int, body: CodeContextCreateRequest,
    db: AsyncSession = Depends(get_session),
):
    result = await code_context_service.set_code_context(db, task_id, body)
    return ApiEnvelope(data=result.model_dump(), message="Code context stored")


@router.get("/api/tasks/{task_id}/code-context")
async def get_code_context(
    task_id: int, db: AsyncSession = Depends(get_session),
):
    result = await code_context_service.get_code_context(db, task_id)
    return ApiEnvelope(data=result.model_dump(), message="Code context retrieved")

"""Patch Sandbox API Router — applies AI-generated patches in sandbox.

This router:
- POST /api/tasks/{task_id}/agent-runs/{run_id}/sandbox/apply-patch
- GET /api/tasks/{task_id}/sandbox/patch-results
- No writes to real file system
- No repository changes or PRs
- No external API calls
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiEnvelope
from app.services import patch_apply_sandbox_service

router = APIRouter(tags=["patch_sandbox"])


@router.post("/api/tasks/{task_id}/agent-runs/{run_id}/sandbox/apply-patch")
async def apply_patch_in_sandbox(
    task_id: int, run_id: int,
    db: AsyncSession = Depends(get_session),
):
    result = await patch_apply_sandbox_service.apply_patch_in_sandbox(db, task_id, run_id)
    return ApiEnvelope(
        data=result.model_dump(),
        message=result.message,
    )


@router.get("/api/tasks/{task_id}/sandbox/patch-results")
async def get_sandbox_patch_results(
    task_id: int,
    db: AsyncSession = Depends(get_session),
):
    results = await patch_apply_sandbox_service.get_sandbox_results(db, task_id)
    return ApiEnvelope(data=results, message="Sandbox results retrieved")

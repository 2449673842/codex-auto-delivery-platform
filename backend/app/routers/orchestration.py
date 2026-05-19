from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.schemas.orchestration import (
    OrchestrationStatusResponse, OrchestrationStepResponse,
    OrchestrationRunRequest, OrchestrationRunResponse,
)
from app.schemas.common import ApiEnvelope
from app.services import orchestration_service

router = APIRouter(tags=["orchestration"])


@router.get("/api/tasks/{task_id}/orchestration/status")
async def get_orchestration_status(task_id: int, db: AsyncSession = Depends(get_session)):
    result = await orchestration_service.get_orchestration_status(db, task_id)
    return ApiEnvelope(data=result.model_dump())


@router.post("/api/tasks/{task_id}/orchestration/step")
async def orchestration_step(task_id: int, db: AsyncSession = Depends(get_session)):
    result = await orchestration_service.orchestration_step(db, task_id)
    return ApiEnvelope(data=result.model_dump())


@router.post("/api/tasks/{task_id}/orchestration/run")
async def orchestration_run(
    task_id: int, body: OrchestrationRunRequest, db: AsyncSession = Depends(get_session)
):
    result = await orchestration_service.orchestration_run(db, task_id, body.max_steps, body.actor)
    return ApiEnvelope(data=result.model_dump())

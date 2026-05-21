from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.ai_dispatch import (
    AiDispatchRequest,
    AiDispatchDryRunResponse,
    AiDispatchExecuteResponse,
)
from app.schemas.common import ApiEnvelope
from app.services import ai_dispatch_service

router = APIRouter(prefix="/api/ai-dispatch", tags=["ai_dispatch"])


@router.post("/dry-run")
async def dry_run(body: AiDispatchRequest) -> ApiEnvelope:
    result = ai_dispatch_service.dry_run(
        task_goal=body.task_goal,
        module_name=body.module_name,
        task_type=body.task_type,
        mode=body.mode,
    )
    return ApiEnvelope(data=result.model_dump())


@router.post("/execute")
async def execute(body: AiDispatchRequest, db: AsyncSession = Depends(get_session)) -> ApiEnvelope:
    result = await ai_dispatch_service.execute(
        db=db,
        task_goal=body.task_goal,
        module_name=body.module_name,
        task_type=body.task_type,
        mode=body.mode,
        task_id=body.task_id,
        project_id=body.project_id,
    )
    return ApiEnvelope(data=result.model_dump())

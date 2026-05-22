from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiEnvelope
from app.schemas.dispatch_batch import DispatchBatchRequest
from app.services import dispatch_batch_service


router = APIRouter(tags=["dispatch_batches"])


@router.post("/api/dispatch-batches/preview")
async def preview(body: DispatchBatchRequest, db: AsyncSession = Depends(get_session)) -> ApiEnvelope:
    result = await dispatch_batch_service.preview(db, body)
    return ApiEnvelope(data=result.model_dump(), message="Dispatch batch preview generated")


@router.post("/api/dispatch-batches/execute")
async def execute(body: DispatchBatchRequest, db: AsyncSession = Depends(get_session)) -> ApiEnvelope:
    result = await dispatch_batch_service.execute(db, body)
    return ApiEnvelope(data=result.model_dump(), message="Dispatch batch executed")


@router.get("/api/tasks/{task_id}/dispatch-batches")
async def list_dispatch_batches(task_id: int, db: AsyncSession = Depends(get_session)) -> ApiEnvelope:
    result = await dispatch_batch_service.list_for_task(db, task_id)
    return ApiEnvelope(data=[item.model_dump() for item in result], message="Dispatch batches retrieved")

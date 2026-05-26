from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiEnvelope
from app.services import evidence_summary_service


router = APIRouter(tags=["evidence_summary"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/api/tasks/{task_id}/timeline")
async def get_task_timeline(task_id: int, db: SessionDep) -> ApiEnvelope:
    result = await evidence_summary_service.get_timeline(db, task_id)
    return ApiEnvelope(data=result.model_dump(), message="Run Timeline listed")


@router.get("/api/tasks/{task_id}/evidence-board")
async def get_task_evidence_board(task_id: int, db: SessionDep) -> ApiEnvelope:
    result = await evidence_summary_service.get_evidence_board(db, task_id)
    return ApiEnvelope(data=result.model_dump(), message="Evidence Board listed")

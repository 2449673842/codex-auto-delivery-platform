from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiEnvelope
from app.schemas.mastermind_review import MastermindReviewExecuteRequest, MastermindReviewPacketPreviewRequest
from app.services import mastermind_review_service


router = APIRouter(tags=["mastermind_review"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/api/tasks/{task_id}/mastermind-review/packet-preview")
async def preview_mastermind_review_packet(
    task_id: int,
    body: MastermindReviewPacketPreviewRequest,
    db: SessionDep,
) -> ApiEnvelope:
    result = await mastermind_review_service.preview_packet(db, task_id, body)
    return ApiEnvelope(data=result.model_dump(), message="Mastermind Review Packet preview generated")


@router.post("/api/tasks/{task_id}/mastermind-review/execute")
async def execute_mastermind_review(
    task_id: int,
    body: MastermindReviewExecuteRequest,
    db: SessionDep,
) -> ApiEnvelope:
    result = await mastermind_review_service.execute_review(db, task_id, body)
    return ApiEnvelope(data=result.model_dump(), message="Mastermind Review execute trial finished")

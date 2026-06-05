from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.autopilot_lite import AutoPilotLitePreviewRequest
from app.schemas.common import ApiEnvelope
from app.services import autopilot_lite_service


router = APIRouter(tags=["autopilot_lite"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/api/tasks/{task_id}/autopilot-lite/preview")
async def preview_autopilot_lite(
    task_id: int,
    body: AutoPilotLitePreviewRequest,
    db: SessionDep,
) -> ApiEnvelope:
    result = await autopilot_lite_service.preview(db, task_id, body)
    return ApiEnvelope(data=result.model_dump(), message="AutoPilot Lite preview generated")

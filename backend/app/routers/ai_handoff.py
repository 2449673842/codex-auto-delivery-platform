from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.ai_handoff import AiHandoffPreviewRequest
from app.schemas.common import ApiEnvelope
from app.services import ai_handoff_service


router = APIRouter(tags=["ai_handoff"])


@router.post("/api/ai-handoff/preview")
async def preview(body: AiHandoffPreviewRequest, db: Annotated[AsyncSession, Depends(get_session)]) -> ApiEnvelope:
    result = await ai_handoff_service.preview(db, body)
    return ApiEnvelope(data=result.model_dump(), message="AI handoff packet preview generated")

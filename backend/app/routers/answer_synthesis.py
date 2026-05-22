from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.answer_synthesis import AnswerSynthesisPreviewRequest
from app.schemas.common import ApiEnvelope
from app.services import answer_synthesis_service


router = APIRouter(tags=["answer_synthesis"])


@router.post("/api/answer-synthesis/preview")
async def preview(body: AnswerSynthesisPreviewRequest, db: AsyncSession = Depends(get_session)) -> ApiEnvelope:
    result = await answer_synthesis_service.preview(db, body)
    return ApiEnvelope(data=result.model_dump(), message="Answer synthesis preview generated")
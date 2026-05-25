from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiEnvelope
from app.schemas.repair_loop import FailureEvidencePreviewRequest
from app.services import repair_loop_service


router = APIRouter(tags=["repair_loop"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/api/repair-loop/failure-evidence/preview")
async def preview_failure_evidence(body: FailureEvidencePreviewRequest, db: SessionDep) -> ApiEnvelope:
    result = await repair_loop_service.preview(db, body)
    return ApiEnvelope(data=result.model_dump(), message="Failure Evidence Packet preview generated")

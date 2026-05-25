from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiEnvelope
from app.schemas.multi_ai_evidence_run import MultiAiEvidenceRunRequest
from app.services import multi_ai_evidence_run_service


router = APIRouter(tags=["multi_ai_evidence_runs"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/api/multi-ai-evidence-runs/preview")
async def preview(body: MultiAiEvidenceRunRequest, db: SessionDep) -> ApiEnvelope:
    result = await multi_ai_evidence_run_service.preview(db, body)
    return ApiEnvelope(data=result.model_dump(), message="Multi-AI Evidence Run preview generated")


@router.post("/api/multi-ai-evidence-runs/execute")
async def execute(body: MultiAiEvidenceRunRequest, db: SessionDep) -> ApiEnvelope:
    result = await multi_ai_evidence_run_service.execute(db, body)
    return ApiEnvelope(data=result.model_dump(), message="Multi-AI Evidence Run executed")


@router.get("/api/tasks/{task_id}/multi-ai-evidence-runs")
async def list_multi_ai_evidence_runs(task_id: int, db: SessionDep) -> ApiEnvelope:
    result = await multi_ai_evidence_run_service.list_for_task(db, task_id)
    return ApiEnvelope(
        data=[item.model_dump() for item in result],
        message="Multi-AI Evidence Runs retrieved",
    )

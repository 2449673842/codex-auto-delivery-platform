from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiEnvelope
from app.schemas.repair_loop import (
    FailureEvidencePreviewRequest,
    RepairAttemptCreateRequest,
    RepairHandoffPreviewRequest,
    RepairPacketGenerateRequest,
    RepairVerificationResultRequest,
)
from app.services import repair_loop_service


router = APIRouter(tags=["repair_loop"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/api/repair-loop/failure-evidence/preview")
async def preview_failure_evidence(body: FailureEvidencePreviewRequest, db: SessionDep) -> ApiEnvelope:
    result = await repair_loop_service.preview(db, body)
    return ApiEnvelope(data=result.model_dump(), message="Failure Evidence Packet preview generated")


@router.post("/api/repair-loop/repair-packet/generate")
async def generate_repair_packet(body: RepairPacketGenerateRequest, db: SessionDep) -> ApiEnvelope:
    result = await repair_loop_service.generate_repair_packet(db, body)
    return ApiEnvelope(data=result.model_dump(), message="Repair Packet generated")


@router.post("/api/repair-loop/codex-handoff/preview")
async def preview_repair_handoff(body: RepairHandoffPreviewRequest, db: SessionDep) -> ApiEnvelope:
    result = await repair_loop_service.preview_repair_handoff(db, body)
    return ApiEnvelope(data=result.model_dump(), message="Repair handoff preview generated")


@router.post("/api/repair-loop/attempts")
async def create_repair_attempt(body: RepairAttemptCreateRequest, db: SessionDep) -> ApiEnvelope:
    result = await repair_loop_service.create_repair_attempt(db, body)
    return ApiEnvelope(data=result.model_dump(), message="Repair attempt created")


@router.get("/api/tasks/{task_id}/repair-attempts")
async def list_repair_attempts(task_id: int, db: SessionDep) -> ApiEnvelope:
    result = await repair_loop_service.list_repair_attempts(db, task_id)
    return ApiEnvelope(data=[item.model_dump() for item in result], message="Repair attempts listed")


@router.post("/api/repair-loop/attempts/{attempt_id}/handoff-created")
async def mark_repair_handoff_created(attempt_id: int, db: SessionDep) -> ApiEnvelope:
    result = await repair_loop_service.mark_repair_handoff_created(db, attempt_id)
    return ApiEnvelope(data=result.model_dump(), message="Repair attempt handoff marked")


@router.post("/api/repair-loop/attempts/{attempt_id}/verification-result")
async def import_repair_verification_result(
    attempt_id: int,
    body: RepairVerificationResultRequest,
    db: SessionDep,
) -> ApiEnvelope:
    result = await repair_loop_service.import_repair_verification_result(db, attempt_id, body)
    return ApiEnvelope(data=result.model_dump(), message="Repair verification result imported")


@router.post("/api/repair-loop/attempts/{attempt_id}/stop")
async def stop_repair_attempt(attempt_id: int, db: SessionDep) -> ApiEnvelope:
    result = await repair_loop_service.stop_repair_attempt(db, attempt_id)
    return ApiEnvelope(data=result.model_dump(), message="Repair attempt stopped")

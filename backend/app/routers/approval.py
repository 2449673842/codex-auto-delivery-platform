from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.schemas.approval_decision import (
    ApprovalEvaluationRequest, ApprovalEvaluationResponse,
    AutoApproveRequest, ApprovalDecisionResponse,
)
from app.schemas.common import ApiEnvelope
from app.services import approval_service

router = APIRouter(tags=["approval"])


@router.post("/api/tasks/{task_id}/evaluate-approval")
async def evaluate_approval(
    task_id: int, body: ApprovalEvaluationRequest, db: AsyncSession = Depends(get_session)
):
    result = await approval_service.evaluate_approval(db, task_id, body)
    return ApiEnvelope(data=result.model_dump())


@router.post("/api/tasks/{task_id}/auto-approve")
async def auto_approve(
    task_id: int, body: AutoApproveRequest, db: AsyncSession = Depends(get_session)
):
    task = await approval_service.auto_approve(db, task_id, body.approval_decision_id, body.actor, body.message)
    return ApiEnvelope(data={"status": task.status}, message="Auto-approved")


@router.get("/api/tasks/{task_id}/approval-decisions")
async def list_approval_decisions(task_id: int, db: AsyncSession = Depends(get_session)):
    from sqlalchemy import select
    from app.models.approval_decision import ApprovalDecision
    result = await db.execute(
        select(ApprovalDecision)
        .where(ApprovalDecision.task_id == task_id)
        .order_by(ApprovalDecision.created_at.desc())
    )
    decisions = result.scalars().all()
    return ApiEnvelope(data=[ApprovalDecisionResponse.model_validate(d, from_attributes=True) for d in decisions])

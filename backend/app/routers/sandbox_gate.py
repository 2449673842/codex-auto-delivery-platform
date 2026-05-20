"""Sandbox Gate API Router — evaluates sandbox apply approval gate.

This router:
- GET /api/tasks/{task_id}/sandbox/gate — evaluate and return gate decision
- No writes to real file system
- No repository changes or PRs
- No external API calls (CI, Sonar, Deploy)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiEnvelope
from app.services import sandbox_approval_gate_service

router = APIRouter(tags=["sandbox_gate"])


@router.get("/api/tasks/{task_id}/sandbox/gate")
async def get_sandbox_gate(
    task_id: int,
    db: AsyncSession = Depends(get_session),
):
    decision = await sandbox_approval_gate_service.evaluate_sandbox_gate(db, task_id)
    return ApiEnvelope(
        data=decision.model_dump(),
        message=decision.message,
    )

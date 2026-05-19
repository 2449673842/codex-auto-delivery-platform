from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.schemas.agent_run import AgentRunCreate, AgentRunResponse, AgentRunUpdate, SubmitResultRequest
from app.schemas.common import ApiEnvelope
from app.services import agent_run_service

router = APIRouter(tags=["agent_runs"])


@router.post("/api/tasks/{task_id}/agent-runs", status_code=201)
async def create_agent_run(task_id: int, body: AgentRunCreate, db: AsyncSession = Depends(get_session)):
    run = await agent_run_service.create_agent_run(db, task_id, body)
    return ApiEnvelope(data=AgentRunResponse.model_validate(run, from_attributes=True))


@router.get("/api/tasks/{task_id}/agent-runs")
async def list_agent_runs(task_id: int, db: AsyncSession = Depends(get_session)):
    runs = await agent_run_service.list_agent_runs(db, task_id)
    return ApiEnvelope(data=[AgentRunResponse.model_validate(r, from_attributes=True) for r in runs])


@router.get("/api/tasks/{task_id}/agent-runs/{run_id}")
async def get_agent_run(task_id: int, run_id: int, db: AsyncSession = Depends(get_session)):
    run = await agent_run_service.get_agent_run(db, run_id)
    return ApiEnvelope(data=AgentRunResponse.model_validate(run, from_attributes=True))


@router.patch("/api/tasks/{task_id}/agent-runs/{run_id}")
async def update_agent_run(task_id: int, run_id: int, body: AgentRunUpdate, db: AsyncSession = Depends(get_session)):
    run = await agent_run_service.update_agent_run(db, run_id, body)
    return ApiEnvelope(data=AgentRunResponse.model_validate(run, from_attributes=True))


@router.post("/api/tasks/{task_id}/agent-runs/{run_id}/submit-result")
async def submit_agent_run_result(task_id: int, run_id: int, body: SubmitResultRequest, db: AsyncSession = Depends(get_session)):
    run = await agent_run_service.submit_agent_run_result(db, run_id, body)
    return ApiEnvelope(data=AgentRunResponse.model_validate(run, from_attributes=True))

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.schemas.agent_review import AgentReviewCreate, AgentReviewResponse
from app.schemas.common import ApiEnvelope
from app.services import agent_review_service

router = APIRouter(tags=["agent_reviews"])


@router.post("/api/tasks/{task_id}/agent-runs/{run_id}/review", status_code=201)
async def create_agent_review(task_id: int, run_id: int, body: AgentReviewCreate, db: AsyncSession = Depends(get_session)):
    review = await agent_review_service.create_agent_review(db, task_id, run_id, body)
    return ApiEnvelope(data=AgentReviewResponse.model_validate(review, from_attributes=True))


@router.get("/api/tasks/{task_id}/agent-reviews")
async def list_agent_reviews(task_id: int, db: AsyncSession = Depends(get_session)):
    reviews = await agent_review_service.list_agent_reviews(db, task_id)
    return ApiEnvelope(data=[AgentReviewResponse.model_validate(r, from_attributes=True) for r in reviews])

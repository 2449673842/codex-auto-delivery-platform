from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiEnvelope
from app.schemas.review import ReviewCreate, ReviewResponse
from app.services import review_service

router = APIRouter(tags=["reviews"])


@router.get("/api/tasks/{task_id}/reviews")
async def list_reviews(task_id: int, db: AsyncSession = Depends(get_session)):
    reviews = await review_service.list_reviews(db, task_id)
    return ApiEnvelope(
        data=[ReviewResponse.model_validate(r, from_attributes=True) for r in reviews]
    )


@router.post("/api/tasks/{task_id}/reviews", status_code=201)
async def submit_review(
    task_id: int, body: ReviewCreate, db: AsyncSession = Depends(get_session)
):
    review = await review_service.submit_review(db, task_id, body)
    return ApiEnvelope(
        data=ReviewResponse.model_validate(review, from_attributes=True)
    )

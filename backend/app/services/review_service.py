from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.models.review_record import ReviewRecord
from app.schemas.review import ReviewCreate
from app.services.event_service import create_event


async def submit_review(
    db: AsyncSession, task_id: int, data: ReviewCreate
) -> ReviewRecord:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status == "archived":
        raise HTTPException(
            status_code=409, detail="Cannot review an archived task"
        )

    review = ReviewRecord(
        task_id=task_id,
        reviewer=data.reviewer,
        decision=data.decision,
        comments=data.comments,
        issues=data.issues,
        linter_passed=data.linter_passed,
    )
    db.add(review)
    await db.flush()
    await db.refresh(review)

    await create_event(
        db,
        task_id=task_id,
        event_type="review_submitted",
        actor=data.reviewer,
        message=f"Review submitted: {data.decision}",
    )
    return review


async def list_reviews(db: AsyncSession, task_id: int) -> list[ReviewRecord]:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    result = await db.execute(
        select(ReviewRecord)
        .where(ReviewRecord.task_id == task_id)
        .order_by(ReviewRecord.created_at.desc())
    )
    return list(result.scalars().all())

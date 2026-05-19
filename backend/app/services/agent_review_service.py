from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.agent_review import AgentReview
from app.models.agent_run import AgentRun
from app.models.agent_profile import AgentProfile
from app.models.task import Task
from app.schemas.agent_review import AgentReviewCreate
from app.services.event_service import create_event


async def create_agent_review(db: AsyncSession, task_id: int, run_id: int, data: AgentReviewCreate) -> AgentReview:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    run = await db.get(AgentRun, run_id)
    if not run or run.task_id != task_id:
        raise HTTPException(status_code=404, detail="AgentRun not found")

    reviewer = await db.get(AgentProfile, data.reviewer_agent_id)
    if not reviewer:
        raise HTTPException(status_code=404, detail="Reviewer Agent not found")

    review = AgentReview(
        task_id=task_id,
        agent_run_id=run_id,
        reviewer_agent_id=data.reviewer_agent_id,
        decision=data.decision,
        risk_level=data.risk_level,
        comments=data.comments,
        issues_json=data.issues_json,
        confidence_score=data.confidence_score,
    )
    db.add(review)
    await db.flush()
    await db.refresh(review)
    await create_event(
        db, task_id=task_id, event_type="agent_review_submitted",
        actor=f"agent:{reviewer.name}",
        message=f"AgentReview #{review.id}: {data.decision} (confidence={data.confidence_score})",
    )
    return review


async def list_agent_reviews(db: AsyncSession, task_id: int) -> list[AgentReview]:
    result = await db.execute(
        select(AgentReview)
        .where(AgentReview.task_id == task_id)
        .order_by(AgentReview.created_at.desc())
    )
    return list(result.scalars().all())

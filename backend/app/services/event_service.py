from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_event import TaskEvent


async def create_event(
    db: AsyncSession,
    task_id: int,
    event_type: str,
    actor: str | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    message: str | None = None,
    payload_json: str | None = None,
) -> TaskEvent:
    event = TaskEvent(
        task_id=task_id,
        event_type=event_type,
        actor=actor,
        from_status=from_status,
        to_status=to_status,
        message=message,
        payload_json=payload_json,
    )
    db.add(event)
    await db.flush()
    await db.refresh(event)
    return event


async def list_events(db: AsyncSession, task_id: int) -> list[TaskEvent]:
    result = await db.execute(
        select(TaskEvent)
        .where(TaskEvent.task_id == task_id)
        .order_by(TaskEvent.created_at.asc())
    )
    return list(result.scalars().all())

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskStatusTransition, SubmitResultRequest
from app.services.event_service import create_event
from app.services.ticket_renderer import render_ticket
from app.enums import ALLOWED_TRANSITIONS, TaskStatus


async def list_tasks(
    db: AsyncSession,
    project_id: int | None = None,
    status: str | None = None,
    page: int = 1,
    size: int = 20,
) -> tuple[list[Task], int]:
    query = select(Task)
    count_query = select(func.count(Task.id))
    if project_id:
        query = query.where(Task.project_id == project_id)
        count_query = count_query.where(Task.project_id == project_id)
    if status:
        query = query.where(Task.status == status)
        count_query = count_query.where(Task.status == status)
    total = await db.scalar(count_query) or 0
    query = (
        query.order_by(Task.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    result = await db.execute(query)
    return list(result.scalars().all()), total


async def get_task(db: AsyncSession, task_id: int) -> Task:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


async def create_task(db: AsyncSession, data: TaskCreate) -> tuple[Task, str]:
    project = await db.get(Project, data.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project_name = project.display_name or project.name
    task = Task(**data.model_dump())
    db.add(task)
    await db.flush()
    await db.refresh(task)
    await create_event(
        db,
        task_id=task.id,
        event_type="status_changed",
        actor=data.planner,
        from_status=None,
        to_status="draft",
        message=f"Task created: {task.title}",
    )
    return task, project_name


async def delete_task(db: AsyncSession, task_id: int) -> None:
    task = await get_task(db, task_id)
    if task.status != TaskStatus.DRAFT.value:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete task in status '{task.status}', only 'draft' can be deleted",
        )
    await db.delete(task)
    await db.flush()


async def _transition(
    db: AsyncSession, task: Task, target: TaskStatus, actor: str | None, message: str | None
) -> Task:
    current = TaskStatus(task.status)
    allowed = ALLOWED_TRANSITIONS.get(current, [])
    if target not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Transition from '{current.value}' to '{target.value}' is not allowed",
        )
    task.status = target.value
    await db.flush()
    await db.refresh(task)
    await create_event(
        db,
        task_id=task.id,
        event_type="status_changed",
        actor=actor,
        from_status=current.value,
        to_status=target.value,
        message=message or f"Status changed: {current.value} -> {target.value}",
    )
    return task


async def generate_ticket(
    db: AsyncSession, task_id: int, body: TaskStatusTransition
) -> Task:
    task = await get_task(db, task_id)
    task.ticket_content = await render_ticket(db, task)
    await db.flush()
    await create_event(
        db,
        task_id=task.id,
        event_type="ticket_generated",
        actor=body.actor,
        message=body.message or "Ticket generated",
    )
    return await _transition(db, task, TaskStatus.TICKET_READY, body.actor, body.message)


async def dispatch_task(
    db: AsyncSession, task_id: int, body: TaskStatusTransition
) -> Task:
    task = await get_task(db, task_id)
    return await _transition(db, task, TaskStatus.DISPATCHED, body.actor, body.message)


async def submit_result(
    db: AsyncSession, task_id: int, body: SubmitResultRequest
) -> Task:
    task = await get_task(db, task_id)
    if body.result_summary:
        task.result_summary = body.result_summary
        await db.flush()
    return await _transition(
        db, task, TaskStatus.RESULT_SUBMITTED, body.actor, body.message
    )


async def start_review(
    db: AsyncSession, task_id: int, body: TaskStatusTransition
) -> Task:
    task = await get_task(db, task_id)
    return await _transition(db, task, TaskStatus.REVIEWING, body.actor, body.message)


async def approve_task(
    db: AsyncSession, task_id: int, body: TaskStatusTransition
) -> Task:
    task = await get_task(db, task_id)
    return await _transition(db, task, TaskStatus.APPROVED, body.actor, body.message)


async def reject_task(
    db: AsyncSession, task_id: int, body: TaskStatusTransition
) -> Task:
    task = await get_task(db, task_id)
    return await _transition(db, task, TaskStatus.REJECTED, body.actor, body.message)


async def request_changes(
    db: AsyncSession, task_id: int, body: TaskStatusTransition
) -> Task:
    task = await get_task(db, task_id)
    return await _transition(
        db, task, TaskStatus.CHANGES_REQUESTED, body.actor, body.message
    )


async def archive_task(
    db: AsyncSession, task_id: int, body: TaskStatusTransition
) -> Task:
    task = await get_task(db, task_id)
    return await _transition(db, task, TaskStatus.ARCHIVED, body.actor, body.message)


async def get_task_project_name(db: AsyncSession, task: Task) -> str | None:
    project = await db.get(Project, task.project_id)
    if project:
        return project.display_name or project.name
    return None

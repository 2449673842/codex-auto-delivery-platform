from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiEnvelope, Pagination
from app.schemas.task import TaskCreate, TaskResponse, TaskStatusTransition
from app.services import project_service, task_service

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("")
async def list_tasks(
    project_id: int | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
):
    tasks, total = await task_service.list_tasks(db, project_id, status, page, size)
    items = []
    for t in tasks:
        resp = TaskResponse.model_validate(t, from_attributes=True)
        if t.project:
            resp.project_name = t.project.display_name or t.project.name
        items.append(resp)
    return ApiEnvelope(
        data=items,
        message=Pagination(page=page, size=size, total=total).model_dump(),
    )


@router.post("", status_code=201)
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_session)):
    task = await task_service.create_task(db, body)
    resp = TaskResponse.model_validate(task, from_attributes=True)
    if task.project:
        resp.project_name = task.project.display_name or task.project.name
    return ApiEnvelope(data=resp)


@router.get("/{task_id}")
async def get_task(task_id: int, db: AsyncSession = Depends(get_session)):
    task = await task_service.get_task(db, task_id)
    resp = TaskResponse.model_validate(task, from_attributes=True)
    if task.project:
        resp.project_name = task.project.display_name or task.project.name
    return ApiEnvelope(data=resp)


@router.delete("/{task_id}")
async def delete_task(task_id: int, db: AsyncSession = Depends(get_session)):
    await task_service.delete_task(db, task_id)
    return ApiEnvelope(data=None, message="Task deleted")


# ─── 流程操作 ────────────────────────────────────────


@router.post("/{task_id}/generate-ticket")
async def generate_ticket(
    task_id: int, body: TaskStatusTransition, db: AsyncSession = Depends(get_session)
):
    task = await task_service.generate_ticket(db, task_id, body)
    return ApiEnvelope(
        data={"ticket_content": task.ticket_content},
        message="Ticket generated",
    )


@router.post("/{task_id}/dispatch")
async def dispatch_task(
    task_id: int, body: TaskStatusTransition, db: AsyncSession = Depends(get_session)
):
    task = await task_service.dispatch_task(db, task_id, body)
    return ApiEnvelope(data={"status": task.status}, message="Task dispatched")


@router.post("/{task_id}/submit-result")
async def submit_result(
    task_id: int, body: TaskStatusTransition, db: AsyncSession = Depends(get_session)
):
    task = await task_service.submit_result(db, task_id, body)
    return ApiEnvelope(data={"status": task.status}, message="Result submitted")


@router.post("/{task_id}/start-review")
async def start_review(
    task_id: int, body: TaskStatusTransition, db: AsyncSession = Depends(get_session)
):
    task = await task_service.start_review(db, task_id, body)
    return ApiEnvelope(data={"status": task.status}, message="Review started")


@router.post("/{task_id}/approve")
async def approve_task(
    task_id: int, body: TaskStatusTransition, db: AsyncSession = Depends(get_session)
):
    task = await task_service.approve_task(db, task_id, body)
    return ApiEnvelope(data={"status": task.status}, message="Task approved")


@router.post("/{task_id}/reject")
async def reject_task(
    task_id: int, body: TaskStatusTransition, db: AsyncSession = Depends(get_session)
):
    task = await task_service.reject_task(db, task_id, body)
    return ApiEnvelope(data={"status": task.status}, message="Task rejected")


@router.post("/{task_id}/request-changes")
async def request_changes(
    task_id: int, body: TaskStatusTransition, db: AsyncSession = Depends(get_session)
):
    task = await task_service.request_changes(db, task_id, body)
    return ApiEnvelope(data={"status": task.status}, message="Changes requested")


@router.post("/{task_id}/archive")
async def archive_task(
    task_id: int, body: TaskStatusTransition, db: AsyncSession = Depends(get_session)
):
    task = await task_service.archive_task(db, task_id, body)
    return ApiEnvelope(data={"status": task.status}, message="Task archived")


# ─── Stub 端点 ────────────────────────────────────────


@router.post("/{task_id}/create-pr")
async def create_pr_stub(task_id: int):
    from app.services.pr_builder import create_pr
    return await create_pr(task_id)


@router.post("/{task_id}/trigger-ci")
async def trigger_ci_stub(task_id: int):
    from app.services.ci_client import trigger_ci
    return await trigger_ci(task_id)


@router.post("/{task_id}/trigger-deploy")
async def trigger_deploy_stub(task_id: int):
    from app.services.deploy_hook import trigger_deploy
    return await trigger_deploy(task_id)

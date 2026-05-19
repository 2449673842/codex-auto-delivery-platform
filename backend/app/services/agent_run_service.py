import hashlib
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.enums import ALLOWED_AGENT_RUN_TRANSITIONS, AgentRunStatus
from app.models.agent_profile import AgentProfile
from app.models.agent_run import AgentRun
from app.models.task import Task
from app.models.task_artifact import TaskArtifact
from app.schemas.agent_run import AgentRunCreate, AgentRunUpdate, SubmitResultRequest
from app.services.event_service import create_event


async def list_agent_runs(db: AsyncSession, task_id: int) -> list[AgentRun]:
    result = await db.execute(
        select(AgentRun)
        .where(AgentRun.task_id == task_id)
        .order_by(AgentRun.created_at.desc())
    )
    return list(result.scalars().all())


async def get_agent_run(db: AsyncSession, run_id: int, task_id: int | None = None) -> AgentRun:
    run = await db.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="AgentRun not found")
    if task_id is not None and run.task_id != task_id:
        raise HTTPException(status_code=404, detail="AgentRun not found for this task")
    return run


async def create_agent_run(db: AsyncSession, task_id: int, data: AgentRunCreate) -> AgentRun:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status == "archived":
        raise HTTPException(status_code=409, detail="Cannot create AgentRun for archived task")
    agent = await db.get(AgentProfile, data.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    run = AgentRun(
        task_id=task_id,
        project_id=task.project_id,
        agent_id=data.agent_id,
        run_type=data.run_type,
        status=AgentRunStatus.QUEUED.value,
        input_prompt=data.input_prompt,
        branch=data.branch,
        commit_sha=data.commit_sha,
        attempt_no=data.attempt_no,
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)
    await create_event(
        db, task_id=task_id, event_type="agent_run_created",
        actor=f"agent:{agent.name}",
        message=f"AgentRun created: {data.run_type} (#{run.id})",
    )
    return run


async def update_agent_run(db: AsyncSession, run_id: int, data: AgentRunUpdate, task_id: int | None = None) -> AgentRun:
    run = await get_agent_run(db, run_id, task_id)
    current = AgentRunStatus(run.status)
    if data.status:
        target = AgentRunStatus(data.status)
        # PATCH only allows: queued->running, queued/running->canceled
        patch_allowed = {
            AgentRunStatus.QUEUED: [AgentRunStatus.RUNNING, AgentRunStatus.CANCELED],
            AgentRunStatus.RUNNING: [AgentRunStatus.CANCELED],
        }
        allowed = patch_allowed.get(current, [])
        if target not in allowed:
            raise HTTPException(
                status_code=409,
                detail=f"PATCH cannot transition from '{current.value}' to '{target.value}'. Use submit-result for terminal states.",
            )
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(run, key, val)
    await db.flush()
    await db.refresh(run)

    if data.status == "running":
        await create_event(
            db, task_id=run.task_id, event_type="agent_run_started",
            actor=f"agent_run:{run_id}",
        )
    elif data.status == "canceled":
        await create_event(
            db, task_id=run.task_id, event_type="agent_run_failed",
            actor=f"agent_run:{run_id}",
            message=f"AgentRun #{run_id} canceled",
        )
    return run


async def submit_agent_run_result(db: AsyncSession, run_id: int, task_id: int, data: SubmitResultRequest) -> AgentRun:
    run = await get_agent_run(db, run_id, task_id)
    current = AgentRunStatus(run.status)
    target = AgentRunStatus(data.status)
    allowed = ALLOWED_AGENT_RUN_TRANSITIONS.get(current, [])
    if target not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"AgentRun transition from '{current.value}' to '{target.value}' not allowed",
        )

    run.status = target.value
    run.output_summary = data.output_summary
    run.output_diff = data.output_diff
    run.output_log = data.output_log
    run.raw_result_json = data.raw_result_json
    run.duration_ms = data.duration_ms
    run.error_message = data.error_message
    await db.flush()

    if data.output_diff:
        sha = hashlib.sha256(data.output_diff.encode("utf-8")).hexdigest()
        artifact = TaskArtifact(
            task_id=run.task_id, artifact_type="diff",
            content=data.output_diff[:50000],
            size_bytes=len(data.output_diff.encode("utf-8")), sha256=sha,
        )
        db.add(artifact)

    if data.output_log:
        sha = hashlib.sha256(data.output_log.encode("utf-8")).hexdigest()
        artifact = TaskArtifact(
            task_id=run.task_id, artifact_type="execution_log",
            content=data.output_log[:50000],
            size_bytes=len(data.output_log.encode("utf-8")), sha256=sha,
        )
        db.add(artifact)

    await db.flush()
    await db.refresh(run)

    event_type = "agent_run_succeeded" if target == AgentRunStatus.SUCCEEDED else "agent_run_failed"
    await create_event(
        db, task_id=run.task_id, event_type=event_type,
        actor=f"agent_run:{run_id}",
        message=f"AgentRun #{run_id} {target.value}: {data.output_summary or ''}",
    )
    return run

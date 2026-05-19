from typing import Any
from fastapi import HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.models.task_artifact import TaskArtifact
from app.models.agent_run import AgentRun
from app.models.agent_review import AgentReview
from app.models.approval_decision import ApprovalDecision
from app.models.agent_profile import AgentProfile
from app.models.task_artifact import TaskArtifact
from app.schemas.task import SubmitResultRequest as TaskSubmitResultRequest
from app.schemas.orchestration import (
    OrchestrationStatusResponse, OrchestrationStepResponse, OrchestrationRunResponse,
)
from app.services import event_service, task_service, risk_assessment_service
from app.services.agent_run_service import create_agent_run, update_agent_run
from app.services.approval_service import evaluate_approval, auto_approve as do_auto_approve
from app.schemas.agent_run import AgentRunCreate, SubmitResultRequest
from app.schemas.approval_decision import ApprovalEvaluationRequest
from app.schemas.task import TaskStatusTransition
from app.enums import TaskStatus, ALLOWED_TRANSITIONS, AgentRunType, AgentRunStatus
import hashlib


async def get_orchestration_status(db: AsyncSession, task_id: int) -> OrchestrationStatusResponse:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    next_action, can_continue, blocked = await _decide_next_action(db, task)
    
    # Get latest IDs
    latest_run = (await db.execute(
        select(AgentRun).where(AgentRun.task_id == task_id).order_by(desc(AgentRun.id)).limit(1)
    )).scalar_one_or_none()
    latest_review = (await db.execute(
        select(AgentReview).where(AgentReview.task_id == task_id).order_by(desc(AgentReview.id)).limit(1)
    )).scalar_one_or_none()
    latest_decision = (await db.execute(
        select(ApprovalDecision).where(ApprovalDecision.task_id == task_id).order_by(desc(ApprovalDecision.id)).limit(1)
    )).scalar_one_or_none()

    return OrchestrationStatusResponse(
        task_id=task_id,
        task_status=task.status,
        next_action=next_action,
        can_auto_continue=can_continue,
        blocked_reasons=blocked,
        latest_agent_run_id=latest_run.id if latest_run else None,
        latest_agent_review_id=latest_review.id if latest_review else None,
        latest_approval_decision_id=latest_decision.id if latest_decision else None,
    )


async def _decide_next_action(db: AsyncSession, task: Task) -> tuple[str | None, bool, list[str]]:
    """Decide the next action based on task status (synchronous helper)."""
    blocked = []
    status = task.status

    if status == TaskStatus.ARCHIVED.value:
        return None, False, ["Task is archived"]

    if status == TaskStatus.DRAFT.value:
        return "generate_ticket", True, []

    if status == TaskStatus.TICKET_READY.value:
        return "dispatch", True, []

    if status == TaskStatus.DISPATCHED.value:
        # Check latest AgentRun status
        latest_run = (await db.execute(
            select(AgentRun).where(AgentRun.task_id == task.id).order_by(desc(AgentRun.id)).limit(1)
        )).scalar_one_or_none()
        if not latest_run:
            return "create_agent_run", True, []
        if latest_run.status in (AgentRunStatus.QUEUED.value, AgentRunStatus.RUNNING.value):
            return "wait_agent_result", False, ["AgentRun is " + latest_run.status]
        if latest_run.status == AgentRunStatus.SUCCEEDED.value:
            return "submit_result", True, []
        if latest_run.status in (AgentRunStatus.FAILED.value, AgentRunStatus.CANCELED.value):
            return "agent_failed", False, ["AgentRun is " + latest_run.status]
        return "create_agent_run", True, []

    if status == TaskStatus.RESULT_SUBMITTED.value:
        return "start_review", True, []

    if status == TaskStatus.REVIEWING.value:
        return "evaluate_approval", True, []

    if status == TaskStatus.HUMAN_REQUIRED.value:
        return None, False, ["Human approval required"]

    if status == TaskStatus.APPROVED.value:
        return None, False, ["Approved, waiting for archive"]

    if status in (TaskStatus.REJECTED.value, TaskStatus.CHANGES_REQUESTED.value):
        return None, False, [f"Task is in '{status}' state"]

    return None, False, [f"Unknown state '{status}'"]


async def orchestration_step(db: AsyncSession, task_id: int, actor: str = "system") -> OrchestrationStepResponse:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    before = task.status
    events_created = []
    action_taken = None
    stopped = False
    stop_reason = None

    if task.status == TaskStatus.ARCHIVED.value:
        stopped = True
        stop_reason = "archived"
    elif task.status == TaskStatus.DRAFT.value:
        await _do_step_generate_ticket(db, task, actor)
        action_taken = "generate_ticket"
        events_created = ["orchestration_step_completed"]
    elif task.status == TaskStatus.TICKET_READY.value:
        await _do_step_dispatch(db, task, actor)
        action_taken = "dispatch"
        events_created = ["orchestration_step_completed"]
    elif task.status == TaskStatus.DISPATCHED.value:
        result = await _do_step_create_agent_run(db, task, actor)
        action_taken = result["action"]
        events_created = result["events"]
        stopped = result.get("stopped", False)
        stop_reason = result.get("stop_reason")
    elif task.status == TaskStatus.RESULT_SUBMITTED.value:
        await _do_step_start_review(db, task, actor)
        action_taken = "start_review"
        events_created = ["orchestration_step_completed"]
    elif task.status == TaskStatus.REVIEWING.value:
        result = await _do_step_evaluate(db, task, actor)
        action_taken = result["action"]
        events_created = result["events"]
        stopped = result.get("stopped", False)
        stop_reason = result.get("stop_reason")
    elif task.status == TaskStatus.HUMAN_REQUIRED.value:
        stopped = True
        stop_reason = "human_required"
    elif task.status == TaskStatus.APPROVED.value:
        stopped = True
        stop_reason = "approved_waiting_archive"
    else:
        stopped = True
        stop_reason = f"no_auto_action_for_{task.status}"

    await event_service.create_event(
        db, task_id=task_id, event_type="orchestration_step_completed",
        actor=actor, message=f"Step: {action_taken or 'none'} -> {task.status}",
    )

    return OrchestrationStepResponse(
        task_id=task_id,
        before_status=before,
        after_status=task.status,
        action_taken=action_taken,
        events_created=events_created,
        stopped=stopped,
        stop_reason=stop_reason,
    )


async def _do_step_generate_ticket(db: AsyncSession, task: Task, actor: str):
    body = TaskStatusTransition(actor=actor, message="Auto-generated ticket")
    await task_service.generate_ticket(db, task.id, body)


async def _do_step_dispatch(db: AsyncSession, task: Task, actor: str):
    body = TaskStatusTransition(actor=actor, message="Auto-dispatched")
    await task_service.dispatch_task(db, task.id, body)


async def _do_step_create_agent_run(db: AsyncSession, task: Task, actor: str) -> dict[str, Any]:
    events = []
    # Check existing AgentRun states
    latest_run = (await db.execute(
        select(AgentRun).where(AgentRun.task_id == task.id).order_by(desc(AgentRun.id)).limit(1)
    )).scalar_one_or_none()
    
    if latest_run and latest_run.status in (AgentRunStatus.FAILED.value, AgentRunStatus.CANCELED.value):
        # Agent failed/canceled, stop
        return {"action": "blocked", "events": [], "stopped": True, "stop_reason": "agent_failed"}
    
    if latest_run and latest_run.status == AgentRunStatus.SUCCEEDED.value:
        # Agent already succeeded, create artifacts and transition
        from app.schemas.task import SubmitResultRequest
        await create_artifact_from_agent_run(db, latest_run)
        body = SubmitResultRequest(actor=actor, message="Auto-submit result", result_summary=latest_run.output_summary)
        await task_service.submit_result(db, task.id, body)
        return {"action": "submit_result", "events": ["orchestration_step_completed"], "stopped": False, "stop_reason": None}
    
    # Find an executor agent
    result = await db.execute(
        select(AgentProfile).where(
            AgentProfile.agent_type == "executor",
            AgentProfile.enabled == True
        ).limit(1)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        # Try any agent
        result = await db.execute(
            select(AgentProfile).where(AgentProfile.enabled == True).limit(1)
        )
        agent = result.scalar_one_or_none()
    if not agent:
        return {"action": "blocked", "events": [], "stopped": True, "stop_reason": "no_executor_agent"}

    # Create AgentRun
    run_data = AgentRunCreate(agent_id=agent.id, run_type="plan", input_prompt=task.description or task.title)
    run = await create_agent_run(db, task.id, run_data)
    events.append("agent_run_auto_created")
    await event_service.create_event(
        db, task_id=task.id, event_type="agent_run_auto_created",
        actor=actor, message=f"AgentRun #{run.id} auto-created",
    )

    # Start AgentRun (queued -> running)
    from app.schemas.agent_run import AgentRunUpdate
    update_data = AgentRunUpdate(status="running")
    await update_agent_run(db, run.id, update_data, task.id)
    events.append("agent_run_auto_started")
    await event_service.create_event(
        db, task_id=task.id, event_type="agent_run_auto_started",
        actor=actor, message=f"AgentRun #{run.id} auto-started",
    )

    # Must stop - can't fake result
    await event_service.create_event(
        db, task_id=task.id, event_type="agent_result_waiting",
        actor=actor, message="Waiting for agent result",
    )
    events.append("agent_result_waiting")

    return {"action": "create_agent_run", "events": events, "stopped": True, "stop_reason": "waiting_for_agent_result"}


async def _do_step_start_review(db: AsyncSession, task: Task, actor: str):
    body = TaskStatusTransition(actor=actor, message="Auto-start review")
    await task_service.start_review(db, task.id, body)


async def _do_step_evaluate(db: AsyncSession, task: Task, actor: str) -> dict[str, Any]:
    events = []
    actions = []

    # 1. Check existing auto-approvable decision
    latest_decision = (await db.execute(
        select(ApprovalDecision).where(
            ApprovalDecision.task_id == task.id,
            ApprovalDecision.auto_approve_allowed == True,
            ApprovalDecision.human_required == False,
        ).order_by(desc(ApprovalDecision.id)).limit(1)
    )).scalar_one_or_none()

    if latest_decision and latest_decision.risk_level == 'low':
        try:
            await do_auto_approve(db, task.id, latest_decision.id, actor, 'Auto-approved by orchestration')
            events.append('approval_auto_applied')
            actions.append('auto_approve')
            return {'action': 'auto_approve', 'events': events, 'stopped': False, 'stop_reason': None}
        except Exception as e:
            return {'action': 'blocked', 'events': events, 'stopped': True, 'stop_reason': str(e)}

    # 2. No existing decision, evaluate
    eval_req = ApprovalEvaluationRequest(actor=actor)
    eval_result = await evaluate_approval(db, task.id, eval_req)
    events.append("approval_auto_evaluated")
    actions.append("evaluate_approval")

    if eval_result.auto_approve_allowed and not eval_result.human_required:
        if eval_result.id > 0:
            try:
                await do_auto_approve(db, task.id, eval_result.id, actor, "Auto-approved by orchestration")
                events.append("approval_auto_applied")
                actions.append("auto_approve")
                return {"action": "auto_approve", "events": events, "stopped": False, "stop_reason": None}
            except Exception as e:
                return {"action": "blocked", "events": events, "stopped": True, "stop_reason": str(e)}

    if eval_result.human_required:
        body = TaskStatusTransition(actor=actor, message="Human approval required")
        await task_service.require_human_approval(db, task.id, body)
        events.append("human_approval_required")
        return {"action": "require_human_approval", "events": events, "stopped": True, "stop_reason": "human_required"}

    return {"action": "blocked", "events": events, "stopped": True, "stop_reason": "evaluation_blocked"}


async def orchestration_run(db: AsyncSession, task_id: int, max_steps: int, actor: str = "system") -> OrchestrationRunResponse:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status == TaskStatus.ARCHIVED.value:
        raise HTTPException(status_code=409, detail="Cannot orchestrate archived task")

    await event_service.create_event(
        db, task_id=task_id, event_type="orchestration_started",
        actor=actor, message=f"Orchestration started, max_steps={max_steps}",
    )

    steps = 0
    actions_taken = []
    stopped = False
    stop_reason = None

    for _ in range(max_steps):
        step_result = await orchestration_step(db, task_id, actor)
        steps += 1
        if step_result.action_taken:
            actions_taken.append(step_result.action_taken)
        if step_result.stopped:
            stopped = True
            stop_reason = step_result.stop_reason
            break

    final_task = await db.get(Task, task_id)
    await event_service.create_event(
        db, task_id=task_id, event_type="orchestration_stopped",
        actor=actor,
        message=f"Orchestration stopped after {steps} steps. Reason: {stop_reason or 'completed'}",
    )

    return OrchestrationRunResponse(
        task_id=task_id,
        steps_executed=steps,
        final_status=final_task.status if final_task else task.status,
        stopped=stopped,
        stop_reason=stop_reason,
        actions=actions_taken,
    )


async def create_artifact_from_agent_run(db: AsyncSession, run: AgentRun) -> TaskArtifact | None:
    """Create TaskArtifact from AgentRun output fields."""
    if not run.output_log and not run.output_diff and not run.raw_result_json:
        return None

    task = await db.get(Task, run.task_id)
    if not task or task.status == "archived":
        return None

    artifact = None
    if run.output_log:
        content = run.output_log
        sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        artifact = TaskArtifact(
            task_id=run.task_id,
            artifact_type="agent_output_log",
            content=content,
            filename=f"agent_run_{run.id}_output_log.txt",
            size_bytes=len(content.encode("utf-8")),
            sha256=sha256,
        )
        db.add(artifact)

    if run.output_diff:
        content = run.output_diff
        sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        artifact = TaskArtifact(
            task_id=run.task_id,
            artifact_type="agent_output_diff",
            content=content,
            filename=f"agent_run_{run.id}_diff.txt",
            size_bytes=len(content.encode("utf-8")),
            sha256=sha256,
        )
        db.add(artifact)

    if run.raw_result_json:
        content = run.raw_result_json
        sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        artifact = TaskArtifact(
            task_id=run.task_id,
            artifact_type="agent_raw_result",
            content=content,
            filename=f"agent_run_{run.id}_raw_result.json",
            size_bytes=len(content.encode("utf-8")),
            sha256=sha256,
        )
        db.add(artifact)

    if artifact:
        await db.flush()
        await event_service.create_event(
            db, task_id=run.task_id, event_type="artifact_uploaded",
            actor=f"agent_run:{run.id}",
            message=f"Artifact created from AgentRun #{run.id}",
        )
    return artifact

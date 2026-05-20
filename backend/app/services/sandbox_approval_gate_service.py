"""Sandbox Approval Gate Service — checks sandbox apply results against acceptance criteria.

This service evaluates whether a sandbox patch application is ready to proceed
toward PR creation. It checks:
- patch_apply_report.applied == true
- changed_files is non-empty
- No forbidden paths
- No secret patterns in the report
- AgentRun risk_level is not high/critical
- No human_required ApprovalDecision
- Task is not archived
- AgentRun belongs to the current task
- Sandbox artifact is the latest successful result

No writes to real file system.
No git operations.
No external API calls (CI, Sonar, Deploy).
"""

import json
import re

from fastapi import HTTPException
from sqlalchemy import select, desc, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.models.agent_run import AgentRun
from app.models.task_artifact import TaskArtifact
from app.models.approval_decision import ApprovalDecision
from app.schemas.sandbox_gate import SandboxGateDecision, SandboxGateBlockedReason
from app.services.ai_output_governance_service import _matches_forbidden
from app.services.event_service import create_event

EVENT_TYPE_PASSED = "sandbox_gate_passed"
EVENT_TYPE_BLOCKED = "sandbox_gate_blocked"
_RUN_ID_FROM_FILENAME = re.compile(r"run_(\d+)")


async def evaluate_sandbox_gate(db: AsyncSession, task_id: int) -> SandboxGateDecision:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    blocked: list[SandboxGateBlockedReason] = []

    # 1. Check task not archived
    if task.status == "archived":
        blocked.append(SandboxGateBlockedReason(reason="archived_task", detail="Task is archived"))

    # 2. Load latest patch_apply_report artifact
    report_artifact = await _get_latest_report_artifact(db, task_id)
    if not report_artifact:
        blocked.append(SandboxGateBlockedReason(reason="no_sandbox_result", detail="No sandbox patch apply result found"))

    report_data = _parse_report_artifact(report_artifact) if report_artifact else None

    if report_data:
        # 3. Check applied == true
        if not report_data.get("applied"):
            blocked.append(SandboxGateBlockedReason(reason="sandbox_not_applied", detail="Patch apply report indicates apply was not successful"))

        # 4. Check changed_files non-empty
        changed_files = report_data.get("changed_files", [])
        if not changed_files:
            blocked.append(SandboxGateBlockedReason(reason="no_changed_files", detail="No files were changed by the sandbox patch"))
        else:
            # 5. Check for forbidden paths
            for cf in changed_files:
                cf_path = cf.get("path", "")
                if _matches_forbidden(cf_path):
                    blocked.append(SandboxGateBlockedReason(
                        reason="forbidden_path",
                        detail=f"Changed file path matches forbidden pattern: {cf_path}",
                    ))

        # 6. Check for secret patterns in report content
        if report_artifact and report_artifact.content:
            if "***REDACTED***" in report_artifact.content:
                blocked.append(SandboxGateBlockedReason(reason="secret_detected", detail="Secret or credential pattern detected in sandbox result"))

        # 7. Check stale artifact
        if not await _is_latest_sandbox_result(db, task_id, report_artifact):
            blocked.append(SandboxGateBlockedReason(reason="stale_sandbox_result", detail="A newer sandbox apply result exists"))

        # 8. Extract run_id from filename and check AgentRun
        run_id = _extract_run_id(report_artifact)
        if run_id is not None:
            run = await db.get(AgentRun, run_id)
            if not run or run.task_id != task_id:
                blocked.append(SandboxGateBlockedReason(reason="agent_run_not_in_task", detail="AgentRun does not belong to this task"))
            else:
                # 9. Check risk_level not high/critical
                if run.risk_level in ("high", "critical"):
                    blocked.append(SandboxGateBlockedReason(reason="risk_too_high", detail=f"AgentRun risk level is '{run.risk_level}'"))

    # 10. Check no human_required ApprovalDecision
    last_decision = await _get_latest_approval_decision(db, task_id)
    if last_decision and last_decision.human_required:
        blocked.append(SandboxGateBlockedReason(reason="human_required", detail="Approval decision requires human intervention"))

    passed = len(blocked) == 0
    event_type = EVENT_TYPE_PASSED if passed else EVENT_TYPE_BLOCKED
    message = "All sandbox approval checks passed" if passed else f"Sandbox gate blocked: {len(blocked)} reason(s)"

    await create_event(
        db, task_id=task_id, event_type=event_type,
        actor=f"sandbox_gate:task_{task_id}",
        message=message,
        payload_json=json.dumps({
            "passed": passed,
            "blocked_reasons": [b.model_dump() for b in blocked],
        }, ensure_ascii=False),
    )

    return SandboxGateDecision(
        passed=passed,
        blocked_reasons=blocked,
        can_prepare_pr=passed,
        message=message,
    )


async def _get_latest_report_artifact(db: AsyncSession, task_id: int) -> TaskArtifact | None:
    result = await db.execute(
        select(TaskArtifact)
        .where(
            TaskArtifact.task_id == task_id,
            TaskArtifact.artifact_type == "patch_apply_report",
        )
        .order_by(desc(TaskArtifact.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


def _parse_report_artifact(artifact: TaskArtifact) -> dict | None:
    if not artifact or not artifact.content:
        return None
    try:
        return json.loads(artifact.content)
    except (json.JSONDecodeError, TypeError):
        return None


def _extract_run_id(artifact: TaskArtifact) -> int | None:
    if not artifact or not artifact.filename:
        return None
    m = _RUN_ID_FROM_FILENAME.search(artifact.filename)
    if m:
        return int(m.group(1))
    return None


async def _is_latest_sandbox_result(db: AsyncSession, task_id: int, artifact: TaskArtifact) -> bool:
    result = await db.execute(
        select(sa_func.count(TaskArtifact.id))
        .where(
            TaskArtifact.task_id == task_id,
            TaskArtifact.artifact_type.in_(["patch_apply_report", "changed_files_summary"]),
            TaskArtifact.created_at > artifact.created_at,
        )
    )
    count = result.scalar() or 0
    return count == 0


async def _get_latest_approval_decision(db: AsyncSession, task_id: int) -> ApprovalDecision | None:
    result = await db.execute(
        select(ApprovalDecision)
        .where(ApprovalDecision.task_id == task_id)
        .order_by(desc(ApprovalDecision.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()

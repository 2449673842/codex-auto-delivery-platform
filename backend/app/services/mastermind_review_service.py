import json
import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.task import Task
from app.models.task_artifact import TaskArtifact
from app.models.task_event import TaskEvent
from app.schemas.mastermind_review import (
    MastermindReviewPacketPreviewRequest,
    MastermindReviewPacketPreviewResponse,
    MastermindReviewRedactionStatus,
    MastermindReviewSourceRef,
)
from app.services import evidence_summary_service, project_memory_service
from app.services.ai_output_governance_service import redact_secrets


PACKET_TYPE = "mastermind_review_packet"
NOT_INCLUDED = "not_included"
SAFETY_NOTES = [
    "Mastermind Review Packet Preview API is read-only.",
    "Request PR metadata, verification results, and SonarCloud summary are used as supplied; the platform does not query GitHub or Sonar.",
    "No Browser AI mastermind review execution, browser launch, provider call, artifact write, PR, CI, Sonar, Deploy, approve, merge, or rework is performed.",
    "No AgentRun, TaskArtifact, TaskEvent, DispatchBatch, DispatchJob, Project, or Task record is created or modified.",
    "No .env, secret_ref, Project.root_path, account, password, cookie, or session value is read or returned.",
]
VERDICTS = ["approved", "request_changes", "needs_human", "invalid_review"]


async def preview_packet(
    db: AsyncSession,
    task_id: int,
    body: MastermindReviewPacketPreviewRequest,
) -> MastermindReviewPacketPreviewResponse:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project_not_found")

    source_refs = [
        MastermindReviewSourceRef(source_type="task", id=task.id, note="Task summary source"),
        MastermindReviewSourceRef(source_type="project", id=project.id, note="Project identity source"),
    ]
    evidence_summary = await _evidence_board_summary(db, task.id, body.include_evidence_board, source_refs)
    timeline_summary = await _timeline_summary(db, task.id, body.include_timeline, source_refs)
    memory_summary = await _project_memory_summary(db, project.id, body.include_project_memory, source_refs)
    handoff_context = await _handoff_context(db, task.id, body.include_handoff_context, source_refs)
    packet = _build_packet(
        task=task,
        project=project,
        body=body,
        evidence_board_summary=evidence_summary,
        run_timeline_summary=timeline_summary,
        project_memory_summary=memory_summary,
        handoff_context=handoff_context,
    )
    packet, truncated = _apply_packet_budget(packet, body.packet_budget)
    safety_notes = [_redact(note) for note in SAFETY_NOTES]
    return MastermindReviewPacketPreviewResponse(
        task_id=task.id,
        project_id=project.id,
        packet_type=PACKET_TYPE,
        packet=packet,
        source_refs=source_refs,
        redaction_status=MastermindReviewRedactionStatus(
            redaction_applied=True,
            truncated=truncated,
            max_chars=body.packet_budget,
        ),
        read_only=True,
        persisted=False,
        safety_notes=safety_notes,
    )


def _build_packet(
    *,
    task: Task,
    project: Project,
    body: MastermindReviewPacketPreviewRequest,
    evidence_board_summary: str,
    run_timeline_summary: str,
    project_memory_summary: str,
    handoff_context: str,
) -> dict[str, Any]:
    return _redact_jsonable({
        "pr": {
            "url": body.pr_url,
            "number": body.pr_number,
            "head_commit": body.head_commit,
            "base_commit": body.base_commit,
            "changed_files": body.changed_files,
            "body": body.pr_body,
        },
        "verification": body.verification_results.model_dump(),
        "sonarcloud": body.sonarcloud.model_dump(),
        "safety_boundary_checklist": _safety_boundary_checklist(),
        "task_summary": _task_summary(task, project),
        "evidence_board_summary": evidence_board_summary,
        "run_timeline_summary": run_timeline_summary,
        "project_memory_summary": project_memory_summary,
        "handoff_context": handoff_context,
        "review_instruction": _review_instruction(),
        "required_output_contract": _required_output_contract(),
    })


def _task_summary(task: Task, project: Project) -> str:
    return _redact(
        "\n".join([
            f"Task #{task.id}: {task.title}",
            f"Project #{project.id}: {project.display_name or project.name}",
            f"Status: {task.status}",
            f"Priority: {task.priority}",
            f"Description: {task.description or ''}",
            f"Result summary: {task.result_summary or ''}",
            f"Target branch: {task.target_branch or ''}",
            "Project.root_path is intentionally not included.",
        ])
    )


async def _evidence_board_summary(
    db: AsyncSession,
    task_id: int,
    include: bool,
    source_refs: list[MastermindReviewSourceRef],
) -> str:
    if not include:
        return NOT_INCLUDED
    board = await evidence_summary_service.get_evidence_board(db, task_id)
    source_refs.append(MastermindReviewSourceRef(source_type="evidence_board", id=task_id, note="Evidence Board summary"))
    counts: dict[str, int] = {}
    lines = [f"Evidence Board items: {len(board.items)}."]
    for item in board.items:
        counts[item.evidence_type] = counts.get(item.evidence_type, 0) + 1
    if counts:
        lines.append("Evidence types: " + ", ".join(f"{key}={value}" for key, value in sorted(counts.items())) + ".")
    for item in board.items[:12]:
        linked_ids = _linked_ids_from_board_item(item)
        lines.append(
            f"- {item.evidence_type}/{item.status} from {item.source}: {item.summary}"
            + (f" linked_ids={linked_ids}" if linked_ids else "")
        )
    return _redact("\n".join(lines))


async def _timeline_summary(
    db: AsyncSession,
    task_id: int,
    include: bool,
    source_refs: list[MastermindReviewSourceRef],
) -> str:
    if not include:
        return NOT_INCLUDED
    timeline = await evidence_summary_service.get_timeline(db, task_id)
    source_refs.append(MastermindReviewSourceRef(source_type="run_timeline", id=task_id, note="Run Timeline summary"))
    lines = [f"Run Timeline items: {len(timeline.items)}."]
    for item in timeline.items[-16:]:
        lines.append(f"- {item.time} {item.type}/{item.status} from {item.source}: {item.summary}")
    return _redact("\n".join(lines))


async def _project_memory_summary(
    db: AsyncSession,
    project_id: int,
    include: bool,
    source_refs: list[MastermindReviewSourceRef],
) -> str:
    if not include:
        return NOT_INCLUDED
    summary = await project_memory_service.get_project_memory_summary(db, project_id)
    source_refs.append(MastermindReviewSourceRef(source_type="project_memory", id=project_id, note="Project Memory summary"))
    return _redact(
        "\n".join([
            summary.summary,
            f"memory_count={summary.memory_count}",
            "memory_types=" + ", ".join(summary.memory_types),
            f"stale_count={summary.stale_count}",
            f"high_confidence_count={summary.high_confidence_count}",
        ])
    )


async def _handoff_context(
    db: AsyncSession,
    task_id: int,
    include: bool,
    source_refs: list[MastermindReviewSourceRef],
) -> str:
    if not include:
        return NOT_INCLUDED
    artifacts = (await db.execute(
        select(TaskArtifact)
        .where(TaskArtifact.task_id == task_id)
        .order_by(TaskArtifact.created_at.desc(), TaskArtifact.id.desc())
    )).scalars().all()
    events = (await db.execute(
        select(TaskEvent)
        .where(TaskEvent.task_id == task_id, TaskEvent.event_type.in_(["repair_attempt", "repair_attempt_status"]))
        .order_by(TaskEvent.created_at.desc(), TaskEvent.id.desc())
    )).scalars().all()
    lines: list[str] = []
    for artifact in artifacts:
        artifact_kind = _artifact_kind(artifact)
        if artifact_kind not in {"ai_handoff", "repair_handoff", "repair_packet"}:
            continue
        source_refs.append(MastermindReviewSourceRef(source_type=artifact_kind, id=artifact.id, note="Handoff context artifact"))
        lines.append(f"- artifact #{artifact.id} {artifact_kind}: {_artifact_summary(artifact)}")
    for event in events[:8]:
        source_refs.append(MastermindReviewSourceRef(source_type="repair_attempt", id=event.id, note="Repair attempt context"))
        lines.append(f"- event #{event.id} {event.event_type}/{event.to_status or ''}: {event.message or ''}")
    return _redact("\n".join(lines) if lines else "not_available")


def _artifact_kind(artifact: TaskArtifact) -> str:
    metadata = _loads_dict(artifact.metadata_json)
    value = str(metadata.get("type") or artifact.artifact_type or "").lower()
    if value in {"ai_handoff", "repair_handoff", "repair_packet"}:
        return value
    return ""


def _artifact_summary(artifact: TaskArtifact) -> str:
    metadata = _loads_dict(artifact.metadata_json)
    content = _loads_dict(artifact.content)
    for source in (metadata, content):
        for key in ("summary", "failure_summary", "recommended_fix_strategy", "handoff_prompt"):
            if source.get(key):
                return _short(source[key], 500)
    return _short(artifact.filename or artifact.artifact_type, 500)


def _safety_boundary_checklist() -> dict[str, bool]:
    return {
        "read_only_preview": True,
        "persisted": False,
        "provider_call": False,
        "browser_ai_execution": False,
        "review_execute_api": False,
        "artifact_write": False,
        "repository_write": False,
        "github_sonar_platform_query": False,
        "auto_approve": False,
        "auto_merge": False,
        "auto_deploy": False,
        "auto_rework": False,
    }


def _review_instruction() -> str:
    return "\n".join([
        "You are reviewing the supplied Mastermind Review Packet.",
        "Do not invent files, checks, commits, Sonar results, or verification outcomes.",
        "Compare PR body claims against packet evidence.",
        "If evidence is missing or ambiguous, return verdict `needs_human`.",
        "If there are concrete blocking issues, return verdict `request_changes`.",
        "Use only these verdicts: approved, request_changes, needs_human, invalid_review.",
        "Return structured JSON only using the required output contract.",
        "If you recommend merge, that recommendation is advisory only.",
        "You do not authorize the platform to auto approve, merge, deploy, or rework.",
    ])


def _required_output_contract() -> dict[str, Any]:
    return {
        "verdict": "approved | request_changes | needs_human | invalid_review",
        "summary": "Short review summary.",
        "blocking_items": [
            {
                "severity": "blocker | major | minor",
                "title": "Issue title",
                "evidence": "Grounded evidence from packet.",
                "recommended_action": "Action.",
            }
        ],
        "recommended_actions": [],
        "safety_notes": [],
        "confidence": "high | medium | low",
        "review_scope_confirmed": True,
    }


def _apply_packet_budget(packet: dict[str, Any], budget: int) -> tuple[dict[str, Any], bool]:
    truncated = False
    if _packet_size(packet) <= budget:
        return packet, truncated
    truncated = True
    text_paths = [
        ("pr", "body"),
        ("handoff_context",),
        ("evidence_board_summary",),
        ("run_timeline_summary",),
        ("project_memory_summary",),
        ("task_summary",),
    ]
    for path in text_paths:
        if _packet_size(packet) <= budget:
            break
        value = _get_path(packet, path)
        if not isinstance(value, str) or len(value) <= 40:
            continue
        overage = _packet_size(packet) - budget
        keep = max(40, len(value) - overage - 80)
        _set_path(packet, path, _truncate(value, keep))
    if _packet_size(packet) > budget:
        for path in text_paths:
            value = _get_path(packet, path)
            if isinstance(value, str) and len(value) > 80:
                _set_path(packet, path, _truncate(value, 80))
    return packet, truncated


def _packet_size(packet: dict[str, Any]) -> int:
    return len(json.dumps(packet, ensure_ascii=False, default=str))


def _get_path(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _set_path(data: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    current = data
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value


def _linked_ids_from_board_item(item: Any) -> dict[str, int]:
    values = {
        "artifact_id": item.artifact_id,
        "agent_run_id": item.agent_run_id,
        "dispatch_batch_id": item.dispatch_batch_id,
        "dispatch_job_id": item.dispatch_job_id,
        "repair_attempt_id": item.repair_attempt_id,
    }
    return {key: value for key, value in values.items() if value is not None}


def _redact_jsonable(value: Any) -> Any:
    if isinstance(value, str):
        return _redact(value)
    if isinstance(value, list):
        return [_redact_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_jsonable(item) for key, item in value.items()}
    return value


def _redact(value: str | None) -> str:
    redacted = redact_secrets(value or "")
    redacted = re.sub(r"\bcookie\s*=\s*\S+", "cookie=***REDACTED***", redacted, flags=re.IGNORECASE)
    redacted = re.sub(r"\bsession\s*=\s*\S+", "session=***REDACTED***", redacted, flags=re.IGNORECASE)
    redacted = re.sub(r"\bsecret_ref\s*=\s*\S+", "secret_ref=***REDACTED***", redacted, flags=re.IGNORECASE)
    return redacted


def _truncate(value: str, limit: int) -> str:
    clean = _redact(value)
    if len(clean) <= limit:
        return clean
    return clean[:limit].rstrip() + "\n...[truncated]"


def _short(value: Any, limit: int) -> str:
    return " ".join(_truncate(str(value or ""), limit).split())


def _loads_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}

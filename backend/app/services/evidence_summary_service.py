import json
import re
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.agent_run import AgentRun
from app.models.dispatch_batch import DispatchBatch
from app.models.dispatch_job import DispatchJob
from app.models.task import Task
from app.models.task_artifact import TaskArtifact
from app.models.task_event import TaskEvent
from app.schemas.evidence_summary import (
    EvidenceBoardFilters,
    EvidenceBoardItem,
    EvidenceBoardResponse,
    EvidenceLinkedIds,
    EvidenceRedactionStatus,
    TimelineItem,
    TimelineResponse,
)
from app.services.ai_output_governance_service import redact_secrets


RAW_EXCERPT_MAX_CHARS = 2000
SUMMARY_MAX_CHARS = 280
SAFETY_FLAGS = ["read_only", "no_repository_writes", "no_provider_call"]
SAFETY_NOTES = [
    "Evidence Summary API is read-only.",
    "No provider call, Browser AI execution, shell, subprocess, GitHub, Sonar, PR, CI, Deploy, approve, or merge is performed.",
    "Existing records are redacted and bounded before returning summaries.",
]

ARTIFACT_EVIDENCE_TYPES = {
    "browser_ai_answer": "browser_ai_answer",
    "answer_synthesis": "answer_synthesis",
    "failure_evidence": "failure_evidence",
    "repair_packet": "repair_packet",
    "repair_handoff": "repair_handoff",
    "verification_result": "verification_result",
    "skill_review_report": "skill_review_report",
    "mastermind_review_report": "mastermind_review_report",
    "sandbox_result": "sandbox_result",
    "patch_artifact": "patch_artifact",
    "patch_apply_report": "sandbox_result",
    "sandbox_gate_result": "sandbox_result",
    "patch": "patch_artifact",
}

ARTIFACT_TIMELINE_TYPES = {
    "browser_ai_answer": "browser_ai_answer_saved",
    "answer_synthesis": "synthesis_refreshed",
    "failure_evidence": "failure_evidence_previewed",
    "repair_packet": "repair_packet_generated",
    "repair_handoff": "repair_handoff_previewed",
    "verification_result": "verification_result_imported",
    "skill_review_report": "skill_review_report_imported",
    "mastermind_review_report": "mastermind_review_report_imported",
}


async def get_timeline(db: AsyncSession, task_id: int) -> TimelineResponse:
    task = await _get_task(db, task_id)
    events, runs, artifacts, batches, jobs = await _load_sources(db, task_id)
    items = [_task_created_item(task)]
    items.extend(_event_timeline_items(events))
    items.extend(_agent_run_timeline_items(runs))
    items.extend(_artifact_timeline_items(artifacts))
    items.extend(_dispatch_timeline_items(batches, jobs))
    return TimelineResponse(
        task_id=task.id,
        project_id=task.project_id,
        items=sorted(items, key=lambda item: item.time),
        read_only=True,
        persisted=False,
    )


async def get_evidence_board(db: AsyncSession, task_id: int) -> EvidenceBoardResponse:
    task = await _get_task(db, task_id)
    events, runs, artifacts, batches, jobs = await _load_sources(db, task_id)
    items: list[EvidenceBoardItem] = []
    items.extend(_event_board_items(events))
    items.extend(_agent_run_board_items(runs))
    items.extend(_artifact_board_items(artifacts))
    items.extend(_dispatch_board_items(batches, jobs))
    return EvidenceBoardResponse(
        task_id=task.id,
        project_id=task.project_id,
        filters=_filters(items),
        items=items,
        read_only=True,
        persisted=False,
    )


async def _get_task(db: AsyncSession, task_id: int) -> Task:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    return task


async def _load_sources(db: AsyncSession, task_id: int) -> tuple[
    list[TaskEvent],
    list[AgentRun],
    list[TaskArtifact],
    list[DispatchBatch],
    list[DispatchJob],
]:
    events = (await db.execute(
        select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.created_at, TaskEvent.id)
    )).scalars().all()
    runs = (await db.execute(
        select(AgentRun)
        .where(AgentRun.task_id == task_id)
        .options(selectinload(AgentRun.agent))
        .order_by(AgentRun.created_at, AgentRun.id)
    )).scalars().all()
    artifacts = (await db.execute(
        select(TaskArtifact).where(TaskArtifact.task_id == task_id).order_by(TaskArtifact.created_at, TaskArtifact.id)
    )).scalars().all()
    batches = (await db.execute(
        select(DispatchBatch)
        .where(DispatchBatch.task_id == task_id)
        .options(selectinload(DispatchBatch.jobs))
        .order_by(DispatchBatch.created_at, DispatchBatch.id)
    )).scalars().unique().all()
    jobs = (await db.execute(
        select(DispatchJob).where(DispatchJob.task_id == task_id).order_by(DispatchJob.created_at, DispatchJob.id)
    )).scalars().all()
    return events, runs, artifacts, batches, jobs


def _task_created_item(task: Task) -> TimelineItem:
    return _timeline_item(
        happened_at=task.created_at,
        type="task_created",
        status=task.status,
        source="task",
        summary=_short(f"{task.title}: {task.description or ''}"),
    )


def _event_timeline_items(events: list[TaskEvent]) -> list[TimelineItem]:
    items: list[TimelineItem] = []
    for event in events:
        payload = _loads_dict(event.payload_json)
        event_type = _timeline_type_for_event(event)
        items.append(_timeline_item(
            happened_at=event.created_at,
            type=event_type,
            status=event.to_status or payload.get("status") or event.event_type,
            source=_event_source(event),
            linked_ids=EvidenceLinkedIds(repair_attempt_id=_repair_attempt_id(event, payload)),
            summary=_short(event.message or _json(payload) or event.event_type),
            safety_flags=_safety_flags_for_payload(payload),
        ))
    return items


def _agent_run_timeline_items(runs: list[AgentRun]) -> list[TimelineItem]:
    items: list[TimelineItem] = []
    for run in runs:
        if run.status == "failed":
            event_type = "ai_run_failed"
        elif run.status == "succeeded":
            event_type = "ai_run_finished"
        else:
            event_type = "ai_run_started"
        items.append(_timeline_item(
            happened_at=run.finished_at or run.started_at or run.created_at,
            type=event_type,
            status=run.status,
            source=_agent_provider(run) or "agent_run",
            linked_ids=EvidenceLinkedIds(agent_run_id=run.id),
            summary=_short(run.error_message or run.output_summary or run.input_prompt or run.run_type),
            safety_flags=_run_safety_flags(run),
        ))
    return items


def _artifact_timeline_items(artifacts: list[TaskArtifact]) -> list[TimelineItem]:
    items: list[TimelineItem] = []
    for artifact in artifacts:
        event_type = ARTIFACT_TIMELINE_TYPES.get(_artifact_evidence_type(artifact), "artifact_created")
        metadata = _loads_dict(artifact.metadata_json)
        items.append(_timeline_item(
            happened_at=artifact.created_at,
            type=event_type,
            status=_artifact_status(metadata),
            source=_artifact_source(artifact, metadata),
            linked_ids=_artifact_linked_ids(artifact, metadata),
            summary=_short(metadata.get("summary") or artifact.filename or artifact.artifact_type),
            safety_flags=_artifact_safety_flags(artifact, metadata),
        ))
    return items


def _dispatch_timeline_items(batches: list[DispatchBatch], jobs: list[DispatchJob]) -> list[TimelineItem]:
    items: list[TimelineItem] = []
    for batch in batches:
        event_type = "multi_ai_evidence_finished" if _is_finished(batch.status) else "multi_ai_evidence_started"
        items.append(_timeline_item(
            happened_at=batch.updated_at or batch.created_at,
            type=event_type,
            status=batch.status,
            source=_dispatch_source(batch),
            linked_ids=EvidenceLinkedIds(dispatch_batch_id=batch.id),
            summary=_short(batch.task_goal or batch.batch_mode),
        ))
    for job in jobs:
        metadata = _loads_dict(job.metadata_json)
        items.append(_timeline_item(
            happened_at=job.finished_at or job.started_at or job.created_at,
            type="multi_ai_evidence_finished" if _is_finished(job.status) else "multi_ai_evidence_started",
            title=f"Dispatch job {job.status}",
            status=job.status,
            source="multi_ai_evidence" if metadata.get("type") == "multi_ai_evidence_job" else "dispatch_job",
            linked_ids=EvidenceLinkedIds(
                agent_run_id=job.agent_run_id,
                dispatch_batch_id=job.batch_id,
                dispatch_job_id=job.id,
            ),
            summary=_short(job.error_message or job.question),
        ))
    return items


def _event_board_items(events: list[TaskEvent]) -> list[EvidenceBoardItem]:
    items: list[EvidenceBoardItem] = []
    for event in events:
        payload = _loads_dict(event.payload_json)
        evidence_type = "repair_attempt" if event.event_type.startswith("repair_attempt") else "task_event"
        excerpt = _excerpt(event.message or _json(payload) or event.event_type)
        items.append(_board_item(
            evidence_type=evidence_type,
            source=_event_source(event),
            status=event.to_status or payload.get("status") or event.event_type,
            repair_attempt_id=_repair_attempt_id(event, payload),
            summary=_short(event.message or event.event_type),
            safety_notes=_safety_notes(payload),
            excerpt=excerpt,
        ))
    return items


def _agent_run_board_items(runs: list[AgentRun]) -> list[EvidenceBoardItem]:
    items: list[EvidenceBoardItem] = []
    for run in runs:
        provider = _agent_provider(run)
        excerpt = _excerpt("\n".join(filter(None, [run.output_summary, run.output_log, run.error_message, run.raw_result_json])))
        items.append(_board_item(
            evidence_type="agent_run",
            source=provider or "agent_run",
            status=run.status,
            provider=provider,
            role=run.run_type or "",
            agent_run_id=run.id,
            summary=_short(run.error_message or run.output_summary or run.run_type),
            safety_notes=_safety_notes(_loads_dict(run.raw_result_json)),
            excerpt=excerpt,
        ))
    return items


def _artifact_board_items(artifacts: list[TaskArtifact]) -> list[EvidenceBoardItem]:
    items: list[EvidenceBoardItem] = []
    for artifact in artifacts:
        metadata = _loads_dict(artifact.metadata_json)
        evidence_type = _artifact_evidence_type(artifact)
        excerpt = _excerpt(artifact.content or _json(metadata), source_truncated=artifact.is_truncated)
        items.append(_board_item(
            evidence_type=evidence_type,
            source=_artifact_source(artifact, metadata),
            status=_artifact_status(metadata),
            provider=str(metadata.get("provider") or ""),
            role=str(metadata.get("role") or metadata.get("target") or ""),
            artifact_id=artifact.id,
            agent_run_id=_int_or_none(metadata.get("agent_run_id")),
            dispatch_batch_id=_int_or_none(metadata.get("dispatch_batch_id")),
            dispatch_job_id=_int_or_none(metadata.get("dispatch_job_id")),
            repair_attempt_id=_int_or_none(metadata.get("repair_attempt_id")),
            summary=_artifact_summary(artifact, metadata),
            safety_notes=_safety_notes(metadata),
            excerpt=excerpt,
        ))
    return items


def _dispatch_board_items(batches: list[DispatchBatch], jobs: list[DispatchJob]) -> list[EvidenceBoardItem]:
    items: list[EvidenceBoardItem] = []
    for batch in batches:
        metadata = _loads_dict(batch.metadata_json)
        summary = _loads_dict(batch.summary_json)
        excerpt = _excerpt("\n".join(filter(None, [batch.task_goal, _json(summary), _json(metadata)])))
        items.append(_board_item(
            evidence_type="multi_ai_evidence",
            source=_dispatch_source(batch),
            status=batch.status,
            dispatch_batch_id=batch.id,
            summary=_short(summary.get("summary") or batch.task_goal or batch.batch_mode),
            safety_notes=_safety_notes(metadata),
            excerpt=excerpt,
        ))
    for job in jobs:
        metadata = _loads_dict(job.metadata_json)
        excerpt = _excerpt("\n".join(filter(None, [job.question, job.error_message, _json(metadata)])))
        items.append(_board_item(
            evidence_type="multi_ai_evidence",
            source="multi_ai_evidence" if metadata.get("type") == "multi_ai_evidence_job" else "dispatch_job",
            status=job.status,
            provider=job.provider or "",
            role=str(metadata.get("role") or job.mode or ""),
            agent_run_id=job.agent_run_id,
            dispatch_batch_id=job.batch_id,
            dispatch_job_id=job.id,
            summary=_short(job.error_message or job.question),
            safety_notes=_safety_notes(metadata),
            excerpt=excerpt,
        ))
    return items


def _board_item(
    *,
    evidence_type: str,
    source: str,
    status: str,
    summary: str,
    excerpt: "_Excerpt",
    safety_notes: list[str],
    provider: str = "",
    role: str = "",
    artifact_id: int | None = None,
    agent_run_id: int | None = None,
    dispatch_batch_id: int | None = None,
    dispatch_job_id: int | None = None,
    repair_attempt_id: int | None = None,
) -> EvidenceBoardItem:
    return EvidenceBoardItem(
        evidence_type=evidence_type,
        source=source,
        status=status,
        provider=provider,
        role=role,
        artifact_id=artifact_id,
        agent_run_id=agent_run_id,
        dispatch_batch_id=dispatch_batch_id,
        dispatch_job_id=dispatch_job_id,
        repair_attempt_id=repair_attempt_id,
        summary=summary,
        raw_excerpt=excerpt.text,
        safety_notes=safety_notes,
        redaction_status=excerpt.status,
    )


def _timeline_item(
    *,
    happened_at: datetime | None,
    type: str,
    status: str,
    source: str,
    summary: str,
    title: str | None = None,
    linked_ids: EvidenceLinkedIds | None = None,
    safety_flags: list[str] | None = None,
) -> TimelineItem:
    return TimelineItem(
        time=_iso(happened_at),
        type=type,
        title=title or _title(type),
        status=status,
        source=source,
        linked_ids=linked_ids or EvidenceLinkedIds(),
        summary=summary,
        safety_flags=safety_flags or SAFETY_FLAGS.copy(),
    )


class _Excerpt:
    def __init__(self, text: str, status: EvidenceRedactionStatus):
        self.text = text
        self.status = status


def _excerpt(value: Any, source_truncated: bool = False) -> _Excerpt:
    redacted = _redact(_string(value))
    truncated = source_truncated or len(redacted) > RAW_EXCERPT_MAX_CHARS
    if len(redacted) > RAW_EXCERPT_MAX_CHARS:
        redacted = redacted[:RAW_EXCERPT_MAX_CHARS].rstrip() + "\n...[truncated]"
    return _Excerpt(
        redacted,
        EvidenceRedactionStatus(redaction_applied=True, truncated=truncated, max_chars=RAW_EXCERPT_MAX_CHARS),
    )


def _filters(items: list[EvidenceBoardItem]) -> EvidenceBoardFilters:
    return EvidenceBoardFilters(
        evidence_type=_unique(item.evidence_type for item in items),
        source=_unique(item.source for item in items),
        status=_unique(item.status for item in items),
        provider=_unique(item.provider for item in items if item.provider),
        role=_unique(item.role for item in items if item.role),
    )


def _timeline_type_for_event(event: TaskEvent) -> str:
    if event.event_type == "repair_attempt":
        return "repair_attempt_created"
    if event.event_type == "repair_attempt_status":
        return "repair_attempt_status_changed"
    if "synthesis" in event.event_type:
        return "synthesis_refreshed"
    return "task_event"


def _artifact_evidence_type(artifact: TaskArtifact) -> str:
    metadata = _loads_dict(artifact.metadata_json)
    explicit_type = str(metadata.get("type") or artifact.artifact_type or "")
    normalized = explicit_type.lower()
    if normalized in ARTIFACT_EVIDENCE_TYPES:
        return ARTIFACT_EVIDENCE_TYPES[normalized]
    artifact_type = (artifact.artifact_type or "").lower()
    return ARTIFACT_EVIDENCE_TYPES.get(artifact_type, "artifact")


def _artifact_source(artifact: TaskArtifact, metadata: dict[str, Any]) -> str:
    if metadata.get("source"):
        return str(metadata["source"])
    evidence_type = _artifact_evidence_type(artifact)
    if evidence_type in {"repair_packet", "repair_handoff", "failure_evidence", "verification_result"}:
        return "repair_loop"
    if evidence_type == "browser_ai_answer":
        return "browser_ai"
    if evidence_type == "answer_synthesis":
        return "answer_synthesis"
    if evidence_type == "skill_review_report":
        return "skill_review"
    if evidence_type == "mastermind_review_report":
        return "mastermind_review"
    if evidence_type == "sandbox_result":
        return "sandbox"
    if evidence_type == "patch_artifact":
        return "patch"
    return "artifact"


def _artifact_linked_ids(artifact: TaskArtifact, metadata: dict[str, Any]) -> EvidenceLinkedIds:
    return EvidenceLinkedIds(
        agent_run_id=_int_or_none(metadata.get("agent_run_id")),
        artifact_id=artifact.id,
        dispatch_batch_id=_int_or_none(metadata.get("dispatch_batch_id")),
        dispatch_job_id=_int_or_none(metadata.get("dispatch_job_id")),
        repair_attempt_id=_int_or_none(metadata.get("repair_attempt_id")),
    )


def _artifact_status(metadata: dict[str, Any]) -> str:
    return str(metadata.get("status") or metadata.get("overall_status") or "completed")


def _artifact_summary(artifact: TaskArtifact, metadata: dict[str, Any]) -> str:
    for key in ("summary", "failure_summary", "recommended_fix_strategy", "answer_preview"):
        if metadata.get(key):
            return _short(metadata[key])
    content = _loads_dict(artifact.content)
    for key in ("summary", "failure_summary", "recommended_fix_strategy", "answer_preview"):
        if content.get(key):
            return _short(content[key])
    return _short(artifact.filename or artifact.artifact_type)


def _dispatch_source(batch: DispatchBatch) -> str:
    metadata = _loads_dict(batch.metadata_json)
    return "multi_ai_evidence" if metadata.get("type") == "multi_ai_evidence_run" else "dispatch_batch"


def _event_source(event: TaskEvent) -> str:
    if event.event_type.startswith("repair_attempt"):
        return "repair_loop"
    return event.actor or "task_event"


def _repair_attempt_id(event: TaskEvent, payload: dict[str, Any]) -> int | None:
    if event.event_type == "repair_attempt":
        return event.id
    return _int_or_none(payload.get("repair_attempt_id"))


def _agent_provider(run: AgentRun) -> str:
    agent = getattr(run, "agent", None)
    return str(getattr(agent, "provider", "") or getattr(agent, "agent_type", "") or "")


def _run_safety_flags(run: AgentRun) -> list[str]:
    flags = SAFETY_FLAGS.copy()
    if run.risk_level in {"high", "critical"}:
        flags.append("has_risk")
    if run.status == "failed":
        flags.append("failed")
    return flags


def _artifact_safety_flags(artifact: TaskArtifact, metadata: dict[str, Any]) -> list[str]:
    flags = SAFETY_FLAGS.copy()
    if artifact.is_truncated or metadata.get("truncated"):
        flags.append("truncated")
    if metadata.get("human_decision_required"):
        flags.append("human_decision_required")
    return flags


def _safety_flags_for_payload(payload: dict[str, Any]) -> list[str]:
    flags = SAFETY_FLAGS.copy()
    if payload.get("human_decision_required"):
        flags.append("human_decision_required")
    if payload.get("safety_flags") and isinstance(payload["safety_flags"], list):
        flags.extend(str(item) for item in payload["safety_flags"])
    return _unique(flags)


def _safety_notes(payload: dict[str, Any]) -> list[str]:
    notes = payload.get("safety_notes")
    if isinstance(notes, list):
        redacted_notes = [_redact(str(note)) for note in notes if str(note).strip()]
        return redacted_notes or SAFETY_NOTES.copy()
    return SAFETY_NOTES.copy()


def _title(event_type: str) -> str:
    return event_type.replace("_", " ").capitalize()


def _short(value: Any, limit: int = SUMMARY_MAX_CHARS) -> str:
    clean = " ".join(_redact(_string(value)).split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def _redact(value: str) -> str:
    redacted = redact_secrets(value or "")
    redacted = re.sub(r"\bcookie\s*=\s*\S+", "cookie=***REDACTED***", redacted, flags=re.IGNORECASE)
    redacted = re.sub(r"\bsession\s*=\s*\S+", "session=***REDACTED***", redacted, flags=re.IGNORECASE)
    return redacted


def _loads_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _json(value: Any) -> str:
    if not value:
        return ""
    return json.dumps(value, ensure_ascii=False, default=str)


def _string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return _json(value)


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _is_finished(status: str) -> bool:
    return status in {"succeeded", "failed", "partial", "completed", "cancelled"}


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _unique(values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in result:
            result.append(text)
    return result

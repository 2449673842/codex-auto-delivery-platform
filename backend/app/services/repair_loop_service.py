import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.agent_run import AgentRun
from app.models.dispatch_batch import DispatchBatch
from app.models.dispatch_job import DispatchJob
from app.models.task import Task
from app.models.task_artifact import TaskArtifact
from app.models.task_event import TaskEvent
from app.schemas.repair_loop import (
    REPAIR_FAILURE_TYPES,
    FailureEvidencePacketResponse,
    FailureEvidencePreviewRequest,
    FailureEvidenceRedactionStatus,
)
from app.services.ai_output_governance_service import redact_secrets


FAILURE_STEP_MAP = {
    "sandbox_failed": "sandbox",
    "sandbox_gate_blocked": "sandbox_gate",
    "verification_failed": "verification",
    "ci_failed": "ci",
    "sonar_failed": "sonar",
    "review_blocked": "review",
    "browser_ai_failed": "browser_ai",
    "multi_ai_evidence_partial": "multi_ai_evidence_run",
}

SAFETY_NOTES = [
    "Failure Evidence preview is read-only.",
    "No provider call is made.",
    "No Browser AI execution or browser launch is performed.",
    "No repository writes, PR, CI, Sonar, Deploy, approve, or merge are performed.",
    "Secrets are redacted and excerpts are bounded before returning the packet.",
    "Project.root_path is not scanned or modified.",
]


class _EvidenceCollector:
    def __init__(self, max_chars: int):
        self.max_chars = max_chars
        self.truncated = False
        self.command_summaries: list[str] = []
        self.stdout_parts: list[str] = []
        self.stderr_parts: list[str] = []
        self.blocked_reasons: list[str] = []
        self.agent_run_ids: list[int] = []
        self.artifact_ids: list[int] = []
        self.dispatch_batch_id: int | None = None
        self.dispatch_job_ids: list[int] = []

    def add_command(self, value: Any) -> None:
        self._append_unique(self.command_summaries, self._string(value))

    def add_stdout(self, value: Any) -> None:
        text = self._string(value)
        if text:
            self.stdout_parts.append(text)

    def add_stderr(self, value: Any) -> None:
        text = self._string(value)
        if text:
            self.stderr_parts.append(text)

    def add_reason(self, value: Any) -> None:
        if isinstance(value, dict):
            value = value.get("reason") or value.get("detail") or value.get("message")
        if isinstance(value, list):
            for item in value:
                self.add_reason(item)
            return
        text = self._excerpt(self._string(value))
        self._append_unique(self.blocked_reasons, text)

    def response(self, task: Task, failure_type: str) -> FailureEvidencePacketResponse:
        stdout_excerpt = self._excerpt("\n\n".join(self.stdout_parts))
        stderr_excerpt = self._excerpt("\n\n".join(self.stderr_parts))
        return FailureEvidencePacketResponse(
            task_id=task.id,
            project_id=task.project_id,
            failure_type=failure_type,
            failed_step=FAILURE_STEP_MAP[failure_type],
            failed_command_summary=self._excerpt("; ".join(self.command_summaries)),
            stdout_excerpt=stdout_excerpt,
            stderr_excerpt=stderr_excerpt,
            blocked_reasons=self.blocked_reasons,
            related_agent_run_ids=self.agent_run_ids,
            related_artifact_ids=self.artifact_ids,
            related_dispatch_batch_id=self.dispatch_batch_id,
            related_dispatch_job_ids=self.dispatch_job_ids,
            safety_notes=SAFETY_NOTES.copy(),
            redaction_status=FailureEvidenceRedactionStatus(
                redaction_applied=True,
                truncated=self.truncated,
                max_chars=self.max_chars,
            ),
            read_only=True,
            persisted=False,
        )

    def _excerpt(self, value: str) -> str:
        redacted = redact_secrets(value or "")
        if len(redacted) > self.max_chars:
            self.truncated = True
            return redacted[:self.max_chars] + "\n...[truncated]"
        return redacted

    @staticmethod
    def _append_unique(items: list[int] | list[str], value: Any) -> None:
        if value in (None, ""):
            return
        if value not in items:
            items.append(value)

    @staticmethod
    def _string(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return json.dumps(value, ensure_ascii=False, default=str)


async def preview(db: AsyncSession, body: FailureEvidencePreviewRequest) -> FailureEvidencePacketResponse:
    if body.failure_type not in REPAIR_FAILURE_TYPES:
        raise HTTPException(status_code=400, detail="unknown_failure_type")
    task = await db.get(Task, body.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")

    collector = _EvidenceCollector(body.max_excerpt_chars)
    await _collect_requested_sources(db, body, collector)
    if not _has_explicit_source(body):
        await _collect_recent_sources(db, task.id, body.failure_type, collector)
    if not collector.command_summaries:
        collector.add_command(body.failure_type)
    if not collector.blocked_reasons:
        collector.add_reason(body.failure_type)
    return collector.response(task, body.failure_type)


async def _collect_requested_sources(
    db: AsyncSession,
    body: FailureEvidencePreviewRequest,
    collector: _EvidenceCollector,
) -> None:
    source = body.source
    if source.agent_run_id is not None:
        run = await db.get(AgentRun, source.agent_run_id)
        _ensure_task_source(run, body.task_id, "agent_run_not_found")
        _collect_run(run, collector)
    if source.artifact_id is not None:
        artifact = await db.get(TaskArtifact, source.artifact_id)
        _ensure_task_source(artifact, body.task_id, "artifact_not_found")
        _collect_artifact(artifact, collector)
    if source.dispatch_batch_id is not None:
        batch = await _get_batch(db, source.dispatch_batch_id)
        _ensure_task_source(batch, body.task_id, "dispatch_batch_not_found")
        _collect_batch(batch, collector)
    if source.dispatch_job_id is not None:
        job = await db.get(DispatchJob, source.dispatch_job_id)
        _ensure_task_source(job, body.task_id, "dispatch_job_not_found")
        _collect_job(job, collector)


async def _collect_recent_sources(
    db: AsyncSession,
    task_id: int,
    failure_type: str,
    collector: _EvidenceCollector,
) -> None:
    await _collect_recent_events(db, task_id, failure_type, collector)
    await _collect_recent_runs(db, task_id, failure_type, collector)
    await _collect_recent_artifacts(db, task_id, failure_type, collector)
    await _collect_recent_dispatch(db, task_id, failure_type, collector)


async def _collect_recent_events(
    db: AsyncSession,
    task_id: int,
    failure_type: str,
    collector: _EvidenceCollector,
) -> None:
    result = await db.execute(
        select(TaskEvent)
        .where(TaskEvent.task_id == task_id)
        .order_by(desc(TaskEvent.created_at), desc(TaskEvent.id))
        .limit(8)
    )
    for event in result.scalars().all():
        haystack = " ".join([event.event_type or "", event.message or "", event.payload_json or ""])
        if _matches_failure(haystack, failure_type):
            _collect_event(event, collector)


async def _collect_recent_runs(
    db: AsyncSession,
    task_id: int,
    failure_type: str,
    collector: _EvidenceCollector,
) -> None:
    result = await db.execute(
        select(AgentRun)
        .where(AgentRun.task_id == task_id)
        .order_by(desc(AgentRun.created_at), desc(AgentRun.id))
        .limit(8)
    )
    for run in result.scalars().all():
        haystack = " ".join([run.status, run.run_type, run.error_message or "", run.raw_result_json or ""])
        if run.status == "failed" or _matches_failure(haystack, failure_type):
            _collect_run(run, collector)


async def _collect_recent_artifacts(
    db: AsyncSession,
    task_id: int,
    failure_type: str,
    collector: _EvidenceCollector,
) -> None:
    result = await db.execute(
        select(TaskArtifact)
        .where(TaskArtifact.task_id == task_id)
        .order_by(desc(TaskArtifact.created_at), desc(TaskArtifact.id))
        .limit(8)
    )
    for artifact in result.scalars().all():
        haystack = " ".join([artifact.artifact_type, artifact.filename or "", artifact.metadata_json or "", artifact.content or ""])
        if _matches_failure(haystack, failure_type):
            _collect_artifact(artifact, collector)


async def _collect_recent_dispatch(
    db: AsyncSession,
    task_id: int,
    failure_type: str,
    collector: _EvidenceCollector,
) -> None:
    result = await db.execute(
        select(DispatchBatch)
        .where(DispatchBatch.task_id == task_id)
        .options(selectinload(DispatchBatch.jobs))
        .order_by(desc(DispatchBatch.created_at), desc(DispatchBatch.id))
        .limit(4)
    )
    for batch in result.scalars().unique().all():
        haystack = " ".join([batch.status, batch.batch_mode, batch.summary_json or "", batch.metadata_json or ""])
        if batch.status in {"failed", "partial", "blocked"} or _matches_failure(haystack, failure_type):
            _collect_batch(batch, collector)


async def _get_batch(db: AsyncSession, batch_id: int) -> DispatchBatch | None:
    result = await db.execute(
        select(DispatchBatch)
        .where(DispatchBatch.id == batch_id)
        .options(selectinload(DispatchBatch.jobs))
    )
    return result.scalars().unique().one_or_none()


def _collect_run(run: AgentRun, collector: _EvidenceCollector) -> None:
    collector._append_unique(collector.agent_run_ids, run.id)
    collector.add_command(f"agent_run:{run.id} {run.run_type} status={run.status}")
    collector.add_stdout(run.output_summary)
    collector.add_stdout(run.output_log)
    collector.add_stderr(run.error_message)
    raw = _loads_dict(run.raw_result_json)
    collector.add_stderr(raw.get("stderr") or raw.get("error") or raw.get("error_message"))
    collector.add_stdout(raw.get("stdout") or raw.get("summary"))
    collector.add_reason(run.error_message if run.status == "failed" else None)
    collector.add_reason(raw.get("blocked_reasons"))


def _collect_artifact(artifact: TaskArtifact, collector: _EvidenceCollector) -> None:
    collector._append_unique(collector.artifact_ids, artifact.id)
    collector.add_command(f"artifact:{artifact.id} {artifact.artifact_type} {artifact.filename or ''}".strip())
    metadata = _loads_dict(artifact.metadata_json)
    collector.add_command(metadata.get("failed_command_summary") or metadata.get("command") or metadata.get("command_summary"))
    collector.add_stdout(metadata.get("stdout") or metadata.get("stdout_excerpt"))
    collector.add_stderr(metadata.get("stderr") or metadata.get("stderr_excerpt") or metadata.get("error"))
    collector.add_reason(metadata.get("blocked_reasons") or metadata.get("reasons"))
    content_data = _loads_dict(artifact.content)
    if content_data:
        collector.add_stdout(content_data.get("stdout") or content_data.get("output"))
        collector.add_stderr(content_data.get("stderr") or content_data.get("error") or content_data.get("error_message"))
        collector.add_reason(content_data.get("blocked_reasons") or content_data.get("errors"))
        if not (content_data.get("stdout") or content_data.get("stderr")):
            collector.add_stdout(content_data)
    else:
        collector.add_stdout(artifact.content)
    if artifact.is_truncated:
        collector.truncated = True


def _collect_event(event: TaskEvent, collector: _EvidenceCollector) -> None:
    collector.add_command(f"event:{event.id} {event.event_type}")
    collector.add_stderr(event.message)
    payload = _loads_dict(event.payload_json)
    collector.add_reason(payload.get("blocked_reasons") or payload.get("reasons"))
    collector.add_stdout(payload.get("stdout") or payload.get("summary"))
    collector.add_stderr(payload.get("stderr") or payload.get("error") or payload.get("message"))


def _collect_batch(batch: DispatchBatch, collector: _EvidenceCollector) -> None:
    collector.dispatch_batch_id = collector.dispatch_batch_id or batch.id
    collector.add_command(f"dispatch_batch:{batch.id} mode={batch.batch_mode} status={batch.status}")
    collector.add_stdout(batch.task_goal)
    collector.add_stdout(_loads_dict(batch.summary_json))
    metadata = _loads_dict(batch.metadata_json)
    collector.add_stdout(metadata)
    collector.add_reason(metadata.get("blocked_reasons"))
    for job in sorted(batch.jobs, key=lambda item: item.sequence_no):
        _collect_job(job, collector)


def _collect_job(job: DispatchJob, collector: _EvidenceCollector) -> None:
    collector._append_unique(collector.dispatch_job_ids, job.id)
    collector.add_command(f"dispatch_job:{job.id} provider={job.provider} status={job.status}")
    collector.add_stdout(job.question)
    collector.add_stderr(job.error_message)
    collector.add_reason(job.error_message if job.status in {"failed", "blocked"} else None)
    metadata = _loads_dict(job.metadata_json)
    collector.add_stdout(metadata)
    collector.add_reason(metadata.get("blocked_reasons"))
    for artifact_id in _loads_int_list(job.artifact_ids_json):
        collector._append_unique(collector.artifact_ids, artifact_id)
    if job.agent_run_id:
        collector._append_unique(collector.agent_run_ids, job.agent_run_id)


def _ensure_task_source(source: Any, task_id: int, detail: str) -> None:
    if source is None or getattr(source, "task_id", None) != task_id:
        raise HTTPException(status_code=404, detail=detail)


def _has_explicit_source(body: FailureEvidencePreviewRequest) -> bool:
    source = body.source
    return any([
        source.agent_run_id is not None,
        source.artifact_id is not None,
        source.dispatch_batch_id is not None,
        source.dispatch_job_id is not None,
    ])


def _matches_failure(text: str, failure_type: str) -> bool:
    normalized = text.lower()
    if failure_type.lower() in normalized:
        return True
    if failure_type == "browser_ai_failed":
        return "browser_ai" in normalized or "browser ai" in normalized or "detect_login" in normalized
    if failure_type == "multi_ai_evidence_partial":
        return "multi_ai_evidence" in normalized or "partial" in normalized
    if failure_type == "sandbox_gate_blocked":
        return "sandbox_gate" in normalized or "gate" in normalized
    return False


def _loads_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _loads_int_list(raw: str | None) -> list[int]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, int)]

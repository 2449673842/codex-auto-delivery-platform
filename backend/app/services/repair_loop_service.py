import hashlib
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
from app.schemas.answer_synthesis import AnswerSynthesisPreviewRequest
from app.schemas.multi_ai_evidence_run import MultiAiEvidenceRunRequest
from app.schemas.repair_loop import (
    REPAIR_FAILURE_TYPES,
    FailureEvidencePacketResponse,
    FailureEvidencePreviewRequest,
    FailureEvidenceRedactionStatus,
    RepairEvidenceBySource,
    RepairPacketGenerateRequest,
    RepairPacketResponse,
)
from app.services import answer_synthesis_service, multi_ai_evidence_run_service
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

REPAIR_PACKET_SAFETY_NOTES = [
    "Repair Packet Generation uses evidence collection only; it does not modify code.",
    "Codex / OMX or the user must execute the repair outside the platform.",
    "No repository writes, PR, CI, Sonar, Deploy, approve, or merge are performed.",
    "max_attempts defaults to 1 and no automatic next attempt is started.",
]

DO_NOT_DO = [
    "Do not read `.env`.",
    "Do not read `secret_ref`.",
    "Do not expose API keys, cookies, sessions, or passwords.",
    "Do not write unrelated files.",
    "Do not auto merge.",
    "Do not auto deploy.",
    "Do not bypass tests.",
    "Do not bypass Browser AI login or captcha.",
    "Verify current master before acting.",
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


async def generate_repair_packet(db: AsyncSession, body: RepairPacketGenerateRequest) -> RepairPacketResponse:
    if body.failure_evidence.failure_type not in REPAIR_FAILURE_TYPES:
        raise HTTPException(status_code=400, detail="unknown_failure_type")
    if body.analysis_mode not in {"broadcast", "routed"}:
        raise HTTPException(status_code=400, detail="invalid_analysis_mode")
    if body.max_attempts != 1:
        raise HTTPException(status_code=400, detail="max_attempts_must_be_1_for_s20_2")
    if body.failure_evidence.task_id != body.task_id:
        raise HTTPException(status_code=400, detail="failure_evidence_task_mismatch")

    task = await db.get(Task, body.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    if task.project_id != body.failure_evidence.project_id:
        raise HTTPException(status_code=400, detail="failure_evidence_project_mismatch")

    evidence_prompt = _repair_analysis_prompt(task, body.failure_evidence)
    evidence_request = MultiAiEvidenceRunRequest(
        task_id=task.id,
        mode=body.analysis_mode,
        providers=body.providers if body.analysis_mode == "broadcast" else [],
        roles=body.roles if body.analysis_mode == "routed" else [],
        prompt_source="custom_prompt",
        custom_prompt=evidence_prompt,
        concurrency_limit=2,
    )
    analysis = await multi_ai_evidence_run_service.execute(db, evidence_request)
    if analysis.overall_status == "blocked":
        raise HTTPException(status_code=400, detail=analysis.error_message or "repair_analysis_blocked")

    try:
        synthesis = await answer_synthesis_service.preview(
            db,
            AnswerSynthesisPreviewRequest(
                task_id=task.id,
                dispatch_batch_id=analysis.dispatch_batch_id,
                include_artifacts=True,
                max_artifact_chars=1600,
            ),
        )
    except Exception:
        synthesis = None

    packet = _build_repair_packet(task, body, analysis, synthesis)
    artifact = _repair_packet_artifact(task.id, packet)
    db.add(artifact)
    await db.flush()
    await db.refresh(artifact)
    packet.repair_packet_artifact_id = artifact.id
    artifact.content = _safe_json(packet.model_dump())
    data = artifact.content.encode("utf-8")
    artifact.size_bytes = len(data)
    artifact.sha256 = hashlib.sha256(data).hexdigest()
    artifact.metadata_json = _safe_json({
        "type": "repair_packet",
        "source_failure_type": packet.source_failure_type,
        "source_artifact_ids": packet.source_artifact_ids,
        "source_agent_run_ids": packet.source_agent_run_ids,
        "source_dispatch_batch_id": packet.source_dispatch_batch_id,
        "analysis_dispatch_batch_id": packet.analysis_dispatch_batch_id,
        "human_decision_required": True,
        "max_attempts": packet.max_attempts,
        "does_not_modify_code": True,
    })
    await db.commit()
    await db.refresh(artifact)
    return packet


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


def _repair_analysis_prompt(task: Task, evidence: FailureEvidencePacketResponse) -> str:
    payload = {
        "task": {
            "task_id": task.id,
            "project_id": task.project_id,
            "title": task.title,
            "description": task.description,
            "status": task.status,
        },
        "failure_evidence": evidence.model_dump(),
        "expected_output": {
            "failure_summary": "Concise description of what failed.",
            "suspected_root_causes": ["likely cause"],
            "recommended_fix_strategy": "Smallest safe repair strategy.",
            "files_likely_involved": ["path hints only if evidence supports them"],
            "commands_to_verify": ["verification command suggestions"],
            "risks": ["remaining risk"],
        },
        "safety_boundaries": DO_NOT_DO,
    }
    return (
        "Analyze this failure evidence for a controlled repair packet. "
        "Do not propose automatic repository writes, PR creation, merge, deploy, or approve actions. "
        "Return repair guidance for Codex / OMX or the user to execute manually.\n\n"
        f"{_redact(json.dumps(payload, ensure_ascii=False, default=str))}"
    )


def _build_repair_packet(
    task: Task,
    body: RepairPacketGenerateRequest,
    analysis,
    synthesis,
) -> RepairPacketResponse:
    evidence = body.failure_evidence
    job_findings = _analysis_job_findings(analysis)
    failed_jobs = _analysis_failed_jobs(analysis)
    common_findings = _synthesis_list(synthesis, "common_findings")
    disagreements = _synthesis_list(synthesis, "disagreements")
    recommended_actions = _synthesis_list(synthesis, "recommended_actions")
    next_questions = _synthesis_list(synthesis, "next_questions")
    artifact_summaries = _synthesis_list(synthesis, "artifact_summaries")

    packet = RepairPacketResponse(
        task_id=task.id,
        project_id=task.project_id,
        failure_summary=_failure_summary(evidence),
        suspected_root_causes=_suspected_root_causes(evidence, common_findings, job_findings),
        evidence_by_source=_evidence_by_source(evidence, analysis, artifact_summaries),
        multi_ai_findings=_unique([*common_findings, *job_findings])[:12],
        disagreements=_unique([*disagreements, *next_questions])[:8],
        recommended_fix_strategy=_recommended_fix_strategy(recommended_actions),
        files_likely_involved=_files_likely_involved(evidence, job_findings, common_findings),
        commands_to_verify=_commands_to_verify(evidence),
        risks=_repair_risks(evidence, analysis, synthesis, failed_jobs, job_findings, common_findings),
        human_decision_required=True,
        codex_handoff_prompt="",
        max_attempts=body.max_attempts,
        do_not_do=DO_NOT_DO.copy(),
        source_failure_type=evidence.failure_type,
        source_artifact_ids=evidence.related_artifact_ids,
        source_agent_run_ids=evidence.related_agent_run_ids,
        source_dispatch_batch_id=evidence.related_dispatch_batch_id,
        source_dispatch_job_ids=evidence.related_dispatch_job_ids,
        analysis_dispatch_batch_id=analysis.dispatch_batch_id,
        analysis_status=analysis.overall_status,
        read_only=False,
        persisted=True,
        safety_notes=[
            *REPAIR_PACKET_SAFETY_NOTES,
            *analysis.safety_gate.safety_notes,
        ],
    )
    packet.codex_handoff_prompt = _codex_handoff_prompt(task, packet)
    return _redact_packet(packet)


def _analysis_job_findings(analysis) -> list[str]:
    return [
        f"{job.provider}/{job.role}: {job.answer_preview}"
        for job in analysis.jobs
        if job.status == "succeeded" and job.answer_preview
    ]


def _analysis_failed_jobs(analysis) -> list[str]:
    return [
        f"{job.provider}/{job.role}: {job.error_message}"
        for job in analysis.jobs
        if job.status in {"failed", "blocked"} and job.error_message
    ]


def _synthesis_list(synthesis, field: str) -> list[Any]:
    return list(getattr(synthesis, field, []) or []) if synthesis else []


def _repair_risks(
    evidence: FailureEvidencePacketResponse,
    analysis,
    synthesis,
    failed_jobs: list[str],
    job_findings: list[str],
    common_findings: list[Any],
) -> list[str]:
    risks = _unique([
        *_synthesis_list(synthesis, "risks"),
        *failed_jobs,
        *evidence.blocked_reasons,
        "Human decision is required before any repair execution.",
    ])
    if analysis.overall_status == "partial":
        risks.append("Multi-AI repair analysis was partial; at least one source failed or was blocked.")
    if not job_findings and not common_findings:
        risks.append("No successful Multi-AI repair finding was available; rely on failure evidence and human review.")
    return _unique(risks)[:12]


def _files_likely_involved(
    evidence: FailureEvidencePacketResponse,
    job_findings: list[str],
    common_findings: list[Any],
) -> list[str]:
    return _extract_file_hints(" ".join([
        evidence.failed_command_summary,
        evidence.stdout_excerpt,
        evidence.stderr_excerpt,
        " ".join(job_findings),
        " ".join(str(item) for item in common_findings),
    ]))


def _recommended_fix_strategy(recommended_actions: list[Any]) -> str:
    strategy = (
        str(recommended_actions[0])
        if recommended_actions
        else "Make the smallest targeted repair based on the failure evidence, then rerun the listed verification commands."
    )
    return _redact(strategy)[:1200]


def _failure_summary(evidence: FailureEvidencePacketResponse) -> str:
    source = evidence.failed_command_summary or "; ".join(evidence.blocked_reasons) or "failure evidence collected"
    return _redact(f"{evidence.failure_type} at {evidence.failed_step}: {source}")[:600]


def _suspected_root_causes(
    evidence: FailureEvidencePacketResponse,
    common_findings: list[Any],
    job_findings: list[str],
) -> list[str]:
    causes = _unique([*evidence.blocked_reasons[:4], *common_findings[:4], *job_findings[:4]])[:8]
    return causes or [f"Failure type {evidence.failure_type} requires manual diagnosis from the collected evidence."]


def _evidence_by_source(evidence: FailureEvidencePacketResponse, analysis, artifact_summaries: list[Any]) -> list[RepairEvidenceBySource]:
    sources = [
        RepairEvidenceBySource(
            source=evidence.failed_step,
            summary=evidence.failed_command_summary or "; ".join(evidence.blocked_reasons) or evidence.failure_type,
            artifact_ids=evidence.related_artifact_ids,
            agent_run_ids=evidence.related_agent_run_ids,
            dispatch_batch_id=evidence.related_dispatch_batch_id,
            dispatch_job_ids=evidence.related_dispatch_job_ids,
        ),
        RepairEvidenceBySource(
            source="multi_ai_evidence_run",
            summary=f"analysis_status={analysis.overall_status}",
            artifact_ids=analysis.source_artifact_ids,
            dispatch_batch_id=analysis.dispatch_batch_id,
            dispatch_job_ids=[job.dispatch_job_id for job in analysis.jobs if job.dispatch_job_id],
            agent_run_ids=[job.agent_run_id for job in analysis.jobs if job.agent_run_id],
        ),
    ]
    for item in artifact_summaries[:6]:
        data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        artifact_id = data.get("artifact_id")
        sources.append(RepairEvidenceBySource(
            source="answer_synthesis_artifact",
            summary=str(data.get("summary") or data.get("filename") or "artifact summary")[:500],
            artifact_ids=[artifact_id] if isinstance(artifact_id, int) else [],
        ))
    return sources


def _commands_to_verify(evidence: FailureEvidencePacketResponse) -> list[str]:
    commands: list[str] = []
    summary = evidence.failed_command_summary.strip()
    if summary and not summary.startswith("artifact:") and not summary.startswith("agent_run:"):
        commands.append(summary[:240])
    if evidence.failure_type in {"sandbox_failed", "sandbox_gate_blocked", "verification_failed"}:
        commands.append("Run the targeted failing pytest/build command from the failure evidence.")
    if evidence.failure_type == "sonar_failed":
        commands.append("Re-run the SonarCloud check or inspect the latest SonarCloud issue list after the fix.")
    if evidence.failure_type == "browser_ai_failed":
        commands.append("Re-run the Browser AI mock smoke or the relevant frontend display smoke.")
    commands.append("Run the smallest relevant regression test before requesting review.")
    return _unique(commands)[:6]


def _extract_file_hints(text: str) -> list[str]:
    hints: list[str] = []
    for token in text.replace("\\", "/").replace('"', " ").replace("'", " ").split():
        clean = token.strip(" ,;:()[]{}")
        if "/" not in clean:
            continue
        if clean.endswith((".py", ".ts", ".vue", ".js", ".json", ".md", ".css")):
            hints.append(clean)
    return _unique(hints)[:10]


def _codex_handoff_prompt(task: Task, packet: RepairPacketResponse) -> str:
    return "\n".join([
        "Read AGENTS.md before acting.",
        "Verify current master before making any repair; do not trust stale commit hints.",
        f"Task #{task.id}: {task.title}",
        f"Failure summary: {packet.failure_summary}",
        "Use this repair packet to make one narrow fix only.",
        f"Recommended fix strategy: {packet.recommended_fix_strategy}",
        f"Commands to verify: {', '.join(packet.commands_to_verify) or 'choose the smallest relevant verification command'}",
        f"Max attempts: {packet.max_attempts}",
        "Do not do:",
        *[f"- {item}" for item in packet.do_not_do],
        "After repair, report modified files, verification results, remaining risks, and wait for mastermind review before merge.",
    ])


def _redact_packet(packet: RepairPacketResponse) -> RepairPacketResponse:
    return RepairPacketResponse(**_redact_obj(packet.model_dump()))


def _repair_packet_artifact(task_id: int, packet: RepairPacketResponse) -> TaskArtifact:
    content = _safe_json(packet.model_dump())
    data = content.encode("utf-8")
    return TaskArtifact(
        task_id=task_id,
        artifact_type="repair_packet",
        filename=f"repair_packet_task_{task_id}.json",
        content=content,
        metadata_json=_safe_json({"type": "repair_packet", "pending_artifact_id": True}),
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


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


def _safe_json(payload: dict[str, Any]) -> str:
    return _redact(json.dumps(payload, ensure_ascii=False, default=str)) or "{}"


def _redact(value: str | None) -> str:
    return redact_secrets(value or "")


def _unique(items: list[Any]) -> list[str]:
    values: list[str] = []
    for item in items:
        if item in (None, ""):
            continue
        text = _redact(str(item)).strip()
        if text and text not in values:
            values.append(text)
    return values


def _redact_obj(value: Any) -> Any:
    if isinstance(value, str):
        return _redact(value)
    if isinstance(value, list):
        return [_redact_obj(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_obj(item) for key, item in value.items()}
    return value

import json
import re
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
from app.schemas.answer_synthesis import (
    AnswerSynthesisPreviewRequest,
    AnswerSynthesisPreviewResponse,
    ArtifactSummary,
)
from app.services.ai_output_governance_service import redact_secrets


SECRET_TOKEN_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}|gh[opsu]_[A-Za-z0-9_]{8,}|AKIA[0-9A-Z]{8,})",
    re.IGNORECASE,
)


def _redact(text: str | None) -> str:
    if not text:
        return ""
    return SECRET_TOKEN_RE.sub("***REDACTED***", redact_secrets(text))


def _loads_list(raw: str | None) -> list[int]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, int)]


def _loads_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _short(text: str, limit: int = 220) -> str:
    clean = " ".join(_redact(text).split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def _risk_from_run(run: AgentRun | None) -> list[str]:
    if not run:
        return []
    risks: list[str] = []
    if run.risk_level in ("high", "critical"):
        risks.append(f"agent_run_{run.id}_risk_level_{run.risk_level}")
    raw = _loads_dict(run.raw_result_json)
    validation = raw.get("validation") if isinstance(raw.get("validation"), dict) else {}
    governance = raw.get("governance") if isinstance(raw.get("governance"), dict) else {}
    dispatch = raw.get("dispatch") if isinstance(raw.get("dispatch"), dict) else {}
    pipeline_status = dispatch.get("pipeline_status") or raw.get("pipeline_status")
    if validation.get("requires_human") or governance.get("requires_human"):
        risks.append(f"agent_run_{run.id}_requires_human")
    if pipeline_status in ("sandbox_failed", "sandbox_gate_blocked", "ai_failed"):
        risks.append(str(pipeline_status))
    raw_text = json.dumps(raw, ensure_ascii=False).lower()
    for marker in ("malformed_response", "sandbox_failed", "sandbox_gate_blocked", "human_required"):
        if marker in raw_text and marker not in risks:
            risks.append(marker)
    return risks


async def _select_batch(
    db: AsyncSession,
    task_id: int,
    dispatch_batch_id: int | None,
) -> DispatchBatch | None:
    stmt = (
        select(DispatchBatch)
        .where(DispatchBatch.task_id == task_id)
        .options(selectinload(DispatchBatch.jobs))
        .order_by(DispatchBatch.id.desc())
    )
    if dispatch_batch_id is not None:
        stmt = stmt.where(DispatchBatch.id == dispatch_batch_id)
    result = await db.execute(stmt)
    return result.scalars().first()


async def preview(
    db: AsyncSession,
    body: AnswerSynthesisPreviewRequest,
) -> AnswerSynthesisPreviewResponse:
    task = await db.get(Task, body.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")

    batch = await _select_batch(db, body.task_id, body.dispatch_batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="dispatch_batch_not_found")

    jobs = sorted(list(batch.jobs), key=lambda item: item.sequence_no)
    source_job_ids = [job.id for job in jobs]
    source_agent_run_ids = sorted({job.agent_run_id for job in jobs if job.agent_run_id})
    artifact_ids = sorted({artifact_id for job in jobs for artifact_id in _loads_list(job.artifact_ids_json)})

    runs_by_id: dict[int, AgentRun] = {}
    if source_agent_run_ids:
        run_result = await db.execute(select(AgentRun).where(AgentRun.id.in_(source_agent_run_ids)))
        runs_by_id = {run.id: run for run in run_result.scalars().all()}

    artifacts_by_id: dict[int, TaskArtifact] = {}
    if artifact_ids:
        artifact_result = await db.execute(select(TaskArtifact).where(TaskArtifact.id.in_(artifact_ids)))
        artifacts_by_id = {artifact.id: artifact for artifact in artifact_result.scalars().all()}

    succeeded_jobs = sum(1 for job in jobs if job.status == "succeeded")
    failed_jobs = sum(1 for job in jobs if job.status == "failed")
    blocked_jobs = sum(1 for job in jobs if job.status == "blocked")

    common_findings: list[str] = []
    risks: list[str] = []
    next_questions: list[str] = []
    modes: set[str] = set()
    statuses: set[str] = set()

    for job in jobs:
        modes.add(job.mode)
        statuses.add(job.status)
        run = runs_by_id.get(job.agent_run_id or 0)
        if job.status == "succeeded" and run and run.output_summary:
            common_findings.append(f"job_{job.id}: {_short(run.output_summary)}")
        if job.status == "blocked":
            risks.append(f"job_{job.id}_blocked: {_short(job.error_message or 'blocked')}")
            next_questions.append(f"How should job {job.id} be unblocked?")
        if job.status == "failed":
            message = job.error_message or (run.error_message if run else "") or "failed"
            risks.append(f"job_{job.id}_failed: {_short(message)}")
            next_questions.append(f"What retry or fix is needed for job {job.id}?")
        if run and run.error_message:
            risks.append(f"agent_run_{run.id}_error: {_short(run.error_message)}")
        risks.extend(_risk_from_run(run))

    artifact_summaries: list[ArtifactSummary] = []
    if body.include_artifacts:
        for artifact_id in artifact_ids:
            artifact = artifacts_by_id.get(artifact_id)
            if not artifact:
                continue
            content = _redact(artifact.content or "")
            limit = body.max_artifact_chars
            truncated = len(content) > limit
            artifact_summaries.append(
                ArtifactSummary(
                    artifact_id=artifact.id,
                    filename=artifact.filename,
                    artifact_type=artifact.artifact_type,
                    summary=content[:limit] if limit else "",
                    is_truncated=truncated,
                )
            )
            if artifact.filename and "patch" in artifact.filename.lower():
                risks.append("patch_artifact_present")

    disagreements: list[str] = []
    if len(statuses) > 1:
        disagreements.append(f"job_statuses_differ: {', '.join(sorted(statuses))}")
    if failed_jobs or blocked_jobs:
        disagreements.append("not_all_jobs_succeeded")
    if len(modes) > 1:
        disagreements.append(f"multiple_modes_present: {', '.join(sorted(modes))}")

    unique_risks = list(dict.fromkeys(_redact(risk) for risk in risks if risk))
    recommended_actions = _recommended_actions(succeeded_jobs, failed_jobs, blocked_jobs, unique_risks, artifact_ids)
    if not next_questions and jobs:
        next_questions.append("Should another AI review the synthesized result before final action?")

    synthesis_status = "empty" if not jobs else ("attention_required" if failed_jobs or blocked_jobs or unique_risks else "ready")
    confidence = _confidence(jobs, succeeded_jobs, failed_jobs, blocked_jobs, unique_risks)

    return AnswerSynthesisPreviewResponse(
        task_id=body.task_id,
        dispatch_batch_id=batch.id,
        synthesis_status=synthesis_status,
        job_count=len(jobs),
        succeeded_jobs=succeeded_jobs,
        failed_jobs=failed_jobs,
        blocked_jobs=blocked_jobs,
        common_findings=list(dict.fromkeys(common_findings))[:10],
        disagreements=disagreements,
        risks=unique_risks,
        recommended_actions=recommended_actions,
        next_questions=list(dict.fromkeys(_redact(item) for item in next_questions))[:8],
        artifact_summaries=artifact_summaries,
        source_job_ids=source_job_ids,
        source_agent_run_ids=source_agent_run_ids,
        source_artifact_ids=artifact_ids,
        confidence=confidence,
        safety_notes=[
            "Deterministic rule-based preview; no AI provider called.",
            "Stateless preview; no AgentRun, TaskArtifact, or TaskEvent is created.",
            "No repository path, environment file, credential reference, shell, PR, CI, Sonar, deploy, approve, or merge action is used.",
        ],
    )


def _recommended_actions(
    succeeded_jobs: int,
    failed_jobs: int,
    blocked_jobs: int,
    risks: list[str],
    artifact_ids: list[int],
) -> list[str]:
    actions: list[str] = []
    if blocked_jobs:
        actions.append("Resolve blocked DispatchJob reasons before relying on the synthesis.")
    if failed_jobs:
        actions.append("Retry or repair failed DispatchJobs, then run synthesis preview again.")
    if any("sandbox_gate_blocked" in risk for risk in risks):
        actions.append("Do not proceed to PR; inspect Sandbox Gate blockers first.")
    if any("sandbox_failed" in risk for risk in risks):
        actions.append("Fix Patch Sandbox failures before downstream review.")
    if any("patch_artifact_present" in risk for risk in risks) or artifact_ids:
        actions.append("Review related artifacts and verify Patch Sandbox / Sandbox Gate status.")
    if succeeded_jobs and not failed_jobs and not blocked_jobs and not risks:
        actions.append("Proceed to human review or local verification; no automatic approval is implied.")
    if not actions:
        actions.append("Collect more AI job outputs before making a final decision.")
    return actions


def _confidence(
    jobs: list[DispatchJob],
    succeeded_jobs: int,
    failed_jobs: int,
    blocked_jobs: int,
    risks: list[str],
) -> float:
    if not jobs:
        return 0.0
    score = succeeded_jobs / len(jobs)
    score -= 0.15 * failed_jobs
    score -= 0.2 * blocked_jobs
    score -= min(0.3, 0.05 * len(risks))
    return round(max(0.0, min(1.0, score)), 2)
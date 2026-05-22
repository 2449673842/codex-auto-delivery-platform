import json
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


SECRET_PREFIXES = ("sk-", "ghp_", "gho_", "ghu_", "ghs_", "AKIA")
TOKEN_TRIM_CHARS = "\"'`.,;:()[]{}<>"


def _redact(text: str | None) -> str:
    if not text:
        return ""
    return _redact_prefixed_tokens(redact_secrets(text))


def _redact_prefixed_tokens(text: str) -> str:
    redacted = text
    for token in text.split():
        candidate = token.strip(TOKEN_TRIM_CHARS)
        if _looks_like_secret_token(candidate):
            redacted = redacted.replace(candidate, "***REDACTED***")
    return redacted


def _looks_like_secret_token(token: str) -> bool:
    if len(token) < 12:
        return False
    if not token.startswith(SECRET_PREFIXES):
        return False
    return all(char.isalnum() or char in "-_" for char in token)


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


def _dict_child(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    return value if isinstance(value, dict) else {}


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
    validation = _dict_child(raw, "validation")
    governance = _dict_child(raw, "governance")
    dispatch = _dict_child(raw, "dispatch")
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

    runs_by_id = await _runs_by_id(db, source_agent_run_ids)
    artifacts_by_id = await _artifacts_by_id(db, artifact_ids)
    counts = _job_counts(jobs)
    common_findings, risks, next_questions, modes, statuses = _summarize_jobs(jobs, runs_by_id)
    artifact_summaries = _summarize_artifacts(body, artifact_ids, artifacts_by_id, risks)
    unique_risks = list(dict.fromkeys(_redact(risk) for risk in risks if risk))
    recommended_actions = _recommended_actions(
        counts["succeeded"], counts["failed"], counts["blocked"], unique_risks, artifact_ids
    )
    if not next_questions and jobs:
        next_questions.append("Should another AI review the synthesized result before final action?")

    return AnswerSynthesisPreviewResponse(
        task_id=body.task_id,
        dispatch_batch_id=batch.id,
        synthesis_status=_synthesis_status(jobs, counts, unique_risks),
        job_count=len(jobs),
        succeeded_jobs=counts["succeeded"],
        failed_jobs=counts["failed"],
        blocked_jobs=counts["blocked"],
        common_findings=list(dict.fromkeys(common_findings))[:10],
        disagreements=_disagreements(statuses, modes, counts),
        risks=unique_risks,
        recommended_actions=recommended_actions,
        next_questions=list(dict.fromkeys(_redact(item) for item in next_questions))[:8],
        artifact_summaries=artifact_summaries,
        source_job_ids=source_job_ids,
        source_agent_run_ids=source_agent_run_ids,
        source_artifact_ids=artifact_ids,
        confidence=_confidence(jobs, counts, unique_risks),
        safety_notes=[
            "Deterministic rule-based preview; no AI provider called.",
            "Stateless preview; no AgentRun, TaskArtifact, or TaskEvent is created.",
            "No repository path, environment file, credential reference, shell, PR, CI, Sonar, deploy, approve, or merge action is used.",
        ],
    )


async def _runs_by_id(db: AsyncSession, run_ids: list[int]) -> dict[int, AgentRun]:
    if not run_ids:
        return {}
    result = await db.execute(select(AgentRun).where(AgentRun.id.in_(run_ids)))
    return {run.id: run for run in result.scalars().all()}


async def _artifacts_by_id(db: AsyncSession, artifact_ids: list[int]) -> dict[int, TaskArtifact]:
    if not artifact_ids:
        return {}
    result = await db.execute(select(TaskArtifact).where(TaskArtifact.id.in_(artifact_ids)))
    return {artifact.id: artifact for artifact in result.scalars().all()}


def _job_counts(jobs: list[DispatchJob]) -> dict[str, int]:
    return {
        "succeeded": sum(1 for job in jobs if job.status == "succeeded"),
        "failed": sum(1 for job in jobs if job.status == "failed"),
        "blocked": sum(1 for job in jobs if job.status == "blocked"),
    }


def _summarize_jobs(
    jobs: list[DispatchJob],
    runs_by_id: dict[int, AgentRun],
) -> tuple[list[str], list[str], list[str], set[str], set[str]]:
    findings: list[str] = []
    risks: list[str] = []
    questions: list[str] = []
    modes: set[str] = set()
    statuses: set[str] = set()
    for job in jobs:
        modes.add(job.mode)
        statuses.add(job.status)
        run = runs_by_id.get(job.agent_run_id or 0)
        _collect_success_finding(job, run, findings)
        _collect_job_risk(job, run, risks, questions)
        risks.extend(_risk_from_run(run))
    return findings, risks, questions, modes, statuses


def _collect_success_finding(job: DispatchJob, run: AgentRun | None, findings: list[str]) -> None:
    if job.status == "succeeded" and run and run.output_summary:
        findings.append(f"job_{job.id}: {_short(run.output_summary)}")


def _collect_job_risk(
    job: DispatchJob,
    run: AgentRun | None,
    risks: list[str],
    questions: list[str],
) -> None:
    if job.status == "blocked":
        risks.append(f"job_{job.id}_blocked: {_short(job.error_message or 'blocked')}")
        questions.append(f"How should job {job.id} be unblocked?")
    if job.status == "failed":
        message = job.error_message or (run.error_message if run else "") or "failed"
        risks.append(f"job_{job.id}_failed: {_short(message)}")
        questions.append(f"What retry or fix is needed for job {job.id}?")
    if run and run.error_message:
        risks.append(f"agent_run_{run.id}_error: {_short(run.error_message)}")


def _summarize_artifacts(
    body: AnswerSynthesisPreviewRequest,
    artifact_ids: list[int],
    artifacts_by_id: dict[int, TaskArtifact],
    risks: list[str],
) -> list[ArtifactSummary]:
    if not body.include_artifacts:
        return []
    summaries: list[ArtifactSummary] = []
    for artifact_id in artifact_ids:
        artifact = artifacts_by_id.get(artifact_id)
        if not artifact:
            continue
        summaries.append(_artifact_summary(artifact, body.max_artifact_chars))
        filename = artifact.filename or ""
        if "patch" in filename.lower():
            risks.append("patch_artifact_present")
    return summaries


def _artifact_summary(artifact: TaskArtifact, max_chars: int) -> ArtifactSummary:
    content = _redact(artifact.content or "")
    limit = max(0, max_chars)
    return ArtifactSummary(
        artifact_id=artifact.id,
        filename=_redact(artifact.filename),
        artifact_type=artifact.artifact_type or "unknown",
        summary=content[:limit] if limit else "",
        is_truncated=len(content) > limit,
    )


def _disagreements(statuses: set[str], modes: set[str], counts: dict[str, int]) -> list[str]:
    disagreements: list[str] = []
    if len(statuses) > 1:
        disagreements.append(f"job_statuses_differ: {', '.join(sorted(statuses))}")
    if counts["failed"] or counts["blocked"]:
        disagreements.append("not_all_jobs_succeeded")
    if len(modes) > 1:
        disagreements.append(f"multiple_modes_present: {', '.join(sorted(modes))}")
    return disagreements


def _synthesis_status(jobs: list[DispatchJob], counts: dict[str, int], risks: list[str]) -> str:
    if not jobs:
        return "empty"
    if counts["failed"] or counts["blocked"] or risks:
        return "attention_required"
    return "ready"


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


def _confidence(jobs: list[DispatchJob], counts: dict[str, int], risks: list[str]) -> float:
    if not jobs:
        return 0.0
    score = counts["succeeded"] / len(jobs)
    score -= 0.15 * counts["failed"]
    score -= 0.2 * counts["blocked"]
    score -= min(0.3, 0.05 * len(risks))
    return round(max(0.0, min(1.0, score)), 2)
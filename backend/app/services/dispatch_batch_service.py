import json
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.dispatch_batch import DispatchBatch
from app.models.dispatch_job import DispatchJob
from app.models.task import Task
from app.models.task_artifact import TaskArtifact
from app.schemas.ai_context_packet import VALID_MODES
from app.schemas.dispatch_batch import (
    DispatchBatchPreviewResponse,
    DispatchBatchRequest,
    DispatchBatchResponse,
    DispatchJobPreview,
    DispatchJobRequest,
    VALID_BATCH_MODES,
)
from app.services import ai_dispatch_service
from app.services.ai_output_governance_service import redact_secrets
from app.services.prompt_template_service import preview as prompt_preview


ALLOWED_PROVIDERS = {"openai"}
_MODE_TO_EXPECTED_ARTIFACT = {
    "planning": "plan.md",
    "patch_generation": "patch.diff",
    "review": "review.md",
    "risk": "risk_report.json",
    "browser_reviewer": "browser_ai_review.json",
}


def _redact_text(value: str | None) -> str | None:
    if value is None:
        return None
    redacted = redact_secrets(value)
    api_key = getattr(settings, "openai_api_key", "") or ""
    if api_key:
        redacted = redacted.replace(api_key, "***REDACTED***")
    return redacted


def _safe_json(payload: dict) -> str:
    return _redact_text(json.dumps(payload, ensure_ascii=False)) or "{}"


async def _get_task(db: AsyncSession, task_id: int) -> Task:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status == "archived":
        raise HTTPException(status_code=409, detail="Task is archived")
    return task


def _validate_batch_mode(batch_mode: str) -> None:
    if batch_mode not in VALID_BATCH_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown batch_mode '{batch_mode}'",
        )


def _validate_job(job: DispatchJobRequest) -> None:
    if job.provider not in ALLOWED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Provider '{job.provider}' is not supported in S12")
    if job.mode not in VALID_MODES:
        raise HTTPException(status_code=400, detail=f"Unknown mode '{job.mode}'")


def _default_question(task_goal: str, index: int) -> str:
    base = task_goal.strip() or "Review this task"
    return base if index == 1 else f"{base} (job {index})"


def _normalized_jobs(body: DispatchBatchRequest) -> list[DispatchJobRequest]:
    jobs = body.jobs or [
        DispatchJobRequest(
            question=_default_question(body.task_goal, 1),
            provider="openai",
            model="gpt-4o-mini",
            mode="review",
        )
    ]
    return jobs


def _safety_boundary(provider: str, mode: str) -> dict:
    return {
        "provider_allowed": provider in settings.provider_allowlist,
        "execution_enabled": settings.ai_execution_enabled,
        "openai_key_present": bool(settings.openai_api_key),
        "mode_valid": mode in VALID_MODES,
        "no_project_root_path": True,
        "no_env_read": True,
        "no_sensitive_reference_read": True,
        "no_shell_subprocess": True,
        "no_external_pr_creation": True,
        "no_external_quality_calls": True,
        "no_external_release_actions": True,
        "no_auto_approve_merge": True,
    }


def _job_preview(body: DispatchBatchRequest, job: DispatchJobRequest, sequence_no: int) -> DispatchJobPreview:
    _validate_job(job)
    preview = prompt_preview(
        task_goal=job.question or body.task_goal,
        module_name=job.module_name,
        task_type=job.task_type,
        mode=job.mode,
    )
    expected = _MODE_TO_EXPECTED_ARTIFACT.get(job.mode, "")
    if preview.output_contract.expected_artifacts:
        expected = preview.output_contract.expected_artifacts[0]
    return DispatchJobPreview(
        sequence_no=sequence_no,
        question=job.question,
        provider=job.provider,
        model=job.model,
        mode=job.mode,
        prompt_hash=preview.prompt_hash,
        context_packet_hash=preview.context_packet_hash,
        expected_artifact_type=expected,
        safety_boundary=_safety_boundary(job.provider, job.mode),
    )


async def preview(db: AsyncSession, body: DispatchBatchRequest) -> DispatchBatchPreviewResponse:
    _validate_batch_mode(body.batch_mode)
    await _get_task(db, body.task_id)
    jobs = [
        _job_preview(body, job, index)
        for index, job in enumerate(_normalized_jobs(body), start=1)
    ]
    return DispatchBatchPreviewResponse(
        task_id=body.task_id,
        batch_mode=body.batch_mode,
        task_goal=body.task_goal,
        jobs=jobs,
        would_execute=False,
    )


def _preflight_block_reason(job: DispatchJobRequest) -> str | None:
    if not settings.ai_execution_enabled:
        return "AI_EXECUTION_ENABLED is not set"
    if not settings.openai_api_key:
        return "OPENAI_API_KEY is not set"
    if job.provider not in settings.provider_allowlist:
        return f"{job.provider} not in provider allowlist"
    if job.mode not in VALID_MODES:
        return f"Unknown mode '{job.mode}'"
    return None


async def _task_artifact_id_set(db: AsyncSession, task_id: int) -> set[int]:
    result = await db.execute(
        select(TaskArtifact.id).where(TaskArtifact.task_id == task_id)
    )
    return {artifact_id for artifact_id in result.scalars().all() if isinstance(artifact_id, int)}


def _job_response_from_model(job: DispatchJob) -> DispatchJobPreview:
    artifact_ids = []
    if job.artifact_ids_json:
        try:
            parsed = json.loads(job.artifact_ids_json)
            if isinstance(parsed, list):
                artifact_ids = [x for x in parsed if isinstance(x, int)]
        except json.JSONDecodeError:
            artifact_ids = []
    return DispatchJobPreview(
        dispatch_job_id=job.id,
        sequence_no=job.sequence_no,
        question=job.question,
        provider=job.provider,
        model=job.model,
        mode=job.mode,
        status=job.status,
        prompt_hash=job.prompt_hash or "",
        context_packet_hash=job.context_packet_hash or "",
        expected_artifact_type=job.expected_artifact_type or "",
        safety_boundary=json.loads(job.metadata_json or "{}").get("safety_boundary", {}),
        agent_run_id=job.agent_run_id,
        artifact_ids=artifact_ids,
        error_message=job.error_message,
    )


def _batch_summary(jobs: list[DispatchJob]) -> dict:
    counts: dict[str, int] = {}
    for job in jobs:
        counts[job.status] = counts.get(job.status, 0) + 1
    return {"job_count": len(jobs), "status_counts": counts}


async def execute(db: AsyncSession, body: DispatchBatchRequest) -> DispatchBatchResponse:
    _validate_batch_mode(body.batch_mode)
    task = await _get_task(db, body.task_id)
    preview_response = await preview(db, body)
    batch = DispatchBatch(
        task_id=task.id,
        batch_mode=body.batch_mode,
        status="running",
        task_goal=_redact_text(body.task_goal),
        metadata_json=_safe_json({
            "batch_mode": body.batch_mode,
            "redaction_applied": True,
            "s12_scope": "dispatch_batch_routed_jobs_mvp",
        }),
    )
    db.add(batch)
    await db.flush()
    await db.refresh(batch)

    created_jobs: list[DispatchJob] = []
    request_jobs = _normalized_jobs(body)
    for job_request, job_preview in zip(request_jobs, preview_response.jobs, strict=True):
        now = datetime.now(timezone.utc)
        dispatch_job = DispatchJob(
            batch_id=batch.id,
            task_id=task.id,
            sequence_no=job_preview.sequence_no,
            question=_redact_text(job_request.question) or "",
            provider=job_request.provider,
            model=job_request.model,
            mode=job_request.mode,
            status="queued",
            prompt_hash=job_preview.prompt_hash,
            context_packet_hash=job_preview.context_packet_hash,
            expected_artifact_type=job_preview.expected_artifact_type,
            metadata_json=_safe_json({"safety_boundary": job_preview.safety_boundary}),
        )
        db.add(dispatch_job)
        await db.flush()

        block_reason = _preflight_block_reason(job_request)
        if block_reason:
            dispatch_job.status = "blocked"
            dispatch_job.error_message = block_reason
            dispatch_job.finished_at = now
            created_jobs.append(dispatch_job)
            continue

        dispatch_job.status = "running"
        dispatch_job.started_at = now
        await db.flush()
        before_artifact_ids = await _task_artifact_id_set(db, task.id)
        result = await ai_dispatch_service.execute(
            db=db,
            task_goal=job_request.question or body.task_goal,
            module_name=job_request.module_name,
            task_type=job_request.task_type,
            mode=job_request.mode,
            task_id=task.id,
            project_id=task.project_id,
        )
        after_artifact_ids = await _task_artifact_id_set(db, task.id)
        new_artifact_ids = sorted(after_artifact_ids - before_artifact_ids)
        dispatch_job.agent_run_id = result.agent_run_id or None
        dispatch_job.artifact_ids_json = json.dumps(new_artifact_ids)
        dispatch_job.prompt_hash = result.prompt_hash
        dispatch_job.context_packet_hash = result.context_packet_hash
        dispatch_job.status = "succeeded" if result.status == "succeeded" else "failed"
        dispatch_job.error_message = None if result.status == "succeeded" else result.output_summary
        dispatch_job.finished_at = datetime.now(timezone.utc)
        created_jobs.append(dispatch_job)

    batch.status = "succeeded"
    if any(job.status == "failed" for job in created_jobs):
        batch.status = "failed"
    elif any(job.status == "blocked" for job in created_jobs):
        batch.status = "blocked"
    batch.summary_json = _safe_json(_batch_summary(created_jobs))
    await db.flush()

    return DispatchBatchResponse(
        dispatch_batch_id=batch.id,
        task_id=batch.task_id,
        batch_mode=batch.batch_mode,
        status=batch.status,
        task_goal=batch.task_goal or "",
        jobs=[_job_response_from_model(job) for job in created_jobs],
        summary=json.loads(batch.summary_json or "{}"),
    )


async def list_for_task(db: AsyncSession, task_id: int) -> list[DispatchBatchResponse]:
    await _get_task(db, task_id)
    result = await db.execute(
        select(DispatchBatch)
        .where(DispatchBatch.task_id == task_id)
        .order_by(DispatchBatch.id)
    )
    batches = result.scalars().unique().all()
    responses: list[DispatchBatchResponse] = []
    for batch in batches:
        jobs_result = await db.execute(
            select(DispatchJob)
            .where(DispatchJob.batch_id == batch.id)
            .order_by(DispatchJob.sequence_no)
        )
        jobs = jobs_result.scalars().all()
        responses.append(
            DispatchBatchResponse(
                dispatch_batch_id=batch.id,
                task_id=batch.task_id,
                batch_mode=batch.batch_mode,
                status=batch.status,
                task_goal=batch.task_goal or "",
                jobs=[_job_response_from_model(job) for job in jobs],
                summary=json.loads(batch.summary_json or "{}"),
            )
        )
    return responses


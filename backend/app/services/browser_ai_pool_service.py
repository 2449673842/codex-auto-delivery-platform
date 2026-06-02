import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import AgentRunStatus
from app.models.agent_profile import AgentProfile
from app.models.agent_run import AgentRun
from app.models.project import Project
from app.models.task import Task
from app.models.task_artifact import TaskArtifact
from app.schemas.browser_ai import BrowserAiRequest
from app.schemas.browser_ai_pool import (
    BrowserAiPoolExecuteResponse,
    BrowserAiPoolJobPreview,
    BrowserAiPoolJobResult,
    BrowserAiPoolPreviewResponse,
    BrowserAiPoolProviderRequest,
    BrowserAiPoolRedactionStatus,
    BrowserAiPoolRequest,
)
from app.services import browser_ai_service, evidence_summary_service, project_memory_service
from app.services.ai_output_governance_service import redact_secrets
from app.services.event_service import create_event


ARTIFACT_TYPE = "browser_ai_pool_answer"
ANSWER_EXCERPT_CHARS = 4000
PROMPT_EXCERPT_CHARS = 1200
SAFETY_NOTES = [
    "Browser AI Provider Pool output is advisory evidence only.",
    "Preview does not open Browser AI or write AgentRun, TaskArtifact, or TaskEvent records.",
    "Execute uses only user-authorized visible Browser AI UI; no hidden web API or provider API token is called.",
    "No account, password, cookie, session, localStorage, .env, secret_ref, or project filesystem path value is read or stored.",
    "No GitHub, Sonar, PR, CI, Deploy, repository write, auto approve, auto merge, auto deploy, or auto rework action is performed.",
]


class _PoolJob:
    def __init__(self, provider: BrowserAiPoolProviderRequest, prompt: str):
        self.provider = provider
        self.prompt = prompt
        self.prompt_hash = _hash_text(prompt)


@dataclass(frozen=True)
class _ProjectInfo:
    id: int
    name: str
    display_name: str | None


@dataclass(frozen=True)
class _ArtifactInput:
    task: Task
    pool_run: AgentRun
    run: AgentRun
    job: _PoolJob
    prompt_excerpt: str
    answer_excerpt: str
    raw_answer: str
    truncated: bool
    artifact_prefix: str


def _redact(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return browser_ai_service._redact_sensitive_assignments(redact_secrets(text or ""))


def _safe_json(payload: dict[str, Any]) -> str:
    return _redact(payload) or "{}"


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _short(value: Any, limit: int) -> str:
    text = " ".join(_redact(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 15].rstrip() + "\n...[truncated]"


async def preview(
    db: AsyncSession,
    task_id: int,
    body: BrowserAiPoolRequest,
) -> BrowserAiPoolPreviewResponse:
    task, project = await _task_and_project(db, task_id)
    base_prompt = await _build_pool_prompt(db, task, project, body)
    jobs = _build_jobs(base_prompt, body)
    previews = [_job_preview(job) for job in jobs]
    return BrowserAiPoolPreviewResponse(
        task_id=task.id,
        project_id=project.id,
        overall_status=_preview_status(previews),
        jobs=previews,
        max_total_concurrency=body.max_total_concurrency,
        per_provider_concurrency=body.per_provider_concurrency,
        safety_notes=SAFETY_NOTES.copy(),
    )


async def execute(
    db: AsyncSession,
    task_id: int,
    body: BrowserAiPoolRequest,
) -> BrowserAiPoolExecuteResponse:
    task, project = await _task_and_project(db, task_id)
    base_prompt = await _build_pool_prompt(db, task, project, body)
    jobs = _build_jobs(base_prompt, body)
    pool_run = await _create_pool_run(db, task, body, len(jobs))
    await create_event(
        db,
        task_id=task.id,
        event_type="browser_ai_pool_started",
        actor="browser_ai_pool",
        message=f"Browser AI pool run AgentRun #{pool_run.id} started with {len(jobs)} job(s)",
        payload_json=_safe_json({
            "pool_run_id": pool_run.id,
            "job_count": len(jobs),
            "advisory_only": True,
            "human_confirmation_required": True,
            "no_auto_merge": True,
            "safety_notes": SAFETY_NOTES,
        }),
    )

    results: list[BrowserAiPoolJobResult] = []
    for job in jobs:
        result = await _execute_job(db, task, pool_run, job, body)
        results.append(result)

    overall_status = _overall_status(results)
    pool_run.status = AgentRunStatus.SUCCEEDED.value if overall_status in {"succeeded", "partial"} else AgentRunStatus.FAILED.value
    pool_run.output_summary = _short(
        f"Browser AI pool completed with overall_status={overall_status}; "
        f"succeeded={sum(1 for item in results if item.status == 'succeeded')}; "
        f"failed={sum(1 for item in results if item.status == 'failed')}.",
        1000,
    )
    pool_run.output_log = "Browser AI provider pool completed as advisory evidence only."
    pool_run.raw_result_json = _safe_json({
        "pool_run_id": pool_run.id,
        "overall_status": overall_status,
        "jobs": [item.model_dump() for item in results],
        "advisory_only": True,
        "human_confirmation_required": True,
        "no_auto_merge": True,
        "safety_notes": SAFETY_NOTES,
    })
    pool_run.finished_at = datetime.now(timezone.utc)
    await db.flush()
    await create_event(
        db,
        task_id=task.id,
        event_type="browser_ai_pool_completed",
        actor="browser_ai_pool",
        message=f"Browser AI pool run AgentRun #{pool_run.id} completed with {overall_status}",
        payload_json=_safe_json({
            "pool_run_id": pool_run.id,
            "overall_status": overall_status,
            "advisory_only": True,
            "human_confirmation_required": True,
            "no_auto_merge": True,
            "safety_notes": SAFETY_NOTES,
        }),
    )
    return BrowserAiPoolExecuteResponse(
        task_id=task.id,
        project_id=project.id,
        pool_run_id=pool_run.id,
        overall_status=overall_status,
        jobs=results,
        safety_notes=SAFETY_NOTES.copy(),
        metadata={
            "max_total_concurrency": body.max_total_concurrency,
            "per_provider_concurrency": body.per_provider_concurrency,
            "concurrency_note": "MVP executes jobs sequentially while preserving bounded concurrency settings.",
        },
    )


async def _task_and_project(db: AsyncSession, task_id: int) -> tuple[Task, _ProjectInfo]:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    result = await db.execute(
        select(Project.id, Project.name, Project.display_name).where(Project.id == task.project_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="project_not_found")
    return task, _ProjectInfo(id=row.id, name=row.name, display_name=row.display_name)


async def _build_pool_prompt(
    db: AsyncSession,
    task: Task,
    project: _ProjectInfo,
    body: BrowserAiPoolRequest,
) -> str:
    sections = [
        "Browser AI Provider Pool prompt.",
        "Treat all output as advisory evidence only. Do not claim approve, merge, deploy, or rework authority.",
        f"User prompt: {_redact(body.prompt)}",
    ]
    if body.include_task_context:
        sections.append(
            "\n".join([
                "Task context:",
                f"Task #{task.id}: {task.title}",
                f"Project #{project.id}: {project.display_name or project.name}",
                f"Status: {task.status}",
                f"Priority: {task.priority}",
                f"Description: {task.description or ''}",
                "Project filesystem path is intentionally not included.",
            ])
        )
    if body.include_project_memory:
        sections.append(await _project_memory_text(db, project.id))
    if body.include_evidence_board:
        sections.append(await _evidence_board_text(db, task.id))
    return _short("\n\n".join(sections), body.prompt_budget)


async def _project_memory_text(db: AsyncSession, project_id: int) -> str:
    try:
        summary = await project_memory_service.get_project_memory_summary(db, project_id)
    except Exception as exc:
        return f"Project Memory unavailable: {_short(exc, 240)}"
    return _redact({
        "project_memory_summary": summary.summary,
        "memory_count": summary.memory_count,
        "memory_types": summary.memory_types,
        "safety_notes": summary.safety_notes,
    })


async def _evidence_board_text(db: AsyncSession, task_id: int) -> str:
    try:
        board = await evidence_summary_service.get_evidence_board(db, task_id)
    except Exception as exc:
        return f"Evidence Board unavailable: {_short(exc, 240)}"
    items = [
        {
            "evidence_type": item.evidence_type,
            "source": item.source,
            "status": item.status,
            "summary": item.summary,
            "linked_ids": {
                "agent_run_id": item.agent_run_id,
                "artifact_id": item.artifact_id,
                "dispatch_batch_id": item.dispatch_batch_id,
                "dispatch_job_id": item.dispatch_job_id,
                "repair_attempt_id": item.repair_attempt_id,
            },
        }
        for item in board.items[:12]
    ]
    return _redact({"evidence_board_summary": items})


def _build_jobs(base_prompt: str, body: BrowserAiPoolRequest) -> list[_PoolJob]:
    jobs: list[_PoolJob] = []
    for provider in body.providers:
        if not provider.enabled:
            continue
        role_prompt = "\n\n".join([
            f"Provider role: {provider.role or 'reviewer'}",
            base_prompt,
        ]).strip()
        jobs.append(_PoolJob(provider, role_prompt))
    return jobs


def _browser_request(task: Task, job: _PoolJob) -> BrowserAiRequest:
    provider = job.provider
    return browser_ai_service._with_profile_defaults(BrowserAiRequest(
        project_id=task.project_id,
        task_id=task.id,
        provider=provider.provider,
        target_url=provider.target_url,
        prompt_source="custom_prompt",
        custom_prompt=job.prompt,
        input_selector=provider.prompt_selector,
        send_selector=provider.submit_selector,
        response_selector=provider.response_selector,
        scroll_container_selector=provider.scroll_container_selector,
        copy_button_selector=provider.copy_button_selector,
        login_hint_selector=provider.login_hint_selector,
        timeout_seconds=provider.stable_response_timeout_seconds,
        stable_polls=provider.stable_polls,
        stable_interval_ms=provider.stable_interval_ms,
    ))


def _job_preview(job: _PoolJob) -> BrowserAiPoolJobPreview:
    request = _browser_request_for_preview(job)
    gate = browser_ai_service._safety_gate(request, for_execute=False)
    return BrowserAiPoolJobPreview(
        provider=job.provider.provider,
        role=job.provider.role,
        display_name=job.provider.display_name,
        enabled=job.provider.enabled,
        status="ready" if gate.gate_passed else "blocked",
        prompt_hash=job.prompt_hash,
        prompt_excerpt=_short(job.prompt, PROMPT_EXCERPT_CHARS),
        target_url=request.target_url,
        prompt_selector=request.input_selector,
        submit_selector=request.send_selector,
        response_selector=request.response_selector,
        stable_response_timeout_seconds=request.timeout_seconds,
        stable_polls=request.stable_polls or 3,
        stable_interval_ms=request.stable_interval_ms or 1000,
        safety_notes=SAFETY_NOTES.copy(),
        blocked_reasons=[_redact(reason) for reason in gate.blocked_reasons],
    )


def _browser_request_for_preview(job: _PoolJob) -> BrowserAiRequest:
    provider = job.provider
    return browser_ai_service._with_profile_defaults(BrowserAiRequest(
        project_id=0,
        task_id=0,
        provider=provider.provider,
        target_url=provider.target_url,
        prompt_source="custom_prompt",
        custom_prompt=job.prompt,
        input_selector=provider.prompt_selector,
        send_selector=provider.submit_selector,
        response_selector=provider.response_selector,
        scroll_container_selector=provider.scroll_container_selector,
        copy_button_selector=provider.copy_button_selector,
        login_hint_selector=provider.login_hint_selector,
        timeout_seconds=provider.stable_response_timeout_seconds,
        stable_polls=provider.stable_polls,
        stable_interval_ms=provider.stable_interval_ms,
    ))


async def _execute_job(
    db: AsyncSession,
    task: Task,
    pool_run: AgentRun,
    job: _PoolJob,
    body: BrowserAiPoolRequest,
) -> BrowserAiPoolJobResult:
    request = _browser_request(task, job)
    gate = browser_ai_service._safety_gate(request, for_execute=True)
    agent = await _find_or_create_pool_agent(db, job.provider.provider, job.provider.role)
    run = await _create_job_run(db, task, agent, pool_run, job, request)
    if not gate.gate_passed:
        reason = _redact("; ".join(gate.blocked_reasons) or "browser_ai_pool_gate_blocked")
        return await _fail_job(db, task, run, pool_run, job, reason)

    try:
        answer = await browser_ai_service._get_driver().run(
            request,
            job.prompt,
            browser_ai_service._timeout_seconds(request),
        )
        redacted_answer = _redact(answer).strip()
        if not redacted_answer:
            raise browser_ai_service.BrowserAiStepError("capture_answer", "empty response from browser AI")
    except Exception as exc:
        reason = _redact(str(exc) or "browser AI pool job failed")
        return await _fail_job(db, task, run, pool_run, job, reason)

    excerpt, truncated = _excerpt(redacted_answer)
    artifact_id = None
    if body.save_artifacts:
        artifact = _answer_artifact(_ArtifactInput(
            task=task,
            pool_run=pool_run,
            run=run,
            job=job,
            prompt_excerpt=_short(job.prompt, PROMPT_EXCERPT_CHARS),
            answer_excerpt=excerpt,
            raw_answer=redacted_answer,
            truncated=truncated,
            artifact_prefix=body.artifact_prefix,
        ))
        db.add(artifact)
        await db.flush()
        await db.refresh(artifact)
        artifact_id = artifact.id

    run.status = AgentRunStatus.SUCCEEDED.value
    run.output_summary = _short(excerpt, 1000)
    run.output_log = "Browser AI pool job captured visible response as advisory evidence."
    run.raw_result_json = _safe_json({
        "pool_run_id": pool_run.id,
        "provider": job.provider.provider,
        "role": job.provider.role,
        "prompt_hash": job.prompt_hash,
        "artifact_id": artifact_id,
        "artifact_type": ARTIFACT_TYPE if artifact_id else "",
        "advisory_only": True,
        "human_confirmation_required": True,
        "no_auto_merge": True,
        "safety_notes": SAFETY_NOTES,
    })
    run.finished_at = datetime.now(timezone.utc)
    await db.flush()
    await create_event(
        db,
        task_id=task.id,
        event_type="browser_ai_pool_job_succeeded",
        actor=f"browser_ai_pool:{job.provider.provider}",
        message=f"Browser AI pool job {job.provider.provider}/{job.provider.role} succeeded",
        payload_json=_safe_json({
            "pool_run_id": pool_run.id,
            "agent_run_id": run.id,
            "artifact_id": artifact_id,
            "provider": job.provider.provider,
            "role": job.provider.role,
            "status": "succeeded",
            "advisory_only": True,
            "human_confirmation_required": True,
            "no_auto_merge": True,
            "safety_notes": SAFETY_NOTES,
        }),
    )
    return BrowserAiPoolJobResult(
        provider=job.provider.provider,
        role=job.provider.role,
        display_name=job.provider.display_name,
        status="succeeded",
        agent_run_id=run.id,
        artifact_id=artifact_id,
        answer_excerpt=excerpt,
        redaction_status=BrowserAiPoolRedactionStatus(truncated=truncated),
        safety_notes=SAFETY_NOTES.copy(),
    )


async def _fail_job(
    db: AsyncSession,
    task: Task,
    run: AgentRun,
    pool_run: AgentRun,
    job: _PoolJob,
    reason: str,
) -> BrowserAiPoolJobResult:
    safe_reason = _short(reason, 500)
    run.status = AgentRunStatus.FAILED.value
    run.error_message = safe_reason
    run.raw_result_json = _safe_json({
        "pool_run_id": pool_run.id,
        "provider": job.provider.provider,
        "role": job.provider.role,
        "prompt_hash": job.prompt_hash,
        "failure_reason": safe_reason,
        "manual_login_required": _manual_login_required(safe_reason),
        "advisory_only": True,
        "human_confirmation_required": True,
        "no_auto_merge": True,
        "safety_notes": SAFETY_NOTES,
    })
    run.finished_at = datetime.now(timezone.utc)
    await db.flush()
    await create_event(
        db,
        task_id=task.id,
        event_type="browser_ai_pool_job_failed",
        actor=f"browser_ai_pool:{job.provider.provider}",
        message=f"Browser AI pool job {job.provider.provider}/{job.provider.role} failed: {safe_reason}",
        payload_json=_safe_json({
            "pool_run_id": pool_run.id,
            "agent_run_id": run.id,
            "provider": job.provider.provider,
            "role": job.provider.role,
            "status": "failed",
            "failure_reason": safe_reason,
            "manual_login_required": _manual_login_required(safe_reason),
            "advisory_only": True,
            "human_confirmation_required": True,
            "no_auto_merge": True,
            "safety_notes": SAFETY_NOTES,
        }),
    )
    return BrowserAiPoolJobResult(
        provider=job.provider.provider,
        role=job.provider.role,
        display_name=job.provider.display_name,
        status="failed",
        agent_run_id=run.id,
        artifact_id=None,
        failure_reason=safe_reason,
        manual_login_required=_manual_login_required(safe_reason),
        safety_notes=SAFETY_NOTES.copy(),
    )


async def _find_or_create_pool_agent(db: AsyncSession, provider: str, role: str) -> AgentProfile:
    name = f"browser-ai-pool-{provider}-{role or 'reviewer'}"
    result = await db.execute(
        select(AgentProfile).where(
            AgentProfile.provider == "browser_ai",
            AgentProfile.agent_type == "browser_ai_pool",
            AgentProfile.name == name,
        )
    )
    agent = result.scalar_one_or_none()
    if agent:
        return agent
    agent = AgentProfile(
        name=name,
        agent_type="browser_ai_pool",
        provider="browser_ai",
        model_name=provider,
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return agent


async def _pool_agent(db: AsyncSession) -> AgentProfile:
    result = await db.execute(
        select(AgentProfile).where(
            AgentProfile.provider == "browser_ai",
            AgentProfile.agent_type == "browser_ai_pool",
            AgentProfile.name == "browser-ai-provider-pool",
        )
    )
    agent = result.scalar_one_or_none()
    if agent:
        return agent
    agent = AgentProfile(
        name="browser-ai-provider-pool",
        agent_type="browser_ai_pool",
        provider="browser_ai",
        model_name="browser_ai_pool",
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return agent


async def _create_pool_run(
    db: AsyncSession,
    task: Task,
    body: BrowserAiPoolRequest,
    job_count: int,
) -> AgentRun:
    agent = await _pool_agent(db)
    prompt_hash = _hash_text(body.prompt or "")
    run = AgentRun(
        task_id=task.id,
        project_id=task.project_id,
        agent_id=agent.id,
        run_type="browser_ai_pool",
        status=AgentRunStatus.RUNNING.value,
        input_prompt=f"Browser AI pool prompt redacted; prompt_hash={prompt_hash}; advisory_only=true",
        started_at=datetime.now(timezone.utc),
        raw_result_json=_safe_json({
            "prompt_hash": prompt_hash,
            "job_count": job_count,
            "max_total_concurrency": body.max_total_concurrency,
            "per_provider_concurrency": body.per_provider_concurrency,
            "advisory_only": True,
            "human_confirmation_required": True,
            "no_auto_merge": True,
            "safety_notes": SAFETY_NOTES,
        }),
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)
    return run


async def _create_job_run(
    db: AsyncSession,
    task: Task,
    agent: AgentProfile,
    pool_run: AgentRun,
    job: _PoolJob,
    request: BrowserAiRequest,
) -> AgentRun:
    run = AgentRun(
        task_id=task.id,
        project_id=task.project_id,
        agent_id=agent.id,
        run_type="browser_ai_pool_job",
        status=AgentRunStatus.RUNNING.value,
        input_prompt=f"Browser AI pool job prompt redacted; prompt_hash={job.prompt_hash}; pool_run_id={pool_run.id}",
        started_at=datetime.now(timezone.utc),
        raw_result_json=_safe_json({
            "pool_run_id": pool_run.id,
            "provider": request.provider,
            "role": job.provider.role,
            "prompt_hash": job.prompt_hash,
            "browser_opened": True,
            "target_url_hint": browser_ai_service._target_url_hint(request.target_url),
            "advisory_only": True,
            "human_confirmation_required": True,
            "no_auto_merge": True,
        }),
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)
    return run


def _answer_artifact(source: _ArtifactInput) -> TaskArtifact:
    payload = {
        "artifact_type": ARTIFACT_TYPE,
        "task_id": source.task.id,
        "project_id": source.task.project_id,
        "pool_run_id": source.pool_run.id,
        "provider": source.job.provider.provider,
        "role": source.job.provider.role,
        "prompt_excerpt": source.prompt_excerpt,
        "answer_excerpt": source.answer_excerpt,
        "raw_answer_redacted": source.raw_answer,
        "manual_login_required": False,
        "redaction_status": {
            "redaction_applied": True,
            "truncated": source.truncated,
            "max_chars": ANSWER_EXCERPT_CHARS,
        },
        "source_agent_run_id": source.run.id,
        "advisory_only": True,
        "human_confirmation_required": True,
        "no_auto_merge": True,
        "safety_notes": SAFETY_NOTES,
    }
    content = _safe_json(payload)
    data = content.encode("utf-8")
    metadata = {
        "type": ARTIFACT_TYPE,
        "status": "succeeded",
        "source": "browser_ai_pool",
        "provider": source.job.provider.provider,
        "role": source.job.provider.role,
        "agent_run_id": source.run.id,
        "pool_run_id": source.pool_run.id,
        "summary": source.answer_excerpt,
        "advisory_only": True,
        "human_confirmation_required": True,
        "no_auto_merge": True,
        "safety_notes": SAFETY_NOTES,
        "truncated": source.truncated,
    }
    safe_prefix = source.artifact_prefix if source.artifact_prefix == ARTIFACT_TYPE else ARTIFACT_TYPE
    return TaskArtifact(
        task_id=source.task.id,
        artifact_type=ARTIFACT_TYPE,
        content=content,
        filename=f"{safe_prefix}_{source.pool_run.id}_{source.run.id}_{source.job.provider.provider}.json",
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        is_truncated=source.truncated,
        metadata_json=_safe_json(metadata),
    )


def _excerpt(answer: str) -> tuple[str, bool]:
    redacted = _redact(answer)
    truncated = len(redacted) > ANSWER_EXCERPT_CHARS
    if truncated:
        return redacted[: ANSWER_EXCERPT_CHARS - 15].rstrip() + "\n...[truncated]", True
    return redacted, False


def _manual_login_required(reason: str) -> bool:
    lowered = reason.lower()
    return "manual login" in lowered or "login" in lowered or "sign in" in lowered


def _preview_status(jobs: list[BrowserAiPoolJobPreview]) -> str:
    if not jobs:
        return "blocked"
    if all(job.status == "ready" for job in jobs):
        return "ready"
    if any(job.status == "ready" for job in jobs):
        return "partial"
    return "blocked"


def _overall_status(jobs: list[BrowserAiPoolJobResult]) -> str:
    if not jobs:
        return "failed"
    succeeded = sum(1 for job in jobs if job.status == "succeeded")
    if succeeded == len(jobs):
        return "succeeded"
    if succeeded:
        return "partial"
    return "failed"

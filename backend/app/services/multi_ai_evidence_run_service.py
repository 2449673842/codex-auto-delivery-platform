import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.dispatch_batch import DispatchBatch
from app.models.dispatch_job import DispatchJob
from app.schemas.ai_handoff import AiHandoffPreviewRequest
from app.models.task import Task
from app.schemas.answer_synthesis import AnswerSynthesisPreviewRequest
from app.schemas.browser_ai import BrowserAiRequest
from app.schemas.multi_ai_evidence_run import (
    EVIDENCE_PROMPT_SOURCES,
    EVIDENCE_RUN_MODES,
    MultiAiEvidenceJobResponse,
    MultiAiEvidenceRunRequest,
    MultiAiEvidenceRunResponse,
    MultiAiEvidenceSafetyGate,
)
from app.services import ai_handoff_service, answer_synthesis_service, browser_ai_service
from app.services.ai_output_governance_service import redact_secrets


ANSWER_PREVIEW_CHARS = 1200
CONCURRENCY_NOTE = "bounded concurrency is planned; current MVP executes jobs sequentially"
SAFETY_NOTES = [
    "Multi-AI Evidence Run collects AI answers as evidence; it does not execute code.",
    "S19 MVP does not write repository files, create PRs, call CI/Sonar/Deploy, approve, or merge.",
    "Browser AI execution remains local-browser only and does not save passwords, cookies, or sessions.",
]


class _EvidenceJob:
    def __init__(self, sequence_no: int, provider: str, role: str, prompt: str):
        self.sequence_no = sequence_no
        self.provider = provider
        self.role = role
        self.prompt = prompt


@dataclass
class _PromptContext:
    prompt: str
    available: bool
    safety_notes: list[str]


def _redact(value: str | None) -> str:
    return redact_secrets(value or "")


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _safe_json(payload: dict[str, Any]) -> str:
    return _redact(json.dumps(payload, ensure_ascii=False)) or "{}"


async def _get_task(db: AsyncSession, task_id: int) -> Task:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    if task.status == "archived":
        raise HTTPException(status_code=409, detail="task_archived")
    return task


def _known_providers() -> set[str]:
    return {profile.provider for profile in browser_ai_service.list_provider_profiles()}


def _providers(body: MultiAiEvidenceRunRequest) -> list[str]:
    if body.mode == "routed":
        return [role.provider.strip() for role in body.roles if role.provider.strip()]
    return [provider.strip() for provider in body.providers if provider.strip()]


async def _base_prompt(db: AsyncSession, task: Task, body: MultiAiEvidenceRunRequest) -> _PromptContext:
    if body.prompt_source == "custom_prompt":
        return _PromptContext(
            prompt=body.custom_prompt.strip(),
            available=bool(body.custom_prompt.strip()),
            safety_notes=["prompt_source=custom_prompt: using user-provided prompt text."],
        )
    if body.prompt_source == "handoff_packet":
        return await _handoff_prompt(db, task)
    if body.prompt_source == "answer_synthesis":
        return await _answer_synthesis_prompt(db, task)
    return _PromptContext(
        prompt=_task_text(task),
        available=True,
        safety_notes=["prompt_source=task_goal: using task title, description, and status."],
    )


async def _handoff_prompt(db: AsyncSession, task: Task) -> _PromptContext:
    try:
        packet = await ai_handoff_service.preview(
            db,
            AiHandoffPreviewRequest(
                project_id=task.project_id,
                task_id=task.id,
                include_recent_batches=True,
                include_answer_synthesis=True,
                include_safety_rules=True,
                max_chars=8000,
            ),
        )
    except Exception as exc:
        reason = _redact(str(exc))[:160] or "handoff packet unavailable"
        return _PromptContext(
            prompt="Prepare a concise handoff-oriented review for this task.\n\n"
            f"{_task_text(task)}\n\nHandoff packet unavailable: {reason}",
            available=False,
            safety_notes=[
                f"prompt_source=handoff_packet unavailable; fell back to task_goal context. reason={reason}",
            ],
        )
    payload = {
        "current_task_summary": packet.current_task_summary,
        "recent_dispatch_summary": packet.recent_dispatch_summary,
        "answer_synthesis_summary": packet.answer_synthesis_summary,
        "next_recommended_steps": packet.next_recommended_steps,
        "next_ai_prompt": packet.next_ai_prompt,
        "safety_rules": packet.safety_rules,
        "safety_notes": packet.safety_notes,
        "source_ids": packet.source_ids.model_dump(),
    }
    return _PromptContext(
        prompt="Use this redacted AI handoff packet as the evidence context.\n\n"
        f"{_redact(json.dumps(payload, ensure_ascii=False, default=str))}",
        available=True,
        safety_notes=[
            "prompt_source=handoff_packet loaded from AI Handoff preview.",
            "AI Handoff preview is stateless and does not call an AI provider.",
        ],
    )


async def _answer_synthesis_prompt(db: AsyncSession, task: Task) -> _PromptContext:
    try:
        synthesis = await answer_synthesis_service.preview(
            db,
            AnswerSynthesisPreviewRequest(
                task_id=task.id,
                dispatch_batch_id=None,
                include_artifacts=True,
                max_artifact_chars=1200,
            ),
        )
    except Exception as exc:
        reason = _redact(str(exc))[:160] or "answer synthesis unavailable"
        return _PromptContext(
            prompt="Review the current task using existing synthesis context if available.\n\n"
            f"{_task_text(task)}\n\nAnswer synthesis unavailable: {reason}",
            available=False,
            safety_notes=[
                f"prompt_source=answer_synthesis unavailable; fell back to task_goal context. reason={reason}",
            ],
        )
    payload = {
        "synthesis_status": synthesis.synthesis_status,
        "job_count": synthesis.job_count,
        "succeeded_jobs": synthesis.succeeded_jobs,
        "failed_jobs": synthesis.failed_jobs,
        "blocked_jobs": synthesis.blocked_jobs,
        "common_findings": synthesis.common_findings,
        "disagreements": synthesis.disagreements,
        "risks": synthesis.risks,
        "recommended_actions": synthesis.recommended_actions,
        "next_questions": synthesis.next_questions,
        "artifact_summaries": [item.model_dump() for item in synthesis.artifact_summaries],
        "source_job_ids": synthesis.source_job_ids,
        "source_agent_run_ids": synthesis.source_agent_run_ids,
        "source_artifact_ids": synthesis.source_artifact_ids,
        "safety_notes": synthesis.safety_notes,
    }
    return _PromptContext(
        prompt="Use this redacted Answer Synthesis preview as the evidence context.\n\n"
        f"{_redact(json.dumps(payload, ensure_ascii=False, default=str))}",
        available=True,
        safety_notes=[
            "prompt_source=answer_synthesis loaded from Answer Synthesis preview.",
            "Answer Synthesis preview is rule-based and does not call an AI provider.",
        ],
    )


def _task_text(task: Task) -> str:
    return "\n".join([
        f"Task: {task.title}",
        f"Description: {task.description or '(none)'}",
        f"Status: {task.status}",
    ])


def _build_jobs(base: str, body: MultiAiEvidenceRunRequest) -> list[_EvidenceJob]:
    if body.mode == "routed":
        jobs: list[_EvidenceJob] = []
        for index, role in enumerate(body.roles, start=1):
            role_name = (role.role or f"role_{index}").strip()
            role_prompt = (role.prompt or "").strip()
            prompt = "\n\n".join([
                f"Role: {role_name}",
                role_prompt or f"Analyze this task from the {role_name} perspective.",
                base,
            ]).strip()
            jobs.append(_EvidenceJob(index, role.provider.strip(), role_name, prompt))
        return jobs
    return [
        _EvidenceJob(index, provider.strip(), "general", base)
        for index, provider in enumerate(body.providers, start=1)
        if provider.strip()
    ]


def _safety_gate(body: MultiAiEvidenceRunRequest, jobs: list[_EvidenceJob], *, for_execute: bool) -> MultiAiEvidenceSafetyGate:
    known = _known_providers()
    providers = [job.provider for job in jobs]
    allowlist = set(settings.browser_ai_provider_allowlist)
    gate = MultiAiEvidenceSafetyGate(
        mode_valid=body.mode in EVIDENCE_RUN_MODES,
        prompt_source_valid=body.prompt_source in EVIDENCE_PROMPT_SOURCES,
        providers_known=bool(providers) and all(provider in known for provider in providers),
        providers_allowed=bool(providers) and all(provider in allowlist for provider in providers),
        job_count_ok=1 <= len(jobs) <= 12,
        browser_ai_enabled=settings.browser_ai_enabled,
        safety_notes=SAFETY_NOTES.copy(),
    )
    if not gate.mode_valid:
        gate.blocked_reasons.append(f"Invalid evidence run mode '{body.mode}'")
    if not gate.prompt_source_valid:
        gate.blocked_reasons.append(f"Invalid prompt_source '{body.prompt_source}'")
    if not providers:
        gate.blocked_reasons.append("At least one evidence job is required")
    for provider in providers:
        if provider not in known:
            gate.blocked_reasons.append(f"Unknown provider '{provider}'")
        if provider not in allowlist:
            gate.blocked_reasons.append(f"Provider '{provider}' is not in BROWSER_AI_PROVIDER_ALLOWLIST")
    if not gate.job_count_ok:
        gate.blocked_reasons.append("Evidence run must contain between 1 and 12 jobs")
    if for_execute and not gate.browser_ai_enabled:
        gate.blocked_reasons.append("BROWSER_AI_ENABLED is not true")
    gate.gate_passed = len(gate.blocked_reasons) == 0
    return gate


async def preview(db: AsyncSession, body: MultiAiEvidenceRunRequest) -> MultiAiEvidenceRunResponse:
    task = await _get_task(db, body.task_id)
    prompt_context = await _base_prompt(db, task, body)
    jobs = _build_jobs(prompt_context.prompt, body)
    gate = _safety_gate(body, jobs, for_execute=False)
    gate.safety_notes.extend(prompt_context.safety_notes)
    return MultiAiEvidenceRunResponse(
        task_id=task.id,
        mode=body.mode,
        prompt_source=body.prompt_source,
        providers=_providers(body),
        jobs=[
            MultiAiEvidenceJobResponse(
                sequence_no=job.sequence_no,
                provider=job.provider,
                role=job.role,
                prompt_source=body.prompt_source,
                prompt_hash=_hash_text(job.prompt),
                question=_redact(job.prompt)[:240],
                error_message="; ".join(gate.blocked_reasons) if not gate.gate_passed else None,
            )
            for job in jobs
        ],
        estimated_job_count=len(jobs),
        concurrency_limit=body.concurrency_limit,
        overall_status="ready" if gate.gate_passed else "blocked",
        safety_gate=gate,
        read_only=True,
        persisted=False,
        error_message="; ".join(gate.blocked_reasons),
    )


async def execute(db: AsyncSession, body: MultiAiEvidenceRunRequest) -> MultiAiEvidenceRunResponse:
    task = await _get_task(db, body.task_id)
    prompt_context = await _base_prompt(db, task, body)
    jobs = _build_jobs(prompt_context.prompt, body)
    gate = _safety_gate(body, jobs, for_execute=True)
    gate.safety_notes.extend(prompt_context.safety_notes)
    if not gate.gate_passed:
        return MultiAiEvidenceRunResponse(
            task_id=task.id,
            mode=body.mode,
            prompt_source=body.prompt_source,
            providers=_providers(body),
            jobs=[
                MultiAiEvidenceJobResponse(
                    sequence_no=job.sequence_no,
                    provider=job.provider,
                    role=job.role,
                    status="blocked",
                    prompt_source=body.prompt_source,
                    prompt_hash=_hash_text(job.prompt),
                    question=_redact(job.prompt)[:240],
                    error_message="; ".join(gate.blocked_reasons),
                )
                for job in jobs
            ],
            estimated_job_count=len(jobs),
            concurrency_limit=body.concurrency_limit,
            overall_status="blocked",
            safety_gate=gate,
            persisted=False,
            error_message="; ".join(gate.blocked_reasons),
        )

    batch = DispatchBatch(
        task_id=task.id,
        batch_mode=body.mode,
        status="running",
        task_goal=_redact(prompt_context.prompt),
        metadata_json=_safe_json({
            "type": "multi_ai_evidence_run",
            "prompt_source": body.prompt_source,
            "prompt_source_available": prompt_context.available,
            "concurrency_limit": body.concurrency_limit,
            "concurrency_note": CONCURRENCY_NOTE,
            "pipeline_implemented": False,
            "repair_loop_implemented": False,
            "safety_notes": gate.safety_notes,
        }),
    )
    db.add(batch)
    await db.flush()
    await db.refresh(batch)

    job_responses: list[MultiAiEvidenceJobResponse] = []
    dispatch_jobs: list[DispatchJob] = []
    for evidence_job in jobs:
        dispatch_job = await _create_dispatch_job(db, task, batch, evidence_job, body)
        dispatch_jobs.append(dispatch_job)
        dispatch_job.status = "running"
        dispatch_job.started_at = datetime.now(timezone.utc)
        await db.flush()
        browser_result = await browser_ai_service.execute(
            db,
            BrowserAiRequest(
                project_id=task.project_id,
                task_id=task.id,
                provider=evidence_job.provider,
                target_url=body.target_url,
                input_selector=body.input_selector,
                send_selector=body.send_selector,
                response_selector=body.response_selector,
                scroll_container_selector=body.scroll_container_selector,
                copy_button_selector=body.copy_button_selector,
                login_hint_selector=body.login_hint_selector,
                prompt_source="custom_prompt",
                custom_prompt=evidence_job.prompt,
                timeout_seconds=body.timeout_seconds,
            ),
        )
        dispatch_job.prompt_hash = browser_result.prompt_hash
        dispatch_job.agent_run_id = browser_result.agent_run_id
        dispatch_job.finished_at = datetime.now(timezone.utc)
        dispatch_job.metadata_json = _safe_json({
            "type": "multi_ai_evidence_job",
            "role": evidence_job.role,
            "prompt_source": body.prompt_source,
            "browser_ai_status": browser_result.status,
            "steps": [step.model_dump() for step in browser_result.steps],
        })
        if browser_result.status == "succeeded" and browser_result.artifact_id:
            dispatch_job.status = "succeeded"
            dispatch_job.artifact_ids_json = json.dumps([browser_result.artifact_id])
            dispatch_job.error_message = None
        elif browser_result.status == "blocked":
            dispatch_job.status = "blocked"
            dispatch_job.artifact_ids_json = json.dumps([])
            dispatch_job.error_message = _redact(browser_result.error_message)[:500]
        else:
            dispatch_job.status = "failed"
            dispatch_job.artifact_ids_json = json.dumps([])
            dispatch_job.error_message = _redact(browser_result.error_message)[:500]
        await db.flush()
        job_responses.append(_job_response(dispatch_job, evidence_job, body.prompt_source, browser_result.answer_preview))

    batch.status = _overall_status(dispatch_jobs)
    batch.summary_json = _safe_json(_batch_summary(dispatch_jobs))
    await db.flush()

    synthesis_status = ""
    source_artifact_ids: list[int] = []
    try:
        synthesis = await answer_synthesis_service.preview(
            db,
            AnswerSynthesisPreviewRequest(task_id=task.id, dispatch_batch_id=batch.id, include_artifacts=True),
        )
        synthesis_status = synthesis.synthesis_status
        source_artifact_ids = synthesis.source_artifact_ids
        synthesis_refreshed = True
    except Exception as exc:
        synthesis_refreshed = False
        synthesis_status = f"synthesis_unavailable: {_redact(str(exc))[:160]}"

    return MultiAiEvidenceRunResponse(
        evidence_run_id=batch.id,
        dispatch_batch_id=batch.id,
        task_id=task.id,
        mode=body.mode,
        prompt_source=body.prompt_source,
        providers=[job.provider for job in jobs],
        jobs=job_responses,
        estimated_job_count=len(jobs),
        concurrency_limit=body.concurrency_limit,
        overall_status=batch.status,
        safety_gate=gate,
        read_only=False,
        persisted=True,
        synthesis_refreshed=synthesis_refreshed,
        synthesis_status=synthesis_status,
        source_artifact_ids=source_artifact_ids,
    )


async def _create_dispatch_job(
    db: AsyncSession,
    task: Task,
    batch: DispatchBatch,
    evidence_job: _EvidenceJob,
    body: MultiAiEvidenceRunRequest,
) -> DispatchJob:
    dispatch_job = DispatchJob(
        batch_id=batch.id,
        task_id=task.id,
        sequence_no=evidence_job.sequence_no,
        question=_redact(evidence_job.prompt),
        provider=evidence_job.provider,
        model=evidence_job.provider,
        mode=body.mode,
        status="queued",
        prompt_hash=_hash_text(evidence_job.prompt),
        expected_artifact_type="browser_ai_answer",
        metadata_json=_safe_json({
            "type": "multi_ai_evidence_job",
            "role": evidence_job.role,
            "prompt_source": body.prompt_source,
        }),
    )
    db.add(dispatch_job)
    await db.flush()
    await db.refresh(dispatch_job)
    return dispatch_job


def _job_response(
    dispatch_job: DispatchJob,
    evidence_job: _EvidenceJob,
    prompt_source: str,
    answer_preview: str = "",
) -> MultiAiEvidenceJobResponse:
    artifact_ids = _loads_int_list(dispatch_job.artifact_ids_json)
    return MultiAiEvidenceJobResponse(
        dispatch_job_id=dispatch_job.id,
        sequence_no=dispatch_job.sequence_no,
        provider=dispatch_job.provider,
        role=evidence_job.role,
        status=dispatch_job.status,
        prompt_source=prompt_source,
        prompt_hash=dispatch_job.prompt_hash or "",
        question=_redact(dispatch_job.question)[:240],
        error_message=dispatch_job.error_message,
        agent_run_id=dispatch_job.agent_run_id,
        artifact_id=artifact_ids[0] if artifact_ids else None,
        artifact_ids=artifact_ids,
        answer_preview=_redact(answer_preview)[:ANSWER_PREVIEW_CHARS],
    )


def _overall_status(jobs: list[DispatchJob]) -> str:
    if not jobs:
        return "blocked"
    succeeded = sum(1 for job in jobs if job.status == "succeeded")
    failed_or_blocked = sum(1 for job in jobs if job.status in {"failed", "blocked"})
    if succeeded == len(jobs):
        return "succeeded"
    if succeeded and failed_or_blocked:
        return "partial"
    if all(job.status == "blocked" for job in jobs):
        return "blocked"
    return "failed"


def _batch_summary(jobs: list[DispatchJob]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for job in jobs:
        counts[job.status] = counts.get(job.status, 0) + 1
    return {
        "type": "multi_ai_evidence_run",
        "job_count": len(jobs),
        "status_counts": counts,
        "concurrency_note": CONCURRENCY_NOTE,
    }


def _loads_int_list(raw: str | None) -> list[int]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, int)]


async def list_for_task(db: AsyncSession, task_id: int) -> list[MultiAiEvidenceRunResponse]:
    await _get_task(db, task_id)
    result = await db.execute(
        select(DispatchBatch)
        .where(DispatchBatch.task_id == task_id)
        .options(selectinload(DispatchBatch.jobs))
        .order_by(DispatchBatch.id)
    )
    batches = [
        batch for batch in result.scalars().unique().all()
        if _is_evidence_batch(batch)
    ]
    responses: list[MultiAiEvidenceRunResponse] = []
    for batch in batches:
        jobs = sorted(batch.jobs, key=lambda item: item.sequence_no)
        response_jobs = [
            MultiAiEvidenceJobResponse(
                dispatch_job_id=job.id,
                sequence_no=job.sequence_no,
                provider=job.provider,
                role=_metadata_role(job.metadata_json),
                status=job.status,
                prompt_source=_metadata_prompt_source(job.metadata_json),
                prompt_hash=job.prompt_hash or "",
                question=_redact(job.question)[:240],
                error_message=job.error_message,
                agent_run_id=job.agent_run_id,
                artifact_id=(_loads_int_list(job.artifact_ids_json) or [None])[0],
                artifact_ids=_loads_int_list(job.artifact_ids_json),
            )
            for job in jobs
        ]
        responses.append(
            MultiAiEvidenceRunResponse(
                evidence_run_id=batch.id,
                dispatch_batch_id=batch.id,
                task_id=batch.task_id,
                mode=batch.batch_mode,
                providers=[job.provider for job in jobs],
                jobs=response_jobs,
                estimated_job_count=len(jobs),
                concurrency_limit=_metadata_concurrency_limit(batch.metadata_json),
                overall_status=batch.status,
                safety_gate=MultiAiEvidenceSafetyGate(gate_passed=True, safety_notes=SAFETY_NOTES.copy()),
                persisted=True,
                synthesis_refreshed=False,
            )
        )
    return responses


def _is_evidence_batch(batch: DispatchBatch) -> bool:
    metadata = _loads_dict(batch.metadata_json)
    return metadata.get("type") == "multi_ai_evidence_run"


def _loads_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _metadata_role(raw: str | None) -> str:
    return str(_loads_dict(raw).get("role") or "general")


def _metadata_prompt_source(raw: str | None) -> str:
    return str(_loads_dict(raw).get("prompt_source") or "task_goal")


def _metadata_concurrency_limit(raw: str | None) -> int:
    value = _loads_dict(raw).get("concurrency_limit")
    return value if isinstance(value, int) else 2

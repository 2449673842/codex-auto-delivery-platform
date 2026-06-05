import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun
from app.models.project import Project
from app.models.task import Task
from app.models.task_artifact import TaskArtifact
from app.models.task_event import TaskEvent
from app.schemas.answer_synthesis import AnswerSynthesisPreviewRequest
from app.schemas.autopilot_lite import (
    AutoPilotLitePreviewRequest,
    AutoPilotLitePreviewResponse,
    AutoPilotLiteStepPreview,
)
from app.schemas.browser_ai_pool import BrowserAiPoolRequest
from app.services import (
    answer_synthesis_service,
    browser_ai_pool_service,
    mastermind_review_service,
)
from app.services.ai_output_governance_service import redact_secrets


SAFETY_NOTES = [
    "AutoPilot Lite preview is advisory only and does not execute Browser AI.",
    "Preview is read-only; it does not write AgentRun, TaskArtifact, TaskEvent, Project, or Task records.",
    "Preview does not call provider API tokens, hidden web APIs, GitHub, Sonar, CI, deploy, shell, or subprocess.",
    "Preview does not read .env, secret_ref, account, password, cookie, session, localStorage, or Project.root_path values.",
    "AutoPilot Lite cannot approve, merge, deploy, rework, write a repository, or bypass login / captcha / 2FA / paywall / rate limits.",
    "Execute stages planned by this preview still require human-controlled boundaries and visible Browser AI UI where applicable.",
]

DEFAULT_PROMPT = (
    "Review this task and provide advisory evidence. Do not claim approve, merge, "
    "deploy, or rework authority."
)


def _redact(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return redact_secrets(text or "")


def _short(value: Any, limit: int = 500) -> str:
    text = " ".join(_redact(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 15].rstrip() + "\n...[truncated]"


async def preview(
    db: AsyncSession,
    task_id: int,
    body: AutoPilotLitePreviewRequest,
) -> AutoPilotLitePreviewResponse:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project_not_found")

    steps: list[AutoPilotLiteStepPreview] = []
    blocking_reasons: list[str] = []
    recommended_actions: list[str] = []

    context_counts = await _context_counts(db, task.id)
    steps.append(_context_step(task, project, context_counts))

    pool_body = BrowserAiPoolRequest(
        prompt=body.prompt or DEFAULT_PROMPT,
        providers=body.providers,
        max_total_concurrency=body.max_total_concurrency,
        per_provider_concurrency=body.per_provider_concurrency,
        include_task_context=body.include_task_context,
        include_project_memory=body.include_project_memory,
        include_evidence_board=body.include_evidence_board,
        prompt_budget=body.prompt_budget,
    )
    pool_preview = await browser_ai_pool_service.preview(db, task.id, pool_body)
    steps.append(_pool_step(pool_preview.overall_status, len(pool_preview.jobs)))
    if pool_preview.overall_status in {"blocked", "empty"}:
        blocking_reasons.append("Browser AI Pool preview has no ready provider jobs.")
        recommended_actions.append("Configure at least one enabled Browser AI provider before executing AutoPilot Lite.")

    synthesis_step, synthesis_status = await _synthesis_step(db, task.id)
    steps.append(synthesis_step)
    if synthesis_status in {"empty", "not_ready"}:
        recommended_actions.append("Collect Browser AI Pool answers before relying on answer synthesis.")

    packet_body = body.mastermind_packet.model_copy(update={
        "include_evidence_board": body.include_evidence_board,
        "include_timeline": body.include_timeline,
        "include_project_memory": body.include_project_memory,
        "packet_budget": body.prompt_budget,
    })
    mastermind_packet = await mastermind_review_service.preview_packet(db, task.id, packet_body)
    steps.append(_mastermind_packet_step(mastermind_packet))

    gate_preview = None
    if body.run_gate_preview:
        gate_preview = await mastermind_review_service.preview_gate(
            db,
            task.id,
            _gate_request_from_packet(packet_body),
        )
        steps.append(_gate_step(gate_preview.gate_status, gate_preview.blocking_reasons))
        blocking_reasons.extend(gate_preview.blocking_reasons)
        recommended_actions.extend(_actions_for_gate(gate_preview.gate_status))
    else:
        steps.append(AutoPilotLiteStepPreview(
            key="controlled_gate_preview",
            title="Controlled Gate Preview",
            status="skipped",
            summary="Gate preview was disabled by request.",
            recommended_actions=["Enable run_gate_preview when a mastermind_review_report is available."],
            safety_notes=SAFETY_NOTES.copy(),
        ))

    recommendation = _recommendation(pool_preview.overall_status, synthesis_status, gate_preview.gate_status if gate_preview else "")
    recommended_actions.extend(_actions_for_recommendation(recommendation))

    return AutoPilotLitePreviewResponse(
        task_id=task.id,
        project_id=project.id,
        mode=body.mode,
        status=_overall_status(recommendation),
        autopilot_state=_state_for_recommendation(recommendation),
        recommendation=recommendation,
        steps=steps,
        provider_jobs=pool_preview.jobs,
        pool_overall_status=pool_preview.overall_status,
        synthesis_status=synthesis_status,
        mastermind_packet_preview=mastermind_packet,
        gate_preview=gate_preview,
        recommended_actions=list(dict.fromkeys(_redact(action) for action in recommended_actions if action)),
        blocking_reasons=list(dict.fromkeys(_redact(reason) for reason in blocking_reasons if reason)),
        safety_notes=SAFETY_NOTES.copy(),
        metadata={
            "mode": body.mode,
            "max_total_concurrency": body.max_total_concurrency,
            "per_provider_concurrency": body.per_provider_concurrency,
            "prompt_budget": body.prompt_budget,
            "preview_only": True,
            "future_execute_flow": [
                "build_context_packet",
                "browser_ai_pool_preview",
                "browser_ai_pool_execute",
                "answer_synthesis_preview",
                "mastermind_review_packet_preview",
                "browser_ai_mastermind_review_execute",
                "controlled_gate_preview",
                "autopilot_recommendation",
            ],
            "context_counts": context_counts,
        },
    )


async def _context_counts(db: AsyncSession, task_id: int) -> dict[str, int]:
    models = {
        "agent_runs": AgentRun,
        "artifacts": TaskArtifact,
        "events": TaskEvent,
    }
    counts = {}
    for name, model in models.items():
        result = await db.execute(select(model).where(model.task_id == task_id))
        counts[name] = len(result.scalars().all())
    return counts


def _context_step(task: Task, project: Project, counts: dict[str, int]) -> AutoPilotLiteStepPreview:
    return AutoPilotLiteStepPreview(
        key="context_packet",
        title="Build context packet",
        status="ready",
        summary=_short(
            f"Task #{task.id} in project #{project.id} is ready for AutoPilot Lite preview. "
            "Project.root_path is intentionally not included."
        ),
        source_ids={"task_id": task.id, "project_id": project.id, **counts},
        safety_notes=SAFETY_NOTES.copy(),
    )


def _pool_step(overall_status: str, job_count: int) -> AutoPilotLiteStepPreview:
    status = "ready" if overall_status == "ready" else overall_status or "empty"
    return AutoPilotLiteStepPreview(
        key="browser_ai_pool",
        title="Browser AI Pool Preview",
        status=status,
        summary=f"{job_count} Browser AI provider job(s) planned.",
        blocking_reasons=[] if status == "ready" else ["No ready Browser AI provider job is available."],
        recommended_actions=[] if status == "ready" else ["Add enabled provider profiles or fix blocked provider settings."],
        safety_notes=SAFETY_NOTES.copy(),
    )


async def _synthesis_step(db: AsyncSession, task_id: int) -> tuple[AutoPilotLiteStepPreview, str]:
    try:
        synthesis = await answer_synthesis_service.preview(
            db,
            AnswerSynthesisPreviewRequest(task_id=task_id, include_artifacts=True, max_artifact_chars=1200),
        )
    except HTTPException as exc:
        if exc.status_code == 404:
            return AutoPilotLiteStepPreview(
                key="answer_synthesis",
                title="Answer Synthesis Preview",
                status="not_ready",
                summary="No dispatch batch or Browser AI evidence is available yet.",
                blocking_reasons=["Answer synthesis needs existing AI evidence."],
                recommended_actions=["Run Browser AI Pool execute before synthesis."],
                safety_notes=SAFETY_NOTES.copy(),
            ), "not_ready"
        raise
    return AutoPilotLiteStepPreview(
        key="answer_synthesis",
        title="Answer Synthesis Preview",
        status=synthesis.synthesis_status,
        summary=f"Synthesis status: {synthesis.synthesis_status}; source artifacts: {len(synthesis.source_artifact_ids)}.",
        blocking_reasons=synthesis.risks,
        recommended_actions=synthesis.recommended_actions,
        source_ids={
            "source_agent_run_ids": synthesis.source_agent_run_ids,
            "source_artifact_ids": synthesis.source_artifact_ids,
            "dispatch_batch_id": synthesis.dispatch_batch_id,
        },
        safety_notes=synthesis.safety_notes + SAFETY_NOTES,
    ), synthesis.synthesis_status


def _mastermind_packet_step(packet: Any) -> AutoPilotLiteStepPreview:
    return AutoPilotLiteStepPreview(
        key="mastermind_review_packet",
        title="Mastermind Review Packet Preview",
        status="ready",
        summary=f"Mastermind packet preview is ready with {len(packet.source_refs)} source reference(s).",
        source_ids={"source_refs": [item.model_dump() for item in packet.source_refs]},
        safety_notes=packet.safety_notes + SAFETY_NOTES,
    )


def _gate_request_from_packet(packet_body: Any) -> Any:
    from app.schemas.mastermind_review import MastermindReviewGatePreviewRequest

    return MastermindReviewGatePreviewRequest(
        current_head_commit=packet_body.head_commit,
        pr_url=packet_body.pr_url,
        pr_number=packet_body.pr_number,
        verification_results=packet_body.verification_results,
        sonarcloud=packet_body.sonarcloud,
    )


def _gate_step(gate_status: str, blocking_reasons: list[str]) -> AutoPilotLiteStepPreview:
    return AutoPilotLiteStepPreview(
        key="controlled_gate_preview",
        title="Controlled Gate Preview",
        status=gate_status,
        summary=f"Controlled Gate Preview returned {gate_status}.",
        blocking_reasons=blocking_reasons,
        recommended_actions=_actions_for_gate(gate_status),
        safety_notes=SAFETY_NOTES.copy(),
    )


def _recommendation(pool_status: str, synthesis_status: str, gate_status: str) -> str:
    if gate_status == "gate_blocked_by_safety":
        return "blocked_by_safety"
    if gate_status == "gate_request_changes":
        return "request_codex_rework"
    if gate_status == "gate_stale_review":
        return "stale_review_rerun_required"
    if gate_status == "gate_invalid_review":
        return "invalid_review_rerun_required"
    if pool_status in {"blocked", "empty"} or synthesis_status in {"empty", "not_ready"}:
        return "insufficient_evidence"
    if gate_status == "gate_advisory_approved":
        return "ready_for_human_confirmation"
    if gate_status in {"gate_needs_human", "gate_not_ready"}:
        return "needs_human_review"
    return "needs_human_review"


def _overall_status(recommendation: str) -> str:
    if recommendation == "ready_for_human_confirmation":
        return "succeeded"
    if recommendation in {"request_codex_rework", "needs_human_review", "insufficient_evidence"}:
        return "needs_human"
    if recommendation == "blocked_by_safety":
        return "failed"
    return "partial"


def _state_for_recommendation(recommendation: str) -> str:
    mapping = {
        "ready_for_human_confirmation": "recommendation_ready",
        "request_codex_rework": "recommendation_ready",
        "needs_human_review": "needs_human",
        "blocked_by_safety": "blocked_by_safety",
        "stale_review_rerun_required": "needs_human",
        "invalid_review_rerun_required": "needs_human",
        "insufficient_evidence": "needs_human",
    }
    return mapping.get(recommendation, "needs_human")


def _actions_for_gate(gate_status: str) -> list[str]:
    mapping = {
        "gate_advisory_approved": [
            "Gate is advisory approved; wait for human confirmation and do not auto approve or merge."
        ],
        "gate_request_changes": ["Generate a repair packet or Codex / OMX handoff candidate for human review."],
        "gate_needs_human": ["Ask a human to inspect missing evidence or low-confidence review output."],
        "gate_blocked_by_safety": ["Stop automation and inspect the safety boundary violation."],
        "gate_stale_review": ["Rerun mastermind review against the current head commit."],
        "gate_invalid_review": ["Rerun mastermind review with a valid structured output contract."],
        "gate_not_ready": ["Create a mastermind_review_report before relying on the gate."],
    }
    return mapping.get(gate_status, ["Inspect gate status before continuing."])


def _actions_for_recommendation(recommendation: str) -> list[str]:
    mapping = {
        "ready_for_human_confirmation": ["Present the advisory result to a human; do not auto approve or merge."],
        "request_codex_rework": ["Prepare a repair handoff candidate; do not modify the repository automatically."],
        "needs_human_review": ["Collect missing context or ask a human to decide the next step."],
        "blocked_by_safety": ["Stop and resolve safety blockers before any further automation."],
        "stale_review_rerun_required": ["Refresh evidence and rerun mastermind review."],
        "invalid_review_rerun_required": ["Regenerate the review packet and rerun mastermind review."],
        "insufficient_evidence": ["Run Browser AI Pool execute to collect advisory evidence first."],
    }
    return mapping.get(recommendation, ["Review AutoPilot Lite preview before continuing."])

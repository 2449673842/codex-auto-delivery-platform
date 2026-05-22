import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.dispatch_batch import DispatchBatch
from app.models.project import Project
from app.models.task import Task
from app.schemas.ai_handoff import (
    AiHandoffPreviewRequest,
    AiHandoffPreviewResponse,
    AiHandoffSourceIds,
)
from app.schemas.answer_synthesis import AnswerSynthesisPreviewRequest
from app.services import answer_synthesis_service
from app.services.answer_synthesis_service import _loads_dict, _loads_list, _redact


PRODUCT_POSITIONING = "Personal Multi-AI Coding Workbench"
LAST_KNOWN_BASE_COMMIT_HINT = "32dcd5a8e11eeef48e0844cf21601561938c2112"
CURRENT_MASTER_COMMIT_HINT = "verify_current_master_on_github_before_acting"
VERIFY_MASTER_NOTE = (
    "Current master commit must be verified from GitHub before acting. "
    "Do not trust this packet as the source of truth for latest master SHA."
)
RECENT_CAPABILITIES = [
    "S11 AI Dispatch + OpenAI Provider + Sandbox Auto Pipeline",
    "S12 Dispatch Batch / Routed Jobs",
    "S13 Multi-AI Answer Workspace",
    "S14 Answer Synthesizer preview",
    "S14.5 Answer Synthesis display on TaskDetail",
]
SAFETY_RULES = [
    "Do not read .env.",
    "Do not read secret_ref.",
    "Do not save API keys, cookies, passwords, or sessions.",
    "Do not access Project.root_path for real repository modification.",
    "Do not execute shell, subprocess, or os.system as product behavior.",
    "Do not create real GitHub PR / CI / Sonar / Deploy actions.",
    "Do not auto approve or merge.",
    "PR body must be accurate and match real GitHub/Sonar state.",
    "All PRs must wait for master-brain review before merge.",
]
SAFETY_NOTES = [
    "Deterministic stateless preview; no AI provider is called.",
    "No AgentRun, TaskArtifact, or TaskEvent is created.",
    "Project.root_path is intentionally not included in the response.",
    "Answer synthesis reuse is local rule-based preview only.",
    CURRENT_MASTER_COMMIT_HINT,
    VERIFY_MASTER_NOTE,
]
DOCS_TO_READ = [
    "AGENTS.md",
    "docs/roadmap/personal-workbench-roadmap.md",
    "docs/design/multi-ai-task-routing.md",
    "docs/design/personal-user-flow.md",
    "docs/design/project-memory.md",
    "docs/design/provider-adapter-strategy.md",
    "docs/design/self-improving-harness.md",
]


def _redact_jsonable(value: Any) -> Any:
    return json.loads(_redact(json.dumps(value, ensure_ascii=False, default=str)))


async def preview(db: AsyncSession, body: AiHandoffPreviewRequest) -> AiHandoffPreviewResponse:
    project = await db.get(Project, body.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project_not_found")
    task = await _load_task(db, body.project_id, body.task_id)
    batches = await _load_recent_batches(db, task.id if task and body.include_recent_batches else None)
    synthesis = await _build_answer_synthesis(db, body, task, batches)
    response = _build_response(body, project, task, batches, synthesis)
    return _truncate_response(response, body.max_chars)


async def _load_task(db: AsyncSession, project_id: int, task_id: int | None) -> Task | None:
    if task_id is None:
        return None
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    if task.project_id != project_id:
        raise HTTPException(status_code=400, detail="task_project_mismatch")
    return task


async def _load_recent_batches(db: AsyncSession, task_id: int | None) -> list[DispatchBatch]:
    if task_id is None:
        return []
    stmt = (
        select(DispatchBatch)
        .where(DispatchBatch.task_id == task_id)
        .options(selectinload(DispatchBatch.jobs))
        .order_by(DispatchBatch.id.desc())
        .limit(3)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _build_answer_synthesis(
    db: AsyncSession,
    body: AiHandoffPreviewRequest,
    task: Task | None,
    batches: list[DispatchBatch],
) -> dict[str, Any]:
    if not body.include_answer_synthesis or not task or not batches:
        return {}
    latest_batch = batches[0]
    try:
        synthesis = await answer_synthesis_service.preview(
            db,
            AnswerSynthesisPreviewRequest(
                task_id=task.id,
                dispatch_batch_id=latest_batch.id,
                include_artifacts=True,
                max_artifact_chars=800,
            ),
        )
    except HTTPException:
        return {}
    return synthesis.model_dump()


def _build_response(
    body: AiHandoffPreviewRequest,
    project: Project,
    task: Task | None,
    batches: list[DispatchBatch],
    synthesis: dict[str, Any],
) -> AiHandoffPreviewResponse:
    source_ids = _source_ids(project.id, task.id if task else None, batches, synthesis)
    project_snapshot = _project_snapshot(project)
    task_summary = _task_summary(task, batches)
    dispatch_summary = _dispatch_summary(batches)
    answer_summary = _answer_synthesis_summary(synthesis)
    steps = _next_steps(task, batches, answer_summary)
    safety_rules = SAFETY_RULES if body.include_safety_rules else []
    next_prompt = _next_ai_prompt(task_summary, dispatch_summary, answer_summary, steps, safety_rules)
    return AiHandoffPreviewResponse(
        project_id=project.id,
        task_id=task.id if task else None,
        handoff_status="ready",
        project_snapshot=project_snapshot,
        current_task_summary=task_summary,
        recent_capabilities=RECENT_CAPABILITIES,
        current_master_commit_hint=CURRENT_MASTER_COMMIT_HINT,
        current_pr_summary=_current_pr_summary(task),
        recent_dispatch_summary=dispatch_summary,
        answer_synthesis_summary=answer_summary,
        safety_rules=safety_rules,
        next_recommended_steps=steps,
        next_ai_prompt=next_prompt,
        source_ids=source_ids,
        redaction_applied=True,
        safety_notes=SAFETY_NOTES,
    )


def _project_snapshot(project: Project) -> dict[str, Any]:
    return _redact_jsonable({
        "project_id": project.id,
        "name": project.name,
        "display_name": project.display_name,
        "positioning": PRODUCT_POSITIONING,
        "current_capabilities": [
            "AI Dispatch",
            "DispatchBatch / DispatchJob",
            "Multi-AI Answer Workspace",
            "Answer Synthesizer",
            "Answer Synthesis Display",
        ],
        "core_flow": "AI Dispatch -> DispatchBatch -> Workspace -> Synthesis",
        "repo_url": project.repo_url,
        "default_branch": project.default_branch,
        "current_branch": project.current_branch,
        "last_known_base_commit_hint": LAST_KNOWN_BASE_COMMIT_HINT,
        "master_commit_verification": CURRENT_MASTER_COMMIT_HINT,
        "commands_hint": {
            "build": project.build_command,
            "test": project.test_command,
            "dev": project.dev_command,
        },
        "root_path": "[not included by handoff preview]",
    })


def _task_summary(task: Task | None, batches: list[DispatchBatch]) -> dict[str, Any]:
    if not task:
        return {
            "scope": "project_level",
            "message": "No task_id provided; generated project-level handoff only.",
        }
    latest_batch = batches[0] if batches else None
    return _redact_jsonable({
        "task_id": task.id,
        "project_id": task.project_id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "planner": task.planner,
        "executor": task.executor,
        "reviewer": task.reviewer,
        "target_branch": task.target_branch,
        "result_summary": task.result_summary,
        "latest_dispatch_batch_id": latest_batch.id if latest_batch else None,
        "latest_dispatch_batch_status": latest_batch.status if latest_batch else None,
    })


def _current_pr_summary(task: Task | None) -> dict[str, Any]:
    if not task:
        return {"status": "not_applicable"}
    return _redact_jsonable({
        "pr_url": task.pr_url,
        "ci_url": task.ci_url,
        "deploy_url": task.deploy_url,
        "note": "Read-only task metadata only; no live GitHub, CI, Sonar, or Deploy call is made.",
    })


def _dispatch_summary(batches: list[DispatchBatch]) -> dict[str, Any]:
    if not batches:
        return {"batch_count": 0, "latest_batch": None, "recent_batches": []}
    summaries = [_batch_summary(batch) for batch in batches]
    return {
        "batch_count": len(batches),
        "latest_batch": summaries[0],
        "recent_batches": summaries,
    }


def _batch_summary(batch: DispatchBatch) -> dict[str, Any]:
    jobs = sorted(batch.jobs, key=lambda item: item.sequence_no)
    counts = {
        "succeeded": sum(1 for job in jobs if job.status == "succeeded"),
        "failed": sum(1 for job in jobs if job.status == "failed"),
        "blocked": sum(1 for job in jobs if job.status == "blocked"),
    }
    return _redact_jsonable({
        "dispatch_batch_id": batch.id,
        "batch_mode": batch.batch_mode,
        "status": batch.status,
        "task_goal": batch.task_goal,
        "summary": _loads_dict(batch.summary_json),
        "job_count": len(jobs),
        "job_counts": counts,
        "jobs": [
            {
                "dispatch_job_id": job.id,
                "sequence_no": job.sequence_no,
                "question": job.question,
                "provider": job.provider,
                "model": job.model,
                "mode": job.mode,
                "status": job.status,
                "prompt_hash": job.prompt_hash,
                "context_packet_hash": job.context_packet_hash,
                "agent_run_id": job.agent_run_id,
                "artifact_ids": _loads_list(job.artifact_ids_json),
                "expected_artifact_type": job.expected_artifact_type,
                "error_message": job.error_message,
            }
            for job in jobs
        ],
    })


def _answer_synthesis_summary(synthesis: dict[str, Any]) -> dict[str, Any]:
    if not synthesis:
        return {"status": "not_available"}
    keys = [
        "dispatch_batch_id",
        "synthesis_status",
        "job_count",
        "succeeded_jobs",
        "failed_jobs",
        "blocked_jobs",
        "common_findings",
        "disagreements",
        "risks",
        "recommended_actions",
        "next_questions",
        "confidence",
        "safety_notes",
    ]
    return _redact_jsonable({key: synthesis.get(key) for key in keys})


def _source_ids(
    project_id: int,
    task_id: int | None,
    batches: list[DispatchBatch],
    synthesis: dict[str, Any],
) -> AiHandoffSourceIds:
    batch_ids = [batch.id for batch in batches]
    job_ids = [job.id for batch in batches for job in batch.jobs]
    run_ids = sorted({job.agent_run_id for batch in batches for job in batch.jobs if job.agent_run_id})
    artifact_ids = sorted({artifact_id for batch in batches for job in batch.jobs for artifact_id in _loads_list(job.artifact_ids_json)})
    if synthesis:
        run_ids = sorted(set(run_ids).union(synthesis.get("source_agent_run_ids") or []))
        artifact_ids = sorted(set(artifact_ids).union(synthesis.get("source_artifact_ids") or []))
    return AiHandoffSourceIds(
        project_id=project_id,
        task_id=task_id,
        dispatch_batch_ids=batch_ids,
        dispatch_job_ids=job_ids,
        agent_run_ids=run_ids,
        artifact_ids=artifact_ids,
    )


def _next_steps(task: Task | None, batches: list[DispatchBatch], synthesis: dict[str, Any]) -> list[str]:
    if not task:
        return ["Pick or create a task before asking another AI to continue implementation work."]
    actions = synthesis.get("recommended_actions") if synthesis else None
    if isinstance(actions, list) and actions:
        return [_redact(str(item)) for item in actions[:5]]
    if not batches:
        return ["Create DispatchBatch preview or execute safe jobs before synthesis."]
    latest = batches[0]
    if any(job.status in ("failed", "blocked") for job in latest.jobs):
        return ["Resolve failed or blocked DispatchJobs, then regenerate answer synthesis."]
    return ["Ask the next AI to review the handoff packet and propose the next narrow implementation step."]


def _next_ai_prompt(
    task_summary: dict[str, Any],
    dispatch_summary: dict[str, Any],
    answer_summary: dict[str, Any],
    steps: list[str],
    safety_rules: list[str],
) -> str:
    lines = [
        "You are taking over this project as the next AI coding agent.",
        f"Project positioning: {PRODUCT_POSITIONING}.",
        f"Current master commit hint: {CURRENT_MASTER_COMMIT_HINT}.",
        f"Last known base commit hint: {LAST_KNOWN_BASE_COMMIT_HINT}.",
        VERIFY_MASTER_NOTE,
        "Completed modules: S11 AI Dispatch, S12 Dispatch Batch/Routed Jobs, S13 Multi-AI Answer Workspace, S14 Answer Synthesizer, S14.5 Synthesis Display.",
        f"Current task: {task_summary.get('title') or task_summary.get('message') or 'project-level handoff'}.",
        f"Task status: {task_summary.get('status', 'n/a')}.",
        f"Latest dispatch batch: {dispatch_summary.get('latest_batch')}.",
        f"Answer synthesis summary: {answer_summary}.",
        f"Read these docs first: {', '.join(DOCS_TO_READ)}.",
        f"Next recommended steps: {'; '.join(steps)}.",
        "Required report format: head SHA, changed files, tests, compileall/build, Sonar status, and safety boundary self-check.",
        "Forbidden actions: do not merge master yourself unless explicitly approved; do not read .env or secret_ref; do not access Project.root_path for real repository modification; do not call real AI/provider unless the stage explicitly allows it; do not create real PR/CI/Sonar/Deploy actions; do not auto approve or merge.",
    ]
    if safety_rules:
        lines.append("Safety rules: " + "; ".join(safety_rules))
    return _redact("\n".join(lines))


def _truncate_response(response: AiHandoffPreviewResponse, max_chars: int) -> AiHandoffPreviewResponse:
    dumped = json.dumps(response.model_dump(), ensure_ascii=False)
    if len(dumped) <= max_chars:
        return response
    response.next_ai_prompt = response.next_ai_prompt[: max(0, max_chars // 3)].rstrip() + "\n[truncated]"
    response.recent_dispatch_summary = _truncate_field(response.recent_dispatch_summary)
    response.answer_synthesis_summary = _truncate_field(response.answer_synthesis_summary)
    response.safety_notes = response.safety_notes + [f"Handoff packet truncated to max_chars={max_chars}."]
    return response


def _truncate_field(value: dict[str, Any]) -> dict[str, Any]:
    return {"truncated": True, "summary": _redact(json.dumps(value, ensure_ascii=False, default=str)[:1000])}

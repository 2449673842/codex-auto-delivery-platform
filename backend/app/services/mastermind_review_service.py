import json
import re
import hashlib
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
from app.models.task_event import TaskEvent
from app.schemas.browser_ai import BrowserAiRequest
from app.schemas.mastermind_review import (
    MastermindReviewExecuteRequest,
    MastermindReviewExecuteResponse,
    MastermindReviewPacketPreviewRequest,
    MastermindReviewPacketPreviewResponse,
    MastermindReviewParsedVerdict,
    MastermindReviewRedactionStatus,
    MastermindReviewSourceRef,
)
from app.services import browser_ai_service, evidence_summary_service, project_memory_service
from app.services.ai_output_governance_service import redact_secrets
from app.services.event_service import create_event


PACKET_TYPE = "mastermind_review_packet"
NOT_INCLUDED = "not_included"
SAFETY_NOTES = [
    "Mastermind Review Packet Preview API is read-only.",
    "Request PR metadata, verification results, and SonarCloud summary are used as supplied; the platform does not query GitHub or Sonar.",
    "No Browser AI mastermind review execution, browser launch, provider call, artifact write, PR, CI, Sonar, Deploy, approve, merge, or rework is performed.",
    "No AgentRun, TaskArtifact, TaskEvent, DispatchBatch, DispatchJob, Project, or Task record is created or modified.",
    "No .env, secret_ref, Project.root_path, account, password, cookie, or session value is read or returned.",
]
EXECUTE_SAFETY_NOTES = [
    "Browser AI Mastermind Review execute is an advisory trial only.",
    "Only user-authorized visible Browser AI UI is used; no hidden web API or provider API is called.",
    "The platform writes only review evidence records: AgentRun, TaskArtifact mastermind_review_report, and TaskEvent.",
    "Approved verdicts do not authorize auto approve, merge, deploy, or rework.",
    "No .env, secret_ref, Project.root_path, account, password, cookie, or session value is read or stored.",
]
VERDICTS = ["approved", "request_changes", "needs_human", "invalid_review"]
CONFIDENCES = {"high", "medium", "low"}
REPORT_ARTIFACT_TYPE = "mastermind_review_report"
RAW_EXCERPT_MAX_CHARS = 4000
INVALID_REVIEW_SAFETY_NOTE = "Invalid review output; human review is required."
AUTHORITY_CONFUSED_PATTERN = re.compile(
    r"\b(i\s+(already\s+)?(approved|merged|deployed|reworked)|"
    r"(i|we|the\s+platform)\s+(will\s+|can\s+|should\s+)?auto[-\s]?(approve|merge|deploy|rework)|"
    r"platform\s+(approved|merged|deployed|reworked))\b",
    re.IGNORECASE,
)


async def execute_review(
    db: AsyncSession,
    task_id: int,
    body: MastermindReviewExecuteRequest,
) -> MastermindReviewExecuteResponse:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project_not_found")

    try:
        preview = await preview_packet(db, task_id, body.packet)
    except HTTPException:
        raise
    except Exception as exc:
        return MastermindReviewExecuteResponse(
            task_id=task.id,
            project_id=project.id,
            status="failed",
            failure_reason=_redact(str(exc) or "packet preview failed"),
            persisted=False,
        )

    prompt = _review_prompt(preview)
    prompt_hash = _hash_text(prompt)
    browser_request = _browser_request(task, project, body, prompt)
    browser_request = browser_ai_service._with_profile_defaults(browser_request)
    gate = browser_ai_service._safety_gate(browser_request, for_execute=True)
    agent = await _find_or_create_mastermind_agent(db, browser_request.provider)
    run = await _create_mastermind_run(db, task, agent, browser_request, prompt_hash)
    if not gate.gate_passed:
        reason = _redact("; ".join(gate.blocked_reasons) or "browser_ai_gate_blocked")
        await _fail_run(db, task, run, browser_request.provider, "mastermind_review_failed", reason)
        return _failed_response(task, run.id, reason)

    await create_event(
        db,
        task_id=task.id,
        event_type="mastermind_review_submitted",
        actor=f"browser_ai:{browser_request.provider}",
        message=f"Mastermind review packet submitted by Browser AI AgentRun #{run.id}",
        payload_json=_redact(json.dumps({
            "agent_run_id": run.id,
            "prompt_hash": prompt_hash,
            "advisory_only": True,
            "no_auto_merge": True,
        }, ensure_ascii=False)),
    )
    try:
        answer = await browser_ai_service._get_driver().run(
            browser_request,
            prompt,
            browser_ai_service._timeout_seconds(browser_request),
        )
        redacted_answer = _redact(answer).strip()
        if not redacted_answer:
            raise browser_ai_service.BrowserAiStepError("capture_answer", "empty response from browser AI")
    except Exception as exc:
        reason = _redact(str(exc) or "browser AI mastermind review failed")
        await _fail_run(db, task, run, browser_request.provider, "mastermind_review_failed", reason)
        return _failed_response(task, run.id, reason)

    await create_event(
        db,
        task_id=task.id,
        event_type="mastermind_review_response_received",
        actor=f"browser_ai:{browser_request.provider}",
        message=f"Mastermind review response received for AgentRun #{run.id}",
        payload_json=_redact(json.dumps({
            "agent_run_id": run.id,
            "raw_answer_chars": len(redacted_answer),
            "advisory_only": True,
        }, ensure_ascii=False)),
    )
    parsed = parse_verdict(redacted_answer)
    excerpt, truncated = _raw_excerpt(redacted_answer, RAW_EXCERPT_MAX_CHARS)
    if not body.save_artifact:
        await _fail_run(db, task, run, browser_request.provider, "mastermind_review_failed", "save_artifact must be true")
        return _failed_response(task, run.id, "save_artifact must be true")
    artifact = _review_artifact(
        task=task,
        run=run,
        request=body,
        parsed=parsed,
        raw_excerpt=excerpt,
        raw_truncated=truncated,
        preview=preview,
    )
    db.add(artifact)
    run.status = AgentRunStatus.SUCCEEDED.value
    run.output_summary = _short(parsed.summary or parsed.verdict, 1000)
    run.output_log = "Browser AI mastermind review response captured and parsed as advisory evidence."
    run.raw_result_json = _redact(json.dumps({
        "provider": browser_request.provider,
        "prompt_hash": prompt_hash,
        "artifact_type": REPORT_ARTIFACT_TYPE,
        "verdict": parsed.verdict,
        "advisory_only": True,
        "human_confirmation_required": True,
        "no_auto_merge": True,
        "safety_notes": parsed.safety_notes,
    }, ensure_ascii=False, default=str))
    run.finished_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(artifact)
    await create_event(
        db,
        task_id=task.id,
        event_type="mastermind_review_report_imported",
        actor=f"browser_ai:{browser_request.provider}",
        message=f"Mastermind review report artifact #{artifact.id} imported with verdict {parsed.verdict}",
        payload_json=_redact(json.dumps({
            "agent_run_id": run.id,
            "artifact_id": artifact.id,
            "verdict": parsed.verdict,
            "advisory_only": True,
            "human_confirmation_required": True,
            "no_auto_merge": True,
        }, ensure_ascii=False)),
    )
    return MastermindReviewExecuteResponse(
        task_id=task.id,
        project_id=task.project_id,
        status="succeeded",
        agent_run_id=run.id,
        artifact_id=artifact.id,
        verdict=parsed.verdict,
        summary=parsed.summary,
        blocking_items=parsed.blocking_items,
        recommended_actions=parsed.recommended_actions,
        safety_notes=_execute_safety_notes(parsed),
        raw_excerpt=excerpt,
        persisted=True,
        parse_errors=parsed.parse_errors,
    )


async def preview_packet(
    db: AsyncSession,
    task_id: int,
    body: MastermindReviewPacketPreviewRequest,
) -> MastermindReviewPacketPreviewResponse:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project_not_found")

    source_refs = [
        MastermindReviewSourceRef(source_type="task", id=task.id, note="Task summary source"),
        MastermindReviewSourceRef(source_type="project", id=project.id, note="Project identity source"),
    ]
    evidence_summary = await _evidence_board_summary(db, task.id, body.include_evidence_board, source_refs)
    timeline_summary = await _timeline_summary(db, task.id, body.include_timeline, source_refs)
    memory_summary = await _project_memory_summary(db, project.id, body.include_project_memory, source_refs)
    handoff_context = await _handoff_context(db, task.id, body.include_handoff_context, source_refs)
    packet = _build_packet(
        task=task,
        project=project,
        body=body,
        evidence_board_summary=evidence_summary,
        run_timeline_summary=timeline_summary,
        project_memory_summary=memory_summary,
        handoff_context=handoff_context,
    )
    packet, truncated = _apply_packet_budget(packet, body.packet_budget)
    safety_notes = [_redact(note) for note in SAFETY_NOTES]
    return MastermindReviewPacketPreviewResponse(
        task_id=task.id,
        project_id=project.id,
        packet_type=PACKET_TYPE,
        packet=packet,
        source_refs=source_refs,
        redaction_status=MastermindReviewRedactionStatus(
            redaction_applied=True,
            truncated=truncated,
            max_chars=body.packet_budget,
        ),
        read_only=True,
        persisted=False,
        safety_notes=safety_notes,
    )


def _build_packet(
    *,
    task: Task,
    project: Project,
    body: MastermindReviewPacketPreviewRequest,
    evidence_board_summary: str,
    run_timeline_summary: str,
    project_memory_summary: str,
    handoff_context: str,
) -> dict[str, Any]:
    return _redact_jsonable({
        "pr": {
            "url": body.pr_url,
            "number": body.pr_number,
            "head_commit": body.head_commit,
            "base_commit": body.base_commit,
            "changed_files": body.changed_files,
            "body": body.pr_body,
        },
        "verification": body.verification_results.model_dump(),
        "sonarcloud": body.sonarcloud.model_dump(),
        "safety_boundary_checklist": _safety_boundary_checklist(),
        "task_summary": _task_summary(task, project),
        "evidence_board_summary": evidence_board_summary,
        "run_timeline_summary": run_timeline_summary,
        "project_memory_summary": project_memory_summary,
        "handoff_context": handoff_context,
        "review_instruction": _review_instruction(),
        "required_output_contract": _required_output_contract(),
    })


def _task_summary(task: Task, project: Project) -> str:
    return _redact(
        "\n".join([
            f"Task #{task.id}: {task.title}",
            f"Project #{project.id}: {project.display_name or project.name}",
            f"Status: {task.status}",
            f"Priority: {task.priority}",
            f"Description: {task.description or ''}",
            f"Result summary: {task.result_summary or ''}",
            f"Target branch: {task.target_branch or ''}",
            "Project.root_path is intentionally not included.",
        ])
    )


async def _evidence_board_summary(
    db: AsyncSession,
    task_id: int,
    include: bool,
    source_refs: list[MastermindReviewSourceRef],
) -> str:
    if not include:
        return NOT_INCLUDED
    board = await evidence_summary_service.get_evidence_board(db, task_id)
    source_refs.append(MastermindReviewSourceRef(source_type="evidence_board", id=task_id, note="Evidence Board summary"))
    counts: dict[str, int] = {}
    lines = [f"Evidence Board items: {len(board.items)}."]
    for item in board.items:
        counts[item.evidence_type] = counts.get(item.evidence_type, 0) + 1
    if counts:
        lines.append("Evidence types: " + ", ".join(f"{key}={value}" for key, value in sorted(counts.items())) + ".")
    for item in board.items[:12]:
        linked_ids = _linked_ids_from_board_item(item)
        lines.append(
            f"- {item.evidence_type}/{item.status} from {item.source}: {item.summary}"
            + (f" linked_ids={linked_ids}" if linked_ids else "")
        )
    return _redact("\n".join(lines))


async def _timeline_summary(
    db: AsyncSession,
    task_id: int,
    include: bool,
    source_refs: list[MastermindReviewSourceRef],
) -> str:
    if not include:
        return NOT_INCLUDED
    timeline = await evidence_summary_service.get_timeline(db, task_id)
    source_refs.append(MastermindReviewSourceRef(source_type="run_timeline", id=task_id, note="Run Timeline summary"))
    lines = [f"Run Timeline items: {len(timeline.items)}."]
    for item in timeline.items[-16:]:
        lines.append(f"- {item.time} {item.type}/{item.status} from {item.source}: {item.summary}")
    return _redact("\n".join(lines))


async def _project_memory_summary(
    db: AsyncSession,
    project_id: int,
    include: bool,
    source_refs: list[MastermindReviewSourceRef],
) -> str:
    if not include:
        return NOT_INCLUDED
    summary = await project_memory_service.get_project_memory_summary(db, project_id)
    source_refs.append(MastermindReviewSourceRef(source_type="project_memory", id=project_id, note="Project Memory summary"))
    return _redact(
        "\n".join([
            summary.summary,
            f"memory_count={summary.memory_count}",
            "memory_types=" + ", ".join(summary.memory_types),
            f"stale_count={summary.stale_count}",
            f"high_confidence_count={summary.high_confidence_count}",
        ])
    )


async def _handoff_context(
    db: AsyncSession,
    task_id: int,
    include: bool,
    source_refs: list[MastermindReviewSourceRef],
) -> str:
    if not include:
        return NOT_INCLUDED
    artifacts = (await db.execute(
        select(TaskArtifact)
        .where(TaskArtifact.task_id == task_id)
        .order_by(TaskArtifact.created_at.desc(), TaskArtifact.id.desc())
    )).scalars().all()
    events = (await db.execute(
        select(TaskEvent)
        .where(TaskEvent.task_id == task_id, TaskEvent.event_type.in_(["repair_attempt", "repair_attempt_status"]))
        .order_by(TaskEvent.created_at.desc(), TaskEvent.id.desc())
    )).scalars().all()
    lines: list[str] = []
    for artifact in artifacts:
        artifact_kind = _artifact_kind(artifact)
        if artifact_kind not in {"ai_handoff", "repair_handoff", "repair_packet"}:
            continue
        source_refs.append(MastermindReviewSourceRef(source_type=artifact_kind, id=artifact.id, note="Handoff context artifact"))
        lines.append(f"- artifact #{artifact.id} {artifact_kind}: {_artifact_summary(artifact)}")
    for event in events[:8]:
        source_refs.append(MastermindReviewSourceRef(source_type="repair_attempt", id=event.id, note="Repair attempt context"))
        lines.append(f"- event #{event.id} {event.event_type}/{event.to_status or ''}: {event.message or ''}")
    return _redact("\n".join(lines) if lines else "not_available")


def _artifact_kind(artifact: TaskArtifact) -> str:
    metadata = _loads_dict(artifact.metadata_json)
    value = str(metadata.get("type") or artifact.artifact_type or "").lower()
    if value in {"ai_handoff", "repair_handoff", "repair_packet"}:
        return value
    return ""


def _artifact_summary(artifact: TaskArtifact) -> str:
    metadata = _loads_dict(artifact.metadata_json)
    content = _loads_dict(artifact.content)
    for source in (metadata, content):
        for key in ("summary", "failure_summary", "recommended_fix_strategy", "handoff_prompt"):
            if source.get(key):
                return _short(source[key], 500)
    return _short(artifact.filename or artifact.artifact_type, 500)


def _safety_boundary_checklist() -> dict[str, bool]:
    return {
        "read_only_preview": True,
        "persisted": False,
        "provider_call": False,
        "browser_ai_execution": False,
        "review_execute_api": False,
        "artifact_write": False,
        "repository_write": False,
        "github_sonar_platform_query": False,
        "auto_approve": False,
        "auto_merge": False,
        "auto_deploy": False,
        "auto_rework": False,
    }


def _review_instruction() -> str:
    return "\n".join([
        "You are reviewing the supplied Mastermind Review Packet.",
        "Do not invent files, checks, commits, Sonar results, or verification outcomes.",
        "Compare PR body claims against packet evidence.",
        "If evidence is missing or ambiguous, return verdict `needs_human`.",
        "If there are concrete blocking issues, return verdict `request_changes`.",
        "Use only these verdicts: approved, request_changes, needs_human, invalid_review.",
        "Return structured JSON only using the required output contract.",
        "If you recommend merge, that recommendation is advisory only.",
        "You do not authorize the platform to auto approve, merge, deploy, or rework.",
    ])


def _required_output_contract() -> dict[str, Any]:
    return {
        "verdict": "approved | request_changes | needs_human | invalid_review",
        "summary": "Short review summary.",
        "blocking_items": [
            {
                "severity": "blocker | major | minor",
                "title": "Issue title",
                "evidence": "Grounded evidence from packet.",
                "recommended_action": "Action.",
            }
        ],
        "recommended_actions": [],
        "safety_notes": [],
        "confidence": "high | medium | low",
        "review_scope_confirmed": True,
    }


def parse_verdict(raw_answer: str) -> MastermindReviewParsedVerdict:
    text = _redact(raw_answer)
    data, parse_errors = _extract_structured_json(text)
    if not isinstance(data, dict):
        return MastermindReviewParsedVerdict(
            verdict="invalid_review",
            summary="Mastermind response did not contain structured JSON.",
            safety_notes=[INVALID_REVIEW_SAFETY_NOTE],
            parse_errors=parse_errors or ["structured_json_not_found"],
        )
    required = ["verdict", "summary", "blocking_items", "recommended_actions", "safety_notes", "confidence", "review_scope_confirmed"]
    missing = [key for key in required if key not in data]
    if missing:
        return MastermindReviewParsedVerdict(
            verdict="invalid_review",
            summary=_redact(str(data.get("summary") or "Mastermind response is missing required fields.")),
            safety_notes=[INVALID_REVIEW_SAFETY_NOTE],
            parse_errors=[f"missing_required_fields:{','.join(missing)}"],
        )
    verdict = str(data.get("verdict") or "").strip()
    parse_errors.extend(_validate_contract_types(data))
    if verdict not in VERDICTS:
        parse_errors.append(f"unknown_verdict:{verdict}")
    if parse_errors:
        return MastermindReviewParsedVerdict(
            verdict="invalid_review",
            summary=_redact(str(data.get("summary") or "Mastermind response failed schema validation.")),
            blocking_items=_list_of_dicts(data.get("blocking_items")),
            recommended_actions=_list_value(data.get("recommended_actions")),
            safety_notes=_list_value(data.get("safety_notes")) + [INVALID_REVIEW_SAFETY_NOTE],
            confidence=_confidence(data.get("confidence")),
            review_scope_confirmed=bool(data.get("review_scope_confirmed")),
            parse_errors=parse_errors,
        )
    safety_notes = [_redact(str(note)) for note in _list_value(data.get("safety_notes"))]
    if _authority_confused(text):
        return MastermindReviewParsedVerdict(
            verdict="needs_human",
            summary=_redact(str(data.get("summary") or "Mastermind response confused advisory review authority.")),
            blocking_items=_list_of_dicts(data.get("blocking_items")),
            recommended_actions=_list_value(data.get("recommended_actions")),
            safety_notes=safety_notes + [
                "Mastermind response mentioned approve, merge, deploy, or rework authority; human confirmation is required.",
            ],
            confidence=_confidence(data.get("confidence")),
            review_scope_confirmed=bool(data.get("review_scope_confirmed")),
        )
    return MastermindReviewParsedVerdict(
        verdict=verdict,
        summary=_redact(str(data.get("summary") or "")),
        blocking_items=_list_of_dicts(data.get("blocking_items")),
        recommended_actions=[_redact(str(item)) for item in _list_value(data.get("recommended_actions"))],
        safety_notes=safety_notes,
        confidence=_confidence(data.get("confidence")),
        review_scope_confirmed=bool(data.get("review_scope_confirmed")),
    )


def _review_prompt(preview: MastermindReviewPacketPreviewResponse) -> str:
    body = {
        "packet_type": preview.packet_type,
        "task_id": preview.task_id,
        "project_id": preview.project_id,
        "packet": preview.packet,
        "source_refs": [ref.model_dump() for ref in preview.source_refs],
        "redaction_status": preview.redaction_status.model_dump(),
        "read_only": True,
        "persisted": False,
        "advisory_only": True,
        "human_confirmation_required": True,
        "no_auto_merge": True,
    }
    return _redact("\n".join([
        "You are the Browser AI GPT mastermind reviewer.",
        "Review the supplied Mastermind Review Packet.",
        "Return structured JSON only. Do not wrap the JSON in prose.",
        _review_instruction(),
        "Required output contract:",
        json.dumps(_required_output_contract(), ensure_ascii=False, indent=2),
        "Mastermind Review Packet:",
        json.dumps(body, ensure_ascii=False, indent=2, default=str),
    ]))


def _browser_request(
    task: Task,
    project: Project,
    body: MastermindReviewExecuteRequest,
    prompt: str,
) -> BrowserAiRequest:
    options = body.browser_ai
    return BrowserAiRequest(
        project_id=project.id,
        task_id=task.id,
        provider=options.provider_profile,
        target_url=options.target_url,
        prompt_source="custom_prompt",
        custom_prompt=prompt,
        input_selector=options.prompt_selector,
        send_selector=options.submit_selector,
        response_selector=options.response_selector,
        scroll_container_selector=options.scroll_container_selector,
        copy_button_selector=options.copy_button_selector,
        login_hint_selector=options.login_hint_selector,
        timeout_seconds=options.stable_response_timeout_seconds,
        stable_polls=options.stable_polls,
        stable_interval_ms=options.stable_interval_ms,
    )


async def _find_or_create_mastermind_agent(db: AsyncSession, provider: str) -> AgentProfile:
    result = await db.execute(
        select(AgentProfile).where(
            AgentProfile.provider == "browser_ai",
            AgentProfile.agent_type == "mastermind_review",
            AgentProfile.name == f"browser-ai-mastermind-{provider}",
        )
    )
    agent = result.scalar_one_or_none()
    if agent:
        return agent
    agent = AgentProfile(
        name=f"browser-ai-mastermind-{provider}",
        agent_type="mastermind_review",
        provider="browser_ai",
        model_name=provider,
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return agent


async def _create_mastermind_run(
    db: AsyncSession,
    task: Task,
    agent: AgentProfile,
    request: BrowserAiRequest,
    prompt_hash: str,
) -> AgentRun:
    run = AgentRun(
        task_id=task.id,
        project_id=task.project_id,
        agent_id=agent.id,
        run_type="mastermind_review",
        status=AgentRunStatus.RUNNING.value,
        input_prompt=f"Mastermind Review prompt redacted; prompt_hash={prompt_hash}; advisory_only=true",
        started_at=datetime.now(timezone.utc),
        raw_result_json=_redact(json.dumps({
            "provider": request.provider,
            "prompt_source": "mastermind_review_packet",
            "prompt_hash": prompt_hash,
            "browser_opened": True,
            "advisory_only": True,
            "no_auto_merge": True,
        }, ensure_ascii=False)),
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)
    return run


async def _fail_run(
    db: AsyncSession,
    task: Task,
    run: AgentRun,
    provider: str,
    event_type: str,
    reason: str,
) -> None:
    run.status = AgentRunStatus.FAILED.value
    run.error_message = _redact(reason)
    run.output_summary = _short(reason, 1000)
    run.finished_at = datetime.now(timezone.utc)
    run.raw_result_json = _redact(json.dumps({
        "status": "failed",
        "failure_reason": reason,
        "advisory_only": True,
        "human_confirmation_required": True,
        "no_auto_merge": True,
    }, ensure_ascii=False))
    await db.flush()
    await create_event(
        db,
        task_id=task.id,
        event_type=event_type,
        actor=f"browser_ai:{provider}",
        message=f"Mastermind review failed for AgentRun #{run.id}: {_short(reason, 500)}",
        payload_json=_redact(json.dumps({
            "agent_run_id": run.id,
            "failure_reason": reason,
            "advisory_only": True,
            "no_auto_merge": True,
        }, ensure_ascii=False)),
    )


def _failed_response(task: Task, run_id: int, reason: str) -> MastermindReviewExecuteResponse:
    return MastermindReviewExecuteResponse(
        task_id=task.id,
        project_id=task.project_id,
        status="failed",
        agent_run_id=run_id,
        artifact_id=None,
        failure_reason=_redact(reason),
        persisted=False,
    )


def _review_artifact(
    *,
    task: Task,
    run: AgentRun,
    request: MastermindReviewExecuteRequest,
    parsed: MastermindReviewParsedVerdict,
    raw_excerpt: str,
    raw_truncated: bool,
    preview: MastermindReviewPacketPreviewResponse,
) -> TaskArtifact:
    payload = _redact_jsonable({
        "artifact_type": REPORT_ARTIFACT_TYPE,
        "task_id": task.id,
        "project_id": task.project_id,
        "pr_url": request.packet.pr_url,
        "pr_number": request.packet.pr_number,
        "head_commit": request.packet.head_commit,
        "base_commit": request.packet.base_commit,
        "verdict": parsed.verdict,
        "summary": parsed.summary,
        "blocking_items": parsed.blocking_items,
        "recommended_actions": parsed.recommended_actions,
        "safety_notes": _execute_safety_notes(parsed),
        "raw_excerpt": raw_excerpt,
        "redaction_status": {
            "redaction_applied": True,
            "truncated": raw_truncated,
            "max_chars": RAW_EXCERPT_MAX_CHARS,
        },
        "source_agent_run_ids": [run.id],
        "source_artifact_ids": [],
        "source_timeline_event_ids": [],
        "source_evidence_ids": [ref.id for ref in preview.source_refs if ref.id is not None],
        "read_only": True,
        "persisted": True,
        "advisory_only": True,
        "human_confirmation_required": True,
        "no_auto_merge": True,
        "parse_errors": parsed.parse_errors,
    })
    content = json.dumps(payload, ensure_ascii=False, default=str)
    data = content.encode("utf-8")
    return TaskArtifact(
        task_id=task.id,
        artifact_type=REPORT_ARTIFACT_TYPE,
        content=content,
        filename=f"mastermind_review_run_{run.id}_report.json",
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        is_truncated=raw_truncated,
        metadata_json=json.dumps({
            "type": REPORT_ARTIFACT_TYPE,
            "source": "mastermind_review",
            "provider": "browser_ai",
            "role": "mastermind_review",
            "agent_run_id": run.id,
            "status": parsed.verdict,
            "summary": parsed.summary,
            "safety_notes": parsed.safety_notes,
            "advisory_only": True,
            "human_confirmation_required": True,
            "no_auto_merge": True,
            "read_only": True,
            "persisted": True,
            "truncated": raw_truncated,
        }, ensure_ascii=False, default=str),
    )


def _execute_safety_notes(parsed: MastermindReviewParsedVerdict) -> list[str]:
    combined = [_redact(str(note)) for note in parsed.safety_notes]
    for note in EXECUTE_SAFETY_NOTES:
        redacted = _redact(note)
        if redacted not in combined:
            combined.append(redacted)
    return combined


def _extract_structured_json(text: str) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    for candidate in _json_candidates(text):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            errors.append(f"json_decode_error:{exc.msg}")
            continue
        if isinstance(data, dict):
            return data, []
        errors.append("json_root_not_object")
    return None, errors


def _json_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for match in re.finditer(r"```(?:json)?\s*", text, flags=re.IGNORECASE):
        start = match.end()
        end = text.find("```", start)
        if end >= 0:
            candidates.append(text[start:end].strip())
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        candidates.append(stripped)
    return candidates


def _validate_contract_types(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(data.get("blocking_items"), list):
        errors.append("blocking_items_not_array")
    if not isinstance(data.get("recommended_actions"), list):
        errors.append("recommended_actions_not_array")
    if not isinstance(data.get("safety_notes"), list):
        errors.append("safety_notes_not_array")
    if _confidence(data.get("confidence")) not in CONFIDENCES:
        errors.append("invalid_confidence")
    if not isinstance(data.get("review_scope_confirmed"), bool):
        errors.append("review_scope_confirmed_not_boolean")
    return errors


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [_redact_jsonable(item) for item in value if isinstance(item, dict)]


def _confidence(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in CONFIDENCES else "low"


def _authority_confused(text: str) -> bool:
    return bool(AUTHORITY_CONFUSED_PATTERN.search(text or ""))


def _raw_excerpt(text: str, limit: int) -> tuple[str, bool]:
    clean = _redact(text)
    if len(clean) <= limit:
        return clean, False
    return clean[:limit].rstrip() + "\n...[truncated]", True


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _apply_packet_budget(packet: dict[str, Any], budget: int) -> tuple[dict[str, Any], bool]:
    truncated = False
    if _packet_size(packet) <= budget:
        return packet, truncated
    truncated = True
    text_paths = [
        ("pr", "body"),
        ("handoff_context",),
        ("evidence_board_summary",),
        ("run_timeline_summary",),
        ("project_memory_summary",),
        ("task_summary",),
    ]
    for path in text_paths:
        if _packet_size(packet) <= budget:
            break
        value = _get_path(packet, path)
        if not isinstance(value, str) or len(value) <= 40:
            continue
        overage = _packet_size(packet) - budget
        keep = max(40, len(value) - overage - 80)
        _set_path(packet, path, _truncate(value, keep))
    if _packet_size(packet) > budget:
        for path in text_paths:
            value = _get_path(packet, path)
            if isinstance(value, str) and len(value) > 80:
                _set_path(packet, path, _truncate(value, 80))
    return packet, truncated


def _packet_size(packet: dict[str, Any]) -> int:
    return len(json.dumps(packet, ensure_ascii=False, default=str))


def _get_path(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _set_path(data: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    current = data
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value


def _linked_ids_from_board_item(item: Any) -> dict[str, int]:
    values = {
        "artifact_id": item.artifact_id,
        "agent_run_id": item.agent_run_id,
        "dispatch_batch_id": item.dispatch_batch_id,
        "dispatch_job_id": item.dispatch_job_id,
        "repair_attempt_id": item.repair_attempt_id,
    }
    return {key: value for key, value in values.items() if value is not None}


def _redact_jsonable(value: Any) -> Any:
    if isinstance(value, str):
        return _redact(value)
    if isinstance(value, list):
        return [_redact_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_jsonable(item) for key, item in value.items()}
    return value


def _redact(value: str | None) -> str:
    redacted = redact_secrets(value or "")
    redacted = re.sub(r"\bcookie\s*=\s*\S+", "cookie=***REDACTED***", redacted, flags=re.IGNORECASE)
    redacted = re.sub(r"\bsession\s*=\s*\S+", "session=***REDACTED***", redacted, flags=re.IGNORECASE)
    redacted = re.sub(r"\bsecret_ref\s*=\s*\S+", "secret_ref=***REDACTED***", redacted, flags=re.IGNORECASE)
    return redacted


def _truncate(value: str, limit: int) -> str:
    clean = _redact(value)
    if len(clean) <= limit:
        return clean
    return clean[:limit].rstrip() + "\n...[truncated]"


def _short(value: Any, limit: int) -> str:
    return " ".join(_truncate(str(value or ""), limit).split())


def _loads_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}

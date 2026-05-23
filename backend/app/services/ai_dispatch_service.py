import json
import hashlib
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.enums import AgentRunStatus, AgentRunType
from app.models.agent_profile import AgentProfile
from app.models.agent_run import AgentRun
from app.models.task import Task
from app.models.task_artifact import TaskArtifact
from app.models.task_event import TaskEvent
from app.schemas.ai_dispatch import (
    AiDispatchDryRunResponse,
    AiDispatchExecuteResponse,
    AiExecuteStep,
    SafetyGateInfo,
)
from app.schemas.ai_provider import AgentRunResult
from app.services.ai_output_governance_service import redact_secrets, validate_patch_diff
from app.services.ai_provider_service import (
    _apply_governance,
    _create_artifacts_from_result,
)
from app.services.event_service import create_event
from app.services.prompt_template_service import preview as prompt_preview


_DISPATCH_ACTOR = "ai_dispatch"
_MODE_TO_RUN_TYPE = {
    "planning": AgentRunType.PLAN.value,
    "patch_generation": AgentRunType.EXECUTE.value,
    "review": AgentRunType.REVIEW.value,
    "risk": AgentRunType.REVIEW.value,
    "browser_reviewer": AgentRunType.REVIEW.value,
}
_MODE_TO_AGENT_TYPE = {
    "planning": "planner",
    "patch_generation": "executor",
    "review": "reviewer",
    "risk": "reviewer",
    "browser_reviewer": "reviewer",
}


def _failed_response(
    *,
    run: AgentRun | None,
    task_id: int | None,
    prompt_hash: str,
    context_packet_hash: str,
    steps: list[AiExecuteStep],
    output_summary: str | None = None,
) -> AiDispatchExecuteResponse:
    return AiDispatchExecuteResponse(
        agent_run_id=run.id if run else 0,
        task_id=task_id,
        status=AgentRunStatus.FAILED.value,
        output_summary=output_summary,
        pipeline_status="ai_failed",
        prompt_hash=prompt_hash,
        context_packet_hash=context_packet_hash,
        steps=steps,
    )


def _redact_dispatch_secrets(text: str | None) -> str | None:
    if text is None:
        return None
    redacted = redact_secrets(text)
    api_key = getattr(settings, "openai_api_key", "") or ""
    if api_key:
        redacted = redacted.replace(api_key, "***REDACTED***")
    return redacted


def _redact_result_for_storage(result):
    result.output_summary = _redact_dispatch_secrets(result.output_summary) or ""
    result.output_log = _redact_dispatch_secrets(result.output_log) or ""
    result.raw_result_json = _redact_dispatch_secrets(result.raw_result_json)
    result.plan_md = _redact_dispatch_secrets(result.plan_md)
    result.patch_diff = _redact_dispatch_secrets(result.patch_diff)
    result.review_md = _redact_dispatch_secrets(result.review_md)
    if result.risk_report:
        safe_json = _redact_dispatch_secrets(json.dumps(result.risk_report, ensure_ascii=False))
        result.risk_report = json.loads(safe_json or "{}")
    return result


def _dispatch_metadata(preview, mode: str) -> dict:
    return {
        "provider": "openai",
        "model": settings.openai_model,
        "mode": mode,
        "prompt_hash": preview.prompt_hash,
        "context_packet_hash": preview.context_packet_hash,
        "estimated_prompt_tokens": preview.token_budget.estimated_prompt_tokens,
        "redaction_applied": True,
    }


def _persist_dispatch_metadata(run: AgentRun, dispatch_metadata: dict) -> None:
    current = {}
    if run.raw_result_json:
        try:
            parsed = json.loads(run.raw_result_json)
            if isinstance(parsed, dict):
                current = parsed
        except json.JSONDecodeError:
            current = {"provider_raw": _redact_dispatch_secrets(run.raw_result_json)}
    current["dispatch"] = dispatch_metadata
    safe_json = _redact_dispatch_secrets(json.dumps(current, ensure_ascii=False)) or "{}"
    run.raw_result_json = safe_json


def _redacted_json_artifact(run: AgentRun, artifact_type: str, filename: str, payload: dict) -> TaskArtifact:
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    content = _redact_dispatch_secrets(content) or "{}"
    data = content.encode("utf-8")
    return TaskArtifact(
        task_id=run.task_id,
        artifact_type=artifact_type,
        content=content,
        filename=filename,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


def _browser_review_artifact_payload(review_md: str | None) -> dict | None:
    review = (review_md or "").strip()
    if not review:
        return None
    parsed = _extract_json_object(review)
    if isinstance(parsed, dict):
        return parsed
    lower = review.lower()
    advisory_ok = "advisory_only" in lower and "true" in lower
    not_final_ok = "not_final_approval" in lower and "true" in lower
    if not advisory_ok or not not_final_ok:
        return None
    return {
        "advisory_only": True,
        "not_final_approval": True,
        "review_md": review,
    }


async def _create_dispatch_mode_artifacts(db: AsyncSession, run: AgentRun, mode: str, result: AgentRunResult) -> None:
    artifact = None
    if mode == "risk" and isinstance(result.risk_report, dict):
        artifact = _redacted_json_artifact(
            run,
            "agent_risk_report",
            f"agent_run_{run.id}_risk_report.json",
            result.risk_report,
        )
    elif mode == "browser_reviewer":
        payload = _browser_review_artifact_payload(result.review_md)
        if isinstance(payload, dict):
            artifact = _redacted_json_artifact(
                run,
                "agent_browser_review",
                f"agent_run_{run.id}_browser_ai_review.json",
                payload,
            )
    if artifact is None:
        return
    db.add(artifact)
    await db.flush()
    await create_event(
        db,
        task_id=run.task_id,
        event_type="artifact_uploaded",
        actor=f"agent_run:{run.id}",
        message=f"S11 dispatch artifact created: {artifact.filename}",
    )


def _extract_json_object(text: str) -> dict | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _parse_dispatch_response(mode: str, response_text: str, ts: str) -> AgentRunResult:
    words = len(response_text.split())
    summary = response_text[:200].replace("\n", " ") + ("..." if len(response_text) > 200 else "")
    if mode == "planning":
        return AgentRunResult(
            output_summary=f"AI-generated plan ({words} words): {summary}",
            output_log=f"[{ts}] AI dispatch generated plan ({words} words)",
            raw_result_json=json.dumps({"plan_md": response_text}, ensure_ascii=False),
            plan_md=response_text,
        )
    if mode == "patch_generation":
        return AgentRunResult(
            output_summary=f"AI-generated patch ({words} words): {summary}",
            output_log=f"[{ts}] AI dispatch generated patch ({words} words)",
            raw_result_json=json.dumps({"patch_diff": response_text}, ensure_ascii=False),
            patch_diff=response_text,
        )
    if mode == "review":
        return AgentRunResult(
            output_summary=f"AI review ({words} words): {summary}",
            output_log=f"[{ts}] AI dispatch generated review ({words} words)",
            raw_result_json=json.dumps({"review_md": response_text}, ensure_ascii=False),
            review_md=response_text,
        )
    if mode == "risk":
        risk_report = _extract_json_object(response_text)
        return AgentRunResult(
            output_summary=f"AI risk assessment ({words} words): {summary}",
            output_log=f"[{ts}] AI dispatch generated risk assessment ({words} words)",
            raw_result_json=json.dumps({"risk_report": risk_report} if risk_report else {"raw_response": response_text}, ensure_ascii=False),
            risk_report=risk_report,
        )
    if mode == "browser_reviewer":
        parsed = _extract_json_object(response_text)
        review_payload = parsed if parsed is not None else {"review_md": response_text}
        review_md = json.dumps(parsed, ensure_ascii=False) if parsed is not None else response_text
        return AgentRunResult(
            output_summary=f"AI browser review ({words} words): {summary}",
            output_log=f"[{ts}] AI dispatch generated browser review ({words} words)",
            raw_result_json=json.dumps({"browser_ai_review": review_payload}, ensure_ascii=False),
            review_md=review_md,
        )
    return AgentRunResult(
        output_summary=f"AI response ({words} words): {summary}",
        output_log=f"[{ts}] AI dispatch generated response ({words} words)",
        raw_result_json=json.dumps({"raw_response": response_text}, ensure_ascii=False),
    )


async def _execute_openai_with_prompt_preview(preview, mode: str) -> AgentRunResult:
    from app.services.openai_provider import OpenAIProvider

    provider = OpenAIProvider()
    response_text = await provider._call_openai(
        preview.system_prompt_preview,
        preview.user_prompt_preview,
    )
    if not response_text or not response_text.strip():
        raise RuntimeError("AI returned empty response")
    return _parse_dispatch_response(mode, response_text, datetime.now(timezone.utc).isoformat())


def _normalize_result_for_mode(result, mode: str):
    """Keep only the artifact type allowed for the requested dispatch mode."""
    if mode == "planning":
        result.patch_diff = None
        result.review_md = None
        result.risk_report = None
    elif mode == "patch_generation":
        result.plan_md = None
        result.review_md = None
        result.risk_report = None
    elif mode == "review":
        result.plan_md = None
        result.patch_diff = None
        result.risk_report = None
    elif mode == "risk":
        result.plan_md = None
        result.patch_diff = None
        result.review_md = None
    elif mode == "browser_reviewer":
        result.plan_md = None
        result.patch_diff = None
        result.risk_report = None
    return result


def _mode_validation_error(result, mode: str) -> str | None:
    if mode == "planning" and not (result.plan_md or "").strip():
        return "malformed_response: planning mode requires plan.md"
    if mode == "patch_generation":
        patch = result.patch_diff or ""
        check = validate_patch_diff(patch)
        if not patch.strip() or not check.has_diff_header or check.is_empty:
            return "malformed_response: patch_generation requires unified diff"
    if mode == "review" and not (result.review_md or "").strip():
        return "malformed_response: review mode requires review.md"
    if mode == "risk":
        if not isinstance(result.risk_report, dict):
            return "malformed_response: risk mode requires valid risk_report.json"
    if mode == "browser_reviewer":
        review = (result.review_md or "").strip()
        parsed = _extract_json_object(review)
        if parsed is not None:
            advisory_ok = parsed.get("advisory_only") is True
            not_final_ok = parsed.get("not_final_approval") is True
        else:
            lower = review.lower()
            advisory_ok = "advisory_only" in lower and "true" in lower
            not_final_ok = "not_final_approval" in lower and "true" in lower
        if not advisory_ok or not not_final_ok:
            return "malformed_response: browser_reviewer requires advisory_only and not_final_approval"
    return None


async def _mark_run_failed(
    db: AsyncSession,
    run: AgentRun,
    task_id: int,
    message: str,
    actor: str = _DISPATCH_ACTOR,
) -> None:
    run.status = AgentRunStatus.FAILED.value
    run.error_message = message
    run.finished_at = datetime.now(timezone.utc)
    await db.flush()
    await create_event(
        db,
        task_id=task_id,
        event_type="agent_run_failed",
        actor=actor,
        message=f"AgentRun #{run.id} failed: {_redact_dispatch_secrets(message)}",
    )


async def _list_artifacts(db: AsyncSession, task_id: int) -> list[dict]:
    result = await db.execute(
        select(TaskArtifact)
        .where(TaskArtifact.task_id == task_id)
        .order_by(TaskArtifact.id)
    )
    return [
        {
            "id": art.id,
            "artifact_type": art.artifact_type,
            "filename": art.filename,
            "size_bytes": art.size_bytes,
            "sha256": art.sha256,
            "content": art.content,
        }
        for art in result.scalars().all()
    ]


async def _list_events(db: AsyncSession, task_id: int) -> list[dict]:
    result = await db.execute(
        select(TaskEvent)
        .where(TaskEvent.task_id == task_id)
        .order_by(TaskEvent.id)
    )
    return [
        {
            "id": event.id,
            "event_type": event.event_type,
            "actor": event.actor,
            "message": event.message,
        }
        for event in result.scalars().all()
    ]


def _check_safety_gate(mode: str) -> SafetyGateInfo:
    from app.schemas.ai_context_packet import VALID_MODES
    gate = SafetyGateInfo(
        execution_enabled=settings.ai_execution_enabled,
        openai_key_present=bool(settings.openai_api_key),
        provider_allowed="openai" in settings.provider_allowlist,
        mode_valid=mode in VALID_MODES,
    )
    gate.gate_passed = (
        gate.execution_enabled
        and gate.openai_key_present
        and gate.provider_allowed
        and gate.mode_valid
        and gate.budget_ok
    )
    return gate


def dry_run(
    task_goal: str,
    module_name: str,
    task_type: str,
    mode: str,
) -> AiDispatchDryRunResponse:
    gate = _check_safety_gate(mode)
    preview = prompt_preview(
        task_goal=task_goal,
        module_name=module_name,
        task_type=task_type,
        mode=mode,
    )
    return AiDispatchDryRunResponse(
        provider="openai",
        model=settings.openai_model,
        mode=mode,
        prompt_hash=preview.prompt_hash,
        context_packet_hash=preview.context_packet_hash,
        estimated_tokens=preview.token_budget.estimated_prompt_tokens,
        safety_gate=gate,
        would_dispatch=False,
    )


async def _find_or_create_openai_agent(db: AsyncSession, mode: str) -> AgentProfile:
    agent_type = _MODE_TO_AGENT_TYPE.get(mode, "planner")
    result = await db.execute(
        select(AgentProfile).where(
            AgentProfile.provider == "openai",
            AgentProfile.agent_type == agent_type,
        )
    )
    agent = result.scalar_one_or_none()
    if agent:
        return agent
    agent = AgentProfile(
        name=f"openai-{agent_type}",
        agent_type=agent_type,
        provider="openai",
        model_name=settings.openai_model,
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return agent


async def _ensure_task(db: AsyncSession, task_id: int | None, project_id: int) -> Task:
    if task_id is not None:
        task = await db.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        if task.status == "archived":
            raise HTTPException(status_code=409, detail="Task is archived")
        return task
    task = Task(
        project_id=project_id,
        title=f"AI Dispatch {datetime.now(timezone.utc).isoformat()}",
        status="dispatched",
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


async def execute(
    db: AsyncSession,
    task_goal: str,
    module_name: str,
    task_type: str,
    mode: str,
    task_id: int | None = None,
    project_id: int = 1,
) -> AiDispatchExecuteResponse:
    steps: list[AiExecuteStep] = []

    def _step(name: str, status: str, details: str | None = None):
        steps.append(AiExecuteStep(step=name, status=status, details=details))

    _step("preflight", "running", "Checking execution preconditions")
    gate = _check_safety_gate(mode)
    if not gate.gate_passed:
        failures = []
        if not gate.execution_enabled:
            failures.append("AI_EXECUTION_ENABLED is not set")
        if not gate.openai_key_present:
            failures.append("OPENAI_API_KEY is not set")
        if not gate.provider_allowed:
            failures.append("openai not in provider allowlist")
        if not gate.mode_valid:
            failures.append(f"Unknown mode '{mode}'")
        _step("preflight", "blocked", "; ".join(failures))
        raise HTTPException(status_code=400, detail="; ".join(failures))
    _step("preflight", "passed", "All preconditions met")

    _step("prompt_build", "running", "Building prompt via Prompt Template Preview")
    preview = prompt_preview(
        task_goal=task_goal,
        module_name=module_name,
        task_type=task_type,
        mode=mode,
    )
    if preview.token_budget.budget_status == "over_limit":
        _step("prompt_build", "blocked", "Token budget over limit")
        raise HTTPException(status_code=400, detail="Token budget over limit")
    budget_status = preview.token_budget.budget_status
    _step("prompt_build", "passed", f"Estimated {preview.token_budget.estimated_prompt_tokens} tokens ({budget_status})")
    dispatch_metadata = _dispatch_metadata(preview, mode)

    _step("agent_setup", "running", "Finding or creating openai agent profile")
    agent = await _find_or_create_openai_agent(db, mode)
    _step("agent_setup", "passed", f"Agent profile #{agent.id} ({agent.provider}/{agent.agent_type})")

    _step("task_setup", "running", "Ensuring task exists")
    task = await _ensure_task(db, task_id, project_id)
    _step("task_setup", "passed", f"Task #{task.id} ({task.status})")

    _step("agent_run_creation", "running", "Creating AgentRun")
    run_type = _MODE_TO_RUN_TYPE.get(mode, AgentRunType.PLAN.value)
    full_prompt = (
        f"Goal: {task_goal or '(not specified)'}\n"
        f"Module: {module_name or '(not specified)'}\n"
        f"Type: {task_type or '(not specified)'}\n"
        f"Mode: {mode}\n"
    )
    run = AgentRun(
        task_id=task.id,
        project_id=task.project_id,
        agent_id=agent.id,
        run_type=run_type,
        status=AgentRunStatus.QUEUED.value,
        input_prompt=full_prompt,
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)
    await create_event(db, task_id=task.id, event_type="agent_run_created",
                       actor=_DISPATCH_ACTOR, message=f"AgentRun #{run.id} created by auto dispatch")
    _step("agent_run_creation", "passed", f"AgentRun #{run.id} ({run_type})")

    _step("status_running", "running", "Transitioning AgentRun to running")
    run.status = AgentRunStatus.RUNNING.value
    run.started_at = datetime.now(timezone.utc)
    await db.flush()
    await create_event(db, task_id=task.id, event_type="agent_run_started",
                       actor=_DISPATCH_ACTOR, message=f"AgentRun #{run.id} started")
    _step("status_running", "passed", "AgentRun is now running")

    _step("ai_execution", "running", "Calling AI provider")
    try:
        result = await _execute_openai_with_prompt_preview(preview, mode)
    except HTTPException:
        await _mark_run_failed(db, run, task.id, "AI provider execution failed")
        _persist_dispatch_metadata(run, dispatch_metadata)
        await db.flush()
        _step("ai_execution", "failed", "AI provider execution failed")
        return _failed_response(
            run=run,
            task_id=task.id,
            prompt_hash=preview.prompt_hash,
            context_packet_hash=preview.context_packet_hash,
            steps=steps,
        )
    except Exception as e:
        await _mark_run_failed(db, run, task.id, str(e))
        _persist_dispatch_metadata(run, dispatch_metadata)
        await db.flush()
        _step("ai_execution", "failed", _redact_dispatch_secrets(str(e)))
        return _failed_response(
            run=run,
            task_id=task.id,
            output_summary="AI provider execution failed",
            prompt_hash=preview.prompt_hash,
            context_packet_hash=preview.context_packet_hash,
            steps=steps,
        )
    _step("ai_execution", "passed", "AI provider returned result successfully")

    result = _redact_result_for_storage(result)
    result = _normalize_result_for_mode(result, mode)
    mode_error = _mode_validation_error(result, mode)
    if mode_error:
        await _mark_run_failed(db, run, task.id, mode_error)
        _persist_dispatch_metadata(run, dispatch_metadata)
        await db.flush()
        _step("response_validation", "failed", mode_error)
        return _failed_response(
            run=run,
            task_id=task.id,
            output_summary="malformed_response",
            prompt_hash=preview.prompt_hash,
            context_packet_hash=preview.context_packet_hash,
            steps=steps,
        )
    _step("response_validation", "passed", f"{mode} response shape is valid")

    _step("governance", "running", "Validating and governing AI output")
    try:
        await _apply_governance(db, run, agent, result, actor=_DISPATCH_ACTOR)
    except HTTPException:
        await _mark_run_failed(db, run, task.id, "Governance validation failed")
        _persist_dispatch_metadata(run, dispatch_metadata)
        await db.flush()
        _step("governance", "failed", "Governance validation failed")
        return _failed_response(
            run=run,
            task_id=task.id,
            output_summary="malformed_response",
            prompt_hash=preview.prompt_hash,
            context_packet_hash=preview.context_packet_hash,
            steps=steps,
        )
    _step("governance", "passed", "AI output passed all validation checks")

    _step("artifact_creation", "running", "Creating artifacts from AI output")
    _persist_dispatch_metadata(run, dispatch_metadata)
    await _create_artifacts_from_result(db, run, result)
    await _create_dispatch_mode_artifacts(db, run, mode, result)
    run.status = AgentRunStatus.SUCCEEDED.value
    run.output_summary = result.output_summary
    run.output_diff = result.patch_diff
    run.output_log = result.output_log
    await db.flush()
    await create_event(db, task_id=task.id, event_type="agent_run_succeeded",
                       actor=_DISPATCH_ACTOR, message=f"AgentRun #{run.id} succeeded")
    _step("artifact_creation", "passed", "Artifacts created and AgentRun marked succeeded")

    sandbox_applied = False
    sandbox_gate_passed = False
    sandbox_blocked_reasons: list[str] = []
    pipeline_status = "succeeded"

    if mode == "patch_generation":
        _step("sandbox_apply", "running", "Auto-applying patch in sandbox")
        try:
            from app.services.patch_apply_sandbox_service import apply_patch_in_sandbox
            sandbox_result = await apply_patch_in_sandbox(db, task.id, run.id)
            sandbox_applied = sandbox_result.success
            if not sandbox_applied:
                pipeline_status = "sandbox_failed"
            _step("sandbox_apply",
                  "passed" if sandbox_applied else "failed",
                  sandbox_result.error_message or "Patch applied" if sandbox_applied else "Apply failed")
        except Exception as e:
            pipeline_status = "sandbox_failed"
            _step("sandbox_apply", "failed", str(e))

        _step("sandbox_gate", "running", "Evaluating sandbox gate")
        try:
            from app.services.sandbox_approval_gate_service import evaluate_and_record_gate
            gate_result = await evaluate_and_record_gate(db, task.id)
            sandbox_gate_passed = gate_result.passed
            sandbox_blocked_reasons = [r.reason for r in (gate_result.blocked_reasons or [])]
            if pipeline_status == "succeeded" and not sandbox_gate_passed:
                pipeline_status = "sandbox_gate_blocked"
            _step("sandbox_gate",
                  "passed" if sandbox_gate_passed else "blocked",
                  "; ".join(sandbox_blocked_reasons) if sandbox_blocked_reasons else "Gate passed")
        except Exception as e:
            if pipeline_status == "succeeded":
                pipeline_status = "sandbox_gate_blocked"
            _step("sandbox_gate", "failed", str(e))

    run.finished_at = datetime.now(timezone.utc)
    await db.flush()

    return AiDispatchExecuteResponse(
        agent_run_id=run.id,
        task_id=task.id,
        status=AgentRunStatus.SUCCEEDED.value,
        output_summary=run.output_summary,
        output_diff=run.output_diff,
        artifacts=await _list_artifacts(db, task.id),
        events=await _list_events(db, task.id),
        sandbox_applied=sandbox_applied,
        sandbox_gate_passed=sandbox_gate_passed,
        sandbox_gate_blocked_reasons=sandbox_blocked_reasons,
        pipeline_status=pipeline_status,
        prompt_hash=preview.prompt_hash,
        context_packet_hash=preview.context_packet_hash,
        token_usage={"estimated_prompt_tokens": preview.token_budget.estimated_prompt_tokens},
        steps=steps,
    )

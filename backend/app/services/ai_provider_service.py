"""AI Provider dispatch service.

Dispatches AgentRun execution through the appropriate provider.
- v0.3: SandboxProvider is the default.
- v0.3 S2: OpenAIProvider is available when explicitly configured (provider="openai").
- If the AgentProfile.provider field is empty or unknown, falls back to sandbox.
- API key is read from OPENAI_API_KEY env var ONLY, never from AgentProfile.secret_ref.
"""

import os
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun
from app.models.task_artifact import TaskArtifact
from app.schemas.ai_provider import AgentRunResult
from app.schemas.agent_run import AgentRunUpdate
from app.services.agent_run_service import update_agent_run
from app.services.sandbox_provider import SandboxProvider
from app.services.event_service import create_event
from app.models.agent_profile import AgentProfile
from app.enums import AgentRunStatus
import hashlib


async def dispatch_agent_run(db: AsyncSession, run_id: int, actor: str = "system") -> AgentRun:
    """Execute an AgentRun through the appropriate provider and update its status.

    v0.3 S2: Provider selection:
    - AgentProfile.provider == "openai" → OpenAIProvider (requires OPENAI_API_KEY)
    - All others (sandbox, empty, unknown, codex, claude, manual) → SandboxProvider
    - API key is read from OPENAI_API_KEY env var, NEVER from AgentProfile.secret_ref

    Flow: queued → running → succeeded (or failed on error)
    On success: writes output_summary, output_log, raw_result_json, creates artifacts.
    On failure: marks as failed, stops further progression.
    """
    run = await db.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="AgentRun not found")

    if run.status != AgentRunStatus.QUEUED.value:
        raise HTTPException(status_code=409, detail=f"Cannot dispatch AgentRun in status '{run.status}'")

    # Step 1: queued → running
    update_data = AgentRunUpdate(status=AgentRunStatus.RUNNING.value)
    await update_agent_run(db, run.id, update_data, run.task_id)

    await create_event(
        db, task_id=run.task_id, event_type="agent_run_started",
        actor=actor, message=f"AgentRun #{run.id} started by {actor}",
    )

    # Step 2: Select provider based on AgentProfile.provider
    agent = await db.get(AgentProfile, run.agent_id)
    agent_provider = agent.provider if agent else ""

    # v0.3 S2: Only "openai" triggers real provider; everything else uses sandbox
    if agent_provider == "openai":
        try:
            from app.services.openai_provider import OpenAIProvider
            provider = OpenAIProvider()
            result = await provider.execute(run)
        except RuntimeError as e:
            # No API key or provider init failure → fail clearly
            run.status = AgentRunStatus.FAILED.value
            run.error_message = "AI provider initialization failed (check API key)"
            await db.flush()
            await create_event(
                db, task_id=run.task_id, event_type="agent_run_failed",
                actor=actor, message=f"AgentRun #{run.id} failed",
            )
            raise HTTPException(status_code=500, detail=f"AgentRun #{run.id} failed: Provider init error")
        except Exception as e:
            # API call failure
            run.status = AgentRunStatus.FAILED.value
            run.error_message = "AI provider execution failed"
            await db.flush()
            await create_event(
                db, task_id=run.task_id, event_type="agent_run_failed",
                actor=actor, message=f"AgentRun #{run.id} failed",
            )
            raise HTTPException(status_code=500, detail=f"AgentRun #{run.id} failed: Execution error")
    else:
        # Sandbox provider (default for all other provider types, including empty/unknown)
        try:
            provider = SandboxProvider()
            result = await provider.execute(run)
        except Exception as e:
            run.status = AgentRunStatus.FAILED.value
            run.error_message = f"Provider execution failed: {str(e)}"
            await db.flush()
            await create_event(
                db, task_id=run.task_id, event_type="agent_run_failed",
                actor=actor, message=f"AgentRun #{run.id} failed",
            )
            raise HTTPException(status_code=500, detail=f"AgentRun #{run.id} execution failed")

    # Step 3: Governance validation (BEFORE final succeeded confirmation)
    import json as _json
    from app.services.ai_output_governance_service import (
        validate_agent_run_result, parse_review_result,
        create_agent_review_from_ai_output, build_trace_json,
        redact_secrets,
    )

    _provider_raw = result.raw_result_json
    risk_report = None
    if result.raw_result_json:
        try:
            parsed = _json.loads(result.raw_result_json)
            if isinstance(parsed, dict):
                risk_report = parsed.get("risk_report")
        except (_json.JSONDecodeError, ValueError):
            pass

    validation = validate_agent_run_result(
        output_summary=result.output_summary,
        output_log=result.output_log,
        raw_result_json=result.raw_result_json,
        plan_md=result.plan_md,
        patch_diff=result.patch_diff,
        review_md=result.review_md,
        risk_report=risk_report,
    )

    trace = build_trace_json(
        provider=agent.provider if agent else "sandbox",
        model=getattr(agent, "model_name", None),
        run_type=run.run_type,
        output_kind=validation.output_kind,
        validation=validation,
    )

    # Secret redaction for provider_raw (safe: never raise)
    try:
        _safe_raw = redact_secrets(_provider_raw) if _provider_raw else None
    except Exception:
        _safe_raw = _provider_raw

    # Build combined raw_result_json: provider_raw + governance + trace
    run.raw_result_json = _json.dumps({
        "provider_raw": _safe_raw,
        "governance": {
            "valid": validation.valid,
            "requires_human": validation.requires_human,
            "risk_level": validation.risk_level,
            "errors": validation.errors,
            "warnings": validation.warnings,
        },
        "trace": _json.loads(trace) if isinstance(trace, str) else trace,
    }, ensure_ascii=False)

    # Step 4: If validation invalid → fail the AgentRun
    if not validation.valid:
        run.status = AgentRunStatus.FAILED.value
        run.error_message = "Governance validation failed"
        await db.flush()
        await create_event(
            db, task_id=run.task_id, event_type="agent_run_failed",
            actor=actor,
            message=f"AgentRun #{run.id} failed governance validation: {validation.errors[0] if validation.errors else 'unknown'}",
        )
        raise HTTPException(
            status_code=422,
            detail=f"AgentRun #{run.id} failed governance validation",
        )

    # Step 5: If requires_human → record ApprovalDecision (NOT auto-approve)
    if validation.requires_human:
        from app.models.approval_decision import ApprovalDecision
        decision = ApprovalDecision(
            task_id=run.task_id,
            risk_level=validation.risk_level or "medium",
            auto_approve_allowed=False,
            human_required=True,
            decision_reason=f"Governance: {validation.risk_level} risk, requires human review",
        )
        db.add(decision)

    # Step 6: Final succeeded
    run.status = AgentRunStatus.SUCCEEDED.value
    run.output_summary = result.output_summary
    run.output_log = result.output_log
    await db.flush()

    await create_event(
        db, task_id=run.task_id, event_type="agent_run_succeeded",
        actor=actor, message=f"AgentRun #{run.id} succeeded: {result.output_summary[:80]}",
    )

    # Step 7: Create AgentReview if review output exists
    if result.review_md:
        review_parsed = parse_review_result(result.review_md)
        if review_parsed.parsed:
            await create_agent_review_from_ai_output(
                db, run.task_id, run.agent_id, run.id,
                review_parsed, actor,
            )

    # Step 8: Create artifacts from output
    await _create_artifacts_from_result(db, run, result)

    return run


async def _create_artifacts_from_result(db: AsyncSession, run: AgentRun, result: AgentRunResult):
    """Create TaskArtifact entries from provider results."""
    artifacts = []

    if result.plan_md:
        content = result.plan_md
        sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        artifacts.append(TaskArtifact(
            task_id=run.task_id, artifact_type="agent_output_log",
            content=content, filename=f"agent_run_{run.id}_plan.md",
            size_bytes=len(content.encode("utf-8")), sha256=sha256,
        ))

    if result.patch_diff:
        content = result.patch_diff
        sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        artifacts.append(TaskArtifact(
            task_id=run.task_id, artifact_type="agent_output_diff",
            content=content, filename=f"agent_run_{run.id}_patch.diff",
            size_bytes=len(content.encode("utf-8")), sha256=sha256,
        ))

    if result.review_md:
        content = result.review_md
        sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        artifacts.append(TaskArtifact(
            task_id=run.task_id, artifact_type="agent_review_report",
            content=content, filename=f"agent_run_{run.id}_review.md",
            size_bytes=len(content.encode("utf-8")), sha256=sha256,
        ))

    if result.raw_result_json:
        content = result.raw_result_json
        sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        artifacts.append(TaskArtifact(
            task_id=run.task_id, artifact_type="agent_raw_result",
            content=content, filename=f"agent_run_{run.id}_result.json",
            size_bytes=len(content.encode("utf-8")), sha256=sha256,
        ))

    for art in artifacts:
        db.add(art)

    if artifacts:
        await db.flush()
        await create_event(
            db, task_id=run.task_id, event_type="artifact_uploaded",
            actor=f"agent_run:{run.id}",
            message=f"{len(artifacts)} artifact(s) created from AgentRun #{run.id}",
        )

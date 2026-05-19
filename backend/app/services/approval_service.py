import json
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import TaskStatus
from app.models.approval_decision import ApprovalDecision
from app.models.approval_policy import ApprovalPolicy
from app.models.task import Task
from app.models.agent_run import AgentRun
from app.models.agent_review import AgentReview
from app.schemas.approval_decision import ApprovalEvaluationRequest, ApprovalEvaluationResponse
from app.services import risk_assessment_service, event_service, task_service


async def evaluate_approval(
    db: AsyncSession, task_id: int, data: ApprovalEvaluationRequest
) -> ApprovalEvaluationResponse:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status == "archived":
        raise HTTPException(status_code=409, detail="Cannot evaluate archived task")

    # Validate agent_run_id belongs to task
    if data.agent_run_id:
        run = await db.get(AgentRun, data.agent_run_id)
        if not run or run.task_id != task_id:
            raise HTTPException(status_code=404, detail="AgentRun not found for this task")

    # Validate agent_review_id belongs to task
    if data.agent_review_id:
        rev = await db.get(AgentReview, data.agent_review_id)
        if not rev or rev.task_id != task_id:
            raise HTTPException(status_code=404, detail="AgentReview not found for this task")

    # Resolve policy
    policy = None
    if data.policy_id:
        policy = await db.get(ApprovalPolicy, data.policy_id)
        if not policy or not policy.enabled:
            raise HTTPException(status_code=404, detail="ApprovalPolicy not found or disabled")
    else:
        # Find project-level policy, fallback to global
        result = await db.execute(
            select(ApprovalPolicy).where(
                ApprovalPolicy.project_id == task.project_id,
                ApprovalPolicy.enabled == True
            ).limit(1)
        )
        policy = result.scalar_one_or_none()
        if not policy:
            result = await db.execute(
                select(ApprovalPolicy).where(
                    ApprovalPolicy.project_id.is_(None),
                    ApprovalPolicy.enabled == True
                ).limit(1)
            )
            policy = result.scalar_one_or_none()
        if not policy:
            # Create default policy
            policy = ApprovalPolicy(name="default", enabled=True)
            db.add(policy)
            await db.flush()

    # Collect inputs for risk assessment
    diff = data.diff_summary
    raw_json = None
    confidence = None
    if data.agent_run_id and run:
        diff = diff or run.output_diff
        raw_json = run.raw_result_json
    if data.agent_review_id and rev:
        confidence = rev.confidence_score
        if not data.security_issues_found and rev.issues_json:
            data.security_issues_found = True

    # Run risk assessment
    risk_result = risk_assessment_service.assess_risk(
        diff=diff,
        raw_result_json=raw_json,
        confidence_score=confidence,
        tests_passed=data.tests_passed,
        sonar_passed=data.sonar_passed,
        security_issues_found=data.security_issues_found,
        changed_files=data.changed_files,
    )

    # Evaluate against policy
    risk_level = risk_result["risk_level"]
    blocked_reasons = []
    auto_approve_allowed = False
    human_required = risk_result["human_required"]

    if policy:
        # Check max risk level
        risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        if risk_order.get(risk_level, 0) > risk_order.get(policy.max_risk_level_for_auto_approve, 0):
            blocked_reasons.append(f"Risk level {risk_level} exceeds policy max {policy.max_risk_level_for_auto_approve}")
            human_required = True

        # Check tests
        if policy.require_tests_passed and data.tests_passed is not True:
            blocked_reasons.append("Tests not passed")
            human_required = True

        # Check security
        if policy.require_no_security_issues and (data.security_issues_found is True or data.security_issues_found is None):
            blocked_reasons.append("Security issues unknown or found")
            human_required = True

        # Check sonar
        if policy.require_sonar_passed and data.sonar_passed is not True:
            blocked_reasons.append("Sonar not passed")
            human_required = True

    # Final decision
    if not blocked_reasons and risk_level in ("low",) and not human_required:
        auto_approve_allowed = True

    # Snapshot for audit
    policy_snapshot = {
        "name": policy.name if policy else "default",
        "max_risk_level": policy.max_risk_level_for_auto_approve if policy else "low",
        "require_tests_passed": policy.require_tests_passed if policy else True,
        "require_sonar_passed": policy.require_sonar_passed if policy else False,
        "require_no_security_issues": policy.require_no_security_issues if policy else True,
    }

    decision = ApprovalDecision(
        task_id=task_id,
        agent_run_id=data.agent_run_id,
        agent_review_id=data.agent_review_id,
        policy_id=policy.id if policy else None,
        risk_level=risk_level,
        auto_approve_allowed=auto_approve_allowed,
        human_required=human_required,
        decision_reason=risk_result["risk_reasons"][0] if risk_result["risk_reasons"] else None,
        blocked_reasons_json=json.dumps(blocked_reasons) if blocked_reasons else None,
        policy_snapshot_json=json.dumps(policy_snapshot),
    )
    db.add(decision)
    await db.flush()
    await db.refresh(decision)

    # Write events
    await event_service.create_event(
        db, task_id=task_id, event_type="risk_assessed",
        actor=data.actor, message=f"Risk level: {risk_level}",
    )

    if human_required:
        await event_service.create_event(
            db, task_id=task_id, event_type="auto_approval_blocked",
            actor=data.actor,
            message=f"Auto-approval blocked: {', '.join(blocked_reasons) if blocked_reasons else risk_level}",
        )
        await event_service.create_event(
            db, task_id=task_id, event_type="human_approval_required",
            actor=data.actor,
            message=f"Human approval required due to: {', '.join(risk_result['risk_reasons'])}",
        )
    else:
        await event_service.create_event(
            db, task_id=task_id, event_type="auto_approval_granted",
            actor=data.actor, message="Auto-approval granted",
        )

    return ApprovalEvaluationResponse(
        id=decision.id,
        task_id=task_id,
        risk_level=risk_level,
        risk_reasons=risk_result["risk_reasons"],
        auto_approve_allowed=auto_approve_allowed,
        human_required=human_required,
        decision_reason=policy_snapshot["name"],
        blocked_reasons=blocked_reasons,
        tests_passed=data.tests_passed,
        security_issues_found=data.security_issues_found,
    )


async def auto_approve(
    db: AsyncSession, task_id: int, approval_decision_id: int, actor: str | None = None, message: str | None = None
) -> Task:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status == "archived":
        raise HTTPException(status_code=409, detail="Cannot auto-approve archived task")
    if task.status not in ("reviewing", "human_required"):
        raise HTTPException(status_code=409, detail=f"Cannot auto-approve task in status {task.status}")

    decision = await db.get(ApprovalDecision, approval_decision_id)
    if not decision or decision.task_id != task_id:
        raise HTTPException(status_code=404, detail="ApprovalDecision not found for this task")
    if not decision.auto_approve_allowed:
        raise HTTPException(status_code=409, detail="Auto-approve not allowed based on policy")
    if decision.human_required:
        raise HTTPException(status_code=409, detail="Human required, cannot auto-approve")
    if decision.risk_level not in ("low",):
        raise HTTPException(status_code=409, detail=f"Risk level {decision.risk_level} too high for auto-approve")

    # Perform the state transition
    body = type("Body", (), {"actor": actor, "message": message or "Auto-approved"})()
    task_obj = await task_service.approve_task(db, task_id, body)

    await event_service.create_event(
        db, task_id=task_id, event_type="auto_approval_granted",
        actor=actor, message=f"Auto-approved based on decision #{approval_decision_id}",
    )
    return task_obj

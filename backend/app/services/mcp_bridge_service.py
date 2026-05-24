import json
import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun
from app.models.project import Project
from app.models.task import Task
from app.models.task_artifact import TaskArtifact
from app.models.task_event import TaskEvent
from app.schemas.ai_handoff import AiHandoffPreviewRequest
from app.schemas.answer_synthesis import AnswerSynthesisPreviewRequest
from app.schemas.browser_ai import BrowserAiRequest
from app.schemas.mcp_bridge import McpCallRequest, McpCallResponse, McpToolDescriptor
from app.services import ai_dispatch_service, ai_handoff_service, answer_synthesis_service, browser_ai_service
from app.services.ai_output_governance_service import redact_secrets
from app.services.sandbox_approval_gate_service import evaluate_sandbox_gate


DEFAULT_BUDGET = 4000
MAX_BUDGET = 12000
ARTIFACT_SUMMARY_CHARS = 900
RUN_SUMMARY_CHARS = 700
DANGEROUS_TOOL_MARKERS = ("execute", "shell", "create_pr", "merge", "deploy", "approve", "ci", "sonar")
READ_ONLY_SAFETY_NOTES = [
    "MCP Bridge S18 is read-only + dry-run only.",
    "No OpenAI execute is allowed.",
    "No Browser AI execute or browser launch is allowed.",
    "No AgentRun, TaskArtifact, or TaskEvent is created by MCP Bridge.",
    "Project.root_path, secret_ref, .env, API keys, cookies, sessions, and passwords are not returned.",
]
ASSIGNMENT_SECRET_RE = re.compile(r"\b(cookie|session|password|token|api_key)\s*=\s*\S+", re.IGNORECASE)


TOOLS: list[McpToolDescriptor] = [
    McpToolDescriptor(name="get_workspace_status", description="Read project/task/run/artifact counts."),
    McpToolDescriptor(name="get_project_summary", description="Read a redacted project summary."),
    McpToolDescriptor(name="list_tasks", description="List task summaries for a project."),
    McpToolDescriptor(name="get_task_brief", description="Read a budget-limited task brief."),
    McpToolDescriptor(name="get_handoff_packet", description="Preview a budget-limited AI handoff packet."),
    McpToolDescriptor(name="get_answer_synthesis", description="Preview rule-based answer synthesis."),
    McpToolDescriptor(name="list_agent_runs", description="List redacted AgentRun summaries."),
    McpToolDescriptor(name="list_task_artifacts", description="List budget-limited TaskArtifact summaries."),
    McpToolDescriptor(name="get_sandbox_status", description="Read sandbox gate status."),
    McpToolDescriptor(name="ai_dispatch_dry_run", description="Preview AI dispatch without provider execution.", dry_run_only=True),
    McpToolDescriptor(name="browser_ai_dry_run", description="Preview Browser AI without opening a browser.", dry_run_only=True),
]
TOOL_NAMES = {tool.name for tool in TOOLS}


def list_tools() -> list[McpToolDescriptor]:
    return TOOLS


async def call_tool(db: AsyncSession, body: McpCallRequest) -> McpCallResponse:
    tool = (body.tool or "").strip()
    if tool not in TOOL_NAMES:
        status = "blocked" if _looks_dangerous_tool(tool) else "failed"
        return _response(tool=tool, status=status, error_message=f"Unsupported MCP tool '{tool}'")
    before = await _counts(db)
    try:
        data = await _dispatch_tool(db, tool, body.arguments or {})
    except HTTPException as exc:
        return _response(tool=tool, status="failed", error_message=str(exc.detail))
    except Exception as exc:
        return _response(tool=tool, status="failed", error_message=_redact(str(exc)))
    after = await _counts(db)
    if after != before:
        return _response(tool=tool, status="blocked", error_message="MCP Bridge blocked unexpected persistence")
    return _response(tool=tool, status="succeeded", data=_redact_jsonable(data))


async def _dispatch_tool(db: AsyncSession, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    if tool == "get_workspace_status":
        return await _workspace_status(db)
    if tool == "get_project_summary":
        return await _project_summary(db, _int_arg(args, "project_id"))
    if tool == "list_tasks":
        return await _list_tasks(db, _int_arg(args, "project_id"))
    if tool == "get_task_brief":
        return await _task_brief(db, _int_arg(args, "task_id"), _budget(args))
    if tool == "get_handoff_packet":
        return await _handoff_packet(db, args)
    if tool == "get_answer_synthesis":
        return await _answer_synthesis(db, _int_arg(args, "task_id"), _budget(args))
    if tool == "list_agent_runs":
        return await _agent_runs(db, _int_arg(args, "task_id"), _budget(args))
    if tool == "list_task_artifacts":
        return await _task_artifacts(db, _int_arg(args, "task_id"), _budget(args))
    if tool == "get_sandbox_status":
        return await _sandbox_status(db, _int_arg(args, "task_id"))
    if tool == "ai_dispatch_dry_run":
        return _ai_dispatch_dry_run(args)
    if tool == "browser_ai_dry_run":
        return await _browser_ai_dry_run(db, args)
    raise ValueError(f"Unhandled tool {tool}")


async def _workspace_status(db: AsyncSession) -> dict[str, Any]:
    return {
        "project_count": await _count(db, Project),
        "task_count": await _count(db, Task),
        "agent_run_count": await _count(db, AgentRun),
        "artifact_count": await _count(db, TaskArtifact),
    }


async def _project_summary(db: AsyncSession, project_id: int) -> dict[str, Any]:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project_not_found")
    task_count = await _count_where(db, Task, Task.project_id == project.id)
    return {
        "project_id": project.id,
        "name": project.name,
        "display_name": project.display_name,
        "repo_url": project.repo_url,
        "default_branch": project.default_branch,
        "current_branch": project.current_branch,
        "is_active": project.is_active,
        "task_count": task_count,
        "root_path": "[not returned by MCP Bridge]",
    }


async def _list_tasks(db: AsyncSession, project_id: int) -> dict[str, Any]:
    stmt = select(Task).where(Task.project_id == project_id).order_by(Task.id.desc()).limit(50)
    tasks = list((await db.execute(stmt)).scalars().all())
    return {
        "project_id": project_id,
        "tasks": [_task_summary(task) for task in tasks],
        "is_truncated": len(tasks) >= 50,
    }


async def _task_brief(db: AsyncSession, task_id: int, budget: int) -> dict[str, Any]:
    task = await _get_task(db, task_id)
    data = {
        "task": _task_summary(task),
        "description": task.description or "",
        "result_summary": task.result_summary or "",
        "ticket_content": task.ticket_content or "",
    }
    return _budgeted(data, budget)


async def _handoff_packet(db: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    task = await _get_task(db, _int_arg(args, "task_id"))
    budget = _budget(args)
    packet = await ai_handoff_service.preview(
        db,
        AiHandoffPreviewRequest(
            project_id=task.project_id,
            task_id=task.id,
            include_recent_batches=True,
            include_answer_synthesis=True,
            include_safety_rules=True,
            max_chars=max(1000, min(budget, 30000)),
        ),
    )
    return _budgeted(packet.model_dump(), budget)


async def _answer_synthesis(db: AsyncSession, task_id: int, budget: int) -> dict[str, Any]:
    try:
        preview = await answer_synthesis_service.preview(
            db,
            AnswerSynthesisPreviewRequest(task_id=task_id, include_artifacts=True, max_artifact_chars=min(budget, 2000)),
        )
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        return {"task_id": task_id, "synthesis_status": "empty", "message": "No dispatch or Browser AI artifacts found"}
    return _budgeted(preview.model_dump(), budget)


async def _agent_runs(db: AsyncSession, task_id: int, budget: int) -> dict[str, Any]:
    stmt = select(AgentRun).where(AgentRun.task_id == task_id).order_by(AgentRun.id.desc()).limit(30)
    runs = list((await db.execute(stmt)).scalars().all())
    data = {
        "task_id": task_id,
        "runs": [
            {
                "id": run.id,
                "project_id": run.project_id,
                "agent_id": run.agent_id,
                "run_type": run.run_type,
                "status": run.status,
                "risk_level": run.risk_level,
                "output_summary": _short(run.output_summary, RUN_SUMMARY_CHARS),
                "error_message": _short(run.error_message, 240),
                "input_prompt": "[redacted by MCP Bridge]",
            }
            for run in runs
        ],
        "is_truncated": len(runs) >= 30,
    }
    return _budgeted(data, budget)


async def _task_artifacts(db: AsyncSession, task_id: int, budget: int) -> dict[str, Any]:
    stmt = select(TaskArtifact).where(TaskArtifact.task_id == task_id).order_by(TaskArtifact.id.desc()).limit(30)
    artifacts = list((await db.execute(stmt)).scalars().all())
    data = {
        "task_id": task_id,
        "artifacts": [
            {
                "id": artifact.id,
                "artifact_type": artifact.artifact_type,
                "filename": artifact.filename,
                "size_bytes": artifact.size_bytes,
                "sha256": artifact.sha256,
                "summary": _short(artifact.content, ARTIFACT_SUMMARY_CHARS),
                "is_content_truncated": bool(artifact.content and len(artifact.content) > ARTIFACT_SUMMARY_CHARS),
            }
            for artifact in artifacts
        ],
        "is_truncated": len(artifacts) >= 30,
    }
    return _budgeted(data, budget)


async def _sandbox_status(db: AsyncSession, task_id: int) -> dict[str, Any]:
    decision = await evaluate_sandbox_gate(db, task_id)
    return decision.model_dump()


def _ai_dispatch_dry_run(args: dict[str, Any]) -> dict[str, Any]:
    result = ai_dispatch_service.dry_run(
        task_goal=str(args.get("task_goal") or ""),
        module_name=str(args.get("module_name") or ""),
        task_type=str(args.get("task_type") or ""),
        mode=str(args.get("mode") or "review"),
    )
    return result.model_dump()


async def _browser_ai_dry_run(db: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    request = BrowserAiRequest(**{
        "project_id": _int_arg(args, "project_id"),
        "task_id": _int_arg(args, "task_id"),
        "provider": str(args.get("provider") or "custom"),
        "target_url": str(args.get("target_url") or ""),
        "prompt_source": str(args.get("prompt_source") or "task_goal"),
        "custom_prompt": str(args.get("custom_prompt") or ""),
        "input_selector": str(args.get("input_selector") or ""),
        "send_selector": str(args.get("send_selector") or ""),
        "response_selector": str(args.get("response_selector") or ""),
        "scroll_container_selector": str(args.get("scroll_container_selector") or ""),
        "copy_button_selector": str(args.get("copy_button_selector") or ""),
        "login_hint_selector": str(args.get("login_hint_selector") or ""),
        "timeout_seconds": args.get("timeout_seconds"),
    })
    result = await browser_ai_service.dry_run(db, request)
    return result.model_dump()


def _response(tool: str, status: str, data: dict[str, Any] | None = None, error_message: str = "") -> McpCallResponse:
    return McpCallResponse(
        tool=tool,
        status=status,
        data=data or {},
        error_message=_redact(error_message),
        read_only=True,
        persisted=False,
        safety_notes=READ_ONLY_SAFETY_NOTES,
    )


def _task_summary(task: Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "project_id": task.project_id,
        "title": task.title,
        "description": _short(task.description, 600),
        "status": task.status,
        "priority": task.priority,
        "source": task.source,
        "planner": task.planner,
        "executor": task.executor,
        "reviewer": task.reviewer,
        "target_branch": task.target_branch,
        "result_summary": _short(task.result_summary, 600),
    }


async def _get_task(db: AsyncSession, task_id: int) -> Task:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    return task


async def _count(db: AsyncSession, model) -> int:
    result = await db.execute(select(func.count()).select_from(model))
    return int(result.scalar_one())


async def _count_where(db: AsyncSession, model, condition) -> int:
    result = await db.execute(select(func.count()).select_from(model).where(condition))
    return int(result.scalar_one())


async def _counts(db: AsyncSession) -> tuple[int, int, int]:
    return (
        await _count(db, AgentRun),
        await _count(db, TaskArtifact),
        await _count(db, TaskEvent),
    )


def _budget(args: dict[str, Any]) -> int:
    raw = args.get("budget", DEFAULT_BUDGET)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_BUDGET
    return max(500, min(value, MAX_BUDGET))


def _int_arg(args: dict[str, Any], name: str) -> int:
    try:
        value = int(args.get(name))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{name}_required") from exc
    if value <= 0:
        raise HTTPException(status_code=400, detail=f"{name}_required")
    return value


def _budgeted(data: dict[str, Any], budget: int) -> dict[str, Any]:
    redacted = _redact_jsonable(data)
    text = json.dumps(redacted, ensure_ascii=False, default=str)
    if len(text) <= budget:
        redacted["is_truncated"] = bool(redacted.get("is_truncated", False))
        return redacted
    return {
        "summary": _redact(text[: max(0, budget - 200)]),
        "is_truncated": True,
        "truncated_reason": f"response exceeded budget={budget}",
    }


def _redact_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _redact_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_jsonable(item) for item in value]
    if isinstance(value, str):
        return _redact(value)
    return value


def _redact(text: str | None) -> str:
    if not text:
        return ""
    return ASSIGNMENT_SECRET_RE.sub(lambda match: f"{match.group(1)}=***REDACTED***", redact_secrets(text))


def _short(text: str | None, limit: int) -> str:
    clean = " ".join(_redact(text).split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def _looks_dangerous_tool(tool: str) -> bool:
    lowered = tool.lower()
    return any(marker in lowered for marker in DANGEROUS_TOOL_MARKERS)

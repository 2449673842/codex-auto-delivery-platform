import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.schemas.project_memory import (
    ProjectMemoryFilters,
    ProjectMemoryItem,
    ProjectMemoryRedactionStatus,
    ProjectMemoryResponse,
    ProjectMemorySourceRef,
    ProjectMemorySummaryResponse,
)
from app.services.ai_output_governance_service import redact_secrets


MEMORY_MAX_CHARS = 4000
UPDATED_AT = "2026-05-27T00:00:00Z"
AGENTS_DOC = "AGENTS.md"
PROJECT_MEMORY_DOC = "docs/design/project-memory.md"
PROJECT_MEMORY_SKILL_STRATEGY_DOC = "docs/strategy/project-memory-vs-agent-skill.md"
ROADMAP_DOC = "docs/roadmap/next-after-s18.md"
SAFETY_NOTES = [
    "Project Memory API is read-only.",
    "Seeded memory is curated from project metadata and documented policy; it does not scan the repository.",
    "No memory write API, provider call, Browser AI execution, shell, subprocess, GitHub, Sonar, PR, CI, Deploy, approve, or merge is performed.",
    "No .env, secret_ref, Project.root_path, or secret value is read or returned.",
]


@dataclass(frozen=True)
class _ProjectMemoryContext:
    project_id: int
    name: str
    display_name: str | None
    repo_url: str | None
    default_branch: str | None
    current_branch: str | None
    frontend_path: str | None
    backend_path: str | None
    package_manager: str | None
    dev_command: str | None
    build_command: str | None
    test_command: str | None


async def get_project_memory(db: AsyncSession, project_id: int) -> ProjectMemoryResponse:
    project = await _get_project_context(db, project_id)
    items = [_memory_item(project, seed) for seed in _seed_records(project)]
    return ProjectMemoryResponse(
        project_id=project.project_id,
        items=items,
        filters=_filters(items),
        read_only=True,
        persisted=False,
        safety_notes=_redact_list(SAFETY_NOTES).value,
    )


async def get_project_memory_summary(db: AsyncSession, project_id: int) -> ProjectMemorySummaryResponse:
    memory = await get_project_memory(db, project_id)
    stale_count = sum(1 for item in memory.items if item.stale)
    high_confidence_count = sum(1 for item in memory.items if item.confidence == "high")
    memory_types = _unique(item.memory_type for item in memory.items)
    summary = _redact_text(
        "Project Memory exposes curated read-only project context for "
        f"{_project_label_from_items(memory.items)}. It covers {len(memory.items)} memory records: "
        f"{', '.join(memory_types)}. It is not an automatic memory generator or executor."
    )
    return ProjectMemorySummaryResponse(
        project_id=memory.project_id,
        summary=summary.value,
        memory_count=len(memory.items),
        memory_types=memory_types,
        stale_count=stale_count,
        high_confidence_count=high_confidence_count,
        read_only=True,
        persisted=False,
        safety_notes=memory.safety_notes,
    )


async def _get_project_context(db: AsyncSession, project_id: int) -> _ProjectMemoryContext:
    result = await db.execute(
        select(
            Project.id,
            Project.name,
            Project.display_name,
            Project.repo_url,
            Project.default_branch,
            Project.current_branch,
            Project.frontend_path,
            Project.backend_path,
            Project.package_manager,
            Project.dev_command,
            Project.build_command,
            Project.test_command,
        ).where(Project.id == project_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="project_not_found")
    return _ProjectMemoryContext(
        project_id=row.id,
        name=row.name,
        display_name=row.display_name,
        repo_url=row.repo_url,
        default_branch=row.default_branch,
        current_branch=row.current_branch,
        frontend_path=row.frontend_path,
        backend_path=row.backend_path,
        package_manager=row.package_manager,
        dev_command=row.dev_command,
        build_command=row.build_command,
        test_command=row.test_command,
    )


def _seed_records(project: _ProjectMemoryContext) -> list[dict[str, Any]]:
    project_label = project.display_name or project.name
    repo = project.repo_url or "codex-auto-delivery-platform"
    return [
        _seed(
            "default-project-profile",
            "project_profile",
            "Project profile",
            (
                f"{project_label} is treated as an AI coding evidence / memory workbench with "
                "FastAPI backend and Vue/Vite frontend."
            ),
            {
                "project_name": project.name,
                "display_name": project.display_name or "",
                "platform_positioning": "AI coding evidence / memory workbench",
                "technology_stack": ["FastAPI backend", "Vue frontend", "Vite frontend build"],
                "repo": repo,
                "default_branch": project.default_branch or "",
                "current_branch": project.current_branch or "",
                "main_directories": ["backend/app", "backend/tests", "frontend/src", "frontend/tests", "docs"],
            },
            PROJECT_MEMORY_DOC,
            ROADMAP_DOC,
        ),
        _seed(
            "default-runbook",
            "runbook",
            "Runbook",
            "Conservative runbook with command placeholders and environment variable names only.",
            {
                "backend_start_command": project.dev_command or "Start backend with the project-approved FastAPI command.",
                "frontend_start_command": "npm.cmd run dev from frontend when UI work needs local preview.",
                "backend_path": project.backend_path or "backend",
                "frontend_path": project.frontend_path or "frontend",
                "package_manager": project.package_manager or "npm",
                "build_command": project.build_command or "npm.cmd run build",
                "test_command": project.test_command or "python -m pytest backend/tests/ -v --rootdir backend",
                "common_ports": ["backend API port from settings", "frontend Vite dev port", "Browser AI mock port when configured"],
                "environment_variable_names_only": ["OPENAI_API_KEY"],
                "local_service_dependencies": ["sub2api when explicitly configured", "Browser AI mock for mock smoke tests"],
                "secret_values_saved": False,
            },
            AGENTS_DOC,
            PROJECT_MEMORY_DOC,
        ),
        _seed(
            "default-verification-policy",
            "verification_policy",
            "Verification policy",
            (
                "Backend changes require targeted pytest, related pytest, full pytest, and compileall; "
                "frontend changes require npm build and frontend display smoke."
            ),
            {
                "backend": [
                    "targeted backend pytest for changed behavior",
                    "S-stage related backend pytest",
                    "python -m pytest backend/tests/ -v --rootdir backend",
                    "python -m compileall backend/app",
                ],
                "frontend": ["npm.cmd run build", "node tests/s4-display.cjs"],
                "browser_ai": ["Browser AI mock smoke when Browser AI / Multi-AI paths are touched"],
                "sonarcloud": [
                    "Quality Gate must be Passed",
                    "Security Hotspots must be 0",
                    "Duplication on New Code should remain within project gate",
                    "New Issues must be 0",
                ],
                "docs_only": "backend pytest, compileall, npm build, and frontend tests may be skipped when only docs changed.",
            },
            AGENTS_DOC,
            PROJECT_MEMORY_DOC,
        ),
        _seed(
            "default-delivery-policy",
            "delivery_policy",
            "Delivery policy",
            "Each stage uses its own PR, Chinese PR body, real verification evidence, and mastermind review before merge.",
            {
                "stage_delivery": "one independent PR per stage",
                "master_policy": "do not directly push master",
                "pr_body_language": "Chinese",
                "pr_body_must_match": ["head commit", "base commit", "changed files", "tests", "SonarCloud"],
                "merge_policy": "merge only after mastermind review",
                "post_merge": "report latest master commit after merge",
            },
            AGENTS_DOC,
            ROADMAP_DOC,
        ),
        _seed(
            "default-safety-policy",
            "safety_policy",
            "Safety policy",
            "Do not read secrets, modify real repositories, create platform PR / CI / Sonar / Deploy capability, or auto approve / merge / deploy.",
            {
                "do_not_read": [".env", "secret_ref"],
                "do_not_expose": ["API keys", "cookies", "sessions", "passwords", "token values"],
                "project_root_path": "do not access Project.root_path for real modification",
                "repository_writes": "do not write real repositories unless a future stage explicitly allows it",
                "platform_capabilities": "do not create PR / CI / Sonar / Deploy platform capability unless explicitly planned",
                "automation_boundary": "do not auto approve, merge, or deploy",
            },
            AGENTS_DOC,
            PROJECT_MEMORY_DOC,
        ),
        _seed(
            "default-known-failures",
            "known_failure",
            "Known failures",
            "Recurring project failures include Sonar false positives, placeholder file damage, Browser AI selector issues, timeouts, missing keys, proxy issues, duplication, and accessibility findings.",
            {
                "failures": [
                    "Sonar hardcoded secret false positive in tests or fixtures",
                    "placeholder / worktree pointer file damage",
                    "Browser AI selector failure",
                    "stable response timeout",
                    "missing OPENAI_API_KEY",
                    "GitHub TLS / proxy failure",
                    "Sonar duplication issue",
                    "accessibility issue",
                ],
                "mitigation_policy": "inspect real diff and risk files; preserve redaction tests with runtime-composed secret-like fixtures.",
            },
            PROJECT_MEMORY_DOC,
            PROJECT_MEMORY_SKILL_STRATEGY_DOC,
        ),
        _seed(
            "default-user-preferences",
            "user_preference",
            "User preferences",
            "Prefer Chinese PR bodies, mastermind-reviewed merges, conservative staged delivery, and platform scope as evidence layer / memory layer.",
            {
                "pr_body": "Chinese",
                "merge": "after mastermind review",
                "delivery_style": "conservative staged delivery",
                "platform_positioning": "evidence layer / memory layer",
                "rejected_positioning": "weak Codex replacement",
                "reporting": "report concrete validation evidence and latest head or master commit",
            },
            PROJECT_MEMORY_DOC,
            PROJECT_MEMORY_SKILL_STRATEGY_DOC,
        ),
        _seed(
            "default-handoff-templates",
            "handoff_template",
            "Handoff templates",
            "Reusable handoff families cover Codex development, OMX controlled workers, PR review, repair handoff, and Browser AI provider runs.",
            {
                "templates": [
                    "Codex development task template",
                    "OMX controlled worker template",
                    "PR review template",
                    "Repair handoff template",
                    "Browser AI provider run template",
                ],
                "required_sections": ["inputs", "scope", "safety boundaries", "verification", "expected output"],
                "execution_authority": "handoff templates prepare context only; they do not execute repair or write code.",
            },
            PROJECT_MEMORY_DOC,
            PROJECT_MEMORY_SKILL_STRATEGY_DOC,
        ),
    ]


def _seed(
    memory_id: str,
    memory_type: str,
    title: str,
    summary: str,
    content: dict[str, Any],
    *source_paths: str,
) -> dict[str, Any]:
    return {
        "memory_id": memory_id,
        "memory_type": memory_type,
        "title": title,
        "summary": summary,
        "content": content,
        "source_refs": _docs_refs(*source_paths),
    }


def _memory_item(project: _ProjectMemoryContext, seed: dict[str, Any]) -> ProjectMemoryItem:
    summary = _redact_text(seed["summary"])
    content = _redact_value(seed["content"])
    safety_notes = _redact_list(SAFETY_NOTES)
    truncated = summary.status.truncated or content.status.truncated or safety_notes.status.truncated
    return ProjectMemoryItem(
        memory_id=seed["memory_id"],
        project_id=project.project_id,
        memory_type=seed["memory_type"],
        title=_redact_text(seed["title"]).value,
        summary=summary.value,
        content=content.value,
        source_refs=[ProjectMemorySourceRef(**source_ref) for source_ref in seed["source_refs"]],
        confidence="high",
        stale=False,
        updated_at=UPDATED_AT,
        redaction_status=ProjectMemoryRedactionStatus(
            redaction_applied=True,
            truncated=truncated,
            max_chars=MEMORY_MAX_CHARS,
        ),
    )


def _filters(items: list[ProjectMemoryItem]) -> ProjectMemoryFilters:
    return ProjectMemoryFilters(
        memory_type=_unique(item.memory_type for item in items),
        confidence=_unique(item.confidence for item in items),
        stale=sorted({item.stale for item in items}),
    )


def _docs_refs(*paths: str) -> list[dict[str, str]]:
    return [{"source_type": "docs", "path": path} for path in paths]


@dataclass(frozen=True)
class _Redacted:
    value: Any
    status: ProjectMemoryRedactionStatus


def _redact_value(value: Any) -> _Redacted:
    raw = json.dumps(value, ensure_ascii=False, default=str)
    redacted = _redact_text(raw)
    try:
        parsed = json.loads(redacted.value)
    except json.JSONDecodeError:
        parsed = {"text": redacted.value}
    return _Redacted(parsed, redacted.status)


def _redact_list(values: list[str]) -> _Redacted:
    redacted_values: list[str] = []
    truncated = False
    for value in values:
        redacted = _redact_text(value)
        redacted_values.append(redacted.value)
        truncated = truncated or redacted.status.truncated
    return _Redacted(
        redacted_values,
        ProjectMemoryRedactionStatus(redaction_applied=True, truncated=truncated, max_chars=MEMORY_MAX_CHARS),
    )


def _redact_text(value: Any) -> _Redacted:
    text = _redact(str(value or ""))
    truncated = len(text) > MEMORY_MAX_CHARS
    if truncated:
        text = text[:MEMORY_MAX_CHARS].rstrip() + "\n...[truncated]"
    return _Redacted(
        text,
        ProjectMemoryRedactionStatus(redaction_applied=True, truncated=truncated, max_chars=MEMORY_MAX_CHARS),
    )


def _redact(value: str) -> str:
    redacted = redact_secrets(value or "")
    redacted = re.sub(r"\bcookie\s*=\s*\S+", "cookie=***REDACTED***", redacted, flags=re.IGNORECASE)
    redacted = re.sub(r"\bsession\s*=\s*\S+", "session=***REDACTED***", redacted, flags=re.IGNORECASE)
    redacted = re.sub(r"\bsecret_ref\s*=\s*\S+", "secret_ref=***REDACTED***", redacted, flags=re.IGNORECASE)
    return redacted


def _project_label_from_items(items: list[ProjectMemoryItem]) -> str:
    profile = next((item for item in items if item.memory_type == "project_profile"), None)
    if not profile:
        return "the project"
    return str(profile.content.get("display_name") or profile.content.get("project_name") or "the project")


def _unique(values: Iterable[Any]) -> list[Any]:
    result: list[Any] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result

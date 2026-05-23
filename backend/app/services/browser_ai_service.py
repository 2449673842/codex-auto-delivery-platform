import hashlib
import json
from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.enums import AgentRunStatus
from app.models.agent_profile import AgentProfile
from app.models.agent_run import AgentRun
from app.models.task import Task
from app.models.task_artifact import TaskArtifact
from app.schemas.browser_ai import BrowserAiRequest, BrowserAiResponse, BrowserAiSafetyGate
from app.services.ai_output_governance_service import redact_secrets
from app.services.event_service import create_event


SUPPORTED_PROVIDERS = {"custom"}
PROMPT_SOURCES = {"task_goal", "handoff_packet", "answer_synthesis", "custom_prompt"}
MAX_TIMEOUT_SECONDS = 600
ANSWER_PREVIEW_CHARS = 1200
STABLE_TEXT_POLLS = 3
STABLE_TEXT_INTERVAL_MS = 500
SENSITIVE_ASSIGNMENT_KEYS = {"cookie", "session", "password", "token", "api_key"}


class BrowserAiDriver(Protocol):
    async def run(self, request: BrowserAiRequest, prompt: str, timeout_seconds: int) -> str:
        ...


_driver_override: BrowserAiDriver | None = None


def set_driver_override(driver: BrowserAiDriver | None) -> None:
    global _driver_override
    _driver_override = driver


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _redact(text: str | None) -> str:
    if not text:
        return ""
    return _redact_sensitive_assignments(redact_secrets(text))


def _redact_sensitive_assignments(text: str) -> str:
    parts = []
    for part in text.split():
        key, sep, _value = part.partition("=")
        if sep and key.lower() in SENSITIVE_ASSIGNMENT_KEYS:
            parts.append(f"{key}=***REDACTED***")
        else:
            parts.append(part)
    return " ".join(parts)


def _is_safe_target_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _target_url_hint(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return "invalid_target_url"
    return f"{parsed.scheme}://{parsed.netloc}"


def _timeout_seconds(request: BrowserAiRequest) -> int:
    raw = request.timeout_seconds or settings.browser_ai_default_timeout_seconds
    return max(1, min(raw, MAX_TIMEOUT_SECONDS))


def _safety_gate(request: BrowserAiRequest, *, for_execute: bool) -> BrowserAiSafetyGate:
    provider = (request.provider or "").strip()
    prompt_source = (request.prompt_source or "").strip()
    provider_allowlist = settings.browser_ai_provider_allowlist
    selectors_present = all([
        bool((request.input_selector or "").strip()),
        bool((request.send_selector or "").strip()),
        bool((request.response_selector or "").strip()),
    ])
    timeout = request.timeout_seconds or settings.browser_ai_default_timeout_seconds
    gate = BrowserAiSafetyGate(
        browser_ai_enabled=settings.browser_ai_enabled,
        provider_allowed=provider in provider_allowlist,
        provider_valid=provider in SUPPORTED_PROVIDERS,
        prompt_source_valid=prompt_source in PROMPT_SOURCES,
        selectors_present=selectors_present,
        target_url_present=_is_safe_target_url(request.target_url or ""),
        timeout_ok=1 <= timeout <= MAX_TIMEOUT_SECONDS,
    )
    if for_execute and not gate.browser_ai_enabled:
        gate.blocked_reasons.append("BROWSER_AI_ENABLED is not true")
    if not gate.provider_valid:
        gate.blocked_reasons.append(f"Unsupported browser AI provider '{provider}'")
    if not gate.provider_allowed:
        gate.blocked_reasons.append(f"Provider '{provider}' is not in BROWSER_AI_PROVIDER_ALLOWLIST")
    if not gate.prompt_source_valid:
        gate.blocked_reasons.append(f"Invalid prompt_source '{prompt_source}'")
    if not gate.target_url_present:
        gate.blocked_reasons.append("target_url must be http(s)")
    if not gate.selectors_present:
        gate.blocked_reasons.append("input_selector, send_selector, and response_selector are required")
    if not gate.timeout_ok:
        gate.blocked_reasons.append(f"timeout_seconds must be between 1 and {MAX_TIMEOUT_SECONDS}")
    gate.gate_passed = len(gate.blocked_reasons) == 0
    if not for_execute and "BROWSER_AI_ENABLED is not true" in gate.blocked_reasons:
        gate.blocked_reasons.remove("BROWSER_AI_ENABLED is not true")
        gate.gate_passed = len(gate.blocked_reasons) == 0
    return gate


async def _get_task(db: AsyncSession, task_id: int, project_id: int) -> Task | None:
    task = await db.get(Task, task_id)
    if not task or task.project_id != project_id:
        return None
    return task


async def _build_prompt(db: AsyncSession, request: BrowserAiRequest) -> str:
    task = await _get_task(db, request.task_id, request.project_id)
    if request.prompt_source == "custom_prompt":
        return request.custom_prompt.strip()
    if request.prompt_source == "answer_synthesis":
        return _task_prompt(task, "Answer synthesis is not available in this MVP. Use the current task context.")
    if request.prompt_source == "handoff_packet":
        return _task_prompt(task, "Prepare a concise answer for the next AI handoff context.")
    return _task_prompt(task, "")


def _task_prompt(task: Task | None, instruction: str) -> str:
    if task is None:
        base = "Task not found."
    else:
        parts = [
            f"Task: {task.title}",
            f"Description: {task.description or '(none)'}",
            f"Status: {task.status}",
        ]
        base = "\n".join(parts)
    return f"{instruction}\n\n{base}".strip()


async def dry_run(db: AsyncSession, request: BrowserAiRequest) -> BrowserAiResponse:
    prompt = await _build_prompt(db, request)
    gate = _safety_gate(request, for_execute=False)
    return BrowserAiResponse(
        status="ready" if gate.gate_passed else "blocked",
        provider=request.provider,
        prompt_hash=_hash_text(prompt),
        safety_gate=gate,
        browser_opened=False,
        persisted=False,
        error_message="; ".join(gate.blocked_reasons) if gate.blocked_reasons else None,
    )


async def execute(db: AsyncSession, request: BrowserAiRequest) -> BrowserAiResponse:
    prompt = await _build_prompt(db, request)
    prompt_hash = _hash_text(prompt)
    gate = _safety_gate(request, for_execute=True)
    if not gate.gate_passed:
        return BrowserAiResponse(
            status="blocked",
            provider=request.provider,
            prompt_hash=prompt_hash,
            safety_gate=gate,
            browser_opened=False,
            persisted=False,
            error_message="; ".join(gate.blocked_reasons),
        )

    task = await _get_task(db, request.task_id, request.project_id)
    if task is None:
        gate.blocked_reasons.append("Task not found for project")
        gate.gate_passed = False
        return BrowserAiResponse(
            status="blocked",
            provider=request.provider,
            prompt_hash=prompt_hash,
            safety_gate=gate,
            error_message="Task not found for project",
        )

    agent = await _find_or_create_browser_agent(db, request.provider)
    run = await _create_run(db, task, agent, prompt, request, prompt_hash)
    try:
        answer = await _get_driver().run(request, prompt, _timeout_seconds(request))
        answer = _redact(answer).strip()
        if not answer:
            raise RuntimeError("empty response from browser AI")
    except Exception as exc:
        message = _redact(str(exc)) or "browser AI execution failed"
        run.status = AgentRunStatus.FAILED.value
        run.error_message = message
        run.finished_at = datetime.now(timezone.utc)
        await db.flush()
        await create_event(
            db,
            task_id=task.id,
            event_type="agent_run_failed",
            actor=f"browser_ai:{request.provider}",
            message=f"Browser AI AgentRun #{run.id} failed: {message}",
        )
        return BrowserAiResponse(
            status="failed",
            provider=request.provider,
            prompt_hash=prompt_hash,
            answer_preview="",
            agent_run_id=run.id,
            artifact_id=None,
            error_message=message,
            safety_gate=gate,
            browser_opened=True,
            persisted=False,
        )

    artifact = _answer_artifact(task.id, run.id, answer, request.provider)
    db.add(artifact)
    run.status = AgentRunStatus.SUCCEEDED.value
    run.output_summary = answer[:ANSWER_PREVIEW_CHARS]
    run.output_log = "Browser AI visible response captured from response_selector."
    run.raw_result_json = _redact(json.dumps({
        "provider": request.provider,
        "target_url_hint": _target_url_hint(request.target_url),
        "prompt_source": request.prompt_source,
        "prompt_hash": prompt_hash,
        "artifact_type": "browser_ai_answer",
        "safety": "local_browser_only_no_auth_persistence",
    }, ensure_ascii=False))
    run.finished_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(artifact)
    await create_event(
        db,
        task_id=task.id,
        event_type="artifact_uploaded",
        actor=f"browser_ai:{request.provider}",
        message=f"Browser AI answer captured in artifact #{artifact.id}",
    )
    await create_event(
        db,
        task_id=task.id,
        event_type="agent_run_succeeded",
        actor=f"browser_ai:{request.provider}",
        message=f"Browser AI AgentRun #{run.id} succeeded",
    )
    return BrowserAiResponse(
        status="succeeded",
        provider=request.provider,
        prompt_hash=prompt_hash,
        answer_preview=answer[:ANSWER_PREVIEW_CHARS],
        agent_run_id=run.id,
        artifact_id=artifact.id,
        safety_gate=gate,
        browser_opened=True,
        persisted=True,
    )


async def _find_or_create_browser_agent(db: AsyncSession, provider: str) -> AgentProfile:
    result = await db.execute(
        select(AgentProfile).where(
            AgentProfile.provider == "browser_ai",
            AgentProfile.agent_type == "reviewer",
            AgentProfile.name == f"browser-ai-{provider}",
        )
    )
    agent = result.scalar_one_or_none()
    if agent:
        return agent
    agent = AgentProfile(
        name=f"browser-ai-{provider}",
        agent_type="reviewer",
        provider="browser_ai",
        model_name=provider,
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return agent


async def _create_run(
    db: AsyncSession,
    task: Task,
    agent: AgentProfile,
    prompt: str,
    request: BrowserAiRequest,
    prompt_hash: str,
) -> AgentRun:
    run = AgentRun(
        task_id=task.id,
        project_id=task.project_id,
        agent_id=agent.id,
        run_type="review",
        status=AgentRunStatus.RUNNING.value,
        input_prompt=f"Browser AI prompt redacted; prompt_hash={prompt_hash}; prompt_source={request.prompt_source}",
        started_at=datetime.now(timezone.utc),
        raw_result_json=_redact(json.dumps({
            "provider": request.provider,
            "prompt_source": request.prompt_source,
            "prompt_hash": prompt_hash,
            "browser_opened": True,
        }, ensure_ascii=False)),
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)
    await create_event(
        db,
        task_id=task.id,
        event_type="agent_run_created",
        actor=f"browser_ai:{request.provider}",
        message=f"Browser AI AgentRun #{run.id} created",
    )
    return run


def _answer_artifact(task_id: int, run_id: int, answer: str, provider: str) -> TaskArtifact:
    data = answer.encode("utf-8")
    return TaskArtifact(
        task_id=task_id,
        artifact_type="browser_ai_answer",
        content=answer,
        filename=f"browser_ai_run_{run_id}_answer.md",
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        metadata_json=json.dumps({
            "provider": provider,
            "source": "visible_response_selector",
            "no_auth_persisted": True,
        }, ensure_ascii=False),
    )


def _get_driver() -> BrowserAiDriver:
    return _driver_override or PlaywrightBrowserAiDriver()


class PlaywrightBrowserAiDriver:
    async def run(self, request: BrowserAiRequest, prompt: str, timeout_seconds: int) -> str:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError("Python playwright package is not installed") from exc

        timeout_ms = timeout_seconds * 1000
        async with async_playwright() as p:
            launch_kwargs = {"headless": settings.browser_ai_headless}
            browser = None
            context = None
            try:
                if settings.browser_ai_user_data_dir:
                    context = await p.chromium.launch_persistent_context(
                        settings.browser_ai_user_data_dir,
                        **launch_kwargs,
                    )
                else:
                    browser = await p.chromium.launch(**launch_kwargs)
                    context = await browser.new_context()
                page = await context.new_page()
                await page.goto(request.target_url, wait_until="domcontentloaded", timeout=timeout_ms)
                input_box = page.locator(request.input_selector).first
                await input_box.fill(prompt, timeout=timeout_ms)
                previous_answer = ""
                response_box = page.locator(request.response_selector).first
                if await response_box.count() > 0:
                    previous_answer = (await response_box.inner_text(timeout=1000)).strip()
                await page.locator(request.send_selector).first.click(timeout=timeout_ms)
                await page.wait_for_selector(request.response_selector, timeout=timeout_ms)
                await page.wait_for_function(
                    """([selector, previous]) => {
                        const node = document.querySelector(selector);
                        return node && node.innerText.trim() && node.innerText.trim() !== previous;
                    }""",
                    arg=[request.response_selector, previous_answer],
                    timeout=timeout_ms,
                )
                if request.scroll_container_selector:
                    await page.locator(request.scroll_container_selector).first.evaluate(
                        "node => { node.scrollTop = node.scrollHeight; }",
                        timeout=timeout_ms,
                    )
                answer = await _read_answer_text(page, request, timeout_ms)
                return answer.strip()
            finally:
                if context is not None:
                    await context.close()
                if browser is not None:
                    await browser.close()


async def _read_answer_text(page, request: BrowserAiRequest, timeout_ms: int) -> str:
    response_box = page.locator(request.response_selector).first
    answer = (await response_box.inner_text(timeout=timeout_ms)).strip()
    for _ in range(STABLE_TEXT_POLLS):
        await page.wait_for_timeout(STABLE_TEXT_INTERVAL_MS)
        latest = (await response_box.inner_text(timeout=timeout_ms)).strip()
        if latest == answer:
            break
        answer = latest
    if not request.copy_button_selector:
        return answer
    try:
        await page.locator(request.copy_button_selector).first.click(timeout=timeout_ms)
        copied = (await page.evaluate("navigator.clipboard.readText()")).strip()
        return copied or answer
    except Exception:
        return answer

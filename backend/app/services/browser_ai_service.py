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
from app.schemas.browser_ai import (
    BrowserAiProviderProfile,
    BrowserAiRequest,
    BrowserAiResponse,
    BrowserAiSafetyGate,
    BrowserAiStep,
)
from app.services.ai_output_governance_service import redact_secrets
from app.services.event_service import create_event


BEST_EFFORT_SELECTOR_NOTE = "Built-in selectors are best-effort and may break when the website changes. Switch to custom if needed."
COPY_BUTTON_SELECTOR = "button[aria-label*='Copy']"
PROFILE_DEFINITIONS: dict[str, dict[str, object]] = {
    "custom": {
        "display_name": "Custom",
        "target_url": "",
        "input_selector": "",
        "send_selector": "",
        "response_selector": "",
        "scroll_container_selector": "",
        "copy_button_selector": "",
        "login_required_hint": False,
        "editable": True,
    },
    "chatgpt_web": {
        "display_name": "ChatGPT Web",
        "target_url": "https://chatgpt.com/",
        "input_selector": "textarea[data-testid='prompt-textarea'], div[contenteditable='true']",
        "send_selector": "button[data-testid='send-button']",
        "response_selector": "[data-message-author-role='assistant']",
        "scroll_container_selector": "main",
        "copy_button_selector": COPY_BUTTON_SELECTOR,
        "login_required_hint": True,
        "editable": True,
    },
    "claude_web": {
        "display_name": "Claude Web",
        "target_url": "https://claude.ai/new",
        "input_selector": "div[contenteditable='true'], textarea",
        "send_selector": "button[aria-label*='Send']",
        "response_selector": "[data-testid='message-content'], .font-claude-message",
        "scroll_container_selector": "main",
        "copy_button_selector": COPY_BUTTON_SELECTOR,
        "login_required_hint": True,
        "editable": True,
    },
    "gemini_web": {
        "display_name": "Gemini Web",
        "target_url": "https://gemini.google.com/app",
        "input_selector": "rich-textarea div[contenteditable='true'], textarea",
        "send_selector": "button[aria-label*='Send']",
        "response_selector": "message-content, .model-response-text",
        "scroll_container_selector": "main",
        "copy_button_selector": COPY_BUTTON_SELECTOR,
        "login_required_hint": True,
        "editable": True,
    },
    "deepseek_web": {
        "display_name": "DeepSeek Web",
        "target_url": "https://chat.deepseek.com/",
        "input_selector": "textarea, div[contenteditable='true']",
        "send_selector": "button[aria-label*='Send'], button[type='submit']",
        "response_selector": ".ds-markdown, [class*='markdown']",
        "scroll_container_selector": "main",
        "copy_button_selector": COPY_BUTTON_SELECTOR,
        "login_required_hint": True,
        "editable": True,
    },
    "kimi_web": {
        "display_name": "Kimi Web",
        "target_url": "https://www.kimi.com/chat/",
        "input_selector": "textarea, div[contenteditable='true']",
        "send_selector": "button[aria-label*='Send'], button[type='submit']",
        "response_selector": ".markdown, [class*='markdown']",
        "scroll_container_selector": "main",
        "copy_button_selector": COPY_BUTTON_SELECTOR,
        "login_required_hint": True,
        "editable": True,
    },
}
SUPPORTED_PROVIDERS = set(PROFILE_DEFINITIONS)
PROMPT_SOURCES = {"task_goal", "handoff_packet", "answer_synthesis", "custom_prompt"}
MAX_TIMEOUT_SECONDS = 600
ANSWER_PREVIEW_CHARS = 1200
SENSITIVE_ASSIGNMENT_KEYS = {"cookie", "session", "password", "token", "api_key"}
TASK_NOT_FOUND_FOR_PROJECT = "Task not found for project"
STEP_ORDER = [
    "validate_request",
    "build_prompt",
    "create_agent_run",
    "open_browser",
    "navigate",
    "fill_prompt",
    "click_send",
    "wait_response",
    "capture_answer",
    "persist_artifact",
    "finish_run",
]
DRY_RUN_STEPS = ["validate_request", "build_prompt"]


class BrowserAiStepError(RuntimeError):
    def __init__(self, step: str, message: str):
        super().__init__(message)
        self.step = step


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


def _safe_step_message(message: str | None, fallback: str) -> str:
    redacted = _redact(message)
    return redacted[:240] if redacted else fallback


def _new_steps(names: list[str]) -> list[BrowserAiStep]:
    return [BrowserAiStep(name=name, status="pending") for name in names]


def _mark_step(steps: list[BrowserAiStep], name: str, status: str, message: str) -> None:
    for step in steps:
        if step.name == name:
            step.status = status
            step.message = _safe_step_message(message, status)
            step.sensitive = False
            break


def _skip_after_failed(steps: list[BrowserAiStep], failed_name: str) -> None:
    found_failed = False
    for step in steps:
        if found_failed and step.status == "pending":
            step.status = "skipped"
            step.message = "Skipped after previous failure"
        if step.name == failed_name:
            found_failed = True


def _pass_before_failed(steps: list[BrowserAiStep], failed_name: str) -> None:
    for step in steps:
        if step.name == failed_name:
            break
        if step.status in {"pending", "running"}:
            step.status = "passed"
            step.message = f"{step.name} completed"


def _finish_pending_steps(steps: list[BrowserAiStep], status: str = "skipped") -> None:
    for step in steps:
        if step.status == "pending":
            step.status = status
            step.message = status.capitalize()


def _step_error_step(exc: Exception) -> str:
    if isinstance(exc, BrowserAiStepError) and exc.step in STEP_ORDER:
        return exc.step
    return "capture_answer"


def _is_safe_target_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _target_url_hint(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return "invalid_target_url"
    return f"{parsed.scheme}://{parsed.netloc}"


def list_provider_profiles() -> list[BrowserAiProviderProfile]:
    return [_profile_response(provider, data) for provider, data in PROFILE_DEFINITIONS.items()]


def _profile_response(provider: str, data: dict[str, object]) -> BrowserAiProviderProfile:
    target_url = str(data.get("target_url") or "")
    selectors_configured = all([
        bool(str(data.get("input_selector") or "")),
        bool(str(data.get("send_selector") or "")),
        bool(str(data.get("response_selector") or "")),
    ])
    return BrowserAiProviderProfile(
        provider=provider,
        display_name=str(data.get("display_name") or provider),
        target_url=target_url,
        target_url_hint=target_url,
        input_selector=str(data.get("input_selector") or ""),
        send_selector=str(data.get("send_selector") or ""),
        response_selector=str(data.get("response_selector") or ""),
        scroll_container_selector=str(data.get("scroll_container_selector") or ""),
        copy_button_selector=str(data.get("copy_button_selector") or ""),
        selectors_configured=selectors_configured,
        login_required_hint=bool(data.get("login_required_hint")),
        editable=bool(data.get("editable", True)),
        best_effort_note="" if provider == "custom" else BEST_EFFORT_SELECTOR_NOTE,
    )


def _profile_defaults(provider: str) -> dict[str, str]:
    raw = PROFILE_DEFINITIONS.get(provider) or {}
    return {
        "target_url": str(raw.get("target_url") or ""),
        "input_selector": str(raw.get("input_selector") or ""),
        "send_selector": str(raw.get("send_selector") or ""),
        "response_selector": str(raw.get("response_selector") or ""),
        "scroll_container_selector": str(raw.get("scroll_container_selector") or ""),
        "copy_button_selector": str(raw.get("copy_button_selector") or ""),
    }


def _with_profile_defaults(request: BrowserAiRequest) -> BrowserAiRequest:
    provider = (request.provider or "").strip()
    defaults = _profile_defaults(provider)
    if not defaults:
        return request
    updates = {
        field: (getattr(request, field) or defaults[field])
        for field in defaults
    }
    return request.model_copy(update=updates)


def _timeout_seconds(request: BrowserAiRequest) -> int:
    raw = request.timeout_seconds or settings.browser_ai_default_timeout_seconds
    return max(1, min(raw, MAX_TIMEOUT_SECONDS))


def _response_timeout_seconds(request: BrowserAiRequest) -> int:
    raw = request.timeout_seconds or settings.browser_ai_response_timeout_seconds
    return max(1, min(raw, MAX_TIMEOUT_SECONDS))


def _stable_poll_count() -> int:
    return max(1, min(settings.browser_ai_stable_polls, 50))


def _stable_interval_ms() -> int:
    return max(100, min(settings.browser_ai_stable_interval_ms, 10_000))


def _safety_gate(request: BrowserAiRequest, *, for_execute: bool) -> BrowserAiSafetyGate:
    request = _with_profile_defaults(request)
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
    request = _with_profile_defaults(request)
    steps = _new_steps(DRY_RUN_STEPS)
    prompt = await _build_prompt(db, request)
    _mark_step(steps, "build_prompt", "passed", "Prompt built")
    gate = _safety_gate(request, for_execute=False)
    if gate.gate_passed:
        _mark_step(steps, "validate_request", "passed", "Request validated")
    else:
        _mark_step(steps, "validate_request", "failed", "; ".join(gate.blocked_reasons))
    return BrowserAiResponse(
        status="ready" if gate.gate_passed else "blocked",
        provider=request.provider,
        prompt_hash=_hash_text(prompt),
        safety_gate=gate,
        browser_opened=False,
        persisted=False,
        error_message="; ".join(gate.blocked_reasons) if gate.blocked_reasons else None,
        steps=steps,
    )


async def execute(db: AsyncSession, request: BrowserAiRequest) -> BrowserAiResponse:
    request = _with_profile_defaults(request)
    steps = _new_steps(STEP_ORDER)
    prompt = await _build_prompt(db, request)
    _mark_step(steps, "build_prompt", "passed", "Prompt built")
    prompt_hash = _hash_text(prompt)
    gate = _safety_gate(request, for_execute=True)
    if not gate.gate_passed:
        _mark_step(steps, "validate_request", "failed", "; ".join(gate.blocked_reasons))
        _finish_pending_steps(steps)
        return BrowserAiResponse(
            status="blocked",
            provider=request.provider,
            prompt_hash=prompt_hash,
            safety_gate=gate,
            browser_opened=False,
            persisted=False,
            error_message="; ".join(gate.blocked_reasons),
            steps=steps,
        )
    _mark_step(steps, "validate_request", "passed", "Request validated")

    task = await _get_task(db, request.task_id, request.project_id)
    if task is None:
        gate.blocked_reasons.append(TASK_NOT_FOUND_FOR_PROJECT)
        gate.gate_passed = False
        _mark_step(steps, "build_prompt", "failed", TASK_NOT_FOUND_FOR_PROJECT)
        _finish_pending_steps(steps)
        return BrowserAiResponse(
            status="blocked",
            provider=request.provider,
            prompt_hash=prompt_hash,
            safety_gate=gate,
            error_message=TASK_NOT_FOUND_FOR_PROJECT,
            steps=steps,
        )

    agent = await _find_or_create_browser_agent(db, request.provider)
    run = await _create_run(db, task, agent, prompt, request, prompt_hash)
    _mark_step(steps, "create_agent_run", "passed", f"AgentRun #{run.id} created")
    try:
        _mark_step(steps, "open_browser", "running", "Opening local browser")
        answer = await _get_driver().run(request, prompt, _timeout_seconds(request))
        for name in [
            "open_browser",
            "navigate",
            "fill_prompt",
            "click_send",
            "wait_response",
            "capture_answer",
        ]:
            if next(step for step in steps if step.name == name).status in {"pending", "running"}:
                _mark_step(steps, name, "passed", f"{name} completed")
        answer = _redact(answer).strip()
        if not answer:
            raise BrowserAiStepError("capture_answer", "empty response from browser AI")
    except Exception as exc:
        message = _redact(str(exc)) or "browser AI execution failed"
        failed_step = _step_error_step(exc)
        _pass_before_failed(steps, failed_step)
        _mark_step(steps, failed_step, "failed", message)
        _skip_after_failed(steps, failed_step)
        _finish_pending_steps(steps)
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
            steps=steps,
        )

    artifact = _answer_artifact(task.id, run.id, answer, request.provider)
    try:
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
    except Exception as exc:
        message = _safe_step_message(str(exc), "artifact persistence failed")
        run.status = AgentRunStatus.FAILED.value
        run.error_message = message
        run.finished_at = datetime.now(timezone.utc)
        _mark_step(steps, "persist_artifact", "failed", message)
        _skip_after_failed(steps, "persist_artifact")
        _finish_pending_steps(steps)
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
            steps=steps,
        )
    _mark_step(steps, "persist_artifact", "passed", f"Artifact #{artifact.id} persisted")
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
    _mark_step(steps, "finish_run", "passed", "Browser AI run finished")
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
        steps=steps,
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
            raise BrowserAiStepError("open_browser", "Python playwright package is not installed") from exc

        timeout_ms = timeout_seconds * 1000
        response_timeout_ms = _response_timeout_seconds(request) * 1000
        async with async_playwright() as p:
            launch_kwargs = {"headless": settings.browser_ai_headless}
            browser = None
            context = None
            try:
                try:
                    if settings.browser_ai_user_data_dir:
                        context = await p.chromium.launch_persistent_context(
                            settings.browser_ai_user_data_dir,
                            **launch_kwargs,
                        )
                    else:
                        browser = await p.chromium.launch(**launch_kwargs)
                        context = await browser.new_context()
                except Exception as exc:
                    raise BrowserAiStepError("open_browser", "browser launch failed") from exc
                page = await context.new_page()
                try:
                    await page.goto(request.target_url, wait_until="domcontentloaded", timeout=timeout_ms)
                except Exception as exc:
                    raise BrowserAiStepError("navigate", "navigation timeout or target page failed to load") from exc
                try:
                    input_box = page.locator(request.input_selector).first
                    await input_box.fill(prompt, timeout=timeout_ms)
                except Exception as exc:
                    raise BrowserAiStepError("fill_prompt", "input selector not found or not fillable") from exc
                previous_answer = ""
                response_box = page.locator(request.response_selector).first
                if await response_box.count() > 0:
                    previous_answer = (await response_box.inner_text(timeout=1000)).strip()
                try:
                    await page.locator(request.send_selector).first.click(timeout=timeout_ms)
                except Exception as exc:
                    raise BrowserAiStepError("click_send", "send selector not found or not clickable") from exc
                try:
                    await _wait_for_stable_answer(page, request, previous_answer, response_timeout_ms)
                except Exception as exc:
                    raise BrowserAiStepError(
                        "wait_response",
                        "timeout waiting for stable response; page may still be generating, login may be required, or selector may be wrong",
                    ) from exc
                if request.scroll_container_selector:
                    await page.locator(request.scroll_container_selector).first.evaluate(
                        "node => { node.scrollTop = node.scrollHeight; }",
                        timeout=timeout_ms,
                    )
                try:
                    answer = await _read_answer_text(page, request, timeout_ms)
                except Exception as exc:
                    raise BrowserAiStepError("capture_answer", "failed to capture visible response") from exc
                return answer.strip()
            finally:
                if context is not None:
                    await context.close()
                if browser is not None:
                    await browser.close()


async def _read_answer_text(page, request: BrowserAiRequest, timeout_ms: int) -> str:
    response_box = page.locator(request.response_selector).first
    answer = (await response_box.inner_text(timeout=timeout_ms)).strip()
    if not request.copy_button_selector:
        return answer
    try:
        await page.locator(request.copy_button_selector).first.click(timeout=timeout_ms)
        copied = (await page.evaluate("navigator.clipboard.readText()")).strip()
        return _prefer_related_clipboard_answer(answer, copied)
    except Exception:
        return answer


def _prefer_related_clipboard_answer(answer: str, copied: str) -> str:
    if copied and answer and (answer in copied or copied in answer):
        return copied
    return answer


async def _wait_for_stable_answer(page, request: BrowserAiRequest, previous_answer: str, timeout_ms: int) -> str:
    await page.wait_for_selector(request.response_selector, timeout=timeout_ms)
    response_box = page.locator(request.response_selector).first
    await _wait_for_answer_change(response_box, page, previous_answer, timeout_ms)
    return await _wait_until_answer_stable(response_box, page, timeout_ms)


async def _wait_for_answer_change(response_box, page, previous_answer: str, timeout_ms: int) -> str:
    deadline = await _deadline_ms(page, timeout_ms)
    while True:
        current = (await response_box.inner_text(timeout=timeout_ms)).strip()
        if current and current != previous_answer:
            return current
        if await _timed_out(page, deadline):
            raise TimeoutError("timeout waiting for answer text to start changing")
        await page.wait_for_timeout(_stable_interval_ms())


async def _wait_until_answer_stable(response_box, page, timeout_ms: int) -> str:
    deadline = await _deadline_ms(page, timeout_ms)
    last_text = (await response_box.inner_text(timeout=timeout_ms)).strip()
    stable_count = 0
    while True:
        await page.wait_for_timeout(_stable_interval_ms())
        current = (await response_box.inner_text(timeout=timeout_ms)).strip()
        if current and current == last_text:
            stable_count += 1
            if stable_count >= _stable_poll_count():
                return current
        else:
            stable_count = 0
            last_text = current
        if await _timed_out(page, deadline):
            raise TimeoutError("timeout waiting for stable response")


async def _deadline_ms(page, timeout_ms: int) -> float:
    now = await page.evaluate("Date.now()")
    return float(now) + timeout_ms


async def _timed_out(page, deadline_ms: float) -> bool:
    now = await page.evaluate("Date.now()")
    return float(now) >= deadline_ms

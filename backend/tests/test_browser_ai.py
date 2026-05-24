import asyncio
import dataclasses
import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.database import Base, get_engine, get_session_factory
from app.main import app
from app.models.agent_run import AgentRun
from app.models.task_artifact import TaskArtifact
from app.models.task_event import TaskEvent


BASE = "/api/browser-ai"


class FakeDriver:
    def __init__(self, answer: str = "Mock visible browser answer"):
        self.answer = answer
        self.calls = []

    async def run(self, request, prompt: str, timeout_seconds: int) -> str:
        self.calls.append((request, prompt, timeout_seconds))
        return self.answer


class FailingDriver:
    async def run(self, request, prompt: str, timeout_seconds: int) -> str:
        raise RuntimeError("selector not found")


class StepFailingDriver:
    def __init__(self, step: str, message: str):
        self.step = step
        self.message = message

    async def run(self, request, prompt: str, timeout_seconds: int) -> str:
        from app.services.browser_ai_service import BrowserAiStepError
        raise BrowserAiStepError(self.step, self.message)


class ClipboardDriver:
    def __init__(self, answer: str, copied: str):
        self.answer = answer
        self.copied = copied

    async def run(self, request, prompt: str, timeout_seconds: int) -> str:
        from app.services.browser_ai_service import _prefer_related_clipboard_answer
        await asyncio.sleep(0)
        return _prefer_related_clipboard_answer(self.answer, self.copied)


class FakeResponseLocator:
    @property
    def first(self):
        return self

    def __init__(self, page):
        self.page = page

    async def inner_text(self, timeout: int):
        await asyncio.sleep(0)
        return self.page.next_text()


class FakeStablePage:
    def __init__(self, texts: list[str], interval_ms: int = 100):
        self.texts = texts
        self.interval_ms = interval_ms
        self.index = 0
        self.now_ms = 0

    def locator(self, selector: str):
        return FakeResponseLocator(self)

    async def wait_for_selector(self, selector: str, timeout: int):
        await asyncio.sleep(0)

    async def wait_for_timeout(self, interval_ms: int):
        self.now_ms += self.interval_ms
        await asyncio.sleep(0)

    async def evaluate(self, expression: str):
        await asyncio.sleep(0)
        if expression == "Date.now()":
            return self.now_ms
        return ""

    def next_text(self) -> str:
        if self.index >= len(self.texts):
            return self.texts[-1] if self.texts else ""
        text = self.texts[self.index]
        self.index += 1
        return text


class StableCaptureDriver:
    def __init__(self, texts: list[str], timeout_ms: int = 5000):
        self.texts = texts
        self.timeout_ms = timeout_ms

    async def run(self, request, prompt: str, timeout_seconds: int) -> str:
        from app.services import browser_ai_service
        page = FakeStablePage(self.texts)
        await browser_ai_service._wait_for_stable_answer(page, request, "", self.timeout_ms)
        return await browser_ai_service._read_answer_text(page, request, self.timeout_ms)


class StableTimeoutDriver:
    def __init__(self, texts: list[str], timeout_ms: int = 250):
        self.texts = texts
        self.timeout_ms = timeout_ms

    async def run(self, request, prompt: str, timeout_seconds: int) -> str:
        from app.services import browser_ai_service
        from app.services.browser_ai_service import BrowserAiStepError
        page = FakeStablePage(self.texts)
        try:
            await browser_ai_service._wait_for_stable_answer(page, request, "", self.timeout_ms)
        except Exception as exc:
            raise BrowserAiStepError("wait_response", str(exc)) from exc
        return await browser_ai_service._read_answer_text(page, request, self.timeout_ms)


@pytest.fixture(autouse=True)
async def _reset_db():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def _reset_driver():
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(None)
    yield
    browser_ai_service.set_driver_override(None)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test.local") as ac:
        yield ac


@pytest.fixture
async def task(client):
    project = (await client.post("/api/projects", json={"name": "browser-ai-test", "root_path": "/unused"})).json()["data"]
    task = (await client.post("/api/tasks", json={
        "project_id": project["id"],
        "title": "Browser AI test task",
        "description": "Send this to a browser AI",
    })).json()["data"]
    return task


@pytest.fixture
def valid_body(task):
    return {
        "project_id": task["project_id"],
        "task_id": task["id"],
        "provider": "custom",
        "target_url": "http://127.0.0.1:9999/mock-browser-ai",
        "prompt_source": "task_goal",
        "custom_prompt": "",
        "input_selector": "textarea[name='prompt']",
        "send_selector": "button[data-send]",
        "response_selector": "[data-answer]",
        "timeout_seconds": 30,
    }


def _install_settings(monkeypatch, **overrides):
    import app.services.browser_ai_service as service
    current = service.settings
    updated = dataclasses.replace(current, **overrides)
    monkeypatch.setattr(service, "settings", updated)
    return updated


async def _counts():
    async with get_engine().connect() as conn:
        runs = (await conn.execute(select(AgentRun))).scalars().all()
        artifacts = (await conn.execute(select(TaskArtifact))).scalars().all()
        events = (await conn.execute(select(TaskEvent))).scalars().all()
    return len(runs), len(artifacts), len(events)


async def _stored_browser_ai_payload() -> str:
    session_factory = get_session_factory()
    async with session_factory() as session:
        artifacts = (await session.execute(select(TaskArtifact))).scalars().all()
        runs = (await session.execute(select(AgentRun))).scalars().all()
        events = (await session.execute(select(TaskEvent))).scalars().all()
    return json.dumps({
        "run_input_prompt": [r.input_prompt for r in runs],
        "run_raw": [r.raw_result_json for r in runs],
        "artifact_content": [a.content for a in artifacts],
        "artifact_metadata": [a.metadata_json for a in artifacts],
        "event_messages": [e.message for e in events],
    })


def _assert_absent_from_response_and_storage(resp, stored: str, values: list[str]) -> None:
    body = json.dumps(resp.json())
    for value in values:
        assert value not in body
        assert value not in stored


def _step(data: dict, name: str) -> dict:
    return next(step for step in data["steps"] if step["name"] == name)


def _assert_step(data: dict, name: str, status: str) -> None:
    assert _step(data, name)["status"] == status


@pytest.mark.asyncio
async def test_dry_run_default_disabled_does_not_open_browser_or_write(client, valid_body):
    before = await _counts()
    resp = await client.post(f"{BASE}/dry-run", json=valid_body)
    after = await _counts()

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["prompt_hash"]
    assert data["browser_opened"] is False
    assert data["persisted"] is False
    assert data["safety_gate"]["browser_ai_enabled"] is False
    _assert_step(data, "validate_request", "passed")
    _assert_step(data, "build_prompt", "passed")
    assert before == after


@pytest.mark.asyncio
async def test_dry_run_enabled_ready_without_opening_browser_or_writing(client, valid_body, monkeypatch):
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")
    before = await _counts()

    resp = await client.post(f"{BASE}/dry-run", json=valid_body)

    data = resp.json()["data"]
    assert data["status"] == "ready"
    assert data["prompt_hash"]
    assert data["browser_opened"] is False
    assert data["persisted"] is False
    assert data["safety_gate"]["gate_passed"] is True
    _assert_step(data, "validate_request", "passed")
    _assert_step(data, "build_prompt", "passed")
    assert before == await _counts()


@pytest.mark.asyncio
async def test_execute_default_disabled_blocked(client, valid_body):
    resp = await client.post(f"{BASE}/execute", json=valid_body)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "blocked"
    assert data["browser_opened"] is False
    assert "BROWSER_AI_ENABLED" in data["error_message"]
    _assert_step(data, "validate_request", "failed")


@pytest.mark.asyncio
async def test_provider_not_allowlisted_blocked(client, valid_body, monkeypatch):
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="chatgpt_web")

    resp = await client.post(f"{BASE}/execute", json=valid_body)

    data = resp.json()["data"]
    assert data["status"] == "blocked"
    assert "not in BROWSER_AI_PROVIDER_ALLOWLIST" in data["error_message"]
    _assert_step(data, "validate_request", "failed")


@pytest.mark.asyncio
async def test_missing_selector_failed_without_opening_browser(client, valid_body, monkeypatch):
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")
    valid_body["input_selector"] = ""

    resp = await client.post(f"{BASE}/execute", json=valid_body)

    data = resp.json()["data"]
    assert data["status"] == "blocked"
    assert data["browser_opened"] is False
    assert "selector" in data["error_message"]
    _assert_step(data, "validate_request", "failed")


@pytest.mark.asyncio
async def test_invalid_prompt_source_blocked_without_opening_browser_or_writing(client, valid_body, monkeypatch):
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")
    valid_body["prompt_source"] = "bad_source"
    before = await _counts()

    dry = await client.post(f"{BASE}/dry-run", json=valid_body)
    execute = await client.post(f"{BASE}/execute", json=valid_body)

    for resp in (dry, execute):
        data = resp.json()["data"]
        assert data["status"] == "blocked"
        assert data["browser_opened"] is False
        assert data["persisted"] is False
        assert data["safety_gate"]["prompt_source_valid"] is False
        assert "Invalid prompt_source" in data["error_message"]
        _assert_step(data, "validate_request", "failed")
    assert before == await _counts()


@pytest.mark.asyncio
async def test_fake_browser_driver_success_creates_agent_run_and_artifact(client, valid_body, monkeypatch):
    from app.services import browser_ai_service
    driver = FakeDriver("Visible answer from mock page")
    browser_ai_service.set_driver_override(driver)
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")

    resp = await client.post(f"{BASE}/execute", json=valid_body)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "succeeded"
    assert data["browser_opened"] is True
    assert data["persisted"] is True
    assert data["agent_run_id"] > 0
    assert data["artifact_id"] > 0
    assert "Visible answer" in data["answer_preview"]
    for step_name in [
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
    ]:
        _assert_step(data, step_name, "passed")
    assert len(driver.calls) == 1
    runs, artifacts, events = await _counts()
    assert runs == 1
    assert artifacts == 1
    assert events >= 3


@pytest.mark.asyncio
async def test_failing_driver_returns_clear_error(client, valid_body, monkeypatch):
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(FailingDriver())
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")

    resp = await client.post(f"{BASE}/execute", json=valid_body)

    data = resp.json()["data"]
    assert data["status"] == "failed"
    assert data["browser_opened"] is True
    assert data["persisted"] is False
    assert "selector not found" in data["error_message"]
    _assert_step(data, "capture_answer", "failed")


@pytest.mark.asyncio
async def test_step_driver_fill_prompt_failure_marks_failed_step(client, valid_body, monkeypatch):
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(StepFailingDriver("fill_prompt", "input selector not found"))
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")

    resp = await client.post(f"{BASE}/execute", json=valid_body)

    data = resp.json()["data"]
    assert data["status"] == "failed"
    _assert_step(data, "fill_prompt", "failed")
    _assert_step(data, "click_send", "skipped")
    assert "input selector not found" in _step(data, "fill_prompt")["message"]


@pytest.mark.asyncio
async def test_step_driver_wait_response_timeout_marks_failed_step(client, valid_body, monkeypatch):
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(StepFailingDriver(
        "wait_response",
        "timeout waiting for stable response; page may still be generating, login may be required, or selector may be wrong",
    ))
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")

    resp = await client.post(f"{BASE}/execute", json=valid_body)

    data = resp.json()["data"]
    assert data["status"] == "failed"
    _assert_step(data, "wait_response", "failed")
    _assert_step(data, "capture_answer", "skipped")
    assert "login may be required" in _step(data, "wait_response")["message"]


@pytest.mark.asyncio
async def test_stable_response_waits_for_final_answer_before_saving(client, valid_body, monkeypatch):
    from app.services import browser_ai_service
    partial_answer = "half answer"
    final_answer = "full answer after stable browser generation"
    browser_ai_service.set_driver_override(StableCaptureDriver([
        partial_answer,
        final_answer,
        final_answer,
        final_answer,
        final_answer,
        final_answer,
        final_answer,
    ]))
    _install_settings(
        monkeypatch,
        browser_ai_enabled=True,
        _browser_ai_provider_allowlist_raw="custom",
        browser_ai_stable_polls=3,
        browser_ai_stable_interval_ms=100,
    )

    resp = await client.post(f"{BASE}/execute", json=valid_body)

    data = resp.json()["data"]
    assert data["status"] == "succeeded"
    assert data["answer_preview"] == final_answer
    _assert_step(data, "wait_response", "passed")
    _assert_step(data, "capture_answer", "passed")
    session_factory = get_session_factory()
    async with session_factory() as session:
        artifact = (await session.execute(select(TaskArtifact))).scalars().one()
    assert artifact.content == final_answer
    assert artifact.content != partial_answer


@pytest.mark.asyncio
async def test_changing_response_until_timeout_marks_wait_response_failed(client, valid_body, monkeypatch):
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(StableTimeoutDriver([
        "token 1",
        "token 2",
        "token 3",
        "token 4",
        "token 5",
        "token 6",
    ]))
    _install_settings(
        monkeypatch,
        browser_ai_enabled=True,
        _browser_ai_provider_allowlist_raw="custom",
        browser_ai_stable_polls=3,
        browser_ai_stable_interval_ms=100,
    )

    resp = await client.post(f"{BASE}/execute", json=valid_body)

    data = resp.json()["data"]
    assert data["status"] == "failed"
    assert data["persisted"] is False
    assert "stable response" in data["error_message"]
    _assert_step(data, "wait_response", "failed")
    _assert_step(data, "capture_answer", "skipped")
    runs, artifacts, _events = await _counts()
    assert runs == 1
    assert artifacts == 0


@pytest.mark.asyncio
async def test_empty_response_marks_capture_answer_failed(client, valid_body, monkeypatch):
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(FakeDriver("   "))
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")

    resp = await client.post(f"{BASE}/execute", json=valid_body)

    data = resp.json()["data"]
    assert data["status"] == "failed"
    assert data["persisted"] is False
    assert "empty response" in data["error_message"]
    _assert_step(data, "wait_response", "passed")
    _assert_step(data, "capture_answer", "failed")
    runs, artifacts, _events = await _counts()
    assert runs == 1
    assert artifacts == 0


@pytest.mark.asyncio
async def test_step_messages_are_redacted(client, valid_body, monkeypatch):
    from app.services import browser_ai_service
    forbidden = ["step-secret", "step-cookie", "step-session", "sk-123456789012345678901234567890"]
    sensitive_key = "pass" + "word"
    raw_message = " ".join([
        f"{sensitive_key}=step-secret",
        "cookie=step-cookie",
        "session=step-session",
        "sk-123456789012345678901234567890",
    ])
    browser_ai_service.set_driver_override(StepFailingDriver("wait_response", raw_message))
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")

    resp = await client.post(f"{BASE}/execute", json=valid_body)

    body = json.dumps(resp.json()["data"]["steps"])
    for value in forbidden:
        assert value not in body


@pytest.mark.asyncio
async def test_does_not_save_cookie_password_session_or_secret(client, valid_body, monkeypatch):
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(FakeDriver("answer with sk-123456789012345678901234567890"))
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")

    resp = await client.post(f"{BASE}/execute", json=valid_body)

    body = json.dumps(resp.json())
    assert "sk-123456789012345678901234567890" not in body
    session_factory = get_session_factory()
    async with session_factory() as session:
        artifacts = (await session.execute(select(TaskArtifact))).scalars().all()
        runs = (await session.execute(select(AgentRun))).scalars().all()
    stored = json.dumps([a.content + (a.metadata_json or "") for a in artifacts]) + json.dumps([r.raw_result_json for r in runs])
    for forbidden in ["cookie", "password", "session", "secret_ref", ".env", "sk-123456789012345678901234567890"]:
        assert forbidden not in stored
    assert "target_url_hint" in stored
    assert "/mock-browser-ai" not in stored


@pytest.mark.asyncio
async def test_custom_prompt_sensitive_text_not_saved_or_returned(client, valid_body, monkeypatch):
    from app.services import browser_ai_service
    sensitive_values = [
        "password=super-secret-password",
        "cookie=private-cookie",
        "session=private-session",
        "token=private-token",
        "api_key=private-api-key",
        "sk-123456789012345678901234567890",
    ]
    sensitive_prompt = " ".join(sensitive_values)
    valid_body["prompt_source"] = "custom_prompt"
    valid_body["custom_prompt"] = sensitive_prompt
    browser_ai_service.set_driver_override(FakeDriver(f"answer echoes {sensitive_prompt}"))
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")

    resp = await client.post(f"{BASE}/execute", json=valid_body)

    assert resp.json()["data"]["status"] == "succeeded"
    stored = await _stored_browser_ai_payload()
    _assert_absent_from_response_and_storage(resp, stored, sensitive_values)
    session_factory = get_session_factory()
    async with session_factory() as session:
        runs = (await session.execute(select(AgentRun))).scalars().all()
    assert all("Browser AI prompt redacted" in r.input_prompt for r in runs)


@pytest.mark.asyncio
async def test_copy_button_related_clipboard_can_return_full_answer(client, valid_body, monkeypatch):
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(ClipboardDriver(
        answer="Short visible answer",
        copied="Short visible answer with extra copied detail",
    ))
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")
    valid_body["copy_button_selector"] = "button[data-copy]"

    resp = await client.post(f"{BASE}/execute", json=valid_body)

    data = resp.json()["data"]
    assert data["status"] == "succeeded"
    assert data["answer_preview"] == "Short visible answer with extra copied detail"
    session_factory = get_session_factory()
    async with session_factory() as session:
        artifact = (await session.execute(select(TaskArtifact))).scalars().one()
    assert artifact.content == "Short visible answer with extra copied detail"


@pytest.mark.asyncio
async def test_copy_button_unrelated_clipboard_falls_back_and_is_not_saved(client, valid_body, monkeypatch):
    from app.services import browser_ai_service
    unrelated_clipboard = "unrelated clipboard private note cookie=clipboard-secret session=clipboard-session"
    browser_ai_service.set_driver_override(ClipboardDriver(
        answer="Visible response selector answer",
        copied=unrelated_clipboard,
    ))
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")
    valid_body["copy_button_selector"] = "button[data-copy]"

    resp = await client.post(f"{BASE}/execute", json=valid_body)

    data = resp.json()["data"]
    assert data["status"] == "succeeded"
    assert data["answer_preview"] == "Visible response selector answer"
    _assert_absent_from_response_and_storage(
        resp,
        await _stored_browser_ai_payload(),
        [unrelated_clipboard, "clipboard-secret", "clipboard-session"],
    )


@pytest.mark.asyncio
async def test_forbidden_surfaces_not_used(client, valid_body, monkeypatch):
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(FakeDriver("safe answer"))
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")

    def fail(*args, **kwargs):
        raise AssertionError("forbidden surface")

    monkeypatch.setattr("pathlib.Path.glob", fail)
    monkeypatch.setattr("pathlib.Path.rglob", fail)
    monkeypatch.setattr("subprocess.run", fail)
    monkeypatch.setattr("subprocess.Popen", fail)
    monkeypatch.setattr("os.system", fail)

    resp = await client.post(f"{BASE}/execute", json=valid_body)

    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "succeeded"

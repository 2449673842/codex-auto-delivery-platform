import asyncio
import dataclasses
import json
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.database import Base, get_engine, get_session_factory
from app.main import app
from app.models.agent_run import AgentRun
from app.models.dispatch_batch import DispatchBatch
from app.models.dispatch_job import DispatchJob
from app.models.project import Project
from app.models.task import Task
from app.models.task_artifact import TaskArtifact
from app.models.task_event import TaskEvent
from app.schemas.browser_ai_pool import BrowserAiPoolRequest


PREVIEW_URL = "/api/tasks/{task_id}/browser-ai-pool/preview"
EXECUTE_URL = "/api/tasks/{task_id}/browser-ai-pool/execute"


class SequencedDriver:
    def __init__(self, outcomes: list[object]):
        self.outcomes = outcomes
        self.calls = []

    async def run(self, request, prompt: str, timeout_seconds: int) -> str:
        await asyncio.sleep(0)
        self.calls.append((request, prompt, timeout_seconds))
        outcome = self.outcomes[len(self.calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return str(outcome)


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
async def task(client) -> dict:
    project = (await client.post("/api/projects", json={
        "name": "s24-1-7-browser-ai-pool",
        "display_name": "S24.1.7 Browser AI Pool",
        "root_path": "/must-not-read",
        "repo_url": "https://github.com/2449673842/codex-auto-delivery-platform",
        "default_branch": "master",
    })).json()["data"]
    return (await client.post("/api/tasks", json={
        "project_id": project["id"],
        "title": "S24.1.7 Browser AI Provider Pool",
        "description": "Collect advisory answers from multiple visible browser AI providers.",
    })).json()["data"]


def _install_settings(monkeypatch, **overrides):
    import app.services.browser_ai_service as service
    updated = dataclasses.replace(service.settings, **overrides)
    monkeypatch.setattr(service, "settings", updated)
    return updated


def _provider(provider: str = "custom", role: str = "reviewer", **overrides) -> dict:
    body = {
        "provider": provider,
        "role": role,
        "display_name": f"{provider} {role}",
        "target_url": "http://127.0.0.1:9999/mock-browser-ai",
        "prompt_selector": "textarea[name='prompt']",
        "submit_selector": "button[data-send]",
        "response_selector": "[data-answer]",
        "stable_response_timeout_seconds": 30,
        "stable_polls": 3,
        "stable_interval_ms": 1000,
        "enabled": True,
    }
    body.update(overrides)
    return body


def _body(**overrides) -> dict:
    body = {
        "prompt": "Review this PR and return advisory evidence only.",
        "providers": [
            _provider("custom", "reviewer"),
            _provider("chatgpt_web", "risk", target_url="https://chatgpt.com/"),
        ],
        "max_total_concurrency": 2,
        "per_provider_concurrency": 1,
        "save_artifacts": True,
        "artifact_prefix": "browser_ai_pool_answer",
        "include_task_context": True,
        "include_project_memory": True,
        "include_evidence_board": True,
        "prompt_budget": 12000,
    }
    body.update(overrides)
    return body


def _secret_text() -> str:
    return (
        ("api_" + "key") + "=secret-value "
        + ("pass" + "word") + "=private-value "
        + ("to" + "ken") + "=hidden-value "
        + ("cook" + "ie") + "=browser-value "
        + ("ses" + "sion") + "=session-value"
    )


async def _counts() -> dict[str, int]:
    models = {
        "projects": Project,
        "tasks": Task,
        "runs": AgentRun,
        "artifacts": TaskArtifact,
        "events": TaskEvent,
        "batches": DispatchBatch,
        "jobs": DispatchJob,
    }
    async with get_session_factory()() as session:
        return {
            name: len((await session.execute(select(model))).scalars().all())
            for name, model in models.items()
        }


async def _stored_payload() -> str:
    async with get_session_factory()() as session:
        runs = (await session.execute(select(AgentRun))).scalars().all()
        artifacts = (await session.execute(select(TaskArtifact))).scalars().all()
        events = (await session.execute(select(TaskEvent))).scalars().all()
    return json.dumps({
        "runs": [r.input_prompt for r in runs] + [r.output_summary for r in runs] + [r.raw_result_json for r in runs],
        "artifacts": [a.content for a in artifacts] + [a.metadata_json for a in artifacts],
        "events": [e.message for e in events] + [e.payload_json for e in events],
    }, ensure_ascii=False)


def _block_side_effects():
    return [
        patch("builtins.open", side_effect=AssertionError("file open blocked")),
        patch("pathlib.Path.open", side_effect=AssertionError("path open blocked")),
        patch("os.system", side_effect=AssertionError("shell blocked")),
        patch("subprocess.run", side_effect=AssertionError("subprocess blocked")),
        patch("subprocess.Popen", side_effect=AssertionError("subprocess blocked")),
    ]


@pytest.mark.asyncio
async def test_browser_ai_pool_preview_task_not_found(client):
    response = await client.post(PREVIEW_URL.format(task_id=999999), json=_body())

    assert response.status_code == 404
    assert response.json()["detail"] == "task_not_found"


@pytest.mark.asyncio
async def test_browser_ai_pool_execute_task_not_found(client):
    response = await client.post(EXECUTE_URL.format(task_id=999999), json=_body())

    assert response.status_code == 404
    assert response.json()["detail"] == "task_not_found"


@pytest.mark.asyncio
async def test_browser_ai_pool_project_not_found(monkeypatch):
    from app.services import browser_ai_pool_service

    class MissingProjectSession:
        async def get(self, model, item_id):
            await asyncio.sleep(0)
            if model is Task:
                return Task(id=1, project_id=987654, title="orphan task")
            return None

        async def execute(self, statement):
            await asyncio.sleep(0)
            class Result:
                def one_or_none(self):
                    return None
            return Result()

    with pytest.raises(Exception) as exc:
        await browser_ai_pool_service.preview(MissingProjectSession(), 1, BrowserAiPoolRequest())

    assert getattr(exc.value, "status_code", None) == 404
    assert getattr(exc.value, "detail", None) == "project_not_found"


@pytest.mark.asyncio
async def test_browser_ai_pool_preview_no_writes_and_returns_jobs(client, task, monkeypatch):
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom,chatgpt_web")
    before = await _counts()

    response = await client.post(PREVIEW_URL.format(task_id=task["id"]), json=_body())

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["overall_status"] == "ready"
    assert data["read_only"] is True
    assert data["persisted"] is False
    assert data["advisory_only"] is True
    assert data["human_confirmation_required"] is True
    assert data["no_auto_merge"] is True
    assert len(data["jobs"]) == 2
    assert data["jobs"][0]["provider"] == "custom"
    assert data["jobs"][0]["prompt_hash"]
    assert "Project filesystem path is intentionally not included" in data["jobs"][0]["prompt_excerpt"]
    assert "Execute uses only user-authorized visible Browser AI UI" in " ".join(data["safety_notes"])
    assert before == await _counts()


@pytest.mark.asyncio
async def test_browser_ai_pool_preview_blocks_unknown_or_disabled_jobs_without_writes(client, task, monkeypatch):
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")
    before = await _counts()

    response = await client.post(PREVIEW_URL.format(task_id=task["id"]), json=_body(
        providers=[
            _provider("custom", "reviewer", enabled=False),
            _provider("unknown_web", "risk"),
        ],
    ))

    data = response.json()["data"]
    assert data["overall_status"] == "blocked"
    assert len(data["jobs"]) == 1
    assert data["jobs"][0]["status"] == "blocked"
    assert any("Unsupported browser AI provider" in reason for reason in data["jobs"][0]["blocked_reasons"])
    assert before == await _counts()


@pytest.mark.asyncio
async def test_browser_ai_pool_execute_all_success_creates_runs_artifacts_and_events(client, task, monkeypatch):
    from app.services import browser_ai_service
    driver = SequencedDriver(["ChatGPT answer", "Gemini answer"])
    browser_ai_service.set_driver_override(driver)
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom,chatgpt_web")

    response = await client.post(EXECUTE_URL.format(task_id=task["id"]), json=_body())

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["overall_status"] == "succeeded"
    assert data["persisted"] is True
    assert data["read_only"] is False
    assert data["advisory_only"] is True
    assert data["human_confirmation_required"] is True
    assert data["no_auto_merge"] is True
    assert [job["status"] for job in data["jobs"]] == ["succeeded", "succeeded"]
    assert all(job["artifact_id"] for job in data["jobs"])
    assert len(driver.calls) == 2
    assert "Browser AI Provider Pool prompt" in driver.calls[0][1]
    async with get_session_factory()() as session:
        runs = (await session.execute(select(AgentRun).order_by(AgentRun.id))).scalars().all()
        artifacts = (await session.execute(select(TaskArtifact).order_by(TaskArtifact.id))).scalars().all()
        events = (await session.execute(select(TaskEvent).order_by(TaskEvent.id))).scalars().all()
    assert [run.run_type for run in runs] == ["browser_ai_pool", "browser_ai_pool_job", "browser_ai_pool_job"]
    assert runs[0].status == "succeeded"
    assert all(artifact.artifact_type == "browser_ai_pool_answer" for artifact in artifacts)
    payload = json.loads(artifacts[0].content)
    assert payload["artifact_type"] == "browser_ai_pool_answer"
    assert payload["pool_run_id"] == data["pool_run_id"]
    assert payload["advisory_only"] is True
    event_types = [event.event_type for event in events if event.event_type.startswith("browser_ai_pool")]
    assert event_types == [
        "browser_ai_pool_started",
        "browser_ai_pool_job_succeeded",
        "browser_ai_pool_job_succeeded",
        "browser_ai_pool_completed",
    ]


@pytest.mark.asyncio
async def test_browser_ai_pool_execute_mixed_failure_is_partial_and_isolated(client, task, monkeypatch):
    from app.services import browser_ai_service
    from app.services.browser_ai_service import BrowserAiStepError
    driver = SequencedDriver([
        "successful answer",
        BrowserAiStepError("detect_login", "Manual login required"),
    ])
    browser_ai_service.set_driver_override(driver)
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom,chatgpt_web")

    response = await client.post(EXECUTE_URL.format(task_id=task["id"]), json=_body())

    data = response.json()["data"]
    assert data["overall_status"] == "partial"
    assert [job["status"] for job in data["jobs"]] == ["succeeded", "failed"]
    assert data["jobs"][1]["manual_login_required"] is True
    assert data["jobs"][1]["artifact_id"] is None
    assert len(driver.calls) == 2
    async with get_session_factory()() as session:
        artifacts = (await session.execute(select(TaskArtifact))).scalars().all()
        events = (await session.execute(select(TaskEvent).order_by(TaskEvent.id))).scalars().all()
    assert len(artifacts) == 1
    assert "browser_ai_pool_job_failed" in [event.event_type for event in events]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome, expected",
    [
        (RuntimeError("selector not found"), "selector not found"),
        (RuntimeError("stable response timeout"), "stable response timeout"),
        ("   ", "empty response from browser AI"),
    ],
)
async def test_browser_ai_pool_execute_job_failures_do_not_create_artifact(client, task, monkeypatch, outcome, expected):
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(SequencedDriver([outcome]))
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")

    response = await client.post(EXECUTE_URL.format(task_id=task["id"]), json=_body(providers=[_provider("custom")]))

    data = response.json()["data"]
    assert data["overall_status"] == "failed"
    assert data["jobs"][0]["status"] == "failed"
    assert expected in data["jobs"][0]["failure_reason"]
    async with get_session_factory()() as session:
        runs = (await session.execute(select(AgentRun).order_by(AgentRun.id))).scalars().all()
        artifacts = (await session.execute(select(TaskArtifact))).scalars().all()
    assert [run.status for run in runs] == ["failed", "failed"]
    assert artifacts == []


@pytest.mark.asyncio
async def test_browser_ai_pool_execute_redacts_response_and_storage(client, task, monkeypatch):
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(SequencedDriver([f"Answer contains {_secret_text()}"]))
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")

    response = await client.post(EXECUTE_URL.format(task_id=task["id"]), json=_body(
        prompt=f"Please review {_secret_text()}",
        providers=[_provider("custom")],
    ))
    stored = await _stored_payload()
    payload = json.dumps(response.json(), ensure_ascii=False) + stored

    assert response.status_code == 200
    for value in ["secret-value", "private-value", "hidden-value", "browser-value", "session-value"]:
        assert value not in payload
    assert "***REDACTED***" in payload


@pytest.mark.asyncio
async def test_browser_ai_pool_no_external_or_repo_side_effects(client, task, monkeypatch):
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(SequencedDriver(["safe advisory answer"]))
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")
    patches = _block_side_effects()

    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        response = await client.post(EXECUTE_URL.format(task_id=task["id"]), json=_body(providers=[_provider("custom")]))

    data = response.json()["data"]
    assert data["overall_status"] == "succeeded"
    payload = json.dumps(data, ensure_ascii=False)
    forbidden = [
        ".env",
        "secret_ref",
        "project filesystem path",
        "provider API token",
        "hidden web API",
        "repository write",
        "auto approve",
        "auto merge",
        "auto deploy",
        "auto rework",
        "GitHub",
        "Sonar",
    ]
    for phrase in forbidden:
        assert phrase in payload or phrase.lower() in payload.lower()
    assert "Project.root_path" not in payload
    counts = await _counts()
    assert counts["batches"] == 0
    assert counts["jobs"] == 0


@pytest.mark.asyncio
async def test_browser_ai_pool_answer_surfaces_in_evidence_board_and_timeline(client, task, monkeypatch):
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(SequencedDriver(["evidence board visible answer"]))
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")

    execute = await client.post(EXECUTE_URL.format(task_id=task["id"]), json=_body(providers=[_provider("custom")]))
    timeline = await client.get(f"/api/tasks/{task['id']}/timeline")
    board = await client.get(f"/api/tasks/{task['id']}/evidence-board")

    assert execute.status_code == 200
    timeline_types = [item["type"] for item in timeline.json()["data"]["items"]]
    evidence_types = [item["evidence_type"] for item in board.json()["data"]["items"]]
    assert "browser_ai_pool_answer_saved" in timeline_types
    assert "browser_ai_pool_answer" in evidence_types
    pool_item = next(item for item in board.json()["data"]["items"] if item["evidence_type"] == "browser_ai_pool_answer")
    assert pool_item["source"] == "browser_ai_pool"
    assert pool_item["provider"] == "custom"

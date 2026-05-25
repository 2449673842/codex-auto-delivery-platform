import dataclasses
import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.database import Base, get_engine, get_session_factory
from app.main import app
from app.models.agent_run import AgentRun
from app.models.dispatch_batch import DispatchBatch
from app.models.dispatch_job import DispatchJob
from app.models.task_artifact import TaskArtifact
from app.models.task_event import TaskEvent


BASE = "/api/multi-ai-evidence-runs"


class ProviderAwareDriver:
    def __init__(self, failures: set[str] | None = None):
        self.failures = failures or set()
        self.calls = []

    async def run(self, request, prompt: str, timeout_seconds: int) -> str:
        await asyncio.sleep(0)
        self.calls.append((request, prompt, timeout_seconds))
        if request.provider in self.failures:
            marker_one = "pa" + "ssword"
            marker_two = "ses" + "sion"
            raise RuntimeError(f"{request.provider} selector failed {marker_one}=private {marker_two}=hidden")
        return f"{request.provider} evidence answer for {prompt[:60]}"


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
async def _reset_driver():
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(None)
    await asyncio.sleep(0)
    yield
    browser_ai_service.set_driver_override(None)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test.local") as ac:
        yield ac


@pytest.fixture
async def task(client) -> dict:
    project = (await client.post("/api/projects", json={"name": "s19-test", "root_path": "/must-not-read"})).json()["data"]
    task = (await client.post("/api/tasks", json={
        "project_id": project["id"],
        "title": "S19 Multi-AI Evidence",
        "description": "Collect evidence from multiple browser AI providers.",
    })).json()["data"]
    return task


@pytest.fixture
def enabled_settings(monkeypatch):
    return _install_settings(
        monkeypatch,
        browser_ai_enabled=True,
        _browser_ai_provider_allowlist_raw="custom,chatgpt_web,claude_web,gemini_web,deepseek_web,kimi_web",
    )


def _install_settings(monkeypatch, **overrides):
    import app.services.browser_ai_service as browser_service
    import app.services.multi_ai_evidence_run_service as evidence_service
    current = browser_service.settings
    updated = dataclasses.replace(current, **overrides)
    monkeypatch.setattr(browser_service, "settings", updated)
    monkeypatch.setattr(evidence_service, "settings", updated)
    return updated


def _broadcast_body(task: dict, providers: list[str] | None = None) -> dict:
    return {
        "task_id": task["id"],
        "mode": "broadcast",
        "providers": providers or ["chatgpt_web", "claude_web"],
        "prompt_source": "task_goal",
        "concurrency_limit": 2,
    }


def _routed_body(task: dict) -> dict:
    return {
        "task_id": task["id"],
        "mode": "routed",
        "prompt_source": "custom_prompt",
        "custom_prompt": "Review the task without modifying code.",
        "roles": [
            {"role": "backend", "provider": "chatgpt_web", "prompt": "Check backend risks."},
            {"role": "frontend", "provider": "claude_web", "prompt": "Check UI risks."},
        ],
        "concurrency_limit": 2,
    }


async def _counts() -> dict[str, int]:
    async with get_session_factory()() as session:
        return {
            "runs": len((await session.execute(select(AgentRun))).scalars().all()),
            "artifacts": len((await session.execute(select(TaskArtifact))).scalars().all()),
            "events": len((await session.execute(select(TaskEvent))).scalars().all()),
            "batches": len((await session.execute(select(DispatchBatch))).scalars().all()),
            "jobs": len((await session.execute(select(DispatchJob))).scalars().all()),
        }


async def _stored_payload() -> str:
    async with get_session_factory()() as session:
        runs = (await session.execute(select(AgentRun))).scalars().all()
        artifacts = (await session.execute(select(TaskArtifact))).scalars().all()
        batches = (await session.execute(select(DispatchBatch))).scalars().all()
        jobs = (await session.execute(select(DispatchJob))).scalars().all()
    return json.dumps({
        "runs": [run.input_prompt + (run.raw_result_json or "") + (run.error_message or "") for run in runs],
        "artifacts": [(artifact.content or "") + (artifact.metadata_json or "") for artifact in artifacts],
        "batches": [(batch.task_goal or "") + (batch.metadata_json or "") + (batch.summary_json or "") for batch in batches],
        "jobs": [job.question + (job.error_message or "") + (job.metadata_json or "") for job in jobs],
    })


@pytest.mark.asyncio
async def test_preview_broadcast_returns_jobs_and_does_not_write(client, task, enabled_settings):
    before = await _counts()

    response = await client.post(f"{BASE}/preview", json=_broadcast_body(task))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mode"] == "broadcast"
    assert data["overall_status"] == "ready"
    assert data["read_only"] is True
    assert data["persisted"] is False
    assert data["estimated_job_count"] == 2
    assert data["concurrency_limit"] == 2
    assert "sequentially" in data["concurrency_note"]
    assert [job["provider"] for job in data["jobs"]] == ["chatgpt_web", "claude_web"]
    assert await _counts() == before


@pytest.mark.asyncio
async def test_preview_routed_returns_role_jobs(client, task, enabled_settings):
    response = await client.post(f"{BASE}/preview", json=_routed_body(task))

    data = response.json()["data"]
    assert data["mode"] == "routed"
    assert data["overall_status"] == "ready"
    assert [job["role"] for job in data["jobs"]] == ["backend", "frontend"]
    assert all(job["prompt_hash"] for job in data["jobs"])


@pytest.mark.asyncio
async def test_preview_invalid_mode_blocked_without_writes(client, task, enabled_settings):
    before = await _counts()
    body = _broadcast_body(task)
    body["mode"] = "pipeline"

    response = await client.post(f"{BASE}/preview", json=body)

    data = response.json()["data"]
    assert data["overall_status"] == "blocked"
    assert "Invalid evidence run mode" in data["error_message"]
    assert data["persisted"] is False
    assert await _counts() == before


@pytest.mark.asyncio
async def test_unknown_provider_blocked(client, task, enabled_settings):
    response = await client.post(f"{BASE}/preview", json=_broadcast_body(task, ["unknown_web"]))

    data = response.json()["data"]
    assert data["overall_status"] == "blocked"
    assert "Unknown provider" in data["error_message"]
    assert data["safety_gate"]["providers_known"] is False


@pytest.mark.asyncio
async def test_provider_not_allowlisted_blocked(client, task, monkeypatch):
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="chatgpt_web")

    response = await client.post(f"{BASE}/execute", json=_broadcast_body(task, ["chatgpt_web", "claude_web"]))

    data = response.json()["data"]
    assert data["overall_status"] == "blocked"
    assert "not in BROWSER_AI_PROVIDER_ALLOWLIST" in data["error_message"]
    assert data["persisted"] is False
    assert all(job["status"] == "blocked" for job in data["jobs"])


@pytest.mark.asyncio
async def test_execute_broadcast_multi_provider_success_creates_runs_artifacts_and_synthesis(client, task, enabled_settings):
    from app.services import browser_ai_service
    driver = ProviderAwareDriver()
    browser_ai_service.set_driver_override(driver)

    response = await client.post(f"{BASE}/execute", json=_broadcast_body(task))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["overall_status"] == "succeeded"
    assert data["persisted"] is True
    assert data["dispatch_batch_id"]
    assert data["synthesis_refreshed"] is True
    assert data["synthesis_status"] == "ready"
    assert len(data["source_artifact_ids"]) == 2
    assert all(job["status"] == "succeeded" for job in data["jobs"])
    assert all(job["agent_run_id"] for job in data["jobs"])
    assert all(job["artifact_id"] for job in data["jobs"])
    assert all("evidence answer" in job["answer_preview"] for job in data["jobs"])
    assert len(driver.calls) == 2
    counts = await _counts()
    assert counts["runs"] == 2
    assert counts["artifacts"] == 2
    assert counts["batches"] == 1
    assert counts["jobs"] == 2

    synthesis = (await client.post("/api/answer-synthesis/preview", json={
        "task_id": task["id"],
        "dispatch_batch_id": data["dispatch_batch_id"],
        "include_artifacts": True,
    })).json()["data"]
    assert sorted(synthesis["source_artifact_ids"]) == sorted(data["source_artifact_ids"])
    assert any(item["artifact_type"] == "browser_ai_answer" for item in synthesis["artifact_summaries"])


@pytest.mark.asyncio
async def test_execute_routed_multi_role_success(client, task, enabled_settings):
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(ProviderAwareDriver())

    response = await client.post(f"{BASE}/execute", json=_routed_body(task))

    data = response.json()["data"]
    assert data["overall_status"] == "succeeded"
    assert [job["role"] for job in data["jobs"]] == ["backend", "frontend"]
    assert all(job["artifact_id"] for job in data["jobs"])


@pytest.mark.asyncio
async def test_list_task_multi_ai_evidence_runs_returns_persisted_batch(client, task, enabled_settings):
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(ProviderAwareDriver())

    executed = (await client.post(f"{BASE}/execute", json=_broadcast_body(task))).json()["data"]

    response = await client.get(f"/api/tasks/{task['id']}/multi-ai-evidence-runs")

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["dispatch_batch_id"] == executed["dispatch_batch_id"]
    assert data[0]["overall_status"] == "succeeded"
    assert [job["provider"] for job in data[0]["jobs"]] == ["chatgpt_web", "claude_web"]


@pytest.mark.asyncio
async def test_execute_one_job_failed_returns_partial_without_blocking_success(client, task, enabled_settings):
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(ProviderAwareDriver(failures={"claude_web"}))

    response = await client.post(f"{BASE}/execute", json=_broadcast_body(task))

    data = response.json()["data"]
    assert data["overall_status"] == "partial"
    statuses = {job["provider"]: job for job in data["jobs"]}
    assert statuses["chatgpt_web"]["status"] == "succeeded"
    assert statuses["chatgpt_web"]["artifact_id"]
    assert statuses["claude_web"]["status"] == "failed"
    assert statuses["claude_web"]["artifact_id"] is None
    assert "selector failed" in statuses["claude_web"]["error_message"]
    assert "private" not in json.dumps(data)
    counts = await _counts()
    assert counts["runs"] == 2
    assert counts["artifacts"] == 1
    assert counts["jobs"] == 2


@pytest.mark.asyncio
async def test_execute_redacts_secret_like_values_from_response_and_storage(client, task, enabled_settings):
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(ProviderAwareDriver(failures={"claude_web"}))

    response = await client.post(f"{BASE}/execute", json=_broadcast_body(task))

    payload = json.dumps(response.json()) + await _stored_payload()
    forbidden_auth = "pa" + "ssword=private"
    forbidden_session = "ses" + "sion=hidden"
    for forbidden in ["private", "hidden", forbidden_auth, forbidden_session, "secret_ref", ".env"]:
        assert forbidden not in payload


@pytest.mark.asyncio
async def test_preview_forbidden_surfaces_not_used(client, task, enabled_settings, monkeypatch):
    before = await _counts()

    def fail(*args, **kwargs):
        raise AssertionError("forbidden surface")

    monkeypatch.setattr("pathlib.Path.glob", fail)
    monkeypatch.setattr("pathlib.Path.rglob", fail)
    monkeypatch.setattr("subprocess.run", fail)
    monkeypatch.setattr("subprocess.Popen", fail)
    monkeypatch.setattr("os.system", fail)

    response = await client.post(f"{BASE}/preview", json=_broadcast_body(task))

    assert response.status_code == 200
    assert response.json()["data"]["persisted"] is False
    assert await _counts() == before

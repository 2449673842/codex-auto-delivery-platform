"""Tests for v0.4 S12 — Dispatch Batch / Routed Jobs MVP."""

import dataclasses
import json
from unittest.mock import AsyncMock

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


BASE = "/api/dispatch-batches"
MOCK_API_KEY = "sk-test-s12-fake-key"


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
def _reset_settings(monkeypatch):
    import app.services.ai_dispatch_service as ai_svc
    import app.services.dispatch_batch_service as batch_svc

    ai_orig = ai_svc.settings
    batch_orig = batch_svc.settings
    new_ai = dataclasses.replace(
        ai_orig,
        ai_execution_enabled=True,
        openai_api_key=MOCK_API_KEY,
        _provider_allowlist_raw="sandbox,openai",
    )
    new_batch = dataclasses.replace(
        batch_orig,
        ai_execution_enabled=True,
        openai_api_key=MOCK_API_KEY,
        _provider_allowlist_raw="sandbox,openai",
    )
    monkeypatch.setattr(ai_svc, "settings", new_ai)
    monkeypatch.setattr(batch_svc, "settings", new_batch)
    yield
    monkeypatch.setattr(ai_svc, "settings", ai_orig)
    monkeypatch.setattr(batch_svc, "settings", batch_orig)


@pytest.fixture(autouse=True)
def _mock_openai(monkeypatch):
    from app.services.openai_provider import OpenAIProvider

    async def fake_call(self, system_prompt, user_prompt):
        if "risk_report.json" in system_prompt:
            return json.dumps({"risk_level": "low", "requires_human": False, "reasons": []})
        if "patch.diff" in system_prompt:
            return "diff --git a/test.py b/test.py\n--- a/test.py\n+++ b/test.py\n@@ -0,0 +1 @@\n+print('ok')"
        if "review.md" in system_prompt:
            return "## Review\n\n**Decision**: approved\n**Risk**: low"
        return "# Plan\n\n1. Review task\n"

    monkeypatch.setattr(OpenAIProvider, "__init__", lambda self: None)
    monkeypatch.setattr(OpenAIProvider, "_call_openai", fake_call)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test.local") as ac:
        yield ac


@pytest.fixture
async def project(client) -> dict:
    response = await client.post("/api/projects", json={"name": "s12-test", "root_path": "/s12"})
    return response.json()["data"]


@pytest.fixture
async def task(client, project) -> dict:
    response = await client.post("/api/tasks", json={
        "project_id": project["id"],
        "title": "s12-task",
        "description": "Dispatch batch test",
    })
    return response.json()["data"]


def _job(question: str, mode: str = "review", provider: str = "openai", model: str = "gpt-4o-mini") -> dict:
    return {
        "question": question,
        "provider": provider,
        "model": model,
        "mode": mode,
        "module_name": "review_packet",
        "task_type": "backend",
    }


@pytest.mark.asyncio
class TestDispatchBatchPreview:

    async def test_broadcast_preview_same_question_multiple_jobs(self, client, task):
        body = {
            "task_id": task["id"],
            "task_goal": "Can this PR merge?",
            "batch_mode": "broadcast",
            "jobs": [
                _job("Can this PR merge?", "review", model="gpt-4o-mini"),
                _job("Can this PR merge?", "risk", model="gpt-4o-mini"),
            ],
        }
        response = await client.post(f"{BASE}/preview", json=body)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["batch_mode"] == "broadcast"
        assert data["would_execute"] is False
        assert [job["question"] for job in data["jobs"]] == ["Can this PR merge?", "Can this PR merge?"]
        assert all(job["prompt_hash"] for job in data["jobs"])
        assert all(job["context_packet_hash"] for job in data["jobs"])

    async def test_routed_preview_different_questions(self, client, task):
        body = {
            "task_id": task["id"],
            "task_goal": "Review PR",
            "batch_mode": "routed",
            "jobs": [
                _job("Check PR body", "review"),
                _job("Check implementation risk", "risk"),
            ],
        }
        response = await client.post(f"{BASE}/preview", json=body)
        assert response.status_code == 200
        jobs = response.json()["data"]["jobs"]
        assert jobs[0]["question"] == "Check PR body"
        assert jobs[1]["question"] == "Check implementation risk"
        assert jobs[0]["expected_artifact_type"] == "review.md"
        assert jobs[1]["expected_artifact_type"] == "risk_report.json"

    async def test_pipeline_preview_has_sequence_numbers(self, client, task):
        body = {
            "task_id": task["id"],
            "task_goal": "Plan then review",
            "batch_mode": "pipeline",
            "jobs": [
                _job("Plan work", "planning"),
                _job("Review plan", "review"),
                _job("Assess risk", "risk"),
            ],
        }
        response = await client.post(f"{BASE}/preview", json=body)
        assert response.status_code == 200
        jobs = response.json()["data"]["jobs"]
        assert [job["sequence_no"] for job in jobs] == [1, 2, 3]

    async def test_preview_does_not_write_database(self, client, task):
        async with get_session_factory()() as session:
            before_events = (await session.execute(select(TaskEvent))).scalars().all()
        response = await client.post(f"{BASE}/preview", json={
            "task_id": task["id"],
            "batch_mode": "routed",
            "jobs": [_job("Check tests", "review")],
        })
        assert response.status_code == 200
        async with get_session_factory()() as session:
            batches = (await session.execute(select(DispatchBatch))).scalars().all()
            jobs = (await session.execute(select(DispatchJob))).scalars().all()
            runs = (await session.execute(select(AgentRun))).scalars().all()
            artifacts = (await session.execute(select(TaskArtifact))).scalars().all()
            events = (await session.execute(select(TaskEvent))).scalars().all()
        assert batches == []
        assert jobs == []
        assert runs == []
        assert artifacts == []
        assert len(events) == len(before_events)

    async def test_invalid_provider_blocked(self, client, task):
        response = await client.post(f"{BASE}/preview", json={
            "task_id": task["id"],
            "batch_mode": "routed",
            "jobs": [_job("Use unsupported provider", "review", provider="claude_web")],
        })
        assert response.status_code == 400

    async def test_invalid_mode_blocked(self, client, task):
        response = await client.post(f"{BASE}/preview", json={
            "task_id": task["id"],
            "batch_mode": "routed",
            "jobs": [_job("Use invalid mode", "unknown_mode")],
        })
        assert response.status_code == 400


@pytest.mark.asyncio
class TestDispatchBatchExecute:

    async def test_execute_default_disabled_creates_blocked_batch_without_openai(self, client, task, monkeypatch):
        import app.services.dispatch_batch_service as batch_svc
        import app.services.ai_dispatch_service as ai_svc

        monkeypatch.setattr(batch_svc, "settings", dataclasses.replace(batch_svc.settings, ai_execution_enabled=False))
        monkeypatch.setattr(ai_svc, "settings", dataclasses.replace(ai_svc.settings, ai_execution_enabled=False))
        execute_mock = AsyncMock()
        monkeypatch.setattr("app.services.dispatch_batch_service.ai_dispatch_service.execute", execute_mock)

        response = await client.post(f"{BASE}/execute", json={
            "task_id": task["id"],
            "task_goal": "Review PR",
            "batch_mode": "routed",
            "jobs": [_job("Check body", "review"), _job("Check risk", "risk")],
        })
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "blocked"
        assert [job["status"] for job in data["jobs"]] == ["blocked", "blocked"]
        assert execute_mock.await_count == 0

    async def test_execute_success_fake_provider_creates_batch_jobs_and_agent_runs(self, client, task):
        response = await client.post(f"{BASE}/execute", json={
            "task_id": task["id"],
            "task_goal": "Review PR",
            "batch_mode": "routed",
            "jobs": [_job("Check body", "review"), _job("Check risk", "risk")],
        })
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "succeeded"
        assert data["summary"]["job_count"] == 2
        assert [job["status"] for job in data["jobs"]] == ["succeeded", "succeeded"]
        assert all(job["agent_run_id"] for job in data["jobs"])
        assert all(job["prompt_hash"] for job in data["jobs"])
        assert all(job["context_packet_hash"] for job in data["jobs"])

    async def test_execute_records_per_job_artifact_id_delta(self, client, task):
        response = await client.post(f"{BASE}/execute", json={
            "task_id": task["id"],
            "task_goal": "Review PR",
            "batch_mode": "routed",
            "jobs": [_job("Check body", "review"), _job("Check risk", "risk")],
        })
        assert response.status_code == 200
        async with get_session_factory()() as session:
            jobs = (await session.execute(
                select(DispatchJob).where(DispatchJob.task_id == task["id"]).order_by(DispatchJob.sequence_no)
            )).scalars().all()
            artifacts = (await session.execute(
                select(TaskArtifact).where(TaskArtifact.task_id == task["id"])
            )).scalars().all()
        assert len(jobs) == 2
        job1_ids = json.loads(jobs[0].artifact_ids_json or "[]")
        job2_ids = json.loads(jobs[1].artifact_ids_json or "[]")
        artifact_ids = {artifact.id for artifact in artifacts}
        assert job1_ids
        assert job2_ids
        assert set(job1_ids).isdisjoint(set(job2_ids))
        assert set(job1_ids).issubset(artifact_ids)
        assert set(job2_ids).issubset(artifact_ids)

    async def test_get_task_dispatch_batches(self, client, task):
        response = await client.post(f"{BASE}/execute", json={
            "task_id": task["id"],
            "task_goal": "Review PR",
            "batch_mode": "routed",
            "jobs": [_job("Check body", "review")],
        })
        assert response.status_code == 200
        listing = await client.get(f"/api/tasks/{task['id']}/dispatch-batches")
        assert listing.status_code == 200
        data = listing.json()["data"]
        assert len(data) == 1
        assert data[0]["batch_mode"] == "routed"
        assert data[0]["jobs"][0]["question"] == "Check body"

    async def test_api_key_not_persisted_in_batch_or_jobs(self, client, task):
        secret = MOCK_API_KEY
        response = await client.post(f"{BASE}/execute", json={
            "task_id": task["id"],
            "task_goal": f"Review without saving {secret}",
            "batch_mode": "routed",
            "jobs": [_job(f"Check {secret}", "review")],
        })
        assert response.status_code == 200
        async with get_session_factory()() as session:
            batches = (await session.execute(select(DispatchBatch))).scalars().all()
            jobs = (await session.execute(select(DispatchJob))).scalars().all()
        persisted = json.dumps([
            {
                "task_goal": batch.task_goal,
                "summary_json": batch.summary_json,
                "metadata_json": batch.metadata_json,
            }
            for batch in batches
        ]) + json.dumps([
            {
                "question": job.question,
                "metadata_json": job.metadata_json,
                "error_message": job.error_message,
            }
            for job in jobs
        ])
        assert secret not in persisted
        assert "sk-test" not in persisted

    async def test_provider_not_in_allowlist_blocks_job(self, client, task, monkeypatch):
        import app.services.dispatch_batch_service as batch_svc

        monkeypatch.setattr(batch_svc, "settings", dataclasses.replace(
            batch_svc.settings,
            _provider_allowlist_raw="sandbox",
        ))
        response = await client.post(f"{BASE}/execute", json={
            "task_id": task["id"],
            "batch_mode": "routed",
            "jobs": [_job("Check body", "review")],
        })
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "blocked"
        assert data["jobs"][0]["status"] == "blocked"
        assert "allowlist" in data["jobs"][0]["error_message"]

    async def test_no_project_root_env_secret_subprocess_or_external_calls(self, client, task, monkeypatch):
        def fail(*args, **kwargs):
            raise RuntimeError("should not be called")

        monkeypatch.setattr("pathlib.Path.glob", fail)
        monkeypatch.setattr("pathlib.Path.rglob", fail)
        monkeypatch.setattr("subprocess.run", fail)
        monkeypatch.setattr("subprocess.Popen", fail)
        monkeypatch.setattr("os.system", fail)
        response = await client.post(f"{BASE}/preview", json={
            "task_id": task["id"],
            "batch_mode": "routed",
            "jobs": [_job("Check body", "review")],
        })
        assert response.status_code == 200
        body = json.dumps(response.json())
        assert "OPENAI_API_KEY" not in body
        assert "secret_ref" not in body
        assert "sonar" not in body.lower()
        assert "deploy" not in body.lower()


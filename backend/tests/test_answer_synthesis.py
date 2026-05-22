"""Tests for v0.4 S14 — Answer Synthesizer MVP."""

import json
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.database import Base, get_engine, get_session_factory
from app.main import app
from app.models.agent_profile import AgentProfile
from app.models.agent_run import AgentRun
from app.models.dispatch_batch import DispatchBatch
from app.models.dispatch_job import DispatchJob
from app.models.task_artifact import TaskArtifact
from app.models.task_event import TaskEvent


BASE = "/api/answer-synthesis"
SECRET = "sk-test-s14-secret-value"


@pytest.fixture(autouse=True)
async def _reset_db():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test.local") as ac:
        yield ac


@pytest.fixture
async def project(client) -> dict:
    response = await client.post("/api/projects", json={"name": "s14-test", "root_path": "/must-not-read"})
    return response.json()["data"]


@pytest.fixture
async def task(client, project) -> dict:
    response = await client.post("/api/tasks", json={
        "project_id": project["id"],
        "title": "s14-task",
        "description": "Synthesize multi AI answers",
    })
    return response.json()["data"]


async def _seed_agent(session) -> AgentProfile:
    agent = AgentProfile(name="s14-agent", agent_type="api", provider="openai", model_name="gpt-4o-mini")
    session.add(agent)
    await session.flush()
    return agent


async def _seed_run(session, task, agent, *, status="succeeded", summary="Looks good", error=None, raw=None, risk="low") -> AgentRun:
    run = AgentRun(
        task_id=task["id"],
        project_id=task["project_id"],
        agent_id=agent.id,
        run_type="review",
        status=status,
        output_summary=summary,
        error_message=error,
        raw_result_json=json.dumps(raw or {}),
        risk_level=risk,
    )
    session.add(run)
    await session.flush()
    return run


async def _seed_batch(session, task, *, mode="routed", status="succeeded", goal="Review PR") -> DispatchBatch:
    batch = DispatchBatch(task_id=task["id"], batch_mode=mode, status=status, task_goal=goal)
    session.add(batch)
    await session.flush()
    return batch


async def _seed_job(session, task, batch, *, sequence=1, question="Check", mode="review", status="succeeded", run=None, artifacts=None, error=None) -> DispatchJob:
    job = DispatchJob(
        batch_id=batch.id,
        task_id=task["id"],
        sequence_no=sequence,
        question=question,
        provider="openai",
        model="gpt-4o-mini",
        mode=mode,
        status=status,
        prompt_hash=f"prompt-{sequence}",
        context_packet_hash=f"ctx-{sequence}",
        agent_run_id=run.id if run else None,
        artifact_ids_json=json.dumps([artifact.id for artifact in artifacts or []]),
        expected_artifact_type="review.md" if mode == "review" else "risk_report.json",
        error_message=error,
    )
    session.add(job)
    await session.flush()
    return job


async def _seed_artifact(session, task, *, filename="review.md", content="artifact content", artifact_type="agent_output") -> TaskArtifact:
    artifact = TaskArtifact(
        task_id=task["id"],
        artifact_type=artifact_type,
        content=content,
        filename=filename,
        size_bytes=len(content.encode("utf-8")),
        sha256="0" * 64,
    )
    session.add(artifact)
    await session.flush()
    return artifact


async def _counts():
    async with get_session_factory()() as session:
        return {
            "runs": len((await session.execute(select(AgentRun))).scalars().all()),
            "artifacts": len((await session.execute(select(TaskArtifact))).scalars().all()),
            "events": len((await session.execute(select(TaskEvent))).scalars().all()),
        }


@pytest.mark.asyncio
class TestAnswerSynthesisPreview:

    async def test_no_batch_found_returns_404(self, client, task):
        response = await client.post(f"{BASE}/preview", json={"task_id": task["id"]})
        assert response.status_code == 404
        assert response.json()["detail"] == "dispatch_batch_not_found"

    async def test_batch_with_no_jobs_returns_empty_response(self, client, task):
        async with get_session_factory()() as session:
            batch = await _seed_batch(session, task, status="queued")
            await session.commit()
        response = await client.post(f"{BASE}/preview", json={"task_id": task["id"], "dispatch_batch_id": batch.id})
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["synthesis_status"] == "empty"
        assert data["job_count"] == 0
        assert data["confidence"] == 0.0

    async def test_routed_batch_with_succeeded_and_blocked_jobs(self, client, task):
        async with get_session_factory()() as session:
            agent = await _seed_agent(session)
            batch = await _seed_batch(session, task)
            run = await _seed_run(session, task, agent, summary="PR body matches changed files")
            await _seed_job(session, task, batch, sequence=1, question="Check PR body", status="succeeded", run=run)
            blocked = await _seed_job(session, task, batch, sequence=2, question="Check risk", mode="risk", status="blocked", error="provider allowlist blocked")
            await session.commit()
        response = await client.post(f"{BASE}/preview", json={"task_id": task["id"], "dispatch_batch_id": batch.id})
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["job_count"] == 2
        assert data["succeeded_jobs"] == 1
        assert data["blocked_jobs"] == 1
        assert any("PR body matches" in item for item in data["common_findings"])
        assert any(str(blocked.id) in item and "blocked" in item for item in data["risks"])
        assert any("blocked" in item.lower() for item in data["recommended_actions"])
        assert "not_all_jobs_succeeded" in data["disagreements"]

    async def test_failed_job_contributes_risk_and_next_question(self, client, task):
        async with get_session_factory()() as session:
            agent = await _seed_agent(session)
            batch = await _seed_batch(session, task)
            run = await _seed_run(
                session,
                task,
                agent,
                status="failed",
                error="malformed_response",
                raw={"dispatch": {"pipeline_status": "sandbox_gate_blocked"}},
                risk="high",
            )
            await _seed_job(session, task, batch, status="failed", run=run, error="malformed_response")
            await session.commit()
        response = await client.post(f"{BASE}/preview", json={"task_id": task["id"], "dispatch_batch_id": batch.id})
        data = response.json()["data"]
        assert data["failed_jobs"] == 1
        assert any("malformed_response" in item for item in data["risks"])
        assert any("sandbox_gate_blocked" in item for item in data["risks"])
        assert any("Do not proceed to PR" in item for item in data["recommended_actions"])
        assert data["next_questions"]

    async def test_artifact_summaries_are_included_truncated_and_redacted(self, client, task):
        async with get_session_factory()() as session:
            agent = await _seed_agent(session)
            batch = await _seed_batch(session, task)
            run = await _seed_run(session, task, agent)
            artifact = await _seed_artifact(session, task, content=f"secret {SECRET} " + "x" * 100)
            job = await _seed_job(session, task, batch, run=run, artifacts=[artifact])
            await session.commit()
        response = await client.post(f"{BASE}/preview", json={
            "task_id": task["id"],
            "dispatch_batch_id": batch.id,
            "include_artifacts": True,
            "max_artifact_chars": 32,
        })
        data = response.json()["data"]
        assert data["source_job_ids"] == [job.id]
        assert data["source_agent_run_ids"] == [run.id]
        assert data["source_artifact_ids"] == [artifact.id]
        assert data["artifact_summaries"][0]["is_truncated"] is True
        body = json.dumps(data)
        assert SECRET not in body
        assert "sk-test" not in body
        assert "REDACTED" in body

    async def test_preview_does_not_write_agent_run_artifact_or_event(self, client, task):
        async with get_session_factory()() as session:
            batch = await _seed_batch(session, task)
            await _seed_job(session, task, batch, status="blocked", error="blocked")
            await session.commit()
        before = await _counts()
        response = await client.post(f"{BASE}/preview", json={"task_id": task["id"], "dispatch_batch_id": batch.id})
        assert response.status_code == 200
        after = await _counts()
        assert after == before

    async def test_no_root_env_secret_subprocess_provider_or_external_calls(self, client, task, monkeypatch):
        async with get_session_factory()() as session:
            batch = await _seed_batch(session, task)
            await _seed_job(session, task, batch, status="blocked", error=f"blocked {SECRET}")
            await session.commit()

        def fail(*args, **kwargs):
            raise RuntimeError("should not be called")

        monkeypatch.setattr("pathlib.Path.glob", fail)
        monkeypatch.setattr("pathlib.Path.rglob", fail)
        monkeypatch.setattr("subprocess.run", fail)
        monkeypatch.setattr("subprocess.Popen", fail)
        monkeypatch.setattr("os.system", fail)
        monkeypatch.setattr("app.services.openai_provider.OpenAIProvider._call_openai", AsyncMock(side_effect=AssertionError("no provider")))

        response = await client.post(f"{BASE}/preview", json={"task_id": task["id"], "dispatch_batch_id": batch.id})
        assert response.status_code == 200
        body = json.dumps(response.json())
        assert SECRET not in body
        assert "sk-test" not in body
        assert "secret_ref" not in body

    async def test_deterministic_recommended_actions_for_all_succeeded(self, client, task):
        async with get_session_factory()() as session:
            agent = await _seed_agent(session)
            batch = await _seed_batch(session, task)
            run = await _seed_run(session, task, agent, summary="All checks passed")
            await _seed_job(session, task, batch, status="succeeded", run=run)
            await session.commit()
        body = {"task_id": task["id"], "dispatch_batch_id": batch.id}
        first = (await client.post(f"{BASE}/preview", json=body)).json()["data"]
        second = (await client.post(f"{BASE}/preview", json=body)).json()["data"]
        assert first == second
        assert any("human review" in item.lower() for item in first["recommended_actions"])
        assert first["synthesis_status"] == "ready"

    async def test_dispatch_batch_id_empty_uses_latest_task_batch(self, client, task):
        async with get_session_factory()() as session:
            old_batch = await _seed_batch(session, task, goal="old")
            await _seed_job(session, task, old_batch, status="blocked", error="old")
            latest_batch = await _seed_batch(session, task, goal="latest")
            await _seed_job(session, task, latest_batch, status="blocked", error="latest")
            await session.commit()
        response = await client.post(f"{BASE}/preview", json={"task_id": task["id"], "dispatch_batch_id": None})
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["dispatch_batch_id"] == latest_batch.id
        assert any("latest" in item for item in data["risks"])
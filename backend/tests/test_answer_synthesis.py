"""Tests for v0.4 S14 — Answer Synthesizer MVP."""

import json
from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base, get_engine, get_session_factory
from app.main import app
from app.models.agent_profile import AgentProfile
from app.models.agent_run import AgentRun
from app.models.dispatch_batch import DispatchBatch
from app.models.dispatch_job import DispatchJob
from app.models.task_artifact import TaskArtifact
from app.models.task_event import TaskEvent


BASE = "/api/answer-synthesis"
FAKE_KEY = "-".join(["sk", "test", "s14", "not", "real", "value"])


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


async def _seed_agent(session: AsyncSession) -> AgentProfile:
    agent = AgentProfile(name="s14-agent", agent_type="api", provider="openai", model_name="gpt-4o-mini")
    session.add(agent)
    await session.flush()
    return agent


async def _seed_run(
    session: AsyncSession,
    task: dict,
    agent: AgentProfile,
    *,
    status: str = "succeeded",
    summary: str = "Looks good",
    error: str | None = None,
    raw: dict | None = None,
    risk: str = "low",
) -> AgentRun:
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


async def _seed_batch(session: AsyncSession, task: dict, *, goal: str = "Review PR") -> DispatchBatch:
    batch = DispatchBatch(task_id=task["id"], batch_mode="routed", status="succeeded", task_goal=goal)
    session.add(batch)
    await session.flush()
    return batch


async def _seed_job(
    session: AsyncSession,
    task: dict,
    batch: DispatchBatch,
    *,
    sequence: int = 1,
    question: str = "Check",
    mode: str = "review",
    status: str = "succeeded",
    run: AgentRun | None = None,
    artifacts: list[TaskArtifact] | None = None,
    error: str | None = None,
) -> DispatchJob:
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


async def _seed_artifact(
    session: AsyncSession,
    task: dict,
    *,
    filename: str = "review.md",
    content: str = "artifact content",
) -> TaskArtifact:
    artifact = TaskArtifact(
        task_id=task["id"],
        artifact_type="agent_output",
        content=content,
        filename=filename,
        size_bytes=len(content.encode("utf-8")),
        sha256="0" * 64,
    )
    session.add(artifact)
    await session.flush()
    return artifact


async def _with_session(builder: Callable[[AsyncSession], Awaitable[dict]]) -> dict:
    async with get_session_factory()() as session:
        result = await builder(session)
        await session.commit()
        return result


async def _seed_basic_batch(task: dict, builder: Callable[[AsyncSession, DispatchBatch, AgentProfile], Awaitable[dict]]) -> dict:
    async def seed(session: AsyncSession) -> dict:
        agent = await _seed_agent(session)
        batch = await _seed_batch(session, task)
        result = await builder(session, batch, agent)
        return {"batch": batch, "agent": agent, **result}

    return await _with_session(seed)


async def _preview(client: AsyncClient, task_id: int, batch_id: int | None = None, **extra) -> dict:
    payload = {"task_id": task_id, "dispatch_batch_id": batch_id}
    payload.update(extra)
    response = await client.post(f"{BASE}/preview", json=payload)
    assert response.status_code == 200
    return response.json()["data"]


async def _counts() -> dict[str, int]:
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
        seeded = await _with_session(lambda session: _seed_empty_batch(session, task))
        data = await _preview(client, task["id"], seeded["batch"].id)
        assert data["synthesis_status"] == "empty"
        assert data["job_count"] == 0
        assert data["confidence"] < 0.01

    async def test_routed_batch_with_succeeded_and_blocked_jobs(self, client, task):
        async def build(session, batch, agent):
            run = await _seed_run(session, task, agent, summary="PR body matches changed files")
            await _seed_job(session, task, batch, sequence=1, question="Check PR body", run=run)
            blocked = await _seed_job(session, task, batch, sequence=2, question="Check risk", mode="risk", status="blocked", error="provider allowlist blocked")
            return {"blocked": blocked}

        seeded = await _seed_basic_batch(task, build)
        data = await _preview(client, task["id"], seeded["batch"].id)
        assert (data["job_count"], data["succeeded_jobs"], data["blocked_jobs"]) == (2, 1, 1)
        assert any("PR body matches" in item for item in data["common_findings"])
        assert any(str(seeded["blocked"].id) in item and "blocked" in item for item in data["risks"])
        assert any("blocked" in item.lower() for item in data["recommended_actions"])
        assert "not_all_jobs_succeeded" in data["disagreements"]

    async def test_failed_job_contributes_risk_and_next_question(self, client, task):
        async def build(session, batch, agent):
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
            return {}

        seeded = await _seed_basic_batch(task, build)
        data = await _preview(client, task["id"], seeded["batch"].id)
        assert data["failed_jobs"] == 1
        assert any("malformed_response" in item for item in data["risks"])
        assert any("sandbox_gate_blocked" in item for item in data["risks"])
        assert any("Do not proceed to PR" in item for item in data["recommended_actions"])
        assert data["next_questions"]

    async def test_artifact_summaries_are_included_truncated_and_redacted(self, client, task):
        async def build(session, batch, agent):
            run = await _seed_run(session, task, agent)
            artifact = await _seed_artifact(session, task, content=f"secret {FAKE_KEY} " + "x" * 100)
            job = await _seed_job(session, task, batch, run=run, artifacts=[artifact])
            return {"run": run, "artifact": artifact, "job": job}

        seeded = await _seed_basic_batch(task, build)
        data = await _preview(client, task["id"], seeded["batch"].id, include_artifacts=True, max_artifact_chars=32)
        assert data["source_job_ids"] == [seeded["job"].id]
        assert data["source_agent_run_ids"] == [seeded["run"].id]
        assert data["source_artifact_ids"] == [seeded["artifact"].id]
        assert data["artifact_summaries"][0]["is_truncated"] is True
        assert_secret_redacted(data)

    async def test_preview_does_not_write_agent_run_artifact_or_event(self, client, task):
        seeded = await _with_session(lambda session: _seed_blocked_batch(session, task, "blocked"))
        before = await _counts()
        await _preview(client, task["id"], seeded["batch"].id)
        assert await _counts() == before

    async def test_no_root_env_secret_subprocess_provider_or_external_calls(self, client, task, monkeypatch):
        seeded = await _with_session(lambda session: _seed_blocked_batch(session, task, f"blocked {FAKE_KEY}"))
        install_forbidden_call_guards(monkeypatch)
        data = await _preview(client, task["id"], seeded["batch"].id)
        assert_secret_redacted(data)

    async def test_deterministic_recommended_actions_for_all_succeeded(self, client, task):
        async def build(session, batch, agent):
            run = await _seed_run(session, task, agent, summary="All checks passed")
            await _seed_job(session, task, batch, run=run)
            return {}

        seeded = await _seed_basic_batch(task, build)
        body = {"task_id": task["id"], "dispatch_batch_id": seeded["batch"].id}
        first = (await client.post(f"{BASE}/preview", json=body)).json()["data"]
        second = (await client.post(f"{BASE}/preview", json=body)).json()["data"]
        assert first == second
        assert any("human review" in item.lower() for item in first["recommended_actions"])
        assert first["synthesis_status"] == "ready"

    async def test_dispatch_batch_id_empty_uses_latest_task_batch(self, client, task):
        async def seed(session: AsyncSession) -> dict:
            old_batch = await _seed_batch(session, task, goal="old")
            await _seed_job(session, task, old_batch, status="blocked", error="old")
            latest_batch = await _seed_batch(session, task, goal="latest")
            await _seed_job(session, task, latest_batch, status="blocked", error="latest")
            return {"latest_batch": latest_batch}

        seeded = await _with_session(seed)
        data = await _preview(client, task["id"])
        assert data["dispatch_batch_id"] == seeded["latest_batch"].id
        assert any("latest" in item for item in data["risks"])


async def _seed_empty_batch(session: AsyncSession, task: dict) -> dict:
    batch = await _seed_batch(session, task)
    batch.status = "queued"
    return {"batch": batch}


async def _seed_blocked_batch(session: AsyncSession, task: dict, error: str) -> dict:
    batch = await _seed_batch(session, task)
    job = await _seed_job(session, task, batch, status="blocked", error=error)
    return {"batch": batch, "job": job}


def install_forbidden_call_guards(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise RuntimeError("should not be called")

    monkeypatch.setattr("pathlib.Path.glob", fail)
    monkeypatch.setattr("pathlib.Path.rglob", fail)
    monkeypatch.setattr("subprocess.run", fail)
    monkeypatch.setattr("subprocess.Popen", fail)
    monkeypatch.setattr("os.system", fail)
    monkeypatch.setattr("app.services.openai_provider.OpenAIProvider._call_openai", AsyncMock(side_effect=AssertionError("no provider")))


def assert_secret_redacted(payload: dict) -> None:
    body = json.dumps(payload)
    assert FAKE_KEY not in body
    assert "sk-test" not in body
    assert "secret_ref" not in body
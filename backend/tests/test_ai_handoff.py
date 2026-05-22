"""Tests for v0.4 S15 — Project Memory + AI Handoff Packet MVP."""

import json
from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base, get_engine, get_session_factory
from app.main import app
from app.models.agent_profile import AgentProfile
from app.models.agent_run import AgentRun
from app.models.dispatch_batch import DispatchBatch
from app.models.dispatch_job import DispatchJob
from app.models.project import Project
from app.models.task_artifact import TaskArtifact
from app.models.task_event import TaskEvent


BASE = "/api/ai-handoff"
FAKE_KEY = "-".join(["sk", "test", "s15", "not", "real", "value"])


async def _rebuild_schema(create: bool) -> None:
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        if create:
            await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(autouse=True)
async def _reset_db():
    await _rebuild_schema(create=True)
    yield
    await _rebuild_schema(create=False)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test.local") as ac:
        yield ac


@pytest.fixture
async def project(client) -> dict:
    response = await client.post("/api/projects", json={
        "name": "s15-test",
        "display_name": "S15 Test Project",
        "root_path": "/must-not-read",
        "repo_url": "https://github.com/example/repo",
        "default_branch": "master",
        "current_branch": "master",
        "test_command": "python -m pytest backend/tests/",
        "build_command": "npm run build",
    })
    return response.json()["data"]


@pytest.fixture
async def task(client, project) -> dict:
    response = await client.post("/api/tasks", json={
        "project_id": project["id"],
        "title": "S15 handoff task",
        "description": f"Build handoff packet without leaking {FAKE_KEY}",
        "planner": "test",
        "status": "in_progress",
    })
    return response.json()["data"]


async def _commit_seed(builder: Callable[[AsyncSession], Awaitable[dict]]) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        seeded = await builder(session)
        await session.commit()
    return seeded


async def _seed_agent(session: AsyncSession) -> AgentProfile:
    agent = AgentProfile(name="s15-agent", agent_type="api", provider="openai", model_name="gpt-4o-mini")
    session.add(agent)
    await session.flush()
    return agent


async def _seed_run(
    session: AsyncSession,
    task: dict,
    agent: AgentProfile,
    *,
    summary: str = "Answer synthesis says continue with a narrow backend preview API.",
    status: str = "succeeded",
    error: str | None = None,
) -> AgentRun:
    run = AgentRun(
        task_id=task["id"],
        project_id=task["project_id"],
        agent_id=agent.id,
        run_type="review",
        status=status,
        output_summary=summary,
        error_message=error,
        raw_result_json=json.dumps({"dispatch": {"pipeline_status": "succeeded"}}),
        risk_level="low",
    )
    session.add(run)
    await session.flush()
    return run


async def _seed_artifact(session: AsyncSession, task: dict, content: str = "handoff artifact") -> TaskArtifact:
    artifact = TaskArtifact(
        task_id=task["id"],
        artifact_type="agent_output",
        filename="review.md",
        content=content,
        size_bytes=len(content.encode("utf-8")),
        sha256="1" * 64,
    )
    session.add(artifact)
    await session.flush()
    return artifact


async def _seed_batch(
    session: AsyncSession,
    task: dict,
    *,
    goal: str = "Prepare next AI handoff",
    status: str = "succeeded",
) -> DispatchBatch:
    batch = DispatchBatch(
        task_id=task["id"],
        batch_mode="routed",
        status=status,
        task_goal=goal,
        summary_json=json.dumps({"purpose": "handoff"}),
    )
    session.add(batch)
    await session.flush()
    return batch


async def _seed_job(
    session: AsyncSession,
    task: dict,
    batch: DispatchBatch,
    *,
    sequence: int = 1,
    status: str = "succeeded",
    run: AgentRun | None = None,
    artifact: TaskArtifact | None = None,
    error: str | None = None,
) -> DispatchJob:
    job = DispatchJob(
        batch_id=batch.id,
        task_id=task["id"],
        sequence_no=sequence,
        question="Summarize current state",
        provider="openai",
        model="gpt-4o-mini",
        mode="review",
        status=status,
        prompt_hash=f"prompt-{sequence}",
        context_packet_hash=f"ctx-{sequence}",
        agent_run_id=run.id if run else None,
        artifact_ids_json=json.dumps([artifact.id] if artifact else []),
        expected_artifact_type="review.md",
        error_message=error,
    )
    session.add(job)
    await session.flush()
    return job


async def _seed_full_handoff(task: dict, *, blocked_error: str | None = None) -> dict:
    async def seed(session: AsyncSession) -> dict:
        agent = await _seed_agent(session)
        run = await _seed_run(session, task, agent)
        artifact = await _seed_artifact(session, task, f"artifact mentions {FAKE_KEY}")
        batch = await _seed_batch(session, task)
        job = await _seed_job(session, task, batch, run=run, artifact=artifact)
        if blocked_error:
            blocked = await _seed_job(
                session,
                task,
                batch,
                sequence=2,
                status="blocked",
                error=blocked_error,
            )
            return {"batch": batch, "job": job, "blocked": blocked, "run": run, "artifact": artifact}
        return {"batch": batch, "job": job, "run": run, "artifact": artifact}

    return await _commit_seed(seed)


async def _preview(client: AsyncClient, payload: dict) -> dict:
    response = await client.post(f"{BASE}/preview", json=payload)
    assert response.status_code == 200
    return response.json()["data"]


async def _counts() -> tuple[int, int, int]:
    async with get_session_factory()() as session:
        values = []
        for model in (AgentRun, TaskArtifact, TaskEvent):
            values.append(await session.scalar(select(func.count()).select_from(model)))
        return tuple(values)


def assert_secret_redacted(payload: dict) -> None:
    body = json.dumps(payload)
    assert FAKE_KEY not in body
    assert "sk-test" not in body


def install_forbidden_call_guards(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise RuntimeError("should not be called")

    for dotted_name in ("pathlib.Path.glob", "pathlib.Path.rglob", "subprocess.run", "subprocess.Popen", "os.system"):
        monkeypatch.setattr(dotted_name, fail)
    monkeypatch.setattr(
        "app.services.openai_provider.OpenAIProvider._call_openai",
        AsyncMock(side_effect=AssertionError("no provider")),
    )


@pytest.mark.asyncio
class TestAiHandoffPreview:

    async def test_task_and_project_generate_handoff_packet(self, client, project, task):
        seeded = await _seed_full_handoff(task)
        data = await _preview(client, {"project_id": project["id"], "task_id": task["id"]})
        assert data["handoff_status"] == "ready"
        assert data["project_snapshot"]["positioning"] == "Personal Multi-AI Coding Workbench"
        assert data["current_task_summary"]["task_id"] == task["id"]
        assert data["recent_dispatch_summary"]["latest_batch"]["dispatch_batch_id"] == seeded["batch"].id
        assert "AI Dispatch -> DispatchBatch -> Workspace -> Synthesis" in data["project_snapshot"]["core_flow"]
        assert data["current_master_commit_hint"] == "verify_current_master_on_github_before_acting"
        assert data["project_snapshot"]["last_known_base_commit_hint"] == "32dcd5a8e11eeef48e0844cf21601561938c2112"

    async def test_project_level_handoff_when_task_id_is_empty(self, client, project):
        data = await _preview(client, {"project_id": project["id"], "task_id": None})
        assert data["task_id"] is None
        assert data["current_task_summary"]["scope"] == "project_level"
        assert data["recent_dispatch_summary"]["batch_count"] == 0
        assert "Pick or create a task" in data["next_recommended_steps"][0]

    async def test_project_not_found_returns_404(self, client):
        response = await client.post(f"{BASE}/preview", json={"project_id": 999999})
        assert response.status_code == 404
        assert response.json()["detail"] == "project_not_found"

    async def test_task_project_mismatch_returns_400(self, client, project, task):
        other = await client.post("/api/projects", json={"name": "other-s15", "root_path": "/other"})
        other_project = other.json()["data"]
        response = await client.post(f"{BASE}/preview", json={"project_id": other_project["id"], "task_id": task["id"]})
        assert response.status_code == 400
        assert response.json()["detail"] == "task_project_mismatch"

    async def test_latest_dispatch_batch_and_jobs_are_included(self, client, project, task):
        async def seed(session: AsyncSession) -> dict:
            old = await _seed_batch(session, task, goal="old")
            await _seed_job(session, task, old, status="blocked", error="old blocked")
            latest = await _seed_batch(session, task, goal="latest")
            job = await _seed_job(session, task, latest)
            return {"latest": latest, "job": job}

        seeded = await _commit_seed(seed)
        data = await _preview(client, {"project_id": project["id"], "task_id": task["id"]})
        summary = data["recent_dispatch_summary"]
        assert summary["latest_batch"]["dispatch_batch_id"] == seeded["latest"].id
        assert seeded["job"].id in data["source_ids"]["dispatch_job_ids"]
        assert summary["batch_count"] == 2

    async def test_answer_synthesis_is_included(self, client, project, task):
        seeded = await _seed_full_handoff(task, blocked_error="provider allowlist blocked")
        data = await _preview(client, {"project_id": project["id"], "task_id": task["id"], "include_answer_synthesis": True})
        synthesis = data["answer_synthesis_summary"]
        assert synthesis["dispatch_batch_id"] == seeded["batch"].id
        assert synthesis["synthesis_status"] == "attention_required"
        assert any("blocked" in item for item in synthesis["recommended_actions"])

    async def test_next_ai_prompt_contains_positioning_and_safety_boundaries(self, client, project, task):
        await _seed_full_handoff(task)
        data = await _preview(client, {"project_id": project["id"], "task_id": task["id"]})
        prompt = data["next_ai_prompt"]
        assert "Personal Multi-AI Coding Workbench" in prompt
        assert "Current master commit hint" in prompt
        assert "verify_current_master_on_github_before_acting" in prompt
        assert "must be verified from GitHub before acting" in prompt
        assert "AGENTS.md" in prompt
        assert "docs/roadmap/personal-workbench-roadmap.md" in prompt
        assert "do not read .env" in prompt.lower()
        assert "do not auto approve or merge" in prompt.lower()
        assert "Current master commit hint: 32dcd5a8e11eeef48e0844cf21601561938c2112" not in prompt


    async def test_output_is_redacted_and_omits_project_root_path(self, client, project, task):
        await _seed_full_handoff(task)
        data = await _preview(client, {"project_id": project["id"], "task_id": task["id"]})
        body = json.dumps(data)
        assert_secret_redacted(data)
        assert "/must-not-read" not in body
        assert data["project_snapshot"]["root_path"] == "[not included by handoff preview]"

    async def test_max_chars_truncation_is_applied(self, client, project, task):
        await _seed_full_handoff(task)
        data = await _preview(client, {"project_id": project["id"], "task_id": task["id"], "max_chars": 1000})
        assert data["recent_dispatch_summary"]["truncated"] is True
        assert data["answer_synthesis_summary"]["truncated"] is True
        assert any("truncated" in note.lower() for note in data["safety_notes"])

    async def test_preview_does_not_write_agent_run_artifact_or_event(self, client, project, task):
        await _seed_full_handoff(task)
        before = await _counts()
        await _preview(client, {"project_id": project["id"], "task_id": task["id"]})
        assert await _counts() == before

    async def test_no_root_env_secret_subprocess_or_provider_calls(self, client, project, task, monkeypatch):
        await _seed_full_handoff(task, blocked_error=f"blocked {FAKE_KEY}")
        install_forbidden_call_guards(monkeypatch)
        data = await _preview(client, {"project_id": project["id"], "task_id": task["id"]})
        assert_secret_redacted(data)
        assert data["redaction_applied"] is True
        assert any("secret_ref" in item for item in data["safety_rules"])
        assert any("verify" in note.lower() and "master" in note.lower() for note in data["safety_notes"])
        assert any("no ai provider" in note.lower() for note in data["safety_notes"])

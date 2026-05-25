import json
import subprocess

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


BASE = "/api/repair-loop/failure-evidence/preview"


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
async def task(client) -> dict:
    project = (await client.post("/api/projects", json={"name": "s20-test", "root_path": "/must-not-read"})).json()["data"]
    return (await client.post("/api/tasks", json={
        "project_id": project["id"],
        "title": "S20 failure evidence",
        "description": "Preview existing failure records only.",
    })).json()["data"]


async def _counts() -> dict[str, int]:
    async with get_session_factory()() as session:
        return {
            "runs": len((await session.execute(select(AgentRun))).scalars().all()),
            "artifacts": len((await session.execute(select(TaskArtifact))).scalars().all()),
            "events": len((await session.execute(select(TaskEvent))).scalars().all()),
            "batches": len((await session.execute(select(DispatchBatch))).scalars().all()),
            "jobs": len((await session.execute(select(DispatchJob))).scalars().all()),
        }


async def _seed_agent_run(task: dict, *, status: str = "failed", error: str = "browser_ai_failed: selector password=private") -> AgentRun:
    async with get_session_factory()() as session:
        agent = AgentProfile(
            name="S20 seed",
            agent_type="reviewer",
            provider="browser_ai",
            model_name="chatgpt_web",
            enabled=True,
        )
        session.add(agent)
        await session.flush()
        run = AgentRun(
            task_id=task["id"],
            project_id=task["project_id"],
            agent_id=agent.id,
            run_type="review",
            status=status,
            input_prompt="seed prompt",
            output_summary="stdout summary",
            output_log="stdout log token=hidden",
            raw_result_json=json.dumps({"stderr": "stderr token=hidden", "blocked_reasons": ["detect_login"]}),
            error_message=error,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return run


async def _seed_artifact(task: dict, *, artifact_type: str = "patch_apply_report", content: str | None = None) -> TaskArtifact:
    async with get_session_factory()() as session:
        artifact = TaskArtifact(
            task_id=task["id"],
            artifact_type=artifact_type,
            filename="sandbox_run_1_report.json",
            content=content or json.dumps({
                "stdout": "apply stdout",
                "stderr": "sandbox gate stderr api_key=secret",
                "blocked_reasons": [{"reason": "risk_too_high"}],
            }),
            metadata_json=json.dumps({"failed_command_summary": "pytest backend/tests/test_x.py"}),
        )
        session.add(artifact)
        await session.commit()
        await session.refresh(artifact)
        return artifact


async def _seed_event(task: dict) -> TaskEvent:
    async with get_session_factory()() as session:
        event = TaskEvent(
            task_id=task["id"],
            event_type="sandbox_gate_blocked",
            actor="sandbox_gate",
            message="Sandbox gate blocked",
            payload_json=json.dumps({"blocked_reasons": [{"reason": "manual_review_required"}]}),
        )
        session.add(event)
        await session.commit()
        await session.refresh(event)
        return event


async def _seed_evidence_batch(task: dict, *, status: str = "partial") -> tuple[DispatchBatch, DispatchJob]:
    async with get_session_factory()() as session:
        batch = DispatchBatch(
            task_id=task["id"],
            batch_mode="broadcast",
            status=status,
            task_goal="multi_ai_evidence_partial analysis prompt",
            metadata_json=json.dumps({"type": "multi_ai_evidence_run"}),
        )
        session.add(batch)
        await session.flush()
        job = DispatchJob(
            batch_id=batch.id,
            task_id=task["id"],
            sequence_no=1,
            question="browser ai failed job question",
            provider="claude_web",
            model="claude_web",
            mode="broadcast",
            status="failed",
            error_message="selector failed password=private",
            metadata_json=json.dumps({"type": "multi_ai_evidence_job", "blocked_reasons": ["selector_failed"]}),
        )
        session.add(job)
        await session.commit()
        await session.refresh(batch)
        await session.refresh(job)
        return batch, job


def _body(task: dict, failure_type: str, source: dict | None = None, max_chars: int = 4000) -> dict:
    return {
        "task_id": task["id"],
        "failure_type": failure_type,
        "source": source or {},
        "max_excerpt_chars": max_chars,
    }


@pytest.mark.asyncio
async def test_preview_sandbox_gate_blocked_from_existing_records(client, task):
    await _seed_event(task)
    artifact = await _seed_artifact(task)
    before = await _counts()

    response = await client.post(BASE, json=_body(task, "sandbox_gate_blocked", {"artifact_id": artifact.id}))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["task_id"] == task["id"]
    assert data["project_id"] == task["project_id"]
    assert data["failure_type"] == "sandbox_gate_blocked"
    assert data["failed_step"] == "sandbox_gate"
    assert "pytest backend/tests/test_x.py" in data["failed_command_summary"]
    assert "apply stdout" in data["stdout_excerpt"]
    assert "sandbox gate stderr" in data["stderr_excerpt"]
    assert "risk_too_high" in data["blocked_reasons"]
    assert data["related_artifact_ids"] == [artifact.id]
    assert data["read_only"] is True
    assert data["persisted"] is False
    assert await _counts() == before


@pytest.mark.asyncio
async def test_preview_browser_ai_failed_from_agent_run(client, task):
    run = await _seed_agent_run(task)

    response = await client.post(BASE, json=_body(task, "browser_ai_failed", {"agent_run_id": run.id}))

    data = response.json()["data"]
    assert data["failed_step"] == "browser_ai"
    assert data["related_agent_run_ids"] == [run.id]
    assert "stdout summary" in data["stdout_excerpt"]
    assert "detect_login" in data["blocked_reasons"]
    assert "browser_ai_failed" in data["blocked_reasons"][0]
    assert "private" not in json.dumps(data)
    assert "hidden" not in json.dumps(data)


@pytest.mark.asyncio
async def test_preview_multi_ai_evidence_partial_from_dispatch_batch(client, task):
    batch, job = await _seed_evidence_batch(task)

    response = await client.post(BASE, json=_body(task, "multi_ai_evidence_partial", {"dispatch_batch_id": batch.id}))

    data = response.json()["data"]
    assert data["failed_step"] == "multi_ai_evidence_run"
    assert data["related_dispatch_batch_id"] == batch.id
    assert data["related_dispatch_job_ids"] == [job.id]
    assert "selector_failed" in data["blocked_reasons"]
    assert "private" not in json.dumps(data)


@pytest.mark.asyncio
async def test_unknown_failure_type_blocked(client, task):
    response = await client.post(BASE, json=_body(task, "auto_fix_repository"))

    assert response.status_code == 400
    assert response.json()["detail"] == "unknown_failure_type"


@pytest.mark.asyncio
async def test_task_not_found(client):
    response = await client.post(BASE, json={
        "task_id": 9999,
        "failure_type": "verification_failed",
        "source": {},
        "max_excerpt_chars": 4000,
    })

    assert response.status_code == 404
    assert response.json()["detail"] == "task_not_found"


@pytest.mark.asyncio
async def test_preview_does_not_call_forbidden_surfaces(client, task, monkeypatch):
    await _seed_agent_run(task)
    before = await _counts()

    def fail(*args, **kwargs):
        raise AssertionError("forbidden surface")

    monkeypatch.setattr("pathlib.Path.glob", fail)
    monkeypatch.setattr("pathlib.Path.rglob", fail)
    monkeypatch.setattr("os.system", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(subprocess, "Popen", fail)
    monkeypatch.setattr("app.services.browser_ai_service.execute", fail)
    monkeypatch.setattr("app.services.browser_ai_service.dry_run", fail)

    response = await client.post(BASE, json=_body(task, "browser_ai_failed"))

    assert response.status_code == 200
    assert response.json()["data"]["persisted"] is False
    assert await _counts() == before


@pytest.mark.asyncio
async def test_secret_like_content_redacted_and_long_content_truncated(client, task):
    long_text = "password=private token=hidden " + "A" * 1000
    artifact = await _seed_artifact(task, artifact_type="execution_log", content=long_text)

    response = await client.post(BASE, json=_body(task, "verification_failed", {"artifact_id": artifact.id}, max_chars=300))

    data = response.json()["data"]
    payload = json.dumps(data)
    assert data["redaction_status"]["redaction_applied"] is True
    assert data["redaction_status"]["truncated"] is True
    assert data["redaction_status"]["max_chars"] == 300
    assert "...[truncated]" in data["stdout_excerpt"]
    assert "password=***REDACTED***" in payload
    assert "private" not in payload
    assert "hidden" not in payload


@pytest.mark.asyncio
async def test_response_contract_read_only_persisted_false_and_safety_notes(client, task):
    response = await client.post(BASE, json=_body(task, "sonar_failed"))

    data = response.json()["data"]
    assert data["read_only"] is True
    assert data["persisted"] is False
    assert data["source_commit_hint"] == "verify_current_master_before_acting"
    assert any("No provider call" in note for note in data["safety_notes"])
    assert any("Project.root_path is not scanned" in note for note in data["safety_notes"])

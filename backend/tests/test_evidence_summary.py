import json
import os
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


TIMELINE_URL = "/api/tasks/{task_id}/timeline"
BOARD_URL = "/api/tasks/{task_id}/evidence-board"


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
    project = (await client.post("/api/projects", json={"name": "s22-1-test", "root_path": "/must-not-read"})).json()["data"]
    return (await client.post("/api/tasks", json={
        "project_id": project["id"],
        "title": "S22.1 Evidence Summary",
        "description": "Read-only evidence aggregation.",
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


def _secret_fixture() -> str:
    return (
        ("api_" + "key") + "=secret-value "
        + ("pass" + "word") + "=private-value "
        + ("to" + "ken") + "=hidden-value "
        + ("cook" + "ie") + "=browser-value "
        + ("ses" + "sion") + "=session-value"
    )


def _artifact(task: dict, artifact_type: str, filename: str, content: str, metadata: dict) -> TaskArtifact:
    return TaskArtifact(
        task_id=task["id"],
        artifact_type=artifact_type,
        filename=filename,
        content=content,
        metadata_json=json.dumps(metadata),
    )


async def _seed_all_sources(task: dict) -> dict[str, int]:
    async with get_session_factory()() as session:
        agent = AgentProfile(
            name="Browser Evidence Agent",
            agent_type="browser_ai",
            provider="browser_ai",
            model_name="chatgpt_web",
            enabled=True,
        )
        session.add(agent)
        await session.flush()

        succeeded_run = AgentRun(
            task_id=task["id"],
            project_id=task["project_id"],
            agent_id=agent.id,
            run_type="reviewer",
            status="succeeded",
            input_prompt="review task",
            output_summary="Browser AI answer saved",
            raw_result_json=json.dumps({"provider": "browser_ai", "safety_notes": ["No repository writes."]}),
        )
        failed_run = AgentRun(
            task_id=task["id"],
            project_id=task["project_id"],
            agent_id=agent.id,
            run_type="tester",
            status="failed",
            input_prompt="test task",
            error_message="verification failed",
            risk_level="high",
        )
        session.add_all([succeeded_run, failed_run])
        await session.flush()

        event = TaskEvent(
            task_id=task["id"],
            event_type="sandbox_gate",
            actor="sandbox_gate",
            to_status="blocked",
            message="Sandbox gate blocked because tests failed",
            payload_json=json.dumps({"blocked_reasons": ["test_failed"], "safety_notes": ["No provider call."]}),
        )
        attempt = TaskEvent(
            task_id=task["id"],
            event_type="repair_attempt",
            actor="user",
            to_status="planned",
            message="Repair attempt planned",
            payload_json=json.dumps({
                "repair_attempt_id": None,
                "attempt_no": 1,
                "status": "planned",
                "executor": "codex",
                "repair_packet_artifact_id": None,
                "safety_notes": ["Timeline only."],
            }),
        )
        status_event = TaskEvent(
            task_id=task["id"],
            event_type="repair_attempt_status",
            actor="user",
            from_status="planned",
            to_status="handoff_created",
            message="Repair handoff created",
            payload_json=json.dumps({"repair_attempt_id": 0, "status": "handoff_created"}),
        )
        session.add_all([event, attempt, status_event])
        await session.flush()
        attempt_payload = json.loads(attempt.payload_json)
        attempt_payload["repair_attempt_id"] = attempt.id
        attempt.payload_json = json.dumps(attempt_payload)
        status_event.payload_json = json.dumps({"repair_attempt_id": attempt.id, "status": "handoff_created"})

        repair_packet = _artifact(
            task,
            "repair_packet",
            "repair_packet.json",
            json.dumps({
                "failure_summary": f"sandbox failed {_secret_fixture()}",
                "recommended_fix_strategy": "Make one narrow fix.",
                "safety_notes": ["Codex / OMX or user must execute repair."],
                "human_decision_required": True,
            }),
            {
                "type": "repair_packet",
                "status": "completed",
                "dispatch_batch_id": 0,
                "summary": "Repair packet summary",
                "human_decision_required": True,
            },
        )
        verification = _artifact(
            task,
            "verification_result",
            "verification_result.json",
            "verification imported",
            {"type": "verification_result", "status": "verification_passed", "repair_attempt_id": attempt.id},
        )
        browser = _artifact(
            task,
            "browser_ai_answer",
            "browser.md",
            "browser answer",
            {"type": "browser_ai_answer", "provider": "browser_ai", "role": "reviewer", "agent_run_id": succeeded_run.id},
        )
        generic = _artifact(
            task,
            "note",
            "note.txt",
            "generic artifact",
            {"summary": "Generic artifact summary"},
        )
        long_artifact = _artifact(
            task,
            "note",
            "long.txt",
            "x" * 2500,
            {"summary": "Long artifact"},
        )
        session.add_all([repair_packet, verification, browser, generic, long_artifact])
        await session.flush()

        batch = DispatchBatch(
            task_id=task["id"],
            batch_mode="broadcast",
            status="partial",
            task_goal="Collect repair analysis",
            metadata_json=json.dumps({"type": "multi_ai_evidence_run", "concurrency_limit": 2}),
            summary_json=json.dumps({"summary": "one provider failed"}),
        )
        session.add(batch)
        await session.flush()
        repair_packet.metadata_json = json.dumps({
            "type": "repair_packet",
            "status": "completed",
            "dispatch_batch_id": batch.id,
            "summary": "Repair packet summary",
            "human_decision_required": True,
        })
        job = DispatchJob(
            batch_id=batch.id,
            task_id=task["id"],
            sequence_no=1,
            question="Review backend risk",
            provider="chatgpt_web",
            model="web",
            mode="repair_reviewer",
            status="succeeded",
            agent_run_id=succeeded_run.id,
            artifact_ids_json=json.dumps([browser.id]),
            expected_artifact_type="browser_ai_answer",
            metadata_json=json.dumps({"type": "multi_ai_evidence_job", "role": "reviewer"}),
        )
        session.add(job)
        await session.commit()
        return {
            "attempt": attempt.id,
            "run": succeeded_run.id,
            "failed_run": failed_run.id,
            "repair_packet": repair_packet.id,
            "verification": verification.id,
            "browser": browser.id,
            "generic": generic.id,
            "batch": batch.id,
            "job": job.id,
        }


def _items_by_type(items: list[dict], item_type: str) -> list[dict]:
    return [item for item in items if item.get("type") == item_type or item.get("evidence_type") == item_type]


@pytest.mark.asyncio
async def test_timeline_and_evidence_board_task_not_found(client):
    timeline = await client.get(TIMELINE_URL.format(task_id=999999))
    board = await client.get(BOARD_URL.format(task_id=999999))

    assert timeline.status_code == 404
    assert timeline.json()["detail"] == "task_not_found"
    assert board.status_code == 404
    assert board.json()["detail"] == "task_not_found"


@pytest.mark.asyncio
async def test_timeline_aggregates_events_runs_artifacts_and_dispatch(client, task):
    ids = await _seed_all_sources(task)

    response = await client.get(TIMELINE_URL.format(task_id=task["id"]))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["read_only"] is True
    assert data["persisted"] is False
    item_types = {item["type"] for item in data["items"]}
    assert "task_created" in item_types
    assert "task_event" in item_types
    assert "ai_run_finished" in item_types
    assert "ai_run_failed" in item_types
    assert "browser_ai_answer_saved" in item_types
    assert "repair_packet_generated" in item_types
    assert "verification_result_imported" in item_types
    assert "repair_attempt_created" in item_types
    assert "repair_attempt_status_changed" in item_types
    assert "multi_ai_evidence_finished" in item_types
    assert any(item["linked_ids"]["dispatch_batch_id"] == ids["batch"] for item in data["items"])
    assert any(item["linked_ids"]["dispatch_job_id"] == ids["job"] for item in data["items"])
    assert any(item["linked_ids"]["repair_attempt_id"] == ids["attempt"] for item in data["items"])


@pytest.mark.asyncio
async def test_evidence_board_aggregates_expected_evidence_types_and_filters(client, task):
    ids = await _seed_all_sources(task)

    response = await client.get(BOARD_URL.format(task_id=task["id"]))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["read_only"] is True
    assert data["persisted"] is False
    evidence_types = {item["evidence_type"] for item in data["items"]}
    assert "task_event" in evidence_types
    assert "agent_run" in evidence_types
    assert "repair_packet" in evidence_types
    assert "verification_result" in evidence_types
    assert "browser_ai_answer" in evidence_types
    assert "artifact" in evidence_types
    assert "repair_attempt" in evidence_types
    assert "multi_ai_evidence" in evidence_types

    repair_items = _items_by_type(data["items"], "repair_packet")
    assert repair_items[0]["artifact_id"] == ids["repair_packet"]
    assert repair_items[0]["dispatch_batch_id"] == ids["batch"]
    assert repair_items[0]["status"] == "completed"

    filters = data["filters"]
    assert "repair_packet" in filters["evidence_type"]
    assert "multi_ai_evidence" in filters["evidence_type"]
    assert "repair_loop" in filters["source"]
    assert "completed" in filters["status"]
    assert "browser_ai" in filters["provider"]
    assert "reviewer" in filters["role"]


@pytest.mark.asyncio
async def test_evidence_board_redacts_and_truncates_raw_excerpt(client, task):
    await _seed_all_sources(task)

    response = await client.get(BOARD_URL.format(task_id=task["id"]))

    data = response.json()["data"]
    payload = json.dumps(data)
    assert "secret-value" not in payload
    assert "private-value" not in payload
    assert "hidden-value" not in payload
    assert "browser-value" not in payload
    assert "session-value" not in payload
    assert "***REDACTED***" in payload

    long_items = [item for item in data["items"] if item["summary"] == "Long artifact"]
    assert long_items
    assert long_items[0]["redaction_status"]["truncated"] is True
    assert long_items[0]["redaction_status"]["max_chars"] == 2000
    assert len(long_items[0]["raw_excerpt"]) < 2050


@pytest.mark.asyncio
async def test_evidence_summary_endpoints_do_not_write(client, task):
    await _seed_all_sources(task)
    before = await _counts()

    timeline = await client.get(TIMELINE_URL.format(task_id=task["id"]))
    board = await client.get(BOARD_URL.format(task_id=task["id"]))

    assert timeline.status_code == 200
    assert board.status_code == 200
    assert await _counts() == before


@pytest.mark.asyncio
async def test_evidence_summary_avoids_forbidden_surfaces(client, task, monkeypatch):
    await _seed_all_sources(task)

    def fail(*args, **kwargs):
        raise AssertionError("forbidden surface")

    monkeypatch.setattr("pathlib.Path.glob", fail)
    monkeypatch.setattr("pathlib.Path.rglob", fail)
    monkeypatch.setattr(os, "system", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(subprocess, "Popen", fail)
    monkeypatch.setattr("app.services.browser_ai_service.execute", fail)
    monkeypatch.setattr("app.services.ai_provider_service.dispatch_agent_run", fail)

    timeline = await client.get(TIMELINE_URL.format(task_id=task["id"]))
    board = await client.get(BOARD_URL.format(task_id=task["id"]))

    assert timeline.status_code == 200
    assert board.status_code == 200

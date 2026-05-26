import json
import os
import subprocess

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.database import Base, get_engine, get_session_factory
from app.main import app
from app.models.task_artifact import TaskArtifact
from app.models.task_event import TaskEvent


ATTEMPTS_BASE = "/api/repair-loop/attempts"


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
    project = (await client.post("/api/projects", json={"name": "s20-4-test", "root_path": "/must-not-read"})).json()["data"]
    return (await client.post("/api/tasks", json={
        "project_id": project["id"],
        "title": "S20.4 Repair Attempt Timeline",
        "description": "Track repair attempts without executing repair.",
    })).json()["data"]


async def _seed_artifact(task: dict, artifact_type: str = "repair_packet") -> int:
    content = {
        "task_id": task["id"],
        "project_id": task["project_id"],
        "failure_summary": "sandbox gate blocked",
        "suspected_root_causes": ["missing verification"],
        "evidence_by_source": [],
        "multi_ai_findings": [],
        "disagreements": [],
        "recommended_fix_strategy": "make one narrow fix",
        "files_likely_involved": [],
        "commands_to_verify": ["python -m pytest backend/tests/test_repair_loop_attempts.py -q --rootdir backend"],
        "risks": ["human review required"],
        "human_decision_required": True,
        "codex_handoff_prompt": "Read AGENTS.md.",
        "max_attempts": 1,
        "do_not_do": ["Do not auto merge.", "Do not auto deploy."],
        "repair_packet_artifact_id": None,
        "source_failure_type": "sandbox_gate_blocked",
        "source_artifact_ids": [],
        "source_agent_run_ids": [],
        "source_dispatch_batch_id": None,
        "source_dispatch_job_ids": [],
        "analysis_dispatch_batch_id": None,
        "analysis_status": "succeeded",
        "read_only": False,
        "persisted": True,
        "safety_notes": [],
    }
    async with get_session_factory()() as session:
        artifact = TaskArtifact(
            task_id=task["id"],
            artifact_type=artifact_type,
            filename=f"{artifact_type}.json",
            content=json.dumps(content),
            metadata_json=json.dumps({"type": artifact_type}),
        )
        session.add(artifact)
        await session.flush()
        content["repair_packet_artifact_id"] = artifact.id
        artifact.content = json.dumps(content)
        await session.commit()
        await session.refresh(artifact)
        return artifact.id


async def _seed_other_task(client, project_id: int) -> dict:
    return (await client.post("/api/tasks", json={
        "project_id": project_id,
        "title": "Other repair task",
        "description": "Artifact mismatch task.",
    })).json()["data"]


def _create_body(task: dict, repair_packet_id: int, **overrides) -> dict:
    body = {
        "task_id": task["id"],
        "executor": "codex",
        "failure_evidence_artifact_id": None,
        "repair_packet_artifact_id": repair_packet_id,
        "handoff_target": "codex",
        "summary": "Use Codex to apply the narrow repair from the repair packet.",
    }
    body.update(overrides)
    return body


async def _create_attempt(client, task: dict, repair_packet_id: int, **overrides) -> dict:
    response = await client.post(ATTEMPTS_BASE, json=_create_body(task, repair_packet_id, **overrides))
    assert response.status_code == 200
    return response.json()["data"]


async def _artifact_count(artifact_type: str) -> int:
    async with get_session_factory()() as session:
        result = await session.execute(select(TaskArtifact).where(TaskArtifact.artifact_type == artifact_type))
        return len(result.scalars().all())


@pytest.mark.asyncio
async def test_create_and_list_repair_attempt(client, task):
    repair_packet_id = await _seed_artifact(task)

    attempt = await _create_attempt(client, task, repair_packet_id)

    assert attempt["attempt_no"] == 1
    assert attempt["status"] == "planned"
    assert attempt["executor"] == "codex"
    assert attempt["handoff_target"] == "codex"
    assert attempt["repair_packet_artifact_id"] == repair_packet_id
    assert attempt["verification_result_artifact_ids"] == []
    assert attempt["read_only"] is False
    assert attempt["persisted"] is True
    assert any("Timeline only" in note for note in attempt["safety_notes"])

    listed = (await client.get(f"/api/tasks/{task['id']}/repair-attempts")).json()["data"]
    assert [item["repair_attempt_id"] for item in listed] == [attempt["repair_attempt_id"]]


@pytest.mark.asyncio
async def test_same_repair_packet_allows_only_one_active_attempt(client, task):
    repair_packet_id = await _seed_artifact(task)
    await _create_attempt(client, task, repair_packet_id)

    response = await client.post(ATTEMPTS_BASE, json=_create_body(task, repair_packet_id))

    assert response.status_code == 400
    assert response.json()["detail"] == "active_repair_attempt_exists_for_repair_packet"


@pytest.mark.asyncio
@pytest.mark.parametrize("field, value, expected_detail", [
    ("executor", "auto_bot", "invalid_repair_attempt_executor"),
    ("handoff_target", "auto_bot", "invalid_repair_handoff_target"),
])
async def test_create_attempt_blocks_invalid_executor_or_handoff(client, task, field, value, expected_detail):
    repair_packet_id = await _seed_artifact(task)

    response = await client.post(ATTEMPTS_BASE, json=_create_body(task, repair_packet_id, **{field: value}))

    assert response.status_code == 400
    assert response.json()["detail"] == expected_detail


@pytest.mark.asyncio
async def test_create_attempt_blocks_missing_or_mismatched_repair_packet(client, task):
    missing = await client.post(ATTEMPTS_BASE, json=_create_body(task, 999999))
    assert missing.status_code == 404
    assert missing.json()["detail"] == "repair_packet_artifact_not_found"

    other = await _seed_other_task(client, task["project_id"])
    other_packet_id = await _seed_artifact(other)
    mismatch = await client.post(ATTEMPTS_BASE, json=_create_body(task, other_packet_id))
    assert mismatch.status_code == 400
    assert mismatch.json()["detail"] == "artifact_task_mismatch"


@pytest.mark.asyncio
async def test_attempt_status_flow_and_verification_import(client, task):
    repair_packet_id = await _seed_artifact(task)
    attempt = await _create_attempt(client, task, repair_packet_id, executor="omx", handoff_target="omx")
    attempt_id = attempt["repair_attempt_id"]

    handoff = await client.post(f"{ATTEMPTS_BASE}/{attempt_id}/handoff-created")
    assert handoff.status_code == 200
    assert handoff.json()["data"]["status"] == "handoff_created"

    passed = await client.post(f"{ATTEMPTS_BASE}/{attempt_id}/verification-result", json={
        "status": "verification_passed",
        "summary": "targeted pytest passed; npm build passed",
        "commands": ["python -m pytest backend/tests/test_repair_loop_attempts.py -q --rootdir backend"],
        "artifact_content": "verification log excerpt",
    })
    passed_data = passed.json()["data"]
    assert passed.status_code == 200
    assert passed_data["status"] == "verification_passed"
    assert passed_data["verification_result_artifact_ids"]
    assert await _artifact_count("verification_result") == 1

    second_packet_id = await _seed_artifact(task)
    failed_attempt = await _create_attempt(client, task, second_packet_id, executor="user", handoff_target="user")
    failed = await client.post(f"{ATTEMPTS_BASE}/{failed_attempt['repair_attempt_id']}/verification-result", json={
        "status": "verification_failed",
        "summary": "frontend smoke failed",
        "commands": ["node frontend/tests/s4-display.cjs"],
        "artifact_content": "smoke failed excerpt",
    })
    assert failed.status_code == 200
    assert failed.json()["data"]["status"] == "verification_failed"


@pytest.mark.asyncio
async def test_stop_attempt_blocks_later_status_changes_and_no_auto_next_attempt(client, task):
    repair_packet_id = await _seed_artifact(task)
    attempt = await _create_attempt(client, task, repair_packet_id)
    attempt_id = attempt["repair_attempt_id"]

    stopped = await client.post(f"{ATTEMPTS_BASE}/{attempt_id}/stop")
    assert stopped.status_code == 200
    assert stopped.json()["data"]["status"] == "stopped"

    handoff = await client.post(f"{ATTEMPTS_BASE}/{attempt_id}/handoff-created")
    assert handoff.status_code == 400
    assert handoff.json()["detail"] == "repair_attempt_stopped"

    verification = await client.post(f"{ATTEMPTS_BASE}/{attempt_id}/verification-result", json={
        "status": "verification_passed",
        "summary": "should not import",
        "commands": [],
        "artifact_content": "",
    })
    assert verification.status_code == 400
    assert verification.json()["detail"] == "repair_attempt_stopped"

    listed = (await client.get(f"/api/tasks/{task['id']}/repair-attempts")).json()["data"]
    assert len(listed) == 1
    assert listed[0]["attempt_no"] == 1


@pytest.mark.asyncio
async def test_attempts_do_not_use_forbidden_surfaces(client, task, monkeypatch):
    repair_packet_id = await _seed_artifact(task)

    def fail(*args, **kwargs):
        raise AssertionError("forbidden surface")

    monkeypatch.setattr("pathlib.Path.glob", fail)
    monkeypatch.setattr("pathlib.Path.rglob", fail)
    monkeypatch.setattr(os, "system", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(subprocess, "Popen", fail)

    attempt = await _create_attempt(client, task, repair_packet_id, executor="generic_ai", handoff_target="generic_ai")
    imported = await client.post(f"{ATTEMPTS_BASE}/{attempt['repair_attempt_id']}/verification-result", json={
        "status": "verification_failed",
        "summary": "imported only",
        "commands": ["not executed by platform"],
        "artifact_content": "manual verification result",
    })

    assert imported.status_code == 200
    assert await _artifact_count("verification_result") == 1

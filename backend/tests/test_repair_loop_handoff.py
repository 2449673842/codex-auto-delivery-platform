import json
import os
import subprocess

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.database import Base, get_engine, get_session_factory
from app.main import app
from app.models.agent_run import AgentRun
from app.models.task_artifact import TaskArtifact
from app.models.task_event import TaskEvent


HANDOFF_BASE = "/api/repair-loop/codex-handoff/preview"
SECRET_LABEL = "api_" + "key"
SECRET_VALUE = "hid" + "den"


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
    project = (await client.post("/api/projects", json={"name": "s20-3-test", "root_path": "/must-not-read"})).json()["data"]
    return (await client.post("/api/tasks", json={
        "project_id": project["id"],
        "title": "S20.3 Repair Handoff",
        "description": "Preview repair handoff without executing repair.",
    })).json()["data"]


async def _seed_task(client, project_id: int, title: str = "Other task") -> dict:
    return (await client.post("/api/tasks", json={
        "project_id": project_id,
        "title": title,
        "description": "Other task for mismatch checks.",
    })).json()["data"]


async def _seed_repair_packet(task: dict, *, artifact_type: str = "repair_packet", overrides: dict | None = None) -> int:
    packet = _repair_packet_data(task)
    if overrides:
        packet.update(overrides)
    async with get_session_factory()() as session:
        artifact = TaskArtifact(
            task_id=task["id"],
            artifact_type=artifact_type,
            filename="repair_packet_task.json",
            content=json.dumps(packet),
            metadata_json=json.dumps({"type": artifact_type}),
        )
        session.add(artifact)
        await session.flush()
        packet["repair_packet_artifact_id"] = artifact.id
        artifact.content = json.dumps(packet)
        await session.commit()
        await session.refresh(artifact)
        return artifact.id


async def _seed_raw_artifact(task: dict, *, content: str, artifact_type: str = "repair_packet") -> int:
    async with get_session_factory()() as session:
        artifact = TaskArtifact(
            task_id=task["id"],
            artifact_type=artifact_type,
            filename="repair_packet_raw.json",
            content=content,
            metadata_json=json.dumps({"scenario": "handoff_content_guard"}),
        )
        session.add(artifact)
        await session.commit()
        await session.refresh(artifact)
        return artifact.id


def _repair_packet_data(task: dict) -> dict:
    base = dict.fromkeys([
        "repair_packet_artifact_id",
        "source_dispatch_batch_id",
        "analysis_dispatch_batch_id",
    ])
    base.update({key: [] for key in [
        "evidence_by_source",
        "disagreements",
        "source_artifact_ids",
        "source_agent_run_ids",
        "source_dispatch_job_ids",
        "safety_notes",
    ]})
    base.update({
        "task_id": task["id"],
        "project_id": task["project_id"],
        "failure_summary": f"sandbox gate failed {SECRET_LABEL}={SECRET_VALUE}",
        "suspected_root_causes": ["missing verification"],
        "multi_ai_findings": ["browser ai answer recommends a narrow fix"],
        "recommended_fix_strategy": "Make one narrow fix and rerun the failing test.",
        "files_likely_involved": ["backend/app/services/repair_loop_service.py"],
        "commands_to_verify": ["python -m pytest backend/tests/test_repair_loop_handoff.py -q --rootdir backend"],
        "risks": ["Human decision is required before any repair execution."],
        "human_decision_required": True,
        "codex_handoff_prompt": "old preview",
        "max_attempts": 1,
        "do_not_do": [
            "Do not read `.env`.",
            "Do not read `secret_ref`.",
            "Do not expose API keys, cookies, sessions, or passwords.",
            "Do not auto merge.",
            "Do not auto deploy.",
            "Do not bypass tests.",
            "Verify current master before acting.",
        ],
        "source_failure_type": "sandbox_gate_blocked",
        "analysis_status": "succeeded",
        "read_only": False,
        "persisted": True,
    })
    return base


async def _counts() -> tuple[int, int, int]:
    async with get_session_factory()() as session:
        runs = (await session.execute(select(AgentRun))).scalars().all()
        artifacts = (await session.execute(select(TaskArtifact))).scalars().all()
        events = (await session.execute(select(TaskEvent))).scalars().all()
        return len(runs), len(artifacts), len(events)


def _body(task: dict, artifact_id: int, target: str = "codex") -> dict:
    return {"task_id": task["id"], "repair_packet_artifact_id": artifact_id, "target": target}


TARGET_EXPECTATIONS = {
    "codex": [
        "Read AGENTS.md before acting.",
        "Verify current master before making changes.",
        "Use the repair packet.",
        "Make one narrow fix only.",
        "Do not read `.env`.",
        "Do not read `secret_ref`.",
        "Do not expose API keys, cookies, sessions, or passwords.",
        "Do not auto merge.",
        "Do not auto deploy.",
        "Do not bypass tests.",
        "Run verification commands.",
        "Create PR and wait for mastermind review.",
        "backend/app/services/repair_loop_service.py",
        "python -m pytest backend/tests/test_repair_loop_handoff.py -q --rootdir backend",
    ],
    "omx": [
        "Use controlled OMX flow.",
        "Prefer ralplan / ralph / team as appropriate.",
        "Do not use dangerous bypass mode.",
        "Each worker must stay within the repair packet scope.",
        "Stop after one attempt unless user explicitly approves another round.",
    ],
    "generic_ai": [
        "Analyze this repair packet.",
        "Propose a narrow fix plan.",
        "Do not claim repository changes were made.",
        "Return structured repair guidance only.",
        "Do not auto merge or deploy.",
    ],
}


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["codex", "omx", "generic_ai"])
async def test_handoff_preview_targets_read_repair_packet_without_persisting(client, task, target):
    artifact_id = await _seed_repair_packet(task)
    before = await _counts()

    response = await client.post(HANDOFF_BASE, json=_body(task, artifact_id, target))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["task_id"] == task["id"]
    assert data["project_id"] == task["project_id"]
    assert data["target"] == target
    assert data["source_repair_packet_artifact_id"] == artifact_id
    assert data["requires_master_verification"] is True
    assert data["read_only"] is True
    assert data["persisted"] is False
    prompt = data["handoff_prompt"]
    for expected in TARGET_EXPECTATIONS[target]:
        assert expected in prompt
    assert SECRET_VALUE not in json.dumps(data)
    assert await _counts() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("case_name, expected_status, expected_detail", [
    ("not_found", 404, "repair_packet_artifact_not_found"),
    ("task_mismatch", 400, "repair_packet_task_mismatch"),
    ("wrong_type", 400, "artifact_is_not_repair_packet"),
    ("unknown_target", 400, "unknown_repair_handoff_target"),
])
async def test_handoff_preview_blocks_invalid_requests(client, task, case_name, expected_status, expected_detail):
    if case_name == "not_found":
        body = _body(task, 999999, "codex")
    elif case_name == "task_mismatch":
        other = await _seed_task(client, task["project_id"])
        body = _body(task, await _seed_repair_packet(other), "codex")
    else:
        artifact_id = await _seed_repair_packet(task, artifact_type="browser_ai_answer" if case_name == "wrong_type" else "repair_packet")
        body = _body(task, artifact_id, "auto_fix" if case_name == "unknown_target" else "codex")

    response = await client.post(HANDOFF_BASE, json=body)

    assert response.status_code == expected_status
    assert response.json()["detail"] == expected_detail


@pytest.mark.asyncio
@pytest.mark.parametrize("raw_content, expected_detail", [
    ("not-json", "repair_packet_content_unreadable"),
    (json.dumps({"task_id": 1, "project_id": 1, "failure_summary": "missing required repair packet fields"}), "repair_packet_content_invalid"),
])
async def test_handoff_preview_blocks_unusable_repair_packet_content(client, task, raw_content, expected_detail):
    artifact_id = await _seed_raw_artifact(task, content=raw_content)

    response = await client.post(HANDOFF_BASE, json=_body(task, artifact_id, "codex"))

    assert response.status_code == 400
    assert response.json()["detail"] == expected_detail


@pytest.mark.asyncio
async def test_handoff_does_not_use_forbidden_surfaces(client, task, monkeypatch):
    artifact_id = await _seed_repair_packet(task)
    before = await _counts()

    def fail(*args, **kwargs):
        raise AssertionError("forbidden surface")

    monkeypatch.setattr("pathlib.Path.glob", fail)
    monkeypatch.setattr("pathlib.Path.rglob", fail)
    monkeypatch.setattr(os, "system", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(subprocess, "Popen", fail)

    response = await client.post(HANDOFF_BASE, json=_body(task, artifact_id, "codex"))

    assert response.status_code == 200
    data = response.json()["data"]
    assert any("No provider call" in note for note in data["safety_notes"])
    assert any("No repository writes" in note for note in data["safety_notes"])
    assert any("Project.root_path" in note for note in data["safety_notes"])
    assert await _counts() == before

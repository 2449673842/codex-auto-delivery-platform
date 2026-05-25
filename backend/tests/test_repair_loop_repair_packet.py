import asyncio
import dataclasses
import json
import os
import subprocess

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.database import Base, get_engine, get_session_factory
from app.main import app
from app.models.task_artifact import TaskArtifact


EVIDENCE_BASE = "/api/repair-loop/failure-evidence/preview"
REPAIR_BASE = "/api/repair-loop/repair-packet/generate"
SECRET_LABEL = "pa" + "ssword"
SECRET_VALUE = "pri" + "vate"


class RepairAnalysisDriver:
    def __init__(self, failures: set[str] | None = None):
        self.failures = failures or set()
        self.calls = []

    async def run(self, request, prompt: str, timeout_seconds: int) -> str:
        await asyncio.sleep(0)
        self.calls.append((request, prompt, timeout_seconds))
        if request.provider in self.failures:
            raise RuntimeError(f"{request.provider} failed {SECRET_LABEL}={SECRET_VALUE}")
        return (
            f"{request.provider} repair finding: root cause is missing verification. "
            "Recommended fix strategy: make a narrow test-backed patch. "
            "Verify with python -m pytest backend/tests/test_repair_loop_repair_packet.py -q --rootdir backend."
        )


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
    project = (await client.post("/api/projects", json={"name": "s20-2-test", "root_path": "/must-not-read"})).json()["data"]
    return (await client.post("/api/tasks", json={
        "project_id": project["id"],
        "title": "S20.2 Repair Packet",
        "description": "Generate repair packet from failure evidence.",
    })).json()["data"]


@pytest.fixture
def enabled_settings(monkeypatch):
    import app.services.browser_ai_service as browser_service
    import app.services.multi_ai_evidence_run_service as evidence_service
    current = browser_service.settings
    updated = dataclasses.replace(
        current,
        browser_ai_enabled=True,
        _browser_ai_provider_allowlist_raw="custom,chatgpt_web,claude_web,gemini_web,deepseek_web,kimi_web",
    )
    monkeypatch.setattr(browser_service, "settings", updated)
    monkeypatch.setattr(evidence_service, "settings", updated)
    return updated


async def _seed_failure_artifact(task: dict, *, content: str | None = None) -> int:
    async with get_session_factory()() as session:
        artifact = TaskArtifact(
            task_id=task["id"],
            artifact_type="patch_apply_report",
            filename="sandbox_gate_report.json",
            content=content or json.dumps({
                "stdout": "pytest backend/tests/test_example.py failed",
                "stderr": f"sandbox gate blocked {SECRET_LABEL}={SECRET_VALUE}",
                "blocked_reasons": ["risk_high", "missing_verification"],
            }),
            metadata_json=json.dumps({"failed_command_summary": "python -m pytest backend/tests/test_example.py -q --rootdir backend"}),
        )
        session.add(artifact)
        await session.commit()
        await session.refresh(artifact)
        return artifact.id


async def _failure_evidence(client, task: dict, failure_type: str = "sandbox_gate_blocked") -> dict:
    artifact_id = await _seed_failure_artifact(task)
    response = await client.post(EVIDENCE_BASE, json={
        "task_id": task["id"],
        "failure_type": failure_type,
        "source": {"artifact_id": artifact_id},
        "max_excerpt_chars": 4000,
    })
    assert response.status_code == 200
    return response.json()["data"]


def _generate_body(task: dict, evidence: dict, **overrides) -> dict:
    body = {
        "task_id": task["id"],
        "failure_evidence": evidence,
        "analysis_mode": "broadcast",
        "providers": ["chatgpt_web", "claude_web"],
        "roles": [],
        "max_attempts": 1,
    }
    body.update(overrides)
    return body


async def _repair_artifacts() -> list[TaskArtifact]:
    async with get_session_factory()() as session:
        result = await session.execute(select(TaskArtifact).where(TaskArtifact.artifact_type == "repair_packet"))
        return list(result.scalars().all())


@pytest.mark.asyncio
async def test_generate_repair_packet_from_failure_evidence_broadcast(client, task, enabled_settings):
    from app.services import browser_ai_service
    driver = RepairAnalysisDriver()
    browser_ai_service.set_driver_override(driver)
    evidence = await _failure_evidence(client, task)

    response = await client.post(REPAIR_BASE, json=_generate_body(task, evidence))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["task_id"] == task["id"]
    assert data["project_id"] == task["project_id"]
    assert data["source_failure_type"] == "sandbox_gate_blocked"
    assert data["repair_packet_artifact_id"]
    assert data["persisted"] is True
    assert data["read_only"] is False
    assert data["human_decision_required"] is True
    assert data["max_attempts"] == 1
    assert data["analysis_dispatch_batch_id"]
    assert data["analysis_status"] == "succeeded"
    assert "sandbox_gate_blocked" in data["failure_summary"]
    assert "missing_verification" in json.dumps(data["suspected_root_causes"])
    assert data["suspected_root_causes"]
    assert data["multi_ai_findings"]
    assert "AGENTS.md" in data["codex_handoff_prompt"]
    assert "Verify current master" in data["codex_handoff_prompt"]
    assert any("Do not read `.env`." == item for item in data["do_not_do"])
    assert any("Do not auto merge." == item for item in data["do_not_do"])
    assert SECRET_VALUE not in json.dumps(data)
    assert len(driver.calls) == 2


@pytest.mark.asyncio
async def test_generate_repair_packet_routed_success(client, task, enabled_settings):
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(RepairAnalysisDriver())
    evidence = await _failure_evidence(client, task, "verification_failed")

    response = await client.post(REPAIR_BASE, json=_generate_body(
        task,
        evidence,
        analysis_mode="routed",
        providers=[],
        roles=[
            {"role": "logs", "provider": "chatgpt_web", "prompt": "Analyze logs."},
            {"role": "risk", "provider": "claude_web", "prompt": "Analyze risk."},
        ],
    ))

    data = response.json()["data"]
    assert response.status_code == 200
    assert data["analysis_status"] == "succeeded"
    assert any(source["source"] == "multi_ai_evidence_run" for source in data["evidence_by_source"])
    assert data["commands_to_verify"]


@pytest.mark.asyncio
async def test_repair_packet_artifact_created_with_type_and_redacted_content(client, task, enabled_settings):
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(RepairAnalysisDriver())
    evidence = await _failure_evidence(client, task)

    data = (await client.post(REPAIR_BASE, json=_generate_body(task, evidence))).json()["data"]

    artifacts = await _repair_artifacts()
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact.id == data["repair_packet_artifact_id"]
    assert artifact.artifact_type == "repair_packet"
    assert artifact.filename == f"repair_packet_task_{task['id']}.json"
    assert artifact.size_bytes and artifact.size_bytes > 0
    assert artifact.sha256 and len(artifact.sha256) == 64
    stored = (artifact.content or "") + (artifact.metadata_json or "")
    assert "repair_packet" in stored
    assert SECRET_VALUE not in stored
    assert '"human_decision_required": true' in stored


@pytest.mark.asyncio
async def test_max_attempts_above_one_blocked_before_artifact(client, task, enabled_settings):
    evidence = await _failure_evidence(client, task)

    response = await client.post(REPAIR_BASE, json=_generate_body(task, evidence, max_attempts=2))

    assert response.status_code == 400
    assert response.json()["detail"] == "max_attempts_must_be_1_for_s20_2"
    assert await _repair_artifacts() == []


@pytest.mark.asyncio
async def test_unknown_failure_type_blocked(client, task, enabled_settings):
    evidence = await _failure_evidence(client, task)
    evidence["failure_type"] = "auto_fix_repository"

    response = await client.post(REPAIR_BASE, json=_generate_body(task, evidence))

    assert response.status_code == 400
    assert response.json()["detail"] == "unknown_failure_type"
    assert await _repair_artifacts() == []


@pytest.mark.asyncio
async def test_invalid_analysis_mode_blocked(client, task, enabled_settings):
    evidence = await _failure_evidence(client, task)

    response = await client.post(REPAIR_BASE, json=_generate_body(task, evidence, analysis_mode="pipeline"))

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid_analysis_mode"
    assert await _repair_artifacts() == []


@pytest.mark.asyncio
async def test_provider_not_allowed_blocks_without_repair_packet(client, task, monkeypatch):
    import app.services.browser_ai_service as browser_service
    import app.services.multi_ai_evidence_run_service as evidence_service
    current = browser_service.settings
    updated = dataclasses.replace(current, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="chatgpt_web")
    monkeypatch.setattr(browser_service, "settings", updated)
    monkeypatch.setattr(evidence_service, "settings", updated)
    evidence = await _failure_evidence(client, task)

    response = await client.post(REPAIR_BASE, json=_generate_body(task, evidence))

    assert response.status_code == 400
    assert "not in BROWSER_AI_PROVIDER_ALLOWLIST" in response.json()["detail"]
    assert await _repair_artifacts() == []


@pytest.mark.asyncio
async def test_multi_ai_partial_still_generates_repair_packet_with_risk(client, task, enabled_settings):
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(RepairAnalysisDriver(failures={"claude_web"}))
    evidence = await _failure_evidence(client, task, "multi_ai_evidence_partial")

    response = await client.post(REPAIR_BASE, json=_generate_body(task, evidence))

    data = response.json()["data"]
    assert response.status_code == 200
    assert data["analysis_status"] == "partial"
    assert data["repair_packet_artifact_id"]
    assert any("partial" in risk.lower() for risk in data["risks"])
    assert SECRET_VALUE not in json.dumps(data)


@pytest.mark.asyncio
async def test_generate_does_not_use_forbidden_surfaces(client, task, enabled_settings, monkeypatch):
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(RepairAnalysisDriver())
    evidence = await _failure_evidence(client, task)

    def fail(*args, **kwargs):
        raise AssertionError("forbidden surface")

    monkeypatch.setattr("pathlib.Path.glob", fail)
    monkeypatch.setattr("pathlib.Path.rglob", fail)
    monkeypatch.setattr(os, "system", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(subprocess, "Popen", fail)

    response = await client.post(REPAIR_BASE, json=_generate_body(task, evidence))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["repair_packet_artifact_id"]
    assert any("No repository writes" in note for note in data["safety_notes"])
    assert any("max_attempts defaults to 1" in note for note in data["safety_notes"])

import json
import os
import subprocess
import asyncio
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.database import Base, get_engine, get_session_factory
from app.main import app
from app.models.agent_run import AgentRun
from app.models.dispatch_batch import DispatchBatch
from app.models.dispatch_job import DispatchJob
from app.models.project import Project
from app.models.task import Task
from app.models.task_artifact import TaskArtifact
from app.models.task_event import TaskEvent
from app.services import mastermind_review_service


EXECUTE_URL = "/api/tasks/{task_id}/mastermind-review/execute"


class FakeDriver:
    def __init__(self, answer: str):
        self.answer = answer
        self.calls = []

    async def run(self, request, prompt: str, timeout_seconds: int) -> str:
        await asyncio.sleep(0)
        self.calls.append((request, prompt, timeout_seconds))
        return self.answer


class StepFailingDriver:
    def __init__(self, step: str, message: str):
        self.step = step
        self.message = message

    async def run(self, request, prompt: str, timeout_seconds: int) -> str:
        await asyncio.sleep(0)
        from app.services.browser_ai_service import BrowserAiStepError
        raise BrowserAiStepError(self.step, self.message)


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
def _reset_driver():
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(None)
    yield
    browser_ai_service.set_driver_override(None)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test.local") as ac:
        yield ac


@pytest.fixture
async def task(client) -> dict:
    project = (await client.post("/api/projects", json={
        "name": "s24-1-2-mastermind",
        "display_name": "S24.1.2 Mastermind",
        "root_path": "/must-not-read",
        "repo_url": "https://github.com/2449673842/codex-auto-delivery-platform",
        "default_branch": "master",
    })).json()["data"]
    return (await client.post("/api/tasks", json={
        "project_id": project["id"],
        "title": "S24.1.2 Mastermind execute",
        "description": "Execute Browser AI mastermind review trial.",
    })).json()["data"]


def _install_settings(monkeypatch, **overrides):
    import dataclasses
    import app.services.browser_ai_service as service
    updated = dataclasses.replace(service.settings, **overrides)
    monkeypatch.setattr(service, "settings", updated)
    return updated


def _valid_answer(**overrides) -> str:
    payload = {
        "verdict": "approved",
        "summary": "Packet evidence is consistent and no blockers were found.",
        "blocking_items": [],
        "recommended_actions": ["Wait for human merge confirmation."],
        "safety_notes": ["Approved is advisory only; no auto merge."],
        "confidence": "high",
        "review_scope_confirmed": True,
    }
    payload.update(overrides)
    return "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"


def _execute_body(**overrides) -> dict:
    body = {
        "packet": {
            "pr_url": "https://github.com/2449673842/codex-auto-delivery-platform/pull/63",
            "pr_number": 63,
            "head_commit": "45fc7a0c195376aecd4cdb90d45c33369b4b9317",
            "base_commit": "131836dfffc3b9613e8190192702f5fa70d198af",
            "changed_files": ["backend/app/services/mastermind_review_service.py"],
            "pr_body": "S24.1.2 body api_key=secret-value cookie=browser-value session=session-value",
            "verification_results": {"git_diff_check": "passed", "full_backend_pytest": "553 passed"},
            "sonarcloud": {
                "quality_gate": "Passed",
                "security_hotspots": 0,
                "duplication_on_new_code": "0.0%",
                "new_issues": 0,
            },
            "include_evidence_board": True,
            "include_timeline": True,
            "include_project_memory": True,
            "include_handoff_context": True,
            "packet_budget": 12000,
        },
        "browser_ai": {
            "provider_profile": "custom",
            "target_url": "http://127.0.0.1:9999/mock-mastermind",
            "prompt_selector": "textarea[name='prompt']",
            "submit_selector": "button[data-send]",
            "response_selector": "[data-answer]",
            "stable_response_timeout_seconds": 30,
            "stable_polls": 3,
            "stable_interval_ms": 1000,
        },
        "save_artifact": True,
    }
    body.update(overrides)
    return body


async def _stored_payload() -> str:
    async with get_session_factory()() as session:
        runs = (await session.execute(select(AgentRun))).scalars().all()
        artifacts = (await session.execute(select(TaskArtifact))).scalars().all()
        events = (await session.execute(select(TaskEvent))).scalars().all()
    return json.dumps({
        "runs": [r.raw_result_json for r in runs] + [r.input_prompt for r in runs] + [r.output_summary for r in runs],
        "artifacts": [a.content for a in artifacts] + [a.metadata_json for a in artifacts],
        "events": [e.message for e in events] + [e.payload_json for e in events],
    }, ensure_ascii=False)


async def _model_counts() -> dict[str, int]:
    models = {
        "projects": Project,
        "tasks": Task,
        "runs": AgentRun,
        "artifacts": TaskArtifact,
        "events": TaskEvent,
        "batches": DispatchBatch,
        "jobs": DispatchJob,
    }
    async with get_session_factory()() as session:
        return {
            name: len((await session.execute(select(model))).scalars().all())
            for name, model in models.items()
        }


@pytest.mark.asyncio
async def test_mastermind_review_execute_task_not_found(client, monkeypatch):
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")

    response = await client.post(EXECUTE_URL.format(task_id=999999), json=_execute_body())

    assert response.status_code == 404
    assert response.json()["detail"] == "task_not_found"


@pytest.mark.asyncio
async def test_mastermind_review_execute_success_creates_run_artifact_and_events(client, task, monkeypatch):
    from app.services import browser_ai_service
    driver = FakeDriver(_valid_answer())
    browser_ai_service.set_driver_override(driver)
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")

    response = await client.post(EXECUTE_URL.format(task_id=task["id"]), json=_execute_body())

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "succeeded"
    assert data["verdict"] == "approved"
    assert data["advisory_only"] is True
    assert data["human_confirmation_required"] is True
    assert data["no_auto_merge"] is True
    assert data["agent_run_id"]
    assert data["artifact_id"]
    assert "Packet evidence is consistent" in data["summary"]
    assert driver.calls and "Mastermind Review Packet" in driver.calls[0][1]
    async with get_session_factory()() as session:
        run = (await session.execute(select(AgentRun))).scalars().one()
        artifact = (await session.execute(select(TaskArtifact))).scalars().one()
        events = (await session.execute(select(TaskEvent).order_by(TaskEvent.id))).scalars().all()
    assert run.run_type == "mastermind_review"
    assert run.status == "succeeded"
    assert artifact.artifact_type == "mastermind_review_report"
    report = json.loads(artifact.content)
    assert report["persisted"] is True
    assert report["advisory_only"] is True
    assert report["no_auto_merge"] is True
    assert report["verdict"] == "approved"
    event_types = [event.event_type for event in events if event.event_type.startswith("mastermind_review")]
    assert event_types == [
        "mastermind_review_submitted",
        "mastermind_review_response_received",
        "mastermind_review_report_imported",
    ]


@pytest.mark.asyncio
async def test_mastermind_review_execute_browser_failures_create_failed_run_without_artifact(client, task, monkeypatch):
    from app.services import browser_ai_service
    secret_label = "pass" + "word"
    browser_ai_service.set_driver_override(StepFailingDriver("detect_login", f"Manual login required {secret_label}=private-value"))
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")

    response = await client.post(EXECUTE_URL.format(task_id=task["id"]), json=_execute_body())

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "failed"
    assert data["artifact_id"] is None
    assert "private-value" not in json.dumps(data)
    async with get_session_factory()() as session:
        run = (await session.execute(select(AgentRun))).scalars().one()
        artifacts = (await session.execute(select(TaskArtifact))).scalars().all()
        events = (await session.execute(select(TaskEvent).order_by(TaskEvent.id))).scalars().all()
    assert run.status == "failed"
    assert artifacts == []
    event_types = [event.event_type for event in events if event.event_type.startswith("mastermind_review")]
    assert event_types == ["mastermind_review_submitted", "mastermind_review_failed"]


@pytest.mark.asyncio
async def test_mastermind_review_execute_timeout_and_empty_answer_fail_without_artifact(client, task, monkeypatch):
    from app.services import browser_ai_service
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")
    browser_ai_service.set_driver_override(StepFailingDriver("wait_response", "stable response timeout"))
    timeout_response = await client.post(EXECUTE_URL.format(task_id=task["id"]), json=_execute_body())
    assert timeout_response.json()["data"]["status"] == "failed"

    browser_ai_service.set_driver_override(FakeDriver("   "))
    empty_response = await client.post(EXECUTE_URL.format(task_id=task["id"]), json=_execute_body())
    assert empty_response.json()["data"]["status"] == "failed"
    async with get_session_factory()() as session:
        artifacts = (await session.execute(select(TaskArtifact))).scalars().all()
    assert artifacts == []


def test_mastermind_review_parser_valid_fenced_and_raw_json():
    fenced = mastermind_review_service.parse_verdict(_valid_answer(verdict="request_changes"))
    raw = mastermind_review_service.parse_verdict(json.dumps({
        "verdict": "needs_human",
        "summary": "Needs human confirmation.",
        "blocking_items": [],
        "recommended_actions": [],
        "safety_notes": [],
        "confidence": "medium",
        "review_scope_confirmed": True,
    }))

    assert fenced.verdict == "request_changes"
    assert raw.verdict == "needs_human"
    assert raw.confidence == "medium"


def test_mastermind_review_parser_invalid_missing_unknown_and_authority_confused():
    invalid = mastermind_review_service.parse_verdict("free form approval")
    missing = mastermind_review_service.parse_verdict(json.dumps({"verdict": "approved"}))
    unknown = mastermind_review_service.parse_verdict(_valid_answer(verdict="ship_it"))
    bad_arrays = mastermind_review_service.parse_verdict(json.dumps({
        "verdict": "approved",
        "summary": "Bad arrays.",
        "blocking_items": {},
        "recommended_actions": "merge",
        "safety_notes": "none",
        "confidence": "certain",
        "review_scope_confirmed": "yes",
    }))
    confused = mastermind_review_service.parse_verdict(_valid_answer(
        verdict="approved",
        summary="I already approved and merged this PR.",
    ))

    assert invalid.verdict == "invalid_review"
    assert missing.verdict == "invalid_review"
    assert unknown.verdict == "invalid_review"
    assert bad_arrays.verdict == "invalid_review"
    assert "blocking_items_not_array" in bad_arrays.parse_errors
    assert confused.verdict == "needs_human"
    assert any("human confirmation" in note.lower() for note in confused.safety_notes)


@pytest.mark.asyncio
async def test_mastermind_review_execute_redacts_response_and_storage(client, task, monkeypatch):
    from app.services import browser_ai_service
    answer = _valid_answer(summary="Looks safe token=hidden-value cookie=browser-value session=session-value")
    browser_ai_service.set_driver_override(FakeDriver(answer))
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")

    response = await client.post(EXECUTE_URL.format(task_id=task["id"]), json=_execute_body())
    stored = await _stored_payload()

    assert response.status_code == 200
    payload = json.dumps(response.json(), ensure_ascii=False) + stored
    for value in ["secret-value", "hidden-value", "browser-value", "session-value"]:
        assert value not in payload
    assert "***REDACTED***" in payload


@pytest.mark.asyncio
async def test_mastermind_review_report_surfaces_in_evidence_board_and_timeline(client, task, monkeypatch):
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(FakeDriver(_valid_answer()))
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")

    execute = await client.post(EXECUTE_URL.format(task_id=task["id"]), json=_execute_body())
    timeline = await client.get(f"/api/tasks/{task['id']}/timeline")
    board = await client.get(f"/api/tasks/{task['id']}/evidence-board")

    assert execute.status_code == 200
    assert "mastermind_review_report_imported" in [item["type"] for item in timeline.json()["data"]["items"]]
    evidence_types = [item["evidence_type"] for item in board.json()["data"]["items"]]
    assert "mastermind_review_report" in evidence_types


@pytest.mark.asyncio
async def test_mastermind_review_execute_avoids_forbidden_surfaces(client, task, monkeypatch):
    from app.services import browser_ai_service
    browser_ai_service.set_driver_override(FakeDriver(_valid_answer()))
    _install_settings(monkeypatch, browser_ai_enabled=True, _browser_ai_provider_allowlist_raw="custom")

    def fail(*args, **kwargs):
        raise AssertionError("forbidden surface")

    for surface in [
        (Path, "glob"),
        (Path, "rglob"),
        (os, "system"),
        (subprocess, "run"),
        (subprocess, "Popen"),
    ]:
        monkeypatch.setattr(surface[0], surface[1], fail)
    for dotted in [
        "app.services.ai_provider_service.dispatch_agent_run",
        "app.services.pr_builder.create_pr",
        "app.services.ci_client.trigger_ci",
        "app.services.deploy_hook.trigger_deploy",
    ]:
        monkeypatch.setattr(dotted, fail)
    before = await _model_counts()

    response = await client.post(EXECUTE_URL.format(task_id=task["id"]), json=_execute_body())

    assert response.status_code == 200
    after = await _model_counts()
    assert after["batches"] == before["batches"]
    assert after["jobs"] == before["jobs"]
    assert after["projects"] == before["projects"]
    assert after["tasks"] == before["tasks"]
    assert after["runs"] == before["runs"] + 1
    assert after["artifacts"] == before["artifacts"] + 1
    assert after["events"] == before["events"] + 3

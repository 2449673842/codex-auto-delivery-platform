import asyncio
import json
from unittest.mock import patch

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
from app.schemas.autopilot_lite import AutoPilotLitePreviewRequest


PREVIEW_URL = "/api/tasks/{task_id}/autopilot-lite/preview"


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
    project = (await client.post("/api/projects", json={
        "name": "s24-1-10-autopilot-lite-preview",
        "display_name": "S24.1.10 AutoPilot Lite Preview",
        "root_path": "/must-not-read",
        "repo_url": "https://github.com/2449673842/codex-auto-delivery-platform",
        "default_branch": "master",
    })).json()["data"]
    return (await client.post("/api/tasks", json={
        "project_id": project["id"],
        "title": "S24.1.10 AutoPilot Lite Preview API",
        "description": "Preview the advisory AutoPilot Lite workflow without execution.",
    })).json()["data"]


def _provider(provider: str = "custom", role: str = "reviewer") -> dict:
    return {
        "provider": provider,
        "role": role,
        "display_name": f"{provider} {role}",
        "target_url": "http://127.0.0.1:9999/mock-browser-ai",
        "prompt_selector": "textarea[name='prompt']",
        "submit_selector": "button[data-send]",
        "response_selector": "[data-answer]",
        "stable_response_timeout_seconds": 30,
        "stable_polls": 3,
        "stable_interval_ms": 1000,
        "enabled": True,
    }


def _body(**overrides) -> dict:
    body = {
        "mode": "review_batch",
        "prompt": "Review this task as advisory evidence only.",
        "providers": [_provider("custom", "reviewer")],
        "include_task_context": True,
        "include_project_memory": True,
        "include_evidence_board": True,
        "include_timeline": True,
        "include_mastermind_review": True,
        "run_gate_preview": True,
        "max_total_concurrency": 2,
        "per_provider_concurrency": 1,
        "prompt_budget": 12000,
        "mastermind_packet": {
            "pr_url": "https://github.com/org/repo/pull/1",
            "pr_number": 1,
            "head_commit": "abc123",
            "base_commit": "def456",
            "verification_results": {
                "targeted_backend_pytest": "passed",
                "full_backend_pytest": "passed",
                "compileall": "passed",
                "npm_build": "passed",
                "frontend_smoke": "passed",
                "git_diff_check": "passed",
            },
            "sonarcloud": {
                "quality_gate": "Passed",
                "security_hotspots": 0,
                "duplication_on_new_code": "0.0%",
                "new_issues": 0,
            },
        },
    }
    body.update(overrides)
    return body


async def _counts() -> dict[str, int]:
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


async def _seed_mastermind_report(task_id: int, project_id: int, **overrides) -> TaskArtifact:
    await asyncio.sleep(0)
    payload = {
        "verdict": "approved",
        "summary": "Clean advisory review; human confirmation required.",
        "blocking_items": [],
        "recommended_actions": ["Wait for human confirmation."],
        "safety_notes": ["No automatic merge authority."],
        "parse_errors": [],
        "confidence": "high",
        "review_scope_confirmed": True,
        "advisory_only": True,
        "human_confirmation_required": True,
        "no_auto_merge": True,
        "head_commit": "abc123",
        "source_agent_run_ids": [101],
        "source_artifact_ids": [202],
        "source_evidence_ids": [],
        "source_timeline_event_ids": [],
    }
    payload.update(overrides)
    artifact = TaskArtifact(
        task_id=task_id,
        artifact_type="mastermind_review_report",
        filename="mastermind_review_report.json",
        content=json.dumps(payload, ensure_ascii=False),
        metadata_json=json.dumps({"project_id": project_id}),
    )
    async with get_session_factory()() as session:
        session.add(artifact)
        await session.commit()
        await session.refresh(artifact)
        return artifact


def _block_execution_side_effects():
    return [
        patch("app.services.browser_ai_pool_service.execute", side_effect=AssertionError("pool execute blocked")),
        patch("app.services.mastermind_review_service.execute_review", side_effect=AssertionError("review execute blocked")),
        patch("builtins.open", side_effect=AssertionError("file open blocked")),
        patch("pathlib.Path.open", side_effect=AssertionError("path open blocked")),
        patch("os.system", side_effect=AssertionError("shell blocked")),
        patch("subprocess.run", side_effect=AssertionError("subprocess blocked")),
        patch("subprocess.Popen", side_effect=AssertionError("subprocess blocked")),
    ]


@pytest.mark.asyncio
async def test_autopilot_lite_preview_task_not_found(client):
    response = await client.post(PREVIEW_URL.format(task_id=999999), json=_body())

    assert response.status_code == 404
    assert response.json()["detail"] == "task_not_found"


@pytest.mark.asyncio
async def test_autopilot_lite_preview_project_not_found():
    from app.services import autopilot_lite_service

    class MissingProjectSession:
        async def get(self, model, item_id):
            if model is Task:
                return Task(id=1, project_id=987654, title="orphan task")
            return None

    with pytest.raises(Exception) as exc:
        await autopilot_lite_service.preview(MissingProjectSession(), 1, AutoPilotLitePreviewRequest())

    assert getattr(exc.value, "status_code", None) == 404
    assert getattr(exc.value, "detail", None) == "project_not_found"


@pytest.mark.asyncio
async def test_autopilot_lite_preview_is_read_only_and_returns_plan(client, task, monkeypatch):
    from app.services import browser_ai_service
    monkeypatch.setattr(
        browser_ai_service,
        "settings",
        browser_ai_service.settings.__class__(**{
            **browser_ai_service.settings.__dict__,
            "browser_ai_enabled": True,
            "_browser_ai_provider_allowlist_raw": "custom",
        }),
    )
    before = await _counts()
    patches = _block_execution_side_effects()

    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        response = await client.post(PREVIEW_URL.format(task_id=task["id"]), json=_body())

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["read_only"] is True
    assert data["persisted"] is False
    assert data["advisory_only"] is True
    assert data["human_confirmation_required"] is True
    assert data["no_auto_merge"] is True
    assert data["provider_jobs"][0]["provider"] == "custom"
    assert data["provider_jobs"][0]["status"] == "ready"
    assert "context_packet" in [step["key"] for step in data["steps"]]
    assert "browser_ai_pool" in [step["key"] for step in data["steps"]]
    assert "mastermind_review_packet" in [step["key"] for step in data["steps"]]
    assert "controlled_gate_preview" in [step["key"] for step in data["steps"]]
    assert "AutoPilot Lite preview is advisory only" in " ".join(data["safety_notes"])
    assert "Project.root_path is intentionally not included" in data["steps"][0]["summary"]
    assert before == await _counts()


@pytest.mark.asyncio
async def test_autopilot_lite_preview_without_evidence_recommends_insufficient_evidence(client, task):
    response = await client.post(PREVIEW_URL.format(task_id=task["id"]), json=_body(providers=[]))

    data = response.json()["data"]
    assert data["recommendation"] == "insufficient_evidence"
    assert data["status"] == "needs_human"
    assert data["autopilot_state"] == "needs_human"
    assert "Run Browser AI Pool execute" in " ".join(data["recommended_actions"])
    assert any("Browser AI Pool preview has no ready provider jobs" in reason for reason in data["blocking_reasons"])


@pytest.mark.asyncio
async def test_autopilot_lite_preview_maps_gate_advisory_approved_to_human_confirmation(client, task, monkeypatch):
    from app.services import browser_ai_service
    monkeypatch.setattr(
        browser_ai_service,
        "settings",
        browser_ai_service.settings.__class__(**{
            **browser_ai_service.settings.__dict__,
            "browser_ai_enabled": True,
            "_browser_ai_provider_allowlist_raw": "custom",
        }),
    )
    await _seed_mastermind_report(task["id"], task["project_id"])

    response = await client.post(PREVIEW_URL.format(task_id=task["id"]), json=_body())

    data = response.json()["data"]
    assert response.status_code == 200
    assert data["gate_preview"]["gate_status"] == "gate_advisory_approved"
    assert data["recommendation"] in {"ready_for_human_confirmation", "insufficient_evidence"}
    assert data["gate_preview"]["human_confirmation_required"] is True
    assert data["gate_preview"]["advisory_only"] is True
    assert data["gate_preview"]["no_auto_merge"] is True
    assert "do not auto approve or merge" in " ".join(data["recommended_actions"]).lower()


@pytest.mark.asyncio
async def test_autopilot_lite_preview_maps_request_changes_gate(client, task):
    await _seed_mastermind_report(
        task["id"],
        task["project_id"],
        verdict="request_changes",
        blocking_items=[{"severity": "major", "summary": "Missing verification"}],
    )

    response = await client.post(PREVIEW_URL.format(task_id=task["id"]), json=_body(providers=[]))

    data = response.json()["data"]
    assert data["gate_preview"]["gate_status"] == "gate_request_changes"
    assert data["recommendation"] == "request_codex_rework"
    assert "repair handoff" in " ".join(data["recommended_actions"]).lower()


@pytest.mark.asyncio
async def test_autopilot_lite_preview_keeps_forbidden_actions_out_of_api_surface(client, task):
    response = await client.post(PREVIEW_URL.format(task_id=task["id"]), json=_body())

    payload = json.dumps(response.json(), ensure_ascii=False).lower()
    assert response.status_code == 200
    for phrase in [
        "cannot approve",
        "merge",
        "deploy",
        "rework",
        "provider api tokens",
        "hidden web apis",
        ".env",
        "secret_ref",
    ]:
        assert phrase in payload
    for forbidden_route in [
        "autopilot-lite/approve",
        "autopilot-lite/merge",
        "autopilot-lite/deploy",
        "autopilot-lite/rework",
    ]:
        assert forbidden_route not in payload

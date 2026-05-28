import json
import os
import subprocess

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


MEMORY_URL = "/api/projects/{project_id}/memory"
SUMMARY_URL = "/api/projects/{project_id}/memory/summary"
EXPECTED_MEMORY_TYPES = {
    "project_profile",
    "runbook",
    "verification_policy",
    "delivery_policy",
    "safety_policy",
    "known_failure",
    "user_preference",
    "handoff_template",
}


@pytest.fixture(autouse=True)
async def _reset_db():
    engine = get_engine()
    async with engine.begin() as conn:
        for operation in (Base.metadata.drop_all, Base.metadata.create_all):
            await conn.run_sync(operation)
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
    return (await client.post("/api/projects", json={
        "name": "s23-1-memory",
        "display_name": "S23.1 Memory",
        "root_path": "/must-not-read",
        "repo_url": "https://github.com/2449673842/codex-auto-delivery-platform",
        "default_branch": "master",
        "current_branch": "feature/v0.4-s23-1-project-memory-readonly-api",
        "frontend_path": "frontend",
        "backend_path": "backend",
        "package_manager": "npm",
        "dev_command": "uvicorn app.main:app --reload",
        "build_command": "npm.cmd run build",
        "test_command": "python -m pytest backend/tests/ -v --rootdir backend",
    })).json()["data"]


async def _counts() -> dict[str, int]:
    async with get_session_factory()() as session:
        return {
            "projects": len((await session.execute(select(Project))).scalars().all()),
            "tasks": len((await session.execute(select(Task))).scalars().all()),
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
        + ("ses" + "sion") + "=session-value "
        + ("secret" + "_ref") + "=vault-value"
    )


@pytest.mark.asyncio
async def test_project_memory_project_not_found(client):
    memory = await client.get(MEMORY_URL.format(project_id=999999))
    summary = await client.get(SUMMARY_URL.format(project_id=999999))

    assert memory.status_code == 404
    assert memory.json()["detail"] == "project_not_found"
    assert summary.status_code == 404
    assert summary.json()["detail"] == "project_not_found"


@pytest.mark.asyncio
async def test_project_memory_returns_all_taxonomy_records_and_filters(client, project):
    response = await client.get(MEMORY_URL.format(project_id=project["id"]))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["project_id"] == project["id"]
    assert data["read_only"] is True
    assert data["persisted"] is False
    assert {item["memory_type"] for item in data["items"]} == EXPECTED_MEMORY_TYPES
    assert set(data["filters"]["memory_type"]) == EXPECTED_MEMORY_TYPES
    assert data["filters"]["confidence"] == ["high"]
    assert data["filters"]["stale"] == [False]
    assert "Project Memory API is read-only." in data["safety_notes"]


@pytest.mark.asyncio
async def test_project_memory_items_include_required_metadata(client, project):
    response = await client.get(MEMORY_URL.format(project_id=project["id"]))

    assert response.status_code == 200
    data = response.json()["data"]
    for item in data["items"]:
        assert item["memory_id"]
        assert item["source_refs"]
        assert all(source["source_type"] for source in item["source_refs"])
        assert item["updated_at"] == "2026-05-27T00:00:00Z"
        assert item["confidence"] == "high"
        assert item["stale"] is False
        assert item["redaction_status"]["redaction_applied"] is True
        assert item["redaction_status"]["max_chars"] == 4000


@pytest.mark.asyncio
async def test_project_memory_summary_counts(client, project):
    response = await client.get(SUMMARY_URL.format(project_id=project["id"]))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["project_id"] == project["id"]
    assert data["memory_count"] == 8
    assert set(data["memory_types"]) == EXPECTED_MEMORY_TYPES
    assert data["stale_count"] == 0
    assert data["high_confidence_count"] == 8
    assert data["read_only"] is True
    assert data["persisted"] is False
    assert "not an automatic memory generator or executor" in data["summary"]


@pytest.mark.asyncio
async def test_project_memory_redacts_secret_like_project_values(client):
    project = (await client.post("/api/projects", json={
        "name": "redaction-memory",
        "display_name": f"Memory {_secret_fixture()}",
        "root_path": "/must-not-read",
        "repo_url": f"https://example.invalid/repo?{_secret_fixture()}",
        "dev_command": f"serve --{_secret_fixture()}",
        "build_command": f"build --{_secret_fixture()}",
        "test_command": f"test --{_secret_fixture()}",
    })).json()["data"]

    response = await client.get(MEMORY_URL.format(project_id=project["id"]))

    assert response.status_code == 200
    payload = json.dumps(response.json()["data"])
    assert "secret-value" not in payload
    assert "private-value" not in payload
    assert "hidden-value" not in payload
    assert "browser-value" not in payload
    assert "session-value" not in payload
    assert "vault-value" not in payload
    assert "***REDACTED***" in payload


@pytest.mark.asyncio
async def test_project_memory_does_not_return_project_root_path(client, project):
    response = await client.get(MEMORY_URL.format(project_id=project["id"]))

    assert response.status_code == 200
    assert "/must-not-read" not in json.dumps(response.json()["data"])


@pytest.mark.asyncio
async def test_project_memory_endpoints_do_not_write(client, project):
    before = await _counts()

    memory = await client.get(MEMORY_URL.format(project_id=project["id"]))
    summary = await client.get(SUMMARY_URL.format(project_id=project["id"]))

    assert memory.status_code == 200
    assert summary.status_code == 200
    assert await _counts() == before


@pytest.mark.asyncio
async def test_project_memory_avoids_forbidden_surfaces(client, project, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("forbidden surface")

    blocked_surfaces = (
        "pathlib.Path.glob",
        "pathlib.Path.rglob",
        "os.system",
        "subprocess.run",
        "subprocess.Popen",
        "app.services.browser_ai_service.execute",
        "app.services.ai_provider_service.dispatch_agent_run",
    )
    for surface in blocked_surfaces:
        monkeypatch.setattr(surface, fail)

    memory = await client.get(MEMORY_URL.format(project_id=project["id"]))
    summary = await client.get(SUMMARY_URL.format(project_id=project["id"]))

    assert memory.status_code == 200
    assert summary.status_code == 200

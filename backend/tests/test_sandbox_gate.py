"""Tests for Sandbox Approval Gate (v0.4 S3).

Covers all gate conditions:
- passed: all checks ok
- blocked: archived task, no sandbox result, not applied, no changed files,
  forbidden path, secret, stale, AgentRun not in task, risk too high,
  human_required, multiple reasons, 404
"""

import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.database import Base, get_engine, get_session_factory
from app.models.task import Task
from app.models.project import Project
from app.models.agent_run import AgentRun
from app.models.task_artifact import TaskArtifact
from app.models.approval_decision import ApprovalDecision

BASE = "/api"


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
async def db_session():
    factory = get_session_factory()
    async with factory() as session:
        yield session
        await session.rollback()


def _make_report_content(applied: bool = True, changed_files: list[dict] | None = None) -> str:
    if changed_files is None:
        changed_files = [{"path": "src/test.py", "status": "modified", "additions": 3, "deletions": 1}]
    report = {"applied": applied, "changed_files": changed_files, "warnings": [], "errors": []}
    return json.dumps(report, ensure_ascii=False)


@pytest.fixture
async def project(client) -> dict:
    r = await client.post(BASE + "/projects", json={
        "name": "gate-test", "root_path": "/gate",
    })
    return r.json()["data"]


@pytest.fixture
async def task(client, project) -> dict:
    r = await client.post(BASE + "/tasks", json={
        "project_id": project["id"], "title": "gate-task",
    })
    return r.json()["data"]


@pytest.fixture
async def agent(client) -> dict:
    r = await client.post(BASE + "/agents", json={
        "name": "gate-agent", "agent_type": "executor", "provider": "local",
    })
    return r.json()["data"]


@pytest.fixture
async def run(client, task, agent) -> dict:
    r = await client.post(BASE + f"/tasks/{task['id']}/agent-runs", json={
        "agent_id": agent["id"], "run_type": "execute", "input_prompt": "test",
    })
    return r.json()["data"]


class TestSandboxGate:

    @pytest.mark.asyncio
    async def test_gate_passed(self, client, task, run, db_session):
        """All conditions met — gate passes."""
        art = TaskArtifact(
            task_id=task["id"], artifact_type="patch_apply_report",
            content=_make_report_content(),
            filename=f"patch_apply_report_run_{run['id']}.json",
        )
        db_session.add(art)
        await db_session.commit()

        resp = await client.get(f"/api/tasks/{task['id']}/sandbox/gate")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["passed"] is True
        assert data["can_prepare_pr"] is True
        assert len(data["blocked_reasons"]) == 0

    @pytest.mark.asyncio
    async def test_blocked_archived_task(self, client, task, run, db_session):
        """Task is archived."""
        t = await db_session.get(Task, task["id"])
        t.status = "archived"
        art = TaskArtifact(
            task_id=task["id"], artifact_type="patch_apply_report",
            content=_make_report_content(),
            filename=f"patch_apply_report_run_{run['id']}.json",
        )
        db_session.add(art)
        await db_session.commit()

        resp = await client.get(f"/api/tasks/{task['id']}/sandbox/gate")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["passed"] is False
        reasons = [r["reason"] for r in data["blocked_reasons"]]
        assert "archived_task" in reasons

    @pytest.mark.asyncio
    async def test_blocked_no_sandbox_result(self, client, task):
        """No report artifact exists."""
        resp = await client.get(f"/api/tasks/{task['id']}/sandbox/gate")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["passed"] is False
        reasons = [r["reason"] for r in data["blocked_reasons"]]
        assert "no_sandbox_result" in reasons

    @pytest.mark.asyncio
    async def test_blocked_not_applied(self, client, task, run, db_session):
        """Patch apply report shows applied=False."""
        art = TaskArtifact(
            task_id=task["id"], artifact_type="patch_apply_report",
            content=_make_report_content(applied=False),
            filename=f"patch_apply_report_run_{run['id']}.json",
        )
        db_session.add(art)
        await db_session.commit()

        resp = await client.get(f"/api/tasks/{task['id']}/sandbox/gate")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["passed"] is False
        reasons = [r["reason"] for r in data["blocked_reasons"]]
        assert "sandbox_not_applied" in reasons

    @pytest.mark.asyncio
    async def test_blocked_no_changed_files(self, client, task, run, db_session):
        """Report has empty changed_files."""
        art = TaskArtifact(
            task_id=task["id"], artifact_type="patch_apply_report",
            content=_make_report_content(changed_files=[]),
            filename=f"patch_apply_report_run_{run['id']}.json",
        )
        db_session.add(art)
        await db_session.commit()

        resp = await client.get(f"/api/tasks/{task['id']}/sandbox/gate")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["passed"] is False
        reasons = [r["reason"] for r in data["blocked_reasons"]]
        assert "no_changed_files" in reasons

    @pytest.mark.asyncio
    async def test_blocked_forbidden_path(self, client, task, run, db_session):
        """Changed file has forbidden path."""
        art = TaskArtifact(
            task_id=task["id"], artifact_type="patch_apply_report",
            content=_make_report_content(changed_files=[{"path": ".env", "status": "modified"}]),
            filename=f"patch_apply_report_run_{run['id']}.json",
        )
        db_session.add(art)
        await db_session.commit()

        resp = await client.get(f"/api/tasks/{task['id']}/sandbox/gate")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["passed"] is False
        reasons = [r["reason"] for r in data["blocked_reasons"]]
        assert "forbidden_path" in reasons

    @pytest.mark.asyncio
    async def test_blocked_secret_detected(self, client, task, run, db_session):
        """Report content contains ***REDACTED*** (valid JSON with redacted value)."""
        content = json.dumps({
            "applied": True,
            "redacted": "***REDACTED***",
            "changed_files": [{"path": "src/test.py", "status": "modified"}],
            "warnings": [], "errors": [],
        }, ensure_ascii=False)
        art = TaskArtifact(
            task_id=task["id"], artifact_type="patch_apply_report",
            content=content,
            filename=f"patch_apply_report_run_{run['id']}.json",
        )
        db_session.add(art)
        await db_session.commit()

        resp = await client.get(f"/api/tasks/{task['id']}/sandbox/gate")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["passed"] is False
        reasons = [r["reason"] for r in data["blocked_reasons"]]
        assert "secret_detected" in reasons

    @pytest.mark.asyncio
    async def test_blocked_stale_result(self, client, task, run, db_session):
        """Newer sandbox result (different type) makes the report stale."""
        from datetime import datetime, timezone
        earlier = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        later = datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
        report_art = TaskArtifact(
            task_id=task["id"], artifact_type="patch_apply_report",
            content=_make_report_content(),
            filename=f"patch_apply_report_run_{run['id']}.json",
            created_at=earlier,
        )
        db_session.add(report_art)
        newer = TaskArtifact(
            task_id=task["id"], artifact_type="changed_files_summary",
            content=_make_report_content(),
            filename=f"changed_files_summary_run_{run['id']}.json",
            created_at=later,
        )
        db_session.add(newer)
        await db_session.commit()

        resp = await client.get(f"/api/tasks/{task['id']}/sandbox/gate")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["passed"] is False
        reasons = [r["reason"] for r in data["blocked_reasons"]]
        assert "stale_sandbox_result" in reasons

    @pytest.mark.asyncio
    async def test_blocked_agent_run_not_in_task(self, client, task, db_session, project, agent):
        """Report's AgentRun belongs to a different task."""
        r2 = await client.post(BASE + "/tasks", json={
            "project_id": project["id"], "title": "other-task",
        })
        other_task = r2.json()["data"]
        ar = await client.post(BASE + f"/tasks/{other_task['id']}/agent-runs", json={
            "agent_id": agent["id"], "run_type": "execute", "input_prompt": "test",
        })
        other_run = ar.json()["data"]
        art = TaskArtifact(
            task_id=task["id"], artifact_type="patch_apply_report",
            content=_make_report_content(),
            filename=f"patch_apply_report_run_{other_run['id']}.json",
        )
        db_session.add(art)
        await db_session.commit()

        resp = await client.get(f"/api/tasks/{task['id']}/sandbox/gate")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["passed"] is False
        reasons = [r["reason"] for r in data["blocked_reasons"]]
        assert "agent_run_not_in_task" in reasons

    @pytest.mark.asyncio
    async def test_blocked_risk_too_high(self, client, task, run, db_session):
        """AgentRun has high/critical risk_level."""
        run_model = await db_session.get(AgentRun, run["id"])
        run_model.risk_level = "high"
        art = TaskArtifact(
            task_id=task["id"], artifact_type="patch_apply_report",
            content=_make_report_content(),
            filename=f"patch_apply_report_run_{run['id']}.json",
        )
        db_session.add(art)
        await db_session.commit()

        resp = await client.get(f"/api/tasks/{task['id']}/sandbox/gate")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["passed"] is False
        reasons = [r["reason"] for r in data["blocked_reasons"]]
        assert "risk_too_high" in reasons

    @pytest.mark.asyncio
    async def test_blocked_human_required(self, client, task, run, db_session):
        """Latest approval decision has human_required=True."""
        art = TaskArtifact(
            task_id=task["id"], artifact_type="patch_apply_report",
            content=_make_report_content(),
            filename=f"patch_apply_report_run_{run['id']}.json",
        )
        db_session.add(art)
        decision = ApprovalDecision(
            task_id=task["id"], human_required=True,
            auto_approve_allowed=False, risk_level="low",
        )
        db_session.add(decision)
        await db_session.commit()

        resp = await client.get(f"/api/tasks/{task['id']}/sandbox/gate")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["passed"] is False
        reasons = [r["reason"] for r in data["blocked_reasons"]]
        assert "human_required" in reasons

    @pytest.mark.asyncio
    async def test_blocked_multiple_reasons(self, client, task, run, db_session):
        """Multiple blocking conditions simultaneously."""
        t = await db_session.get(Task, task["id"])
        t.status = "archived"
        run_model = await db_session.get(AgentRun, run["id"])
        run_model.risk_level = "critical"
        content = json.dumps({
            "applied": True,
            "redacted": "***REDACTED***",
            "changed_files": [{"path": "src/test.py", "status": "modified"}],
            "warnings": [], "errors": [],
        }, ensure_ascii=False)
        art = TaskArtifact(
            task_id=task["id"], artifact_type="patch_apply_report",
            content=content,
            filename=f"patch_apply_report_run_{run['id']}.json",
        )
        db_session.add(art)
        decision = ApprovalDecision(
            task_id=task["id"], human_required=True,
            auto_approve_allowed=False, risk_level="low",
        )
        db_session.add(decision)
        await db_session.commit()

        resp = await client.get(f"/api/tasks/{task['id']}/sandbox/gate")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["passed"] is False
        reasons = [r["reason"] for r in data["blocked_reasons"]]
        assert "archived_task" in reasons
        assert "risk_too_high" in reasons
        assert "secret_detected" in reasons
        assert "human_required" in reasons

    @pytest.mark.asyncio
    async def test_gate_404(self, client):
        resp = await client.get("/api/tasks/99999/sandbox/gate")
        assert resp.status_code == 404

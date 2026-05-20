"""Sandbox Approval Gate tests (v0.4 S3).

All gate conditions, plus integration via real sandbox apply API.
"""

import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.database import Base, get_engine, get_session_factory
from app.models.task import Task
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


# ── Shared helpers ──

def _report_json(applied: bool = True, changed_files: list[dict] | None = None) -> str:
    if changed_files is None:
        changed_files = [{"path": "src/test.py", "status": "modified", "additions": 3, "deletions": 1}]
    return json.dumps({"applied": applied, "changed_files": changed_files, "warnings": [], "errors": []},
                      ensure_ascii=False)


def _redacted_content() -> str:
    return json.dumps({"applied": True, "redacted": "***REDACTED***",
                       "changed_files": [{"path": "src/test.py", "status": "modified"}],
                       "warnings": [], "errors": []}, ensure_ascii=False)


async def _add_artifact(db_session, task_id, content, filename):
    art = TaskArtifact(task_id=task_id, artifact_type="patch_apply_report",
                       content=content, filename=filename)
    db_session.add(art)
    await db_session.commit()


async def _add_report(db_session, task_id, run_id, **kw):
    await _add_artifact(db_session, task_id, _report_json(**kw),
                        f"patch_apply_report_run_{run_id}.json")


def _gate(client, task_id):
    return client.get(f"/api/tasks/{task_id}/sandbox/gate")


async def _gate_data(client, task_id):
    r = await _gate(client, task_id)
    return r.json()["data"]


def _reasons(data):
    return [r["reason"] for r in data["blocked_reasons"]]


async def _setup_sandbox_run(client, task_id, agent_id, diff):
    """Create, run, succeed an AgentRun, then sandbox-apply."""
    await client.post(BASE + f"/tasks/{task_id}/code-context", json={
        "files": [{"path": "src/util.py", "content": "def f() -> int:\n    return 1\n", "language": "python"}]
    })
    actor = {"actor": "test"}
    await client.post(BASE + f"/tasks/{task_id}/generate-ticket", json=actor)
    await client.post(BASE + f"/tasks/{task_id}/dispatch", json=actor)
    r = await client.post(BASE + f"/tasks/{task_id}/agent-runs", json={
        "agent_id": agent_id, "run_type": "execute", "input_prompt": "test",
    })
    run = r.json()["data"]
    await client.patch(BASE + f"/tasks/{task_id}/agent-runs/{run['id']}", json={"status": "running"})
    await client.post(BASE + f"/tasks/{task_id}/agent-runs/{run['id']}/submit-result", json={
        "status": "succeeded", "output_summary": "ok", "output_log": "ok", "output_diff": diff,
    })
    r = await client.post(BASE + f"/tasks/{task_id}/agent-runs/{run['id']}/sandbox/apply-patch")
    assert r.status_code == 200
    return run


# ── Fixtures ──

@pytest.fixture
async def project(client) -> dict:
    r = await client.post(BASE + "/projects", json={"name": "gate-test", "root_path": "/gate"})
    return r.json()["data"]


@pytest.fixture
async def agent(client) -> dict:
    r = await client.post(BASE + "/agents", json={
        "name": "gate-agent", "agent_type": "executor", "provider": "local",
    })
    return r.json()["data"]


@pytest.fixture
async def task(client, project) -> dict:
    r = await client.post(BASE + "/tasks", json={"project_id": project["id"], "title": "gate-task"})
    return r.json()["data"]


@pytest.fixture
async def run(client, task, agent) -> dict:
    r = await client.post(BASE + f"/tasks/{task['id']}/agent-runs", json={
        "agent_id": agent["id"], "run_type": "execute", "input_prompt": "test",
    })
    return r.json()["data"]


# ═══════════════════════════════════════════════
# Unit tests — each gate condition
# ═══════════════════════════════════════════════

class TestSandboxGateUnit:

    @pytest.mark.asyncio
    async def test_gate_passed(self, client, task, run, db_session):
        await _add_report(db_session, task["id"], run["id"])
        data = await _gate_data(client, task["id"])
        assert data["passed"] is True
        assert data["can_prepare_pr"] is True
        assert len(data["blocked_reasons"]) == 0

    @pytest.mark.asyncio
    async def test_blocked_archived_task(self, client, task, run, db_session):
        t = await db_session.get(Task, task["id"])
        t.status = "archived"
        await _add_report(db_session, task["id"], run["id"])
        assert "archived_task" in _reasons(await _gate_data(client, task["id"]))

    @pytest.mark.asyncio
    async def test_blocked_no_sandbox_result(self, client, task):
        assert "no_sandbox_result" in _reasons(await _gate_data(client, task["id"]))

    @pytest.mark.asyncio
    async def test_blocked_not_applied(self, client, task, run, db_session):
        await _add_report(db_session, task["id"], run["id"], applied=False)
        assert "sandbox_not_applied" in _reasons(await _gate_data(client, task["id"]))

    @pytest.mark.asyncio
    async def test_blocked_no_changed_files(self, client, task, run, db_session):
        await _add_report(db_session, task["id"], run["id"], changed_files=[])
        assert "no_changed_files" in _reasons(await _gate_data(client, task["id"]))

    @pytest.mark.asyncio
    async def test_blocked_forbidden_path(self, client, task, run, db_session):
        await _add_report(db_session, task["id"], run["id"],
                          changed_files=[{"path": ".env", "status": "modified"}])
        assert "forbidden_path" in _reasons(await _gate_data(client, task["id"]))

    @pytest.mark.asyncio
    async def test_blocked_secret_detected(self, client, task, run, db_session):
        await _add_artifact(db_session, task["id"], _redacted_content(),
                            f"patch_apply_report_run_{run['id']}.json")
        assert "secret_detected" in _reasons(await _gate_data(client, task["id"]))

    @pytest.mark.asyncio
    async def test_same_run_artifacts_not_stale(self, client, task, run, db_session):
        """Same-run summary/preview must not trigger false-positive stale."""
        report = TaskArtifact(task_id=task["id"], artifact_type="patch_apply_report",
                              content=_report_json(),
                              filename=f"patch_apply_report_run_{run['id']}.json")
        db_session.add(report)
        await db_session.flush()
        for t in ("changed_files_summary", "changed_file_preview"):
            db_session.add(TaskArtifact(task_id=task["id"], artifact_type=t,
                                        content=_report_json(),
                                        filename=f"{t}_run_{run['id']}.json"))
        await db_session.commit()
        data = await _gate_data(client, task["id"])
        assert data["passed"] is True
        assert "stale_sandbox_result" not in _reasons(data)

    @pytest.mark.asyncio
    async def test_blocked_agent_run_unknown(self, client, task, db_session):
        await _add_artifact(db_session, task["id"], _report_json(), "patch_apply_report.json")
        data = await _gate_data(client, task["id"])
        assert data["passed"] is False
        assert "agent_run_unknown" in _reasons(data)

    @pytest.mark.asyncio
    async def test_blocked_agent_run_not_in_task(self, client, task, db_session, project, agent):
        r2 = await client.post(BASE + "/tasks", json={"project_id": project["id"], "title": "other"})
        other_task = r2.json()["data"]
        ar = await client.post(BASE + f"/tasks/{other_task['id']}/agent-runs", json={
            "agent_id": agent["id"], "run_type": "execute", "input_prompt": "test",
        })
        await _add_report(db_session, task["id"], ar.json()["data"]["id"])
        assert "agent_run_not_in_task" in _reasons(await _gate_data(client, task["id"]))

    @pytest.mark.asyncio
    async def test_blocked_risk_too_high(self, client, task, run, db_session):
        run_model = await db_session.get(AgentRun, run["id"])
        run_model.risk_level = "high"
        await _add_report(db_session, task["id"], run["id"])
        assert "risk_too_high" in _reasons(await _gate_data(client, task["id"]))

    @pytest.mark.asyncio
    async def test_blocked_human_required(self, client, task, run, db_session):
        await _add_report(db_session, task["id"], run["id"])
        db_session.add(ApprovalDecision(task_id=task["id"], human_required=True,
                                        auto_approve_allowed=False, risk_level="low"))
        await db_session.commit()
        assert "human_required" in _reasons(await _gate_data(client, task["id"]))

    @pytest.mark.asyncio
    async def test_blocked_multiple_reasons(self, client, task, run, db_session):
        t = await db_session.get(Task, task["id"])
        t.status = "archived"
        run_model = await db_session.get(AgentRun, run["id"])
        run_model.risk_level = "critical"
        await _add_artifact(db_session, task["id"], _redacted_content(),
                            f"patch_apply_report_run_{run['id']}.json")
        db_session.add(ApprovalDecision(task_id=task["id"], human_required=True,
                                        auto_approve_allowed=False, risk_level="low"))
        await db_session.commit()
        reasons = _reasons(await _gate_data(client, task["id"]))
        assert "archived_task" in reasons
        assert "risk_too_high" in reasons
        assert "secret_detected" in reasons
        assert "human_required" in reasons

    @pytest.mark.asyncio
    async def test_gate_404(self, client):
        assert (await _gate(client, 99999)).status_code == 404


# ═══════════════════════════════════════════════
# Integration tests — real sandbox apply API
# ═══════════════════════════════════════════════

class TestSandboxGateIntegration:

    DIFF = ("diff --git a/src/util.py b/src/util.py\n"
            "--- a/src/util.py\n"
            "+++ b/src/util.py\n"
            "@@ -1,2 +1,3 @@\n"
            " def f() -> int:\n"
            "+    # updated\n"
            "     return 1\n")

    @pytest.mark.asyncio
    async def test_gate_passed_after_sandbox_apply(self, client, project, agent):
        """Real sandbox apply → gate passed, no stale false positive."""
        r = await client.post(BASE + "/tasks", json={
            "project_id": project["id"], "title": "sandbox-gate-int",
        })
        task_id = r.json()["data"]["id"]
        await _setup_sandbox_run(client, task_id, agent["id"], self.DIFF)
        data = await _gate_data(client, task_id)
        reasons = _reasons(data)
        assert data["passed"] is True, f"gate blocked by: {reasons}"
        assert "stale_sandbox_result" not in reasons

    @pytest.mark.asyncio
    async def test_gate_passed_via_post(self, client, project, agent):
        """POST /evaluate-gate writes event; verify via event list."""
        r = await client.post(BASE + "/tasks", json={
            "project_id": project["id"], "title": "sandbox-gate-post",
        })
        task_id = r.json()["data"]["id"]
        await _setup_sandbox_run(client, task_id, agent["id"], self.DIFF)
        data = (await client.post(f"/api/tasks/{task_id}/sandbox/evaluate-gate")).json()["data"]
        assert data["passed"] is True
        events = (await client.get(BASE + f"/tasks/{task_id}/events")).json()["data"]
        gate_events = [e for e in events if e["event_type"].startswith("sandbox_gate_")]
        assert len(gate_events) >= 1

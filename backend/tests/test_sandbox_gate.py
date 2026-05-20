"""Tests for Sandbox Approval Gate (v0.4 S3)."""
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


def _report_content(applied=True, changed_files=None, redacted=False):
    if changed_files is None:
        changed_files = [{"path": "src/test.py", "status": "modified", "additions": 3, "deletions": 1}]
    d = {"applied": applied, "changed_files": changed_files, "warnings": [], "errors": []}
    if redacted:
        d["redacted"] = "***REDACTED***"
    return json.dumps(d, ensure_ascii=False)


async def _add_report(db, tid, rid, **kw):
    db.add(TaskArtifact(task_id=tid, artifact_type="patch_apply_report",
           content=_report_content(**kw), filename=f"patch_apply_report_run_{rid}.json"))
    await db.commit()


@pytest.fixture
async def project(client):
    r = await client.post(BASE + "/projects", json={"name": "gate-test", "root_path": "/gate"})
    return r.json()["data"]


@pytest.fixture
async def agent(client):
    r = await client.post(BASE + "/agents", json={
        "name": "gate-agent", "agent_type": "executor", "provider": "local"})
    return r.json()["data"]


@pytest.fixture
async def task(client, project):
    r = await client.post(BASE + "/tasks", json={"project_id": project["id"], "title": "gate-task"})
    return r.json()["data"]


@pytest.fixture
async def run(client, task, agent):
    r = await client.post(BASE + f"/tasks/{task['id']}/agent-runs",
                          json={"agent_id": agent["id"], "run_type": "execute", "input_prompt": "test"})
    return r.json()["data"]


@pytest.mark.asyncio
class TestSandboxGate:

    @staticmethod
    async def _reasons(client, tid):
        g = await client.get(f"/api/tasks/{tid}/sandbox/gate")
        return [r["reason"] for r in g.json()["data"]["blocked_reasons"]]

    # --- passed ---
    async def test_passed(self, client, task, run, db_session):
        await _add_report(db_session, task["id"], run["id"])
        data = (await client.get(f"/api/tasks/{task['id']}/sandbox/gate")).json()["data"]
        assert data["passed"] is True
        assert len(data["blocked_reasons"]) == 0

    # --- blocked: report-level conditions ---
    @pytest.mark.parametrize("kw,expect", [
        ({"applied": False}, "sandbox_not_applied"),
        ({"changed_files": []}, "no_changed_files"),
        ({"changed_files": [{"path": ".env", "status": "modified"}]}, "forbidden_path"),
        ({"redacted": True}, "secret_detected"),
    ])
    async def test_report_conditions(self, client, task, run, db_session, kw, expect):
        await _add_report(db_session, task["id"], run["id"], **kw)
        r = await self._reasons(client, task["id"])
        assert expect in r

    # --- blocked: no sandbox result ---
    async def test_no_result(self, client, task):
        r = await self._reasons(client, task["id"])
        assert "no_sandbox_result" in r

    # --- blocked: archived ---
    async def test_archived(self, client, task, run, db_session):
        t = await db_session.get(Task, task["id"])
        t.status = "archived"
        await _add_report(db_session, task["id"], run["id"])
        r = await self._reasons(client, task["id"])
        assert "archived_task" in r

    # --- blocked: stale ---
    async def test_not_stale(self, client, task, run, db_session):
        await _add_report(db_session, task["id"], run["id"])
        for t in ("changed_files_summary", "changed_file_preview"):
            db_session.add(TaskArtifact(task_id=task["id"], artifact_type=t,
                           content=_report_content(), filename=f"{t}_run_{run['id']}.json"))
        await db_session.commit()
        assert (await client.get(f"/api/tasks/{task['id']}/sandbox/gate")).json()["data"]["passed"] is True

    # --- blocked: agent_run_unknown ---
    async def test_run_unknown(self, client, task, db_session):
        db_session.add(TaskArtifact(task_id=task["id"], artifact_type="patch_apply_report",
                       content=_report_content(), filename="patch_apply_report.json"))
        await db_session.commit()
        r = await self._reasons(client, task["id"])
        assert "agent_run_unknown" in r

    # --- blocked: cross-task agent run ---
    async def test_wrong_task_run(self, client, task, db_session, project, agent):
        r = await client.post(BASE + "/tasks", json={"project_id": project["id"], "title": "other"})
        other = r.json()["data"]
        ar = await client.post(BASE + f"/tasks/{other['id']}/agent-runs",
                               json={"agent_id": agent["id"], "run_type": "execute", "input_prompt": "test"})
        await _add_report(db_session, task["id"], ar.json()["data"]["id"])
        r = await self._reasons(client, task["id"])
        assert "agent_run_not_in_task" in r

    # --- blocked: risk too high ---
    async def test_high_risk(self, client, task, run, db_session):
        (await db_session.get(AgentRun, run["id"])).risk_level = "high"
        await _add_report(db_session, task["id"], run["id"])
        r = await self._reasons(client, task["id"])
        assert "risk_too_high" in r

    # --- blocked: human required ---
    async def test_human(self, client, task, run, db_session):
        await _add_report(db_session, task["id"], run["id"])
        db_session.add(ApprovalDecision(task_id=task["id"], human_required=True,
                                        auto_approve_allowed=False, risk_level="low"))
        await db_session.commit()
        r = await self._reasons(client, task["id"])
        assert "human_required" in r

    # --- blocked: multiple reasons ---
    async def test_multiple(self, client, task, run, db_session):
        (await db_session.get(Task, task["id"])).status = "archived"
        (await db_session.get(AgentRun, run["id"])).risk_level = "critical"
        db_session.add(TaskArtifact(task_id=task["id"], artifact_type="patch_apply_report",
                       content=_report_content(redacted=True),
                       filename=f"patch_apply_report_run_{run['id']}.json"))
        db_session.add(ApprovalDecision(task_id=task["id"], human_required=True,
                                        auto_approve_allowed=False, risk_level="low"))
        await db_session.commit()
        r = await self._reasons(client, task["id"])
        for w in ("archived_task", "risk_too_high", "secret_detected", "human_required"):
            assert w in r

    # --- 404 ---
    async def test_404(self, client):
        assert (await client.get("/api/tasks/99999/sandbox/gate")).status_code == 404

    # --- integration: GET ---
    async def test_get(self, client, project, agent):
        r = await client.post(BASE + "/tasks", json={
            "project_id": project["id"], "title": "int-get"})
        tid = r.json()["data"]["id"]
        await client.post(BASE + f"/tasks/{tid}/code-context", json={
            "files": [{"path": "src/greeting.py",
                       "content": "def greet(name: str) -> str:\n    return f\"Hello, {name}!\"\n",
                       "language": "python"}]})
        await client.post(BASE + f"/tasks/{tid}/generate-ticket", json={"actor": "test"})
        await client.post(BASE + f"/tasks/{tid}/dispatch", json={"actor": "test"})
        r = await client.post(BASE + f"/tasks/{tid}/agent-runs", json={
            "agent_id": agent["id"], "run_type": "execute", "input_prompt": "Add i18n"})
        rid = r.json()["data"]["id"]
        await client.patch(BASE + f"/tasks/{tid}/agent-runs/{rid}", json={"status": "running"})
        await client.post(BASE + f"/tasks/{tid}/agent-runs/{rid}/submit-result", json={
            "status": "succeeded", "output_summary": "ok", "output_log": "ok",
            "output_diff": ("diff --git a/src/greeting.py b/src/greeting.py\n"
                            "--- a/src/greeting.py\n+++ b/src/greeting.py\n"
                            "@@ -1,2 +1,5 @@\n def greet(name: str) -> str:\n"
                            "+    if name:\n"
                            "     return f\"Hello, {name}!\"\n"
                            "+    return \"Hello, World!\"\n")})
        r = await client.post(BASE + f"/tasks/{tid}/agent-runs/{rid}/sandbox/apply-patch")
        assert r.status_code == 200
        data = (await client.get(f"/api/tasks/{tid}/sandbox/gate")).json()["data"]
        reasons = [r["reason"] for r in data["blocked_reasons"]]
        assert data["passed"] is True
        assert "stale_sandbox_result" not in reasons

    # --- integration: POST ---
    async def test_post(self, client, project, agent):
        r = await client.post(BASE + "/tasks", json={
            "project_id": project["id"], "title": "int-post"})
        tid = r.json()["data"]["id"]
        await client.post(BASE + f"/tasks/{tid}/code-context", json={
            "files": [{"path": "src/util.py",
                       "content": "def util() -> str:\n    return \"ok\"\n",
                       "language": "python"}]})
        await client.post(BASE + f"/tasks/{tid}/generate-ticket", json={"actor": "test"})
        await client.post(BASE + f"/tasks/{tid}/dispatch", json={"actor": "test"})
        r = await client.post(BASE + f"/tasks/{tid}/agent-runs", json={
            "agent_id": agent["id"], "run_type": "execute", "input_prompt": "test"})
        rid = r.json()["data"]["id"]
        await client.patch(BASE + f"/tasks/{tid}/agent-runs/{rid}", json={"status": "running"})
        await client.post(BASE + f"/tasks/{tid}/agent-runs/{rid}/submit-result", json={
            "status": "succeeded", "output_summary": "ok", "output_log": "ok",
            "output_diff": ("diff --git a/src/util.py b/src/util.py\n"
                            "--- a/src/util.py\n+++ b/src/util.py\n"
                            "@@ -1,2 +1,3 @@\n def util() -> str:\n+    # updated\n     return \"ok\"\n")})
        r = await client.post(BASE + f"/tasks/{tid}/agent-runs/{rid}/sandbox/apply-patch")
        assert r.status_code == 200
        data = (await client.post(f"/api/tasks/{tid}/sandbox/evaluate-gate")).json()["data"]
        assert data["passed"] is True
        ev = (await client.get(BASE + f"/tasks/{tid}/events")).json()["data"]
        assert any(e["event_type"].startswith("sandbox_gate_") for e in ev)

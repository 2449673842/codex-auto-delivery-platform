"""Tests for Sandbox Approval Gate (v0.4 S3)."""
import json
import itertools
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.database import Base, get_engine, get_session_factory
from app.models.task import Task
from app.models.agent_run import AgentRun
from app.models.task_artifact import TaskArtifact
from app.models.approval_decision import ApprovalDecision


@pytest.fixture(autouse=True)
async def _reset_db():
    engine = get_engine()
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def cli():
    t = ASGITransport(app=app)
    async with AsyncClient(transport=t, base_url="https://x") as ac:
        yield ac


@pytest.fixture
async def db():
    f = get_session_factory()
    async with f() as s:
        yield s
        await s.rollback()


_ctr = iter(itertools.count())


def _rpt(applied=True, files=None, redacted=False):
    if files is None:
        files = [{"path": "x.py", "status": "modified", "additions": 3, "deletions": 1}]
    d = {"applied": applied, "changed_files": files, "warnings": [], "errors": []}
    if redacted:
        d["redacted"] = "***REDACTED***"
    return json.dumps(d, ensure_ascii=False)


async def _setup(cli):
    n = next(_ctr)
    r = await cli.post("/api/projects", json={"name": f"p{n}", "root_path": f"/p{n}"})
    pid = r.json()["data"]["id"]
    r = await cli.post("/api/agents", json={"name": f"a{n}", "agent_type": "executor", "provider": "local"})
    aid = r.json()["data"]["id"]
    r = await cli.post("/api/tasks", json={"project_id": pid, "title": f"t{n}"})
    tid = r.json()["data"]["id"]
    r = await cli.post(f"/api/tasks/{tid}/agent-runs",
                       json={"agent_id": aid, "run_type": "execute", "input_prompt": "go"})
    return {"pid": pid, "aid": aid, "tid": tid, "rid": r.json()["data"]["id"]}


async def _add_art(db, tid, rid, **kw):
    db.add(TaskArtifact(task_id=tid, artifact_type="patch_apply_report",
           content=_rpt(**kw), filename=f"patch_apply_report_run_{rid}.json"))
    await db.commit()


async def _reasons(cli, tid):
    g = await cli.get(f"/api/tasks/{tid}/sandbox/gate")
    return [x["reason"] for x in g.json()["data"]["blocked_reasons"]]


@pytest.mark.asyncio
class Tests:

    async def test_passed(self, cli, db):
        s = await _setup(cli)
        await _add_art(db, s["tid"], s["rid"])
        d = (await cli.get(f"/api/tasks/{s['tid']}/sandbox/gate")).json()["data"]
        assert d["passed"]
        assert len(d["blocked_reasons"]) == 0

    async def test_archived(self, cli, db):
        s = await _setup(cli)
        (await db.get(Task, s["tid"])).status = "archived"
        await _add_art(db, s["tid"], s["rid"])
        assert "archived_task" in await _reasons(cli, s["tid"])

    async def test_no_result(self, cli, db):
        s = await _setup(cli)
        assert "no_sandbox_result" in await _reasons(cli, s["tid"])

    async def test_not_applied(self, cli, db):
        s = await _setup(cli)
        await _add_art(db, s["tid"], s["rid"], applied=False)
        assert "sandbox_not_applied" in await _reasons(cli, s["tid"])

    async def test_no_files(self, cli, db):
        s = await _setup(cli)
        await _add_art(db, s["tid"], s["rid"], files=[])
        assert "no_changed_files" in await _reasons(cli, s["tid"])

    async def test_forbidden_path(self, cli, db):
        s = await _setup(cli)
        await _add_art(db, s["tid"], s["rid"], files=[{"path": ".env", "status": "modified"}])
        assert "forbidden_path" in await _reasons(cli, s["tid"])

    async def test_secret(self, cli, db):
        s = await _setup(cli)
        db.add(TaskArtifact(task_id=s["tid"], artifact_type="patch_apply_report",
               content=_rpt(redacted=True), filename=f"patch_apply_report_run_{s['rid']}.json"))
        await db.commit()
        assert "secret_detected" in await _reasons(cli, s["tid"])

    async def test_not_stale(self, cli, db):
        s = await _setup(cli)
        await _add_art(db, s["tid"], s["rid"])
        for t in ("changed_files_summary", "changed_file_preview"):
            db.add(TaskArtifact(task_id=s["tid"], artifact_type=t, content=_rpt(),
                                filename=f"{t}_run_{s['rid']}.json"))
        await db.commit()
        assert (await cli.get(f"/api/tasks/{s['tid']}/sandbox/gate")).json()["data"]["passed"]

    async def test_run_unknown(self, cli, db):
        s = await _setup(cli)
        db.add(TaskArtifact(task_id=s["tid"], artifact_type="patch_apply_report",
               content=_rpt(), filename="patch_apply_report.json"))
        await db.commit()
        assert "agent_run_unknown" in await _reasons(cli, s["tid"])

    async def test_wrong_task(self, cli, db):
        main = await _setup(cli)
        other = await _setup(cli)
        await _add_art(db, other["tid"], main["rid"])
        assert "agent_run_not_in_task" in await _reasons(cli, other["tid"])

    async def test_high_risk(self, cli, db):
        s = await _setup(cli)
        (await db.get(AgentRun, s["rid"])).risk_level = "high"
        await _add_art(db, s["tid"], s["rid"])
        assert "risk_too_high" in await _reasons(cli, s["tid"])

    async def test_human(self, cli, db):
        s = await _setup(cli)
        await _add_art(db, s["tid"], s["rid"])
        db.add(ApprovalDecision(task_id=s["tid"], human_required=True, auto_approve_allowed=False, risk_level="low"))
        await db.commit()
        assert "human_required" in await _reasons(cli, s["tid"])

    async def test_multiple(self, cli, db):
        s = await _setup(cli)
        (await db.get(Task, s["tid"])).status = "archived"
        (await db.get(AgentRun, s["rid"])).risk_level = "critical"
        db.add(TaskArtifact(task_id=s["tid"], artifact_type="patch_apply_report",
               content=_rpt(redacted=True), filename=f"patch_apply_report_run_{s['rid']}.json"))
        db.add(ApprovalDecision(task_id=s["tid"], human_required=True, auto_approve_allowed=False, risk_level="low"))
        await db.commit()
        r = await _reasons(cli, s["tid"])
        for w in ("archived_task", "risk_too_high", "secret_detected", "human_required"):
            assert w in r

    async def test_404(self, cli):
        assert (await cli.get("/api/tasks/99999/sandbox/gate")).status_code == 404

    async def test_integration_get(self, cli):
        s = await _setup(cli)
        await cli.post(f"/api/tasks/{s['tid']}/code-context", json={
            "files": [{"path": "src/g.py",
                       "content": "def g(n: str) -> str:\n    return f\"Hello, {n}!\"\n",
                       "language": "python"}]})
        await cli.post(f"/api/tasks/{s['tid']}/generate-ticket", json={"actor": "t"})
        await cli.post(f"/api/tasks/{s['tid']}/dispatch", json={"actor": "t"})
        await cli.patch(f"/api/tasks/{s['tid']}/agent-runs/{s['rid']}", json={"status": "running"})
        await cli.post(f"/api/tasks/{s['tid']}/agent-runs/{s['rid']}/submit-result", json={
            "status": "succeeded", "output_summary": "ok", "output_log": "ok",
            "output_diff": ("diff --git a/src/g.py b/src/g.py\n--- a/src/g.py\n+++ b/src/g.py\n"
                            "@@ -1,2 +1,5 @@\n def g(n: str) -> str:\n+    if n:\n     return f\"Hello, {n}!\"\n+    return \"Hello!\"\n")})
        assert (await cli.post(f"/api/tasks/{s['tid']}/agent-runs/{s['rid']}/sandbox/apply-patch")).status_code == 200
        d = (await cli.get(f"/api/tasks/{s['tid']}/sandbox/gate")).json()["data"]
        assert d["passed"]

    async def test_integration_post(self, cli):
        s = await _setup(cli)
        await cli.post(f"/api/tasks/{s['tid']}/code-context", json={
            "files": [{"path": "src/u.py",
                       "content": "def u() -> str:\n    return \"ok\"\n",
                       "language": "python"}]})
        await cli.post(f"/api/tasks/{s['tid']}/generate-ticket", json={"actor": "t"})
        await cli.post(f"/api/tasks/{s['tid']}/dispatch", json={"actor": "t"})
        await cli.patch(f"/api/tasks/{s['tid']}/agent-runs/{s['rid']}", json={"status": "running"})
        await cli.post(f"/api/tasks/{s['tid']}/agent-runs/{s['rid']}/submit-result", json={
            "status": "succeeded", "output_summary": "ok", "output_log": "ok",
            "output_diff": ("diff --git a/src/u.py b/src/u.py\n--- a/src/u.py\n+++ b/src/u.py\n"
                            "@@ -1,2 +1,3 @@\n def u() -> str:\n+    # updated\n     return \"ok\"\n")})
        assert (await cli.post(f"/api/tasks/{s['tid']}/agent-runs/{s['rid']}/sandbox/apply-patch")).status_code == 200
        assert (await cli.post(f"/api/tasks/{s['tid']}/sandbox/evaluate-gate")).json()["data"]["passed"]
        ev = (await cli.get(f"/api/tasks/{s['tid']}/events")).json()["data"]
        assert any(e["event_type"].startswith("sandbox_gate_") for e in ev)

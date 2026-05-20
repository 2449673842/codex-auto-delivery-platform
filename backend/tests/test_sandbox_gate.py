"""Sandbox Approval Gate tests (v0.4 S3)."""
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


# ── Helpers ──

def _report_json(applied=True, changed_files=None):
    if changed_files is None:
        changed_files = [{"path": "src/test.py", "status": "modified", "additions": 3, "deletions": 1}]
    return json.dumps({"applied": applied, "changed_files": changed_files, "warnings": [], "errors": []},
                      ensure_ascii=False)


def _redacted():
    return json.dumps({"applied": True, "redacted": "***REDACTED***",
                       "changed_files": [{"path": "src/test.py", "status": "modified"}],
                       "warnings": [], "errors": []}, ensure_ascii=False)


async def _add_report(db, tid, rid, **kw):
    art = TaskArtifact(task_id=tid, artifact_type="patch_apply_report",
                       content=_report_json(**kw), filename=f"patch_apply_report_run_{rid}.json")
    db.add(art)
    await db.commit()


async def _gate_data(client, tid):
    return (await client.get(f"/api/tasks/{tid}/sandbox/gate")).json()["data"]


def _reasons(data):
    return [r["reason"] for r in data["blocked_reasons"]]


async def _setup_sandbox(client, tid, aid, diff):
    await client.post(BASE + f"/tasks/{tid}/code-context", json={
        "files": [{"path": "src/util.py", "content": "def f() -> int:\n    return 1\n", "language": "python"}]})
    await client.post(BASE + f"/tasks/{tid}/generate-ticket", json={"actor": "test"})
    await client.post(BASE + f"/tasks/{tid}/dispatch", json={"actor": "test"})
    r = await client.post(BASE + f"/tasks/{tid}/agent-runs", json={
        "agent_id": aid, "run_type": "execute", "input_prompt": "test"})
    rid = r.json()["data"]["id"]
    await client.patch(BASE + f"/tasks/{tid}/agent-runs/{rid}", json={"status": "running"})
    await client.post(BASE + f"/tasks/{tid}/agent-runs/{rid}/submit-result", json={
        "status": "succeeded", "output_summary": "ok", "output_log": "ok", "output_diff": diff})
    r = await client.post(BASE + f"/tasks/{tid}/agent-runs/{rid}/sandbox/apply-patch")
    assert r.status_code == 200


# ── Fixtures ──

@pytest.fixture
async def project(client):
    r = await client.post(BASE + "/projects", json={"name": "gate-test", "root_path": "/gate"})
    return r.json()["data"]


@pytest.fixture
async def agent(client):
    r = await client.post(BASE + "/agents", json={"name": "gate-agent", "agent_type": "executor", "provider": "local"})
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


# ═══════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════

SIMPLE = [
    (True, None, None, True),
    (False, None, "sandbox_not_applied", False),
    (True, [], "no_changed_files", False),
    (True, [{"path": ".env", "status": "modified"}], "forbidden_path", False),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("applied,files,reason,passed", SIMPLE)
async def test_report_conditions(client, task, run, db_session, applied, files, reason, passed):
    await _add_report(db_session, task["id"], run["id"], applied=applied, changed_files=files)
    data = await _gate_data(client, task["id"])
    assert data["passed"] is passed
    assert data["can_prepare_pr"] is passed
    if passed:
        assert len(data["blocked_reasons"]) == 0
    else:
        assert reason in _reasons(data)


@pytest.mark.asyncio
async def test_archived_task(client, task, run, db_session):
    t = await db_session.get(Task, task["id"])
    t.status = "archived"
    await _add_report(db_session, task["id"], run["id"])
    assert "archived_task" in _reasons(await _gate_data(client, task["id"]))


@pytest.mark.asyncio
async def test_no_sandbox_result(client, task):
    assert "no_sandbox_result" in _reasons(await _gate_data(client, task["id"]))


@pytest.mark.asyncio
async def test_secret_detected(client, task, run, db_session):
    art = TaskArtifact(task_id=task["id"], artifact_type="patch_apply_report",
                       content=_redacted(), filename=f"patch_apply_report_run_{run['id']}.json")
    db_session.add(art)
    await db_session.commit()
    assert "secret_detected" in _reasons(await _gate_data(client, task["id"]))


@pytest.mark.asyncio
async def test_same_run_not_stale(client, task, run, db_session):
    await _add_report(db_session, task["id"], run["id"])
    for t in ("changed_files_summary", "changed_file_preview"):
        db_session.add(TaskArtifact(task_id=task["id"], artifact_type=t,
                                    content=_report_json(), filename=f"{t}_run_{run['id']}.json"))
    await db_session.commit()
    assert (await _gate_data(client, task["id"]))["passed"] is True


@pytest.mark.asyncio
async def test_agent_run_unknown(client, task, db_session):
    art = TaskArtifact(task_id=task["id"], artifact_type="patch_apply_report",
                       content=_report_json(), filename="patch_apply_report.json")
    db_session.add(art)
    await db_session.commit()
    assert "agent_run_unknown" in _reasons(await _gate_data(client, task["id"]))


@pytest.mark.asyncio
async def test_wrong_task_run(client, task, db_session, project, agent):
    r = await client.post(BASE + "/tasks", json={"project_id": project["id"], "title": "other"})
    other = r.json()["data"]["id"]
    r = await client.post(BASE + f"/tasks/{other}/agent-runs",
                          json={"agent_id": agent["id"], "run_type": "execute", "input_prompt": "test"})
    await _add_report(db_session, task["id"], r.json()["data"]["id"])
    assert "agent_run_not_in_task" in _reasons(await _gate_data(client, task["id"]))


@pytest.mark.asyncio
async def test_risk_too_high(client, task, run, db_session):
    r = await db_session.get(AgentRun, run["id"])
    r.risk_level = "high"
    await _add_report(db_session, task["id"], run["id"])
    assert "risk_too_high" in _reasons(await _gate_data(client, task["id"]))


@pytest.mark.asyncio
async def test_human_required(client, task, run, db_session):
    await _add_report(db_session, task["id"], run["id"])
    db_session.add(ApprovalDecision(task_id=task["id"], human_required=True, auto_approve_allowed=False, risk_level="low"))
    await db_session.commit()
    assert "human_required" in _reasons(await _gate_data(client, task["id"]))


@pytest.mark.asyncio
async def test_multiple_reasons(client, task, run, db_session):
    (await db_session.get(Task, task["id"])).status = "archived"
    (await db_session.get(AgentRun, run["id"])).risk_level = "critical"
    art = TaskArtifact(task_id=task["id"], artifact_type="patch_apply_report",
                       content=_redacted(), filename=f"patch_apply_report_run_{run['id']}.json")
    db_session.add(art)
    db_session.add(ApprovalDecision(task_id=task["id"], human_required=True, auto_approve_allowed=False, risk_level="low"))
    await db_session.commit()
    reasons = _reasons(await _gate_data(client, task["id"]))
    for r in ("archived_task", "risk_too_high", "secret_detected", "human_required"):
        assert r in reasons


@pytest.mark.asyncio
async def test_gate_404(client):
    assert (await client.get("/api/tasks/99999/sandbox/gate")).status_code == 404


# ── Integration ──

DIFF = ("diff --git a/src/util.py b/src/util.py\n"
        "--- a/src/util.py\n"
        "+++ b/src/util.py\n"
        "@@ -1,2 +1,3 @@\n"
        " def f() -> int:\n"
        "+    # updated\n"
        "     return 1\n")


@pytest.mark.asyncio
async def test_gate_passed_after_sandbox_apply(client, project, agent):
    r = await client.post(BASE + "/tasks", json={"project_id": project["id"], "title": "int-sandbox"})
    tid = r.json()["data"]["id"]
    await _setup_sandbox(client, tid, agent["id"], DIFF)
    assert (await _gate_data(client, tid))["passed"] is True


@pytest.mark.asyncio
async def test_post_writes_event(client, project, agent):
    r = await client.post(BASE + "/tasks", json={"project_id": project["id"], "title": "int-event"})
    tid = r.json()["data"]["id"]
    await _setup_sandbox(client, tid, agent["id"], DIFF)
    d = (await client.post(f"/api/tasks/{tid}/sandbox/evaluate-gate")).json()["data"]
    assert d["passed"] is True
    ev = (await client.get(BASE + f"/tasks/{tid}/events")).json()["data"]
    assert any(e["event_type"].startswith("sandbox_gate_") for e in ev)

"""Sandbox Approval Gate tests (v0.4 S3)."""
import json, pytest
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
    factory = get_session_factory()
    async with factory() as s:
        yield s
        await s.rollback()


@pytest.mark.asyncio
async def test_passed(cli, db):
    r0 = await cli.post("/api/projects", json={"name": "p0", "root_path": "/p0"})
    pid = r0.json()["data"]["id"]
    r1 = await cli.post("/api/agents", json={"name": "a0", "agent_type": "executor", "provider": "local"})
    aid = r1.json()["data"]["id"]
    r2 = await cli.post("/api/tasks", json={"project_id": pid, "title": "passed"})
    tid = r2.json()["data"]["id"]
    r3 = await cli.post(f"/api/tasks/{tid}/agent-runs", json={"agent_id": aid, "run_type": "execute", "input_prompt": "test"})
    rid = r3.json()["data"]["id"]
    art = TaskArtifact(task_id=tid, artifact_type="patch_apply_report",
                       content=json.dumps({"applied": True, "changed_files": [{"path": "a.py", "status": "modified", "additions": 1, "deletions": 0}], "warnings": [], "errors": []}),
                       filename=f"patch_apply_report_run_{rid}.json")
    db.add(art)
    await db.commit()
    d = (await cli.get(f"/api/tasks/{tid}/sandbox/gate")).json()["data"]
    assert d["passed"] is True
    assert len(d["blocked_reasons"]) == 0


@pytest.mark.asyncio
async def test_archived(cli, db):
    r0 = await cli.post("/api/projects", json={"name": "p1", "root_path": "/p1"})
    pid = r0.json()["data"]["id"]
    r1 = await cli.post("/api/tasks", json={"project_id": pid, "title": "archived"})
    t = await db.get(Task, r1.json()["data"]["id"])
    t.status = "archived"
    r2 = await cli.post("/api/agents", json={"name": "a1", "agent_type": "executor", "provider": "local"})
    aid = r2.json()["data"]["id"]
    r3 = await cli.post(f"/api/tasks/{t.id}/agent-runs", json={"agent_id": aid, "run_type": "execute", "input_prompt": "test"})
    rid = r3.json()["data"]["id"]
    db.add(TaskArtifact(task_id=t.id, artifact_type="patch_apply_report",
           content=json.dumps({"applied": True, "changed_files": [{"path": "b.py", "status": "modified", "additions": 2, "deletions": 1}], "warnings": [], "errors": []}),
           filename=f"patch_apply_report_run_{rid}.json"))
    await db.commit()
    reasons = [r["reason"] for r in (await cli.get(f"/api/tasks/{t.id}/sandbox/gate")).json()["data"]["blocked_reasons"]]
    assert "archived_task" in reasons


@pytest.mark.asyncio
async def test_no_result(cli):
    r0 = await cli.post("/api/projects", json={"name": "p2", "root_path": "/p2"})
    pid = r0.json()["data"]["id"]
    r1 = await cli.post("/api/tasks", json={"project_id": pid, "title": "no-result"})
    tid = r1.json()["data"]["id"]
    reasons = [r["reason"] for r in (await cli.get(f"/api/tasks/{tid}/sandbox/gate")).json()["data"]["blocked_reasons"]]
    assert "no_sandbox_result" in reasons


@pytest.mark.asyncio
async def test_not_applied(cli, db):
    r0 = await cli.post("/api/projects", json={"name": "p3", "root_path": "/p3"})
    pid = r0.json()["data"]["id"]
    r1 = await cli.post("/api/agents", json={"name": "a2", "agent_type": "executor", "provider": "local"})
    aid = r1.json()["data"]["id"]
    r2 = await cli.post("/api/tasks", json={"project_id": pid, "title": "not-applied"})
    tid = r2.json()["data"]["id"]
    r3 = await cli.post(f"/api/tasks/{tid}/agent-runs", json={"agent_id": aid, "run_type": "execute", "input_prompt": "test"})
    rid = r3.json()["data"]["id"]
    db.add(TaskArtifact(task_id=tid, artifact_type="patch_apply_report",
           content=json.dumps({"applied": False, "changed_files": [], "warnings": [], "errors": ["failed"]}),
           filename=f"patch_apply_report_run_{rid}.json"))
    await db.commit()
    reasons = [r["reason"] for r in (await cli.get(f"/api/tasks/{tid}/sandbox/gate")).json()["data"]["blocked_reasons"]]
    assert "sandbox_not_applied" in reasons


@pytest.mark.asyncio
async def test_no_files(cli, db):
    r0 = await cli.post("/api/projects", json={"name": "p4", "root_path": "/p4"})
    pid = r0.json()["data"]["id"]
    r1 = await cli.post("/api/agents", json={"name": "a3", "agent_type": "executor", "provider": "local"})
    aid = r1.json()["data"]["id"]
    r2 = await cli.post("/api/tasks", json={"project_id": pid, "title": "no-files"})
    tid = r2.json()["data"]["id"]
    r3 = await cli.post(f"/api/tasks/{tid}/agent-runs", json={"agent_id": aid, "run_type": "execute", "input_prompt": "test"})
    rid = r3.json()["data"]["id"]
    db.add(TaskArtifact(task_id=tid, artifact_type="patch_apply_report",
           content=json.dumps({"applied": True, "changed_files": [], "warnings": [], "errors": []}),
           filename=f"patch_apply_report_run_{rid}.json"))
    await db.commit()
    reasons = [r["reason"] for r in (await cli.get(f"/api/tasks/{tid}/sandbox/gate")).json()["data"]["blocked_reasons"]]
    assert "no_changed_files" in reasons


@pytest.mark.asyncio
async def test_forbidden_path(cli, db):
    r0 = await cli.post("/api/projects", json={"name": "p5", "root_path": "/p5"})
    pid = r0.json()["data"]["id"]
    r1 = await cli.post("/api/tasks", json={"project_id": pid, "title": "forbidden"})
    tid = r1.json()["data"]["id"]
    r2 = await cli.post("/api/agents", json={"name": "a4", "agent_type": "executor", "provider": "local"})
    aid = r2.json()["data"]["id"]
    r3 = await cli.post(f"/api/tasks/{tid}/agent-runs", json={"agent_id": aid, "run_type": "execute", "input_prompt": "test"})
    rid = r3.json()["data"]["id"]
    db.add(TaskArtifact(task_id=tid, artifact_type="patch_apply_report",
           content=json.dumps({"applied": True, "changed_files": [{"path": ".env", "status": "modified"}], "warnings": [], "errors": []}),
           filename=f"patch_apply_report_run_{rid}.json"))
    await db.commit()
    reasons = [r["reason"] for r in (await cli.get(f"/api/tasks/{tid}/sandbox/gate")).json()["data"]["blocked_reasons"]]
    assert "forbidden_path" in reasons


@pytest.mark.asyncio
async def test_secret(cli, db):
    r0 = await cli.post("/api/projects", json={"name": "p6", "root_path": "/p6"})
    pid = r0.json()["data"]["id"]
    r1 = await cli.post("/api/tasks", json={"project_id": pid, "title": "secret"})
    tid = r1.json()["data"]["id"]
    r2 = await cli.post("/api/agents", json={"name": "a5", "agent_type": "executor", "provider": "local"})
    aid = r2.json()["data"]["id"]
    r3 = await cli.post(f"/api/tasks/{tid}/agent-runs", json={"agent_id": aid, "run_type": "execute", "input_prompt": "test"})
    rid = r3.json()["data"]["id"]
    db.add(TaskArtifact(task_id=tid, artifact_type="patch_apply_report",
           content=json.dumps({"applied": True, "redacted": "***REDACTED***", "changed_files": [{"path": "x.py", "status": "modified"}], "warnings": [], "errors": []}),
           filename=f"patch_apply_report_run_{rid}.json"))
    await db.commit()
    reasons = [r["reason"] for r in (await cli.get(f"/api/tasks/{tid}/sandbox/gate")).json()["data"]["blocked_reasons"]]
    assert "secret_detected" in reasons


@pytest.mark.asyncio
async def test_same_run_not_stale(cli, db):
    r0 = await cli.post("/api/projects", json={"name": "p7", "root_path": "/p7"})
    pid = r0.json()["data"]["id"]
    r1 = await cli.post("/api/tasks", json={"project_id": pid, "title": "not-stale"})
    tid = r1.json()["data"]["id"]
    r2 = await cli.post("/api/agents", json={"name": "a6", "agent_type": "executor", "provider": "local"})
    aid = r2.json()["data"]["id"]
    r3 = await cli.post(f"/api/tasks/{tid}/agent-runs", json={"agent_id": aid, "run_type": "execute", "input_prompt": "test"})
    rid = r3.json()["data"]["id"]
    for a_type in ("patch_apply_report", "changed_files_summary", "changed_file_preview"):
        db.add(TaskArtifact(task_id=tid, artifact_type=a_type,
               content=json.dumps({"applied": True, "changed_files": [{"path": "y.py", "status": "modified", "additions": 1, "deletions": 0}], "warnings": [], "errors": []}),
               filename=f"{a_type}_run_{rid}.json"))
    await db.commit()
    data = (await cli.get(f"/api/tasks/{tid}/sandbox/gate")).json()["data"]
    assert data["passed"] is True
    assert "stale_sandbox_result" not in [r["reason"] for r in data["blocked_reasons"]]


@pytest.mark.asyncio
async def test_run_unknown(cli, db):
    r0 = await cli.post("/api/projects", json={"name": "p8", "root_path": "/p8"})
    pid = r0.json()["data"]["id"]
    r1 = await cli.post("/api/tasks", json={"project_id": pid, "title": "unknown"})
    tid = r1.json()["data"]["id"]
    db.add(TaskArtifact(task_id=tid, artifact_type="patch_apply_report",
           content=json.dumps({"applied": True, "changed_files": [], "warnings": [], "errors": []}),
           filename="patch_apply_report.json"))
    await db.commit()
    reasons = [r["reason"] for r in (await cli.get(f"/api/tasks/{tid}/sandbox/gate")).json()["data"]["blocked_reasons"]]
    assert "agent_run_unknown" in reasons


@pytest.mark.asyncio
async def test_wrong_task(cli, db):
    r0 = await cli.post("/api/projects", json={"name": "p9", "root_path": "/p9"})
    pid = r0.json()["data"]["id"]
    r1 = await cli.post("/api/tasks", json={"project_id": pid, "title": "main"})
    main_tid = r1.json()["data"]["id"]
    r2 = await cli.post("/api/tasks", json={"project_id": pid, "title": "other"})
    other_tid = r2.json()["data"]["id"]
    r3 = await cli.post("/api/agents", json={"name": "a7", "agent_type": "executor", "provider": "local"})
    aid = r3.json()["data"]["id"]
    r4 = await cli.post(f"/api/tasks/{main_tid}/agent-runs", json={"agent_id": aid, "run_type": "execute", "input_prompt": "test"})
    cross_rid = r4.json()["data"]["id"]
    db.add(TaskArtifact(task_id=other_tid, artifact_type="patch_apply_report",
           content=json.dumps({"applied": True, "changed_files": [{"path": "z.py", "status": "modified", "additions": 3, "deletions": 0}], "warnings": [], "errors": []}),
           filename=f"patch_apply_report_run_{cross_rid}.json"))
    await db.commit()
    reasons = [r["reason"] for r in (await cli.get(f"/api/tasks/{other_tid}/sandbox/gate")).json()["data"]["blocked_reasons"]]
    assert "agent_run_not_in_task" in reasons


@pytest.mark.asyncio
async def test_high_risk(cli, db):
    r0 = await cli.post("/api/projects", json={"name": "pa", "root_path": "/pa"})
    pid = r0.json()["data"]["id"]
    r1 = await cli.post("/api/tasks", json={"project_id": pid, "title": "high-risk"})
    tid = r1.json()["data"]["id"]
    r2 = await cli.post("/api/agents", json={"name": "a8", "agent_type": "executor", "provider": "local"})
    aid = r2.json()["data"]["id"]
    r3 = await cli.post(f"/api/tasks/{tid}/agent-runs", json={"agent_id": aid, "run_type": "execute", "input_prompt": "test"})
    rid = r3.json()["data"]["id"]
    (await db.get(AgentRun, rid)).risk_level = "high"
    db.add(TaskArtifact(task_id=tid, artifact_type="patch_apply_report",
           content=json.dumps({"applied": True, "changed_files": [{"path": "w.py", "status": "modified", "additions": 5, "deletions": 2}], "warnings": [], "errors": []}),
           filename=f"patch_apply_report_run_{rid}.json"))
    await db.commit()
    reasons = [r["reason"] for r in (await cli.get(f"/api/tasks/{tid}/sandbox/gate")).json()["data"]["blocked_reasons"]]
    assert "risk_too_high" in reasons


@pytest.mark.asyncio
async def test_human_review(cli, db):
    r0 = await cli.post("/api/projects", json={"name": "pb", "root_path": "/pb"})
    pid = r0.json()["data"]["id"]
    r1 = await cli.post("/api/tasks", json={"project_id": pid, "title": "human"})
    tid = r1.json()["data"]["id"]
    r2 = await cli.post("/api/agents", json={"name": "a9", "agent_type": "executor", "provider": "local"})
    aid = r2.json()["data"]["id"]
    r3 = await cli.post(f"/api/tasks/{tid}/agent-runs", json={"agent_id": aid, "run_type": "execute", "input_prompt": "test"})
    rid = r3.json()["data"]["id"]
    db.add(TaskArtifact(task_id=tid, artifact_type="patch_apply_report",
           content=json.dumps({"applied": True, "changed_files": [{"path": "v.py", "status": "modified", "additions": 0, "deletions": 1}], "warnings": [], "errors": []}),
           filename=f"patch_apply_report_run_{rid}.json"))
    db.add(ApprovalDecision(task_id=tid, human_required=True, auto_approve_allowed=False, risk_level="low"))
    await db.commit()
    reasons = [r["reason"] for r in (await cli.get(f"/api/tasks/{tid}/sandbox/gate")).json()["data"]["blocked_reasons"]]
    assert "human_required" in reasons


@pytest.mark.asyncio
async def test_multiple_blocks(cli, db):
    r0 = await cli.post("/api/projects", json={"name": "pc", "root_path": "/pc"})
    pid = r0.json()["data"]["id"]
    r1 = await cli.post("/api/tasks", json={"project_id": pid, "title": "multi"})
    t = await db.get(Task, r1.json()["data"]["id"])
    t.status = "archived"
    r2 = await cli.post("/api/agents", json={"name": "aa", "agent_type": "executor", "provider": "local"})
    aid = r2.json()["data"]["id"]
    r3 = await cli.post(f"/api/tasks/{t.id}/agent-runs", json={"agent_id": aid, "run_type": "execute", "input_prompt": "test"})
    rid = r3.json()["data"]["id"]
    (await db.get(AgentRun, rid)).risk_level = "critical"
    db.add(TaskArtifact(task_id=t.id, artifact_type="patch_apply_report",
           content=json.dumps({"applied": True, "redacted": "***REDACTED***", "changed_files": [{"path": "u.py", "status": "modified"}], "warnings": [], "errors": []}),
           filename=f"patch_apply_report_run_{rid}.json"))
    db.add(ApprovalDecision(task_id=t.id, human_required=True, auto_approve_allowed=False, risk_level="low"))
    await db.commit()
    reasons = [r["reason"] for r in (await cli.get(f"/api/tasks/{t.id}/sandbox/gate")).json()["data"]["blocked_reasons"]]
    for want in ("archived_task", "risk_too_high", "secret_detected", "human_required"):
        assert want in reasons


@pytest.mark.asyncio
async def test_404(cli):
    assert (await cli.get("/api/tasks/99999/sandbox/gate")).status_code == 404


@pytest.mark.asyncio
async def test_sandbox_integration(cli):
    r0 = await cli.post("/api/projects", json={"name": "pd", "root_path": "/pd"})
    pid = r0.json()["data"]["id"]
    r1 = await cli.post("/api/tasks", json={"project_id": pid, "title": "sandbox-int"})
    tid = r1.json()["data"]["id"]
    r2 = await cli.post("/api/agents", json={"name": "ab", "agent_type": "executor", "provider": "local"})
    aid = r2.json()["data"]["id"]
    await cli.post(f"/api/tasks/{tid}/code-context", json={
        "files": [{"path": "src/util.py", "content": "def f() -> int:\n    return 1\n", "language": "python"}]})
    await cli.post(f"/api/tasks/{tid}/generate-ticket", json={"actor": "test"})
    await cli.post(f"/api/tasks/{tid}/dispatch", json={"actor": "test"})
    r3 = await cli.post(f"/api/tasks/{tid}/agent-runs", json={"agent_id": aid, "run_type": "execute", "input_prompt": "test"})
    rid = r3.json()["data"]["id"]
    await cli.patch(f"/api/tasks/{tid}/agent-runs/{rid}", json={"status": "running"})
    await cli.post(f"/api/tasks/{tid}/agent-runs/{rid}/submit-result", json={
        "status": "succeeded", "output_summary": "ok", "output_log": "ok",
        "output_diff": ("diff --git a/src/util.py b/src/util.py\n"
                        "--- a/src/util.py\n+++ b/src/util.py\n"
                        "@@ -1,2 +1,3 @@\n def f() -> int:\n+    # updated\n     return 1\n")})
    r4 = await cli.post(f"/api/tasks/{tid}/agent-runs/{rid}/sandbox/apply-patch")
    assert r4.status_code == 200
    data = (await cli.get(f"/api/tasks/{tid}/sandbox/gate")).json()["data"]
    assert data["passed"] is True


@pytest.mark.asyncio
async def test_post_evaluate(cli):
    r0 = await cli.post("/api/projects", json={"name": "pe", "root_path": "/pe"})
    pid = r0.json()["data"]["id"]
    r1 = await cli.post("/api/tasks", json={"project_id": pid, "title": "post-gate"})
    tid = r1.json()["data"]["id"]
    r2 = await cli.post("/api/agents", json={"name": "ac", "agent_type": "executor", "provider": "local"})
    aid = r2.json()["data"]["id"]
    await cli.post(f"/api/tasks/{tid}/code-context", json={
        "files": [{"path": "src/util.py", "content": "def f() -> int:\n    return 1\n", "language": "python"}]})
    await cli.post(f"/api/tasks/{tid}/generate-ticket", json={"actor": "test"})
    await cli.post(f"/api/tasks/{tid}/dispatch", json={"actor": "test"})
    r3 = await cli.post(f"/api/tasks/{tid}/agent-runs", json={"agent_id": aid, "run_type": "execute", "input_prompt": "test"})
    rid = r3.json()["data"]["id"]
    await cli.patch(f"/api/tasks/{tid}/agent-runs/{rid}", json={"status": "running"})
    await cli.post(f"/api/tasks/{tid}/agent-runs/{rid}/submit-result", json={
        "status": "succeeded", "output_summary": "ok", "output_log": "ok",
        "output_diff": ("diff --git a/src/util.py b/src/util.py\n"
                        "--- a/src/util.py\n+++ b/src/util.py\n"
                        "@@ -1,2 +1,3 @@\n def f() -> int:\n+    # updated\n     return 1\n")})
    r4 = await cli.post(f"/api/tasks/{tid}/agent-runs/{rid}/sandbox/apply-patch")
    assert r4.status_code == 200
    d = (await cli.post(f"/api/tasks/{tid}/sandbox/evaluate-gate")).json()["data"]
    assert d["passed"] is True
    ev = (await cli.get(f"/api/tasks/{tid}/events")).json()["data"]
    assert any(e["event_type"].startswith("sandbox_gate_") for e in ev)

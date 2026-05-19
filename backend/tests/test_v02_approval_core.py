"""v0.2 S5-S6: Approval Evaluation + Auto Approve Tests"""
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.database import Base, get_engine

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
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest.fixture
async def project(client) -> dict:
    r = await client.post(BASE + "/projects", json={"name": "approval-test", "root_path": "/test"})
    return r.json()["data"]

@pytest.fixture
async def task(client, project) -> dict:
    r = await client.post(BASE + "/tasks", json={"project_id": project["id"], "title": "approval-task", "planner": "test"})
    return r.json()["data"]

@pytest.fixture
async def policy(client) -> dict:
    r = await client.post(BASE + "/approval-policies", json={"name": "default"})
    return r.json()["data"]

@pytest.fixture
async def agent(client) -> dict:
    r = await client.post(BASE + "/agents", json={"name": "test-agent", "agent_type": "reviewer", "provider": "manual"})
    return r.json()["data"]

t_actor = {"actor": "test"}

@pytest.mark.asyncio
async def test_evaluate_approval_creates_decision(client, task):
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={})
    assert r.status_code == 200
    assert r.json()["data"]["risk_level"] is not None

@pytest.mark.asyncio
async def test_low_risk_auto_approve_allowed(client, task):
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"tests_passed": True, "security_issues_found": False})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["risk_level"] == "low"
    assert d["auto_approve_allowed"] is True
    assert d["human_required"] is False

@pytest.mark.asyncio
async def test_high_risk_from_security_issues(client, task):
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"security_issues_found": True})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["risk_level"] in ("high", "critical")
    assert d["human_required"] is True

@pytest.mark.asyncio
async def test_high_risk_from_tests_failed(client, task):
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"tests_passed": False})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["risk_level"] in ("high", "critical")
    assert d["human_required"] is True

@pytest.mark.asyncio
async def test_high_risk_from_sonar_failed(client, task):
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"sonar_passed": False})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["risk_level"] in ("high", "critical")
    assert d["human_required"] is True

@pytest.mark.asyncio
async def test_critical_from_subprocess(client, task):
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"diff_summary": "subprocess.call"})
    assert r.status_code == 200
    assert r.json()["data"]["risk_level"] == "critical"

@pytest.mark.asyncio
async def test_critical_from_plaintext_secret(client, task):
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"diff_summary": "api_key = 'sk-test12345678901234567890'"})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["risk_level"] == "critical"

@pytest.mark.asyncio
async def test_tests_not_passed_blocked(client, task, policy):
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"tests_passed": False, "policy_id": policy['id']})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["auto_approve_allowed"] is False
    assert d["human_required"] is True

@pytest.mark.asyncio
async def test_tests_missing_blocked(client, task):
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"tests_passed": None})
    assert r.status_code == 200
    assert r.json()["data"]["human_required"] is True

@pytest.mark.asyncio
async def test_security_issues_blocked(client, task):
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"tests_passed": True, "security_issues_found": True})
    assert r.status_code == 200
    assert r.json()["data"]["human_required"] is True

@pytest.mark.asyncio
async def test_agent_run_wrong_task_404(client, task, project, agent):
    r = await client.post(BASE + "/tasks", json={"project_id": project["id"], "title": "other", "planner": "test"})
    other = r.json()["data"]
    r = await client.post(BASE + f"/tasks/{task['id']}/agent-runs", json={"agent_id": agent['id'], "run_type": "test"})
    rid = r.json()["data"]["id"]
    r = await client.post(BASE + f"/tasks/{other['id']}/evaluate-approval", json={"agent_run_id": rid})
    assert r.status_code == 404

@pytest.mark.asyncio
async def test_agent_review_wrong_task_404(client, task, project, agent):
    r = await client.post(BASE + "/tasks", json={"project_id": project["id"], "title": "other", "planner": "test"})
    other = r.json()["data"]
    r = await client.post(BASE + f"/tasks/{task['id']}/agent-runs", json={"agent_id": agent['id'], "run_type": "review"})
    rid = r.json()["data"]["id"]
    await client.patch(BASE + f"/tasks/{task['id']}/agent-runs/{rid}", json={"status": "running"})
    await client.post(BASE + f"/tasks/{task['id']}/agent-runs/{rid}/submit-result", json={"status": "succeeded"})
    rv = await client.post(BASE + f"/tasks/{task['id']}/agent-runs/{rid}/review", json={"reviewer_agent_id": agent['id'], "decision": "approved", "confidence_score": 0.9})
    rev_id = rv.json()["data"]["id"]
    r = await client.post(BASE + f"/tasks/{other['id']}/evaluate-approval", json={"agent_review_id": rev_id})
    assert r.status_code == 404

@pytest.mark.asyncio
async def test_archived_task_evaluate_409(client, task):
    a = t_actor
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=a)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=a)
    await client.post(BASE + f"/tasks/{task['id']}/submit-result", json=a)
    await client.post(BASE + f"/tasks/{task['id']}/start-review", json=a)
    await client.post(BASE + f"/tasks/{task['id']}/approve", json=a)
    await client.post(BASE + f"/tasks/{task['id']}/archive", json=a)
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={})
    assert r.status_code == 409

@pytest.mark.asyncio
async def test_auto_approve_only_reviewing(client, task):
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"tests_passed": True, "security_issues_found": False})
    did = r.json()["data"]["id"]
    r = await client.post(BASE + f"/tasks/{task['id']}/auto-approve", json={"approval_decision_id": did})
    assert r.status_code == 409

@pytest.mark.asyncio
async def test_auto_approve_success(client, task):
    a = t_actor
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=a)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=a)
    await client.post(BASE + f"/tasks/{task['id']}/submit-result", json=a)
    await client.post(BASE + f"/tasks/{task['id']}/start-review", json=a)
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"tests_passed": True, "security_issues_found": False, "actor": "ai1"})
    did = r.json()["data"]["id"]
    r = await client.post(BASE + f"/tasks/{task['id']}/auto-approve", json={"approval_decision_id": did, "actor": "ai1"})
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "approved"

@pytest.mark.asyncio
async def test_auto_approve_human_required_state_409(client, task):
    a = t_actor
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=a)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=a)
    await client.post(BASE + f"/tasks/{task['id']}/submit-result", json=a)
    await client.post(BASE + f"/tasks/{task['id']}/start-review", json=a)
    await client.post(BASE + f"/tasks/{task['id']}/require-human-approval", json=a)
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"tests_passed": True, "security_issues_found": False})
    did = r.json()["data"]["id"]
    r = await client.post(BASE + f"/tasks/{task['id']}/auto-approve", json={"approval_decision_id": did})
    assert r.status_code == 409

@pytest.mark.asyncio
async def test_auto_approve_high_risk_409(client, task):
    a = t_actor
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=a)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=a)
    await client.post(BASE + f"/tasks/{task['id']}/submit-result", json=a)
    await client.post(BASE + f"/tasks/{task['id']}/start-review", json=a)
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"security_issues_found": True})
    did = r.json()["data"]["id"]
    r = await client.post(BASE + f"/tasks/{task['id']}/auto-approve", json={"approval_decision_id": did})
    assert r.status_code == 409

@pytest.mark.asyncio
async def test_auto_approve_critical_risk_409(client, task):
    a = t_actor
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=a)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=a)
    await client.post(BASE + f"/tasks/{task['id']}/submit-result", json=a)
    await client.post(BASE + f"/tasks/{task['id']}/start-review", json=a)
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"diff_summary": "subprocess.call"})
    did = r.json()["data"]["id"]
    r = await client.post(BASE + f"/tasks/{task['id']}/auto-approve", json={"approval_decision_id": did})
    assert r.status_code == 409

@pytest.mark.asyncio
async def test_risk_assessed_event_written(client, task):
    await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"actor": "test"})
    r = await client.get(BASE + f"/tasks/{task['id']}/events")
    types = [e["event_type"] for e in r.json()["data"]]
    assert "risk_assessed" in types

@pytest.mark.asyncio
async def test_auto_approval_blocked_event(client, task):
    await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"security_issues_found": True, "actor": "test"})
    r = await client.get(BASE + f"/tasks/{task['id']}/events")
    types = [e["event_type"] for e in r.json()["data"]]
    assert "auto_approval_blocked" in types
    assert "human_approval_required" in types

@pytest.mark.asyncio
async def test_auto_approval_granted_event(client, task):
    a = t_actor
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=a)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=a)
    await client.post(BASE + f"/tasks/{task['id']}/submit-result", json=a)
    await client.post(BASE + f"/tasks/{task['id']}/start-review", json=a)
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"tests_passed": True, "security_issues_found": False, "actor": "ai1"})
    did = r.json()["data"]["id"]
    await client.post(BASE + f"/tasks/{task['id']}/auto-approve", json={"approval_decision_id": did, "actor": "ai1"})
    r = await client.get(BASE + f"/tasks/{task['id']}/events")
    types = [e["event_type"] for e in r.json()["data"]]
    assert "auto_approval_granted" in types


@pytest.mark.asyncio
async def test_default_policy_blocks_missing_security(client, task):
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"tests_passed": True})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["auto_approve_allowed"] is False
    assert d["human_required"] is True


@pytest.mark.asyncio
async def test_default_policy_allows_full_low_risk(client, task):
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"tests_passed": True, "security_issues_found": False})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["risk_level"] == "low"
    assert d["auto_approve_allowed"] is True
    assert d["human_required"] is False


@pytest.mark.asyncio
async def test_default_policy_snapshot_correct(client, task):
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["decision_reason"] == "default (memory)"
    assert d["auto_approve_allowed"] is False
    assert d["human_required"] is True
    r2 = await client.get(BASE + f"/tasks/{task['id']}/approval-decisions")
    decisions = r2.json()["data"]
    assert len(decisions) >= 1

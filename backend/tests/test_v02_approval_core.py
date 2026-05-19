"""v0.2 S5-S6: Approval Evaluation + Auto Approve  Tests"""
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
async def test_medium_risk_human_required(client, task):
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"tests_passed": True, "security_issues_found": True})
    assert r.status_code == 200
    assert r.json()["data"]["human_required"] is True

@pytest.mark.asyncio
async def test_high_risk_human_required(client, task):
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"diff_summary": "ALTER TABLE users ADD COLUMN token"})
    assert r.status_code == 200
    assert r.json()["data"]["risk_level"] in ("high", "critical")

@pytest.mark.asyncio
async def test_critical_risk_human_required(client, task):
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"diff_summary": "subprocess.call"})
    assert r.status_code == 200
    assert r.json()["data"]["risk_level"] == "critical"

@pytest.mark.asyncio
async def test_tests_not_passed_blocked(client, task, policy):
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"tests_passed": False, "policy_id": policy["id"]})
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
async def test_sonar_failed_blocked(client, task):
    r = await client.post(BASE + "/approval-policies", json={"name": "sonar-pol", "require_sonar_passed": True})
    pid = r.json()["data"]["id"]
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"tests_passed": True, "sonar_passed": False, "policy_id": pid})
    assert r.status_code == 200
    assert r.json()["data"]["human_required"] is True

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
async def test_auto_approve_human_required_decision_409(client, task):
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
async def test_auto_approve_wrong_decision_task_404(client, task, project):
    r = await client.post(BASE + "/tasks", json={"project_id": project["id"], "title": "other", "planner": "test"})
    other = r.json()["data"]
    a = t_actor
    await client.post(BASE + f"/tasks/{other['id']}/generate-ticket", json=a)
    await client.post(BASE + f"/tasks/{other['id']}/dispatch", json=a)
    await client.post(BASE + f"/tasks/{other['id']}/submit-result", json=a)
    await client.post(BASE + f"/tasks/{other['id']}/start-review", json=a)
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"tests_passed": True, "security_issues_found": False})
    did = r.json()["data"]["id"]
    r = await client.post(BASE + f"/tasks/{other['id']}/auto-approve", json={"approval_decision_id": did})
    assert r.status_code == 404

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

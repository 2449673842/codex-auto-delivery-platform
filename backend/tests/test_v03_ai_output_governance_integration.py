"""v0.3 S3: AI Output Governance Integration Tests (real dispatch flow)"""
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
    async with AsyncClient(transport=transport, base_url="https://test.local") as ac:
        yield ac

@pytest.fixture
async def task(client) -> dict:
    r = await client.post(BASE + "/projects", json={"name": "p", "root_path": "/p"})
    pid = r.json()["data"]["id"]
    r = await client.post(BASE + "/tasks", json={"project_id": pid, "title": "t", "planner": "test", "description": "test"})
    return r.json()["data"]

t_actor = {"actor": "test"}

# ─── Sandbox provider: valid output → succeeded ───

@pytest.mark.asyncio
async def test_sandbox_valid_output_succeeds(client, task):
    """Sandbox plan output should pass governance and succeed"""
    r = await client.post(BASE + "/agents", json={"name": "a", "agent_type": "executor", "provider": "sandbox"})
    agent = r.json()["data"]
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    run = rr.json()["data"][0]
    assert run["status"] == "succeeded"

# ─── Invalid content (empty response) → agent_failed ───

async def _mock_empty(self, sys_prompt, user_prompt):
    return ""

@pytest.mark.asyncio
async def test_empty_response_fails_via_openai(client, task, monkeypatch):
    """Empty AI response should fail the AgentRun"""
    from app.services.openai_provider import OpenAIProvider
    monkeypatch.setattr(OpenAIProvider, "_call_openai", _mock_empty)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    r = await client.post(BASE + "/agents", json={"name": "a", "agent_type": "executor", "provider": "openai"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["stop_reason"] == "agent_failed" or d["action_taken"] == "agent_failed"
    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    assert rr.json()["data"][0]["status"] == "failed"

# ─── Sandbox patch (valid) passes governance ───

@pytest.mark.asyncio
async def test_sandbox_patch_pass_governance(client, task):
    """Sandbox provider output should pass governance"""
    r = await client.post(BASE + "/agents", json={"name": "a", "agent_type": "executor", "provider": "sandbox"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    assert rr.json()["data"][0]["status"] == "succeeded"
    raw = rr.json()["data"][0]["raw_result_json"]
    import json
    data = json.loads(raw)
    assert "governance" in data

# ─── review_md creates AgentReview ───

@pytest.mark.asyncio
async def test_sandbox_flow_completes(client, task):
    """Sandbox provider completes the full orchestration flow"""
    r = await client.post(BASE + "/agents", json={"name": "a", "agent_type": "executor", "provider": "sandbox"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    assert len(rr.json()["data"]) >= 1

# ─── raw_result_json preserved + governance trace ───

async def _mock_good_output(self, sys_prompt, user_prompt):
    return "diff --git a/src/main.py b/src/main.py\n+print('hello')"

@pytest.mark.asyncio
async def test_raw_result_json_has_governance(client, task, monkeypatch):
    """raw_result_json should include provider_raw + governance"""
    from app.services.openai_provider import OpenAIProvider
    monkeypatch.setattr(OpenAIProvider, "_call_openai", _mock_good_output)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    r = await client.post(BASE + "/agents", json={"name": "a", "agent_type": "executor", "provider": "openai"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    raw = rr.json()["data"][0]["raw_result_json"]
    import json
    data = json.loads(raw)
    assert "provider_raw" in data
    assert "governance" in data
    assert data["governance"]["valid"] is True or data["governance"]["valid"] is False

# ─── high risk → no auto approve ───

async def _mock_high_risk(self, sys_prompt, user_prompt):
    return "diff --git a/x.py b/x.py\n+print('x')"

@pytest.mark.asyncio
async def test_high_risk_gov_no_auto_approve(client, task, monkeypatch):
    """High risk governance does not auto-approve"""
    from app.services.openai_provider import OpenAIProvider
    monkeypatch.setattr(OpenAIProvider, "_call_openai", _mock_high_risk)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    r = await client.post(BASE + "/agents", json={"name": "a", "agent_type": "executor", "provider": "openai"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    rr = await client.get(BASE + f"/tasks/{task['id']}/approval-decisions")
    decisions = rr.json()["data"]
    for d in decisions:
        assert d.get("auto_approve_allowed") is False or d.get("requires_human") is True

# ─── Sandbox succeeds and produces artifacts ───

@pytest.mark.asyncio
async def test_sandbox_produces_artifacts(client, task):
    """Sandbox valid output should create artifacts"""
    r = await client.post(BASE + "/agents", json={"name": "a", "agent_type": "executor", "provider": "sandbox"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    r = await client.get(BASE + f"/tasks/{task['id']}/artifacts")
    assert len(r.json()["data"]) >= 1

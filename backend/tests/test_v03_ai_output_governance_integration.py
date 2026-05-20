"""v0.3 S3: AI Output Governance Integration Tests (real dispatch flow)"""
import pytest
import json
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

# ─── Sandbox: valid output succeeds ───

@pytest.mark.asyncio
async def test_sandbox_valid_output_succeeds(client, task):
    r = await client.post(BASE + "/agents", json={"name": "a1", "agent_type": "executor", "provider": "sandbox"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    assert rr.json()["data"][0]["status"] == "succeeded"

# ─── Sandbox completes + artifacts created ───

@pytest.mark.asyncio
async def test_sandbox_produces_artifacts(client, task):
    r = await client.post(BASE + "/agents", json={"name": "a2", "agent_type": "executor", "provider": "sandbox"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    r = await client.get(BASE + f"/tasks/{task['id']}/artifacts")
    assert len(r.json()["data"]) >= 1

# ─── Empty OpenAI response → agent_failed (provider layer) ───

async def _mock_empty(self, sys_prompt, user_prompt):
    return ""

@pytest.mark.asyncio
async def test_empty_response_fails(client, task, monkeypatch):
    from app.services.openai_provider import OpenAIProvider
    monkeypatch.setattr(OpenAIProvider, "_call_openai", _mock_empty)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    r = await client.post(BASE + "/agents", json={"name": "a3", "agent_type": "executor", "provider": "openai"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["stop_reason"] == "agent_failed" or d["action_taken"] == "agent_failed"
    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    assert rr.json()["data"][0]["status"] == "failed"

# ─── Governance trace exists in raw_result_json ───

async def _mock_plan(self, sys_prompt, user_prompt):
    return "# Plan\n1. Do X\n2. Do Y"

@pytest.mark.asyncio
async def test_governance_trace_in_raw(client, task, monkeypatch):
    from app.services.openai_provider import OpenAIProvider
    monkeypatch.setattr(OpenAIProvider, "_call_openai", _mock_plan)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")
    r = await client.post(BASE + "/agents", json={"name": "a4", "agent_type": "executor", "provider": "openai"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    raw = rr.json()["data"][0]["raw_result_json"]
    data = json.loads(raw)
    assert "provider_raw" in data
    assert "governance" in data
    assert "valid" in data["governance"]

# ─── Sandbox plan produces governance trace ───

@pytest.mark.asyncio
async def test_sandbox_governance_trace(client, task):
    r = await client.post(BASE + "/agents", json={"name": "a5", "agent_type": "executor", "provider": "sandbox"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    raw = rr.json()["data"][0]["raw_result_json"]
    data = json.loads(raw)
    assert "governance" in data
    assert data["governance"]["valid"] is True

# ─── Secret patch governance (unit-level, not real dispatch) ───
# Note: execute-type direct dispatch via factory creates session mismatch.
# Governance validation for secret patches is tested at unit level in test_v03_ai_output_governance.py.

# ─── raw_result_json has governance + provider_raw ───

@pytest.mark.asyncio
async def test_sandbox_raw_has_governance_and_raw(client, task):
    r = await client.post(BASE + "/agents", json={"name": "a7", "agent_type": "executor", "provider": "sandbox"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    raw = rr.json()["data"][0]["raw_result_json"]
    data = json.loads(raw)
    assert "provider_raw" in data
    assert "governance" in data
    assert "trace" in data

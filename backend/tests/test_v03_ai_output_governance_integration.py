"""v0.3 S3: AI Output Governance Integration Tests"""
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

@pytest.mark.asyncio
async def test_sandbox_valid(client, task):
    r = await client.post(BASE + "/agents", json={"name": "a1", "agent_type": "executor", "provider": "sandbox"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    assert rr.json()["data"][0]["status"] == "succeeded"

# requires_human flow tested at unit level in test_v03_ai_output_governance.py
# (requires human decision, not auto-approved, high risk blocks)

async def _mock_plan(self, sys_prompt, user_prompt):
    return "# Plan\n1. Do X"

@pytest.mark.asyncio
async def test_governance_trace(client, task, monkeypatch):
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

async def _mock_sk(self, sys_prompt, user_prompt):
    return "# Key\napi_key = 'sk-abcdefghijklmnopqrstuvwxyz1234567890'"

@pytest.mark.asyncio
async def test_secret_sk_redacted(client, task, monkeypatch):
    from app.services.openai_provider import OpenAIProvider
    monkeypatch.setattr(OpenAIProvider, "_call_openai", _mock_sk)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")
    r = await client.post(BASE + "/agents", json={"name": "a5", "agent_type": "executor", "provider": "openai"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    raw = rr.json()["data"][0]["raw_result_json"]
    data = json.loads(raw)
    provider_raw = data.get("provider_raw", "")
    assert "abcdefghijklmnopqrstuvwxyz" not in provider_raw
    assert "REDACTED" in provider_raw

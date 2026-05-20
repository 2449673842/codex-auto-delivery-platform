"""v0.3 S3: AI Output Governance Integration Tests"""
import pytest
import json
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.database import Base, get_engine
from app.schemas.ai_provider import AgentRunResult

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
    """Sandbox provider executes successfully through full dispatch flow."""
    r = await client.post(BASE + "/agents", json={"name": "a1", "agent_type": "executor", "provider": "sandbox"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    assert rr.json()["data"][0]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_governance_trace_with_sandbox(client, task):
    """Sandbox provider execution produces governance trace in raw_result_json."""
    r = await client.post(BASE + "/agents", json={"name": "a2", "agent_type": "executor", "provider": "sandbox"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    raw = rr.json()["data"][0]["raw_result_json"]
    data = json.loads(raw)
    assert "provider_raw" in data
    assert "governance" in data
    assert "valid" in data["governance"]
    assert "trace" in data


@pytest.mark.asyncio
async def test_sandbox_no_secret_in_provider_raw(client, task):
    """Sandbox provider output contains no secrets (safe by design)."""
    r = await client.post(BASE + "/agents", json={"name": "a3", "agent_type": "executor", "provider": "sandbox"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    raw = rr.json()["data"][0]["raw_result_json"]
    data = json.loads(raw)
    provider_raw = data.get("provider_raw", "")
    assert "sk-" not in provider_raw
    assert "ghp_" not in provider_raw
    assert "password=" not in provider_raw


@pytest.mark.asyncio
async def test_requires_human_high_risk_approval_decision(client, task, monkeypatch):
    """High risk report triggers ApprovalDecision with requires_human."""
    async def _mock_execute(self, run):
        return AgentRunResult(
            output_summary="High risk output",
            output_log="Generated",
            raw_result_json=json.dumps({"risk_report": {"risk_level": "high", "summary": "SQL injection"}}),
        )
    from app.services.openai_provider import OpenAIProvider
    monkeypatch.setattr(OpenAIProvider, "execute", _mock_execute)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")
    r = await client.post(BASE + "/agents", json={"name": "a4", "agent_type": "executor", "provider": "openai"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    ar = rr.json()["data"][0]
    assert ar["status"] == "succeeded"
    data = json.loads(ar["raw_result_json"])
    assert data["governance"]["requires_human"] is True
    assert data["governance"]["risk_level"] == "high"
    dr = await client.get(BASE + f"/tasks/{task['id']}/approval-decisions")
    resp_data = dr.json()
    decisions = resp_data.get("data", resp_data.get("data", []))
    decisions_list = decisions if isinstance(decisions, list) else []
    assert len(decisions_list) >= 1
    latest = decisions_list[-1]
    assert latest["human_required"] is True
    assert latest["auto_approve_allowed"] is False


@pytest.mark.asyncio
async def test_requires_human_secret_pattern_in_patch(client, task, monkeypatch):
    """Patch with secret pattern triggers requires_human + ApprovalDecision."""
    async def _mock_execute(self, run):
        return AgentRunResult(
            output_summary="Patch with secret",
            output_log="Generated",
            raw_result_json=json.dumps({"patch_diff": "diff --git a/config.py b/config.py\n--- a/config.py\n+++ b/config.py\n+password = 'hunter2'\n+DEBUG=True"}),
            patch_diff="diff --git a/config.py b/config.py\n--- a/config.py\n+++ b/config.py\n+password = 'hunter2'\n+DEBUG=True",
        )
    from app.services.openai_provider import OpenAIProvider
    monkeypatch.setattr(OpenAIProvider, "execute", _mock_execute)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")
    r = await client.post(BASE + "/agents", json={"name": "a5", "agent_type": "executor", "provider": "openai"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    ar = rr.json()["data"][0]
    assert ar["status"] == "succeeded"
    data = json.loads(ar["raw_result_json"])
    assert data["governance"]["requires_human"] is True
    dr = await client.get(BASE + f"/tasks/{task['id']}/approval-decisions")
    resp_data = dr.json()
    decisions = resp_data.get("data", resp_data.get("data", []))
    decisions_list = decisions if isinstance(decisions, list) else []
    assert len(decisions_list) >= 1
    latest = decisions_list[-1]
    assert latest["human_required"] is True
    assert latest["auto_approve_allowed"] is False


@pytest.mark.asyncio
async def test_requires_human_forbidden_path(client, task, monkeypatch):
    """Forbidden path modification triggers requires_human + ApprovalDecision."""
    async def _mock_execute(self, run):
        return AgentRunResult(
            output_summary="Forbidden path",
            output_log="Generated",
            raw_result_json=json.dumps({"patch_diff": "diff --git a/.env b/.env\n--- a/.env\n+++ b/.env\n+SECRET=value"}),
            patch_diff="diff --git a/.env b/.env\n--- a/.env\n+++ b/.env\n+SECRET=value",
        )
    from app.services.openai_provider import OpenAIProvider
    monkeypatch.setattr(OpenAIProvider, "execute", _mock_execute)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")
    r = await client.post(BASE + "/agents", json={"name": "a6", "agent_type": "executor", "provider": "openai"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    ar = rr.json()["data"][0]
    assert ar["status"] == "succeeded"
    data = json.loads(ar["raw_result_json"])
    assert data["governance"]["requires_human"] is True
    dr = await client.get(BASE + f"/tasks/{task['id']}/approval-decisions")
    resp_data = dr.json()
    decisions = resp_data.get("data", resp_data.get("data", []))
    decisions_list = decisions if isinstance(decisions, list) else []
    assert len(decisions_list) >= 1
    latest = decisions_list[-1]
    assert latest["human_required"] is True
    assert latest["auto_approve_allowed"] is False


@pytest.mark.asyncio
async def test_task_not_auto_approved_for_human_required(client, task, monkeypatch):
    """Task with human_required is NOT auto-approved by orchestration."""
    async def _mock_execute(self, run):
        return AgentRunResult(
            output_summary="Critical risk",
            output_log="Generated",
            raw_result_json=json.dumps({"risk_report": {"risk_level": "critical", "summary": "RCE"}}),
        )
    from app.services.openai_provider import OpenAIProvider
    monkeypatch.setattr(OpenAIProvider, "execute", _mock_execute)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")
    r = await client.post(BASE + "/agents", json={"name": "a7", "agent_type": "executor", "provider": "openai"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    tr = await client.get(BASE + f"/tasks/{task['id']}")
    resp_data = tr.json()
    task_data = resp_data.get("data", resp_data.get("data", {}))
    status = task_data.get("status", "") if isinstance(task_data, dict) else ""
    assert status != "approved", "orchestration must not auto-approve human_required tasks"


@pytest.mark.asyncio
async def test_artifact_secret_redaction(client, task, monkeypatch):
    """Artifact content is redacted for secrets before storage."""
    fake_secret_plan = "#Plan\napi_key = 'sk-abcdefghijklmnopqrstuvwxyz1234567890'\npassword = 'secret123'"
    async def _mock_execute(self, run):
        return AgentRunResult(
            output_summary="Plan with secrets",
            output_log="Generated",
            raw_result_json=json.dumps({"plan_md": fake_secret_plan}),
            plan_md=fake_secret_plan,
        )
    from app.services.openai_provider import OpenAIProvider
    monkeypatch.setattr(OpenAIProvider, "execute", _mock_execute)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")
    r = await client.post(BASE + "/agents", json={"name": "a8", "agent_type": "executor", "provider": "openai"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    ar = rr.json()["data"][0]
    assert ar["status"] == "succeeded"
    raw = json.loads(ar["raw_result_json"])
    assert "sk-abcdefghijklmnopqrstuvwxyz1234567890" not in raw.get("provider_raw", "")
    assert "***REDACTED***" in raw.get("provider_raw", "")
    ar_resp = await client.get(BASE + f"/tasks/{task['id']}/artifacts")
    artifacts_data = ar_resp.json()
    items = artifacts_data.get("data", artifacts_data.get("data", []))
    art_items = items if isinstance(items, list) else []
    found_plan = False
    for art in art_items:
        if "plan.md" in art.get("filename", ""):
            found_plan = True
            assert "sk-abcdefghijklmnopqrstuvwxyz1234567890" not in art.get("content", "")
            assert "***REDACTED***" in art.get("content", "")
            assert "secret123" not in art.get("content", "")
    assert found_plan, "plan artifact should exist"

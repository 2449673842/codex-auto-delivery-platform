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

async def _do_steps(client, task_id: int, agent_name: str):
    """Setup agent + generate-ticket + dispatch for tests."""
    r = await client.post(BASE + "/agents", json={"name": agent_name, "agent_type": "executor", "provider": "sandbox"})
    await client.post(BASE + f"/tasks/{task_id}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task_id}/dispatch", json=t_actor)
    return r.json()["data"]["id"]

async def _openai_steps(client, task_id: int, agent_name: str):
    """Setup openai agent + generate-ticket + dispatch."""
    await client.post(BASE + "/agents", json={"name": agent_name, "agent_type": "executor", "provider": "openai"})
    await client.post(BASE + f"/tasks/{task_id}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task_id}/dispatch", json=t_actor)

async def _orch_step(client, task_id: int, agent_name: str, monkeypatch, mock_result: AgentRunResult):
    """Full openai dispatch: setup → mock → orchestrate → return agent-run data."""
    await _openai_steps(client, task_id, agent_name)
    from app.services.openai_provider import OpenAIProvider
    async def _mock_exec(self, _run, _code_context=None):  # NOSONAR - must be async to replace async method
        return mock_result
    monkeypatch.setattr(OpenAIProvider, "execute", _mock_exec)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")  # NOSONAR - mock key for tests
    r = await client.post(BASE + f"/tasks/{task_id}/orchestration/step")
    assert r.status_code == 200, f"orchestration failed: {r.text}"
    rr = await client.get(BASE + f"/tasks/{task_id}/agent-runs")
    return rr.json()["data"][0]

def _get_tail(resp_json: dict) -> dict:
    """Extract last approval decision from response."""
    decisions = resp_json.get("data", resp_json.get("data", []))
    items = decisions if isinstance(decisions, list) else []
    return items[-1] if items else {}


@pytest.mark.asyncio
async def test_sandbox_valid(client, task):
    """Sandbox provider executes through full dispatch flow."""
    await _do_steps(client, task["id"], "a1")
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    assert rr.json()["data"][0]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_governance_trace_with_sandbox(client, task):
    """Sandbox execution produces governance trace in raw_result_json."""
    await _do_steps(client, task["id"], "a2")
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    data = json.loads(rr.json()["data"][0]["raw_result_json"])
    assert "provider_raw" in data
    assert "governance" in data
    assert "valid" in data["governance"]
    assert "trace" in data


@pytest.mark.asyncio
async def test_sandbox_no_secret(client, task):
    """Sandbox output contains no secrets."""
    await _do_steps(client, task["id"], "a3")
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    prov = json.loads(rr.json()["data"][0]["raw_result_json"]).get("provider_raw", "")
    assert "sk-" not in prov
    assert "ghp_" not in prov
    assert "password=" not in prov


@pytest.mark.asyncio
async def test_high_risk_approval_decision(client, task, monkeypatch):
    """High risk triggers ApprovalDecision with human_required."""
    ar = await _orch_step(client, task["id"], "a4", monkeypatch, AgentRunResult(
        output_summary="High risk output", output_log="Generated",
        raw_result_json=json.dumps({"risk_report": {"risk_level": "high", "summary": "SQL injection"}}),
    ))
    assert ar["status"] == "succeeded"
    data = json.loads(ar["raw_result_json"])
    assert data["governance"]["requires_human"] is True
    assert data["governance"]["risk_level"] == "high"
    dr = await client.get(BASE + f"/tasks/{task['id']}/approval-decisions")
    last = _get_tail(dr.json())
    assert last.get("human_required") is True
    assert last.get("auto_approve_allowed") is False


@pytest.mark.asyncio
async def test_secret_patch_approval_decision(client, task, monkeypatch):
    """Secret patch triggers ApprovalDecision."""
    patch = "diff --git a/config.py b/config.py\n--- a/config.py\n+++ b/config.py\n+password = 'hunter2'\n+DEBUG=True"
    ar = await _orch_step(client, task["id"], "a5", monkeypatch, AgentRunResult(
        output_summary="Patch with secret", output_log="Generated",
        raw_result_json=json.dumps({"patch_diff": patch}), patch_diff=patch,
    ))
    assert ar["status"] == "succeeded"
    assert json.loads(ar["raw_result_json"])["governance"]["requires_human"] is True
    dr = await client.get(BASE + f"/tasks/{task['id']}/approval-decisions")
    last = _get_tail(dr.json())
    assert last.get("human_required") is True
    assert last.get("auto_approve_allowed") is False


@pytest.mark.asyncio
async def test_forbidden_path_approval_decision(client, task, monkeypatch):
    """Forbidden path modification triggers ApprovalDecision."""
    patch = "diff --git a/.env b/.env\n--- a/.env\n+++ b/.env\n+SECRET=value"
    ar = await _orch_step(client, task["id"], "a6", monkeypatch, AgentRunResult(
        output_summary="Forbidden path", output_log="Generated",
        raw_result_json=json.dumps({"patch_diff": patch}), patch_diff=patch,
    ))
    assert ar["status"] == "succeeded"
    assert json.loads(ar["raw_result_json"])["governance"]["requires_human"] is True
    dr = await client.get(BASE + f"/tasks/{task['id']}/approval-decisions")
    last = _get_tail(dr.json())
    assert last.get("human_required") is True
    assert last.get("auto_approve_allowed") is False


@pytest.mark.asyncio
async def test_human_required_not_auto_approved(client, task, monkeypatch):
    """human_required task not auto-approved by orchestration."""
    await _orch_step(client, task["id"], "a7", monkeypatch, AgentRunResult(
        output_summary="Critical risk", output_log="Generated",
        raw_result_json=json.dumps({"risk_report": {"risk_level": "critical", "summary": "RCE"}}),
    ))
    tr = await client.get(BASE + f"/tasks/{task['id']}")
    td = tr.json().get("data", tr.json().get("data", {}))
    status = td.get("status", "") if isinstance(td, dict) else ""
    assert status != "approved", "must not auto-approve human_required"


@pytest.mark.asyncio
async def test_artifact_secret_redaction(client, task, monkeypatch):
    """Artifact content is redacted for secrets."""
    secret_plan = "#Plan\napi_key = 'sk-abcdefghijklmnopqrstuvwxyz1234567890'\npassword = 'secret123'"
    ar = await _orch_step(client, task["id"], "a8", monkeypatch, AgentRunResult(
        output_summary="Plan with secrets", output_log="Generated",
        raw_result_json=json.dumps({"plan_md": secret_plan}), plan_md=secret_plan,
    ))
    assert ar["status"] == "succeeded"
    raw = json.loads(ar["raw_result_json"])
    assert "sk-abcdefghijklmnopqrstuvwxyz1234567890" not in raw.get("provider_raw", "")
    assert "***REDACTED***" in raw.get("provider_raw", "")
    ar_resp = await client.get(BASE + f"/tasks/{task['id']}/artifacts")
    items = ar_resp.json().get("data", ar_resp.json().get("data", []))
    arts = items if isinstance(items, list) else []
    plan_arts = [a for a in arts if "plan.md" in a.get("filename", "")]
    assert len(plan_arts) >= 1, "plan artifact should exist"
    for a in plan_arts:
        assert "sk-abcdefghijklmnopqrstuvwxyz1234567890" not in a.get("content", "")
        assert "***REDACTED***" in a.get("content", "")
        assert "secret123" not in a.get("content", "")

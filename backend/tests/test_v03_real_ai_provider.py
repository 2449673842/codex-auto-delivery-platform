"""v0.3 S2: Real AI Provider Tests"""
import pytest
import ast
import os as os_mod
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
async def project(client) -> dict:
    r = await client.post(BASE + "/projects", json={"name": "rai-test", "root_path": "/rai"})
    return r.json()["data"]

@pytest.fixture
async def task(client, project) -> dict:
    r = await client.post(BASE + "/tasks", json={"project_id": project["id"], "title": "rai-task", "planner": "test", "description": "real ai test"})
    return r.json()["data"]

t_actor = {"actor": "test"}

# ─── Default provider is still sandbox ───

@pytest.mark.asyncio
async def test_default_provider_is_sandbox(client, task):
    """Default provider (sandbox) should use SandboxProvider"""
    r = await client.post(BASE + "/agents", json={"name": "default-agent", "agent_type": "executor", "provider": "sandbox"})
    agent = r.json()["data"]
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    assert r.json()["data"]["action_taken"] == "create_and_run_agent"

@pytest.mark.asyncio
async def test_non_openai_falls_back_to_sandbox(client, task):
    """codex/claude/manual provider should fall back to sandbox"""
    for prov in ["codex", "claude", "manual"]:
        r = await client.post(BASE + "/agents", json={"name": f"{prov}-agent", "agent_type": "executor", "provider": prov})
        agent = r.json()["data"]
        r2 = await client.post(BASE + "/tasks", json={"project_id": (await client.post(BASE + "/projects", json={"name": f"{prov}-proj", "root_path": "/x"})).json()["data"]["id"], "title": f"{prov}-task", "planner": "test"})
        t2 = r2.json()["data"]
        await client.post(BASE + f"/tasks/{t2['id']}/generate-ticket", json=t_actor)
        await client.post(BASE + f"/tasks/{t2['id']}/dispatch", json=t_actor)
        r3 = await client.post(BASE + f"/tasks/{t2['id']}/orchestration/step")
        assert r3.status_code == 200

# ─── OpenAI provider: no API key → failed ───

@pytest.mark.asyncio
async def test_openai_no_api_key_fails(client, task, monkeypatch):
    """OpenAI provider without API key should fail AgentRun"""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = await client.post(BASE + "/agents", json={"name": "openai-agent", "agent_type": "executor", "provider": "openai"})
    agent = r.json()["data"]
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["stop_reason"] == "agent_failed"

# ─── OpenAI provider: mocked success ───

async def _mock_openai_call(self, sys_prompt, user_prompt):
    return "# Mocked Plan\n1. Step one\n2. Step two"

async def _mock_openai_patch(self, sys_prompt, user_prompt):
    return "diff --git a/src/main.py b/src/main.py\n+print('hello')"

async def _mock_openai_review(self, sys_prompt, user_prompt):
    return "# Review\nApproved. Low risk."

async def _mock_openai_empty(self, sys_prompt, user_prompt):
    return ""

@pytest.mark.asyncio
async def test_openai_mocked_plan(client, task, monkeypatch):
    """OpenAI provider with mocked API should produce plan.md"""
    from app.services.openai_provider import OpenAIProvider
    monkeypatch.setattr(OpenAIProvider, "_call_openai", _mock_openai_call)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")  # NOSONAR - mock key for tests

    r = await client.post(BASE + "/agents", json={"name": "mock-plan", "agent_type": "executor", "provider": "openai"})
    agent = r.json()["data"]
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200

    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    run = rr.json()["data"][0]
    assert run["status"] == "succeeded"
    assert run["output_summary"] is not None
    assert "plan" in (run["raw_result_json"] or "").lower()

@pytest.mark.asyncio
async def test_openai_mocked_creates_artifacts(client, task, monkeypatch):
    """OpenAI provider should create artifacts from AI output"""
    from app.services.openai_provider import OpenAIProvider
    monkeypatch.setattr(OpenAIProvider, "_call_openai", _mock_openai_call)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")  # NOSONAR - mock key for tests

    r = await client.post(BASE + "/agents", json={"name": "mock-art", "agent_type": "executor", "provider": "openai"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    
    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    run = rr.json()["data"][0]
    assert run["status"] == "succeeded"
    assert "plan" in (run["raw_result_json"] or "").lower()
    
    arts = await client.get(BASE + f"/tasks/{task['id']}/artifacts")
    assert len(arts.json()["data"]) >= 1

@pytest.mark.asyncio
async def test_openai_execute_saves_patch_diff(client, task, monkeypatch):
    """OpenAI execute run_type should save patch.diff artifact"""
    from app.services.openai_provider import OpenAIProvider
    monkeypatch.setattr(OpenAIProvider, "_call_openai", _mock_openai_patch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")  # NOSONAR - mock key for tests

    r = await client.post(BASE + "/agents", json={"name": "exec-diff", "agent_type": "executor", "provider": "openai"})
    agent = r.json()["data"]
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    # v0.4 S1: execute requires code context
    await client.post(BASE + f"/tasks/{task['id']}/code-context", json={
        "files": [{"path": "src/example.py", "content": "# placeholder\n", "language": "python"}]
    })
    # Create AgentRun with execute type directly via API
    r = await client.post(BASE + f"/tasks/{task['id']}/agent-runs", json={"agent_id": agent["id"], "run_type": "execute", "input_prompt": "add a function"})
    rid = r.json()["data"]["id"]
    # Dispatch via direct database session (bypass orchestration wait logic)
    from app.database import get_session_factory
    from app.services.ai_provider_service import dispatch_agent_run
    factory = get_session_factory()
    async with factory() as db:
        await dispatch_agent_run(db, rid, "test")
        await db.commit()

    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    run = rr.json()["data"][0]
    assert run["status"] == "succeeded"
    assert "patch_diff" in (run["raw_result_json"] or "")

    arts = await client.get(BASE + f"/tasks/{task['id']}/artifacts")
    artifacts = arts.json()["data"]
    diff_arts = [a for a in artifacts if a["artifact_type"] == "agent_output_diff"]
    assert len(diff_arts) >= 1, "No agent_output_diff artifact found"
    assert ".diff" in diff_arts[0]["filename"]
    assert "diff --git" in diff_arts[0]["content"]

# ─── API key not exposed ───

@pytest.mark.asyncio
async def test_openai_key_not_in_logs(client, task, monkeypatch):
    """API key must NOT appear in any persistent field"""
    from app.services.openai_provider import OpenAIProvider
    monkeypatch.setattr(OpenAIProvider, "_call_openai", _mock_openai_call)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret-key-12345")  # NOSONAR - mock key for test

    r = await client.post(BASE + "/agents", json={"name": "key-test", "agent_type": "executor", "provider": "openai"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")

    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    run = rr.json()["data"][0]
    for field in ["output_log", "raw_result_json", "error_message"]:
        val = run.get(field) or ""
        assert "sk-test-secret-key" not in val, f"API key leak in {field}"
    arts = await client.get(BASE + f"/tasks/{task['id']}/artifacts")
    for a in arts.json()["data"]:
        assert "sk-test-secret-key" not in (a.get("content") or ""), "API key leak in artifact"

@pytest.mark.asyncio
async def test_openai_err_message_no_key(client, task, monkeypatch):
    """Error message from OpenAI failure must not contain API key"""
    from app.services.openai_provider import OpenAIProvider
    async def failing_with_key(self, sys_prompt, user_prompt):
        raise RuntimeError("API call failed: sk-test-secret-key-123")  # NOSONAR - fake key in error
    monkeypatch.setattr(OpenAIProvider, "_call_openai", failing_with_key)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret-key-123")  # NOSONAR - mock key for test

    r = await client.post(BASE + "/agents", json={"name": "fail-key", "agent_type": "executor", "provider": "openai"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")

    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    run = rr.json()["data"][0]
    assert "sk-test-secret-key" not in (run.get("error_message") or "")
    
    ev = await client.get(BASE + f"/tasks/{task['id']}/events")
    for e in ev.json()["data"]:
        assert "sk-test-secret-key" not in (e.get("message") or "")

# ─── Malformed AI response → AgentRun failed ───

@pytest.mark.asyncio
async def test_malformed_openai_agent_failed(client, task, monkeypatch):
    """Empty AI response should fail the AgentRun (not succeed)"""
    from app.services.openai_provider import OpenAIProvider
    monkeypatch.setattr(OpenAIProvider, "_call_openai", _mock_openai_empty)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")  # NOSONAR - mock key for tests

    r = await client.post(BASE + "/agents", json={"name": "empty-test", "agent_type": "executor", "provider": "openai"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["stopped"] is True
    assert d["stop_reason"] == "agent_failed"

    rr = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    run = rr.json()["data"][0]
    assert run["status"] == "failed"

    # Task should stay dispatched
    r = await client.get(BASE + f"/tasks/{task['id']}")
    assert r.json()["data"]["status"] == "dispatched"

    # No success artifacts
    arts = await client.get(BASE + f"/tasks/{task['id']}/artifacts")
    assert len(arts.json()["data"]) == 0

    # Status shows agent_failed
    r = await client.get(BASE + f"/tasks/{task['id']}/orchestration/status")
    assert r.json()["data"]["next_action"] == "agent_failed"
    assert r.json()["data"]["can_auto_continue"] is False

@pytest.mark.asyncio
async def test_malformed_response_no_auto_approve(client, task, monkeypatch):
    """After AI response, approval is still required"""
    from app.services.openai_provider import OpenAIProvider
    monkeypatch.setattr(OpenAIProvider, "_call_openai", _mock_openai_call)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-mock")  # NOSONAR - mock key for tests

    r = await client.post(BASE + "/agents", json={"name": "no-auto", "agent_type": "executor", "provider": "openai"})
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={})
    assert r.json()["data"]["auto_approve_allowed"] is False

# ─── Security boundary: AST checks ───

def test_openai_no_shell():
    """OpenAI provider does not use subprocess/os.system"""
    src_path = os_mod.path.join(os_mod.path.dirname(__file__), '../app/services/openai_provider.py')
    with open(src_path, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in ('system', 'popen'):
                raise AssertionError(f'OpenAI provider should not use {func.attr}')
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ('subprocess',):
                    raise AssertionError('OpenAI provider should not import subprocess')

def test_openai_no_project_root():
    """OpenAI provider does not access Project.root_path"""
    src_path = os_mod.path.join(os_mod.path.dirname(__file__), '../app/services/openai_provider.py')
    with open(src_path, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Attribute) and node.value.attr == 'root_path':
                raise AssertionError(f'OpenAI provider should not access .root_path')
            if isinstance(node.value, ast.Name) and node.value.id == 'Project':
                raise AssertionError(f'OpenAI provider should not access Project')
        if isinstance(node, ast.Import):
            for alias in node.names:
                if 'pathlib' in alias.name:
                    raise AssertionError(f'OpenAI provider should not use pathlib')

def test_openai_no_secret_ref():
    """OpenAI provider does not access secret_ref"""
    src_path = os_mod.path.join(os_mod.path.dirname(__file__), '../app/services/openai_provider.py')
    with open(src_path, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == 'secret_ref':
            raise AssertionError('OpenAI provider should not access secret_ref')

def test_dispatch_no_secret_ref_access():
    """dispatch_agent_run does not access AgentProfile.secret_ref"""
    src_path = os_mod.path.join(os_mod.path.dirname(__file__), '../app/services/ai_provider_service.py')
    with open(src_path, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == 'secret_ref':
            raise AssertionError('dispatch should not access secret_ref')

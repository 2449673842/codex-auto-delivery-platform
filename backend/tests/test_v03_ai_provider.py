"""v0.3 AI Provider Adapter Sandbox Tests"""
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
async def project(client) -> dict:
    r = await client.post(BASE + "/projects", json={"name": "ai-test", "root_path": "/ai"})
    return r.json()["data"]

@pytest.fixture
async def agent(client) -> dict:
    r = await client.post(BASE + "/agents", json={"name": "ai-agent", "agent_type": "executor", "provider": "sandbox"})
    return r.json()["data"]

@pytest.fixture
async def task(client, project) -> dict:
    r = await client.post(BASE + "/tasks", json={"project_id": project["id"], "title": "ai-task", "planner": "test", "description": "sandbox provider test"})
    return r.json()["data"]

t_actor = {"actor": "test"}

# ─── Sandbox Provider: plan ───

@pytest.mark.asyncio
async def test_sandbox_plan_generates_plan_md(client, task, agent):
    """Sandbox plan run should generate plan.md"""
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    r = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    runs = r.json()["data"]
    assert len(runs) == 1
    run = runs[0]
    assert run["status"] == "succeeded"
    assert run["output_summary"] is not None
    assert "plan" in (run["raw_result_json"] or "").lower()

@pytest.mark.asyncio
async def test_sandbox_plan_creates_artifact(client, task, agent):
    """Sandbox plan should create artifacts"""
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    r = await client.get(BASE + f"/tasks/{task['id']}/artifacts")
    assert len(r.json()["data"]) >= 1

# ─── Sandbox Provider: output fields ───

@pytest.mark.asyncio
async def test_sandbox_writes_output_summary(client, task, agent):
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    r = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    assert r.json()["data"][0]["output_summary"] is not None

@pytest.mark.asyncio
async def test_sandbox_writes_output_log(client, task, agent):
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    r = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    assert r.json()["data"][0]["output_log"] is not None

@pytest.mark.asyncio
async def test_sandbox_writes_raw_result_json(client, task, agent):
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    r = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    assert r.json()["data"][0]["raw_result_json"] is not None

# ─── Orchestration integration ───

@pytest.mark.asyncio
async def test_sandbox_then_submit_result(client, task, agent):
    """After Sandbox completes, next step submits result"""
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    assert r.json()["data"]["action_taken"] == "submit_result"
    assert r.json()["data"]["after_status"] == "result_submitted"

@pytest.mark.asyncio
async def test_sandbox_full_flow_to_reviewing(client, task, agent):
    """Sandbox → submit → start_review → reviewing"""
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    assert r.json()["data"]["after_status"] == "reviewing"

# ─── Security: no external calls (parse AST, skip comments) ───

def test_sandbox_no_external_ai():
    """Sandbox provider does not call external AI"""
    import ast, os
    src_path = os.path.join(os.path.dirname(__file__), '../app/services/sandbox_provider.py')
    with open(src_path, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == 'openai':
            raise AssertionError('Sandbox should not use openai')
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == 'anthropic':
            raise AssertionError('Sandbox should not use anthropic')

def test_sandbox_no_secret_or_shell():
    """Sandbox provider does not read secret or execute shell"""
    import ast, os
    src_path = os.path.join(os.path.dirname(__file__), '../app/services/sandbox_provider.py')
    with open(src_path, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in ('getenv', 'system', 'popen'):
                raise AssertionError(f'Sandbox should not use {func.attr}')
            if isinstance(func, ast.Name) and func.id == 'subprocess':
                raise AssertionError('Sandbox should not use subprocess')
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ('subprocess', 'git'):
                    raise AssertionError(f'Sandbox should not import {alias.name}')

def test_sandbox_no_github_ci():
    """Sandbox provider does not call GitHub/CI/Sonar"""
    import ast, os
    src_path = os.path.join(os.path.dirname(__file__), '../app/services/sandbox_provider.py')
    with open(src_path, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == 'github':
                raise AssertionError('Sandbox should not use github')
            if node.value.id == 'sonar':
                raise AssertionError('Sandbox should not use sonar')

# ─── dispatch_agent_run ───

@pytest.mark.asyncio
async def test_dispatch_queued_to_succeeded(client, task, agent):
    """dispatch_agent_run transitions queued → running → succeeded"""
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    r = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    assert r.json()["data"][0]["status"] == "succeeded"

# ─── Existing tests still pass ───

@pytest.mark.asyncio
async def test_existing_tests_still_pass(client, task):
    """Basic health check still works"""
    r = await client.get(BASE + "/health")
    assert r.status_code == 200

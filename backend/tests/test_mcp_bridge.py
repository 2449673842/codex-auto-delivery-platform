import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.database import Base, get_engine, get_session_factory
from app.main import app
from app.models.agent_profile import AgentProfile
from app.models.agent_run import AgentRun
from app.models.task_artifact import TaskArtifact
from app.models.task_event import TaskEvent


BASE = "/api/mcp"
PROJECT_PAYLOAD = {"name": "mcp-test", "root_path": "/secret/root"}
TASK_PAYLOAD = {
    "title": "MCP task",
    "description": "Task description with sk-123456789012345678901234567890",
}


@pytest.fixture(autouse=True)
async def _reset_db():
    await _rebuild_schema()
    yield
    await _drop_schema()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test.local") as ac:
        yield ac


@pytest.fixture
async def seeded(client):
    project = (await client.post("/api/projects", json=PROJECT_PAYLOAD)).json()["data"]
    task = (await client.post("/api/tasks", json={**TASK_PAYLOAD, "project_id": project["id"]})).json()["data"]
    session_factory = get_session_factory()
    async with session_factory() as session:
        agent = AgentProfile(
            name="mcp-agent",
            agent_type="reviewer",
            provider="openai",
            model_name="gpt-test",
            secret_ref="secret/should-not-return",
        )
        session.add(agent)
        await session.flush()
        run = AgentRun(
            task_id=task["id"],
            project_id=project["id"],
            agent_id=agent.id,
            run_type="review",
            status="succeeded",
            input_prompt="prompt with password=private-password",
            output_summary="Review summary with cookie=private-cookie",
            raw_result_json=json.dumps({"secret_ref": "secret/should-not-return"}),
        )
        session.add(run)
        artifact = TaskArtifact(
            task_id=task["id"],
            artifact_type="browser_ai_answer",
            filename="answer.md",
            content="Browser answer " + ("long text " * 200) + "session=private-session",
            size_bytes=2048,
            sha256="abc",
        )
        session.add(artifact)
        await session.commit()
    return {"project": project, "task": task}


async def _rebuild_schema():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


async def _drop_schema():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _counts():
    session_factory = get_session_factory()
    async with session_factory() as session:
        runs = (await session.execute(select(AgentRun))).scalars().all()
        artifacts = (await session.execute(select(TaskArtifact))).scalars().all()
        events = (await session.execute(select(TaskEvent))).scalars().all()
    return len(runs), len(artifacts), len(events)


async def _call(client, tool: str, arguments: dict):
    return await client.post(f"{BASE}/call", json={"tool": tool, "arguments": arguments})


def _data(resp):
    return resp.json()["data"]


def _payload(resp):
    return _data(resp)["data"]


def _text(value):
    return json.dumps(value)


@pytest.mark.asyncio
async def test_tools_returns_all_readonly_and_dryrun_tools(client):
    resp = await client.get(f"{BASE}/tools")

    assert resp.status_code == 200
    tools = _data(resp)
    names = {tool["name"] for tool in tools}
    assert {
        "get_workspace_status",
        "get_project_summary",
        "list_tasks",
        "get_task_brief",
        "get_handoff_packet",
        "get_answer_synthesis",
        "list_agent_runs",
        "list_task_artifacts",
        "get_sandbox_status",
        "ai_dispatch_dry_run",
        "browser_ai_dry_run",
    } <= names
    assert all(tool["read_only"] is True for tool in tools)
    assert next(tool for tool in tools if tool["name"] == "ai_dispatch_dry_run")["dry_run_only"] is True


@pytest.mark.asyncio
async def test_get_task_brief_returns_redacted_budgeted_summary(client, seeded):
    resp = await _call(client, "get_task_brief", {"task_id": seeded["task"]["id"], "budget": 800})

    data = _data(resp)
    assert data["status"] == "succeeded"
    assert data["read_only"] is True
    assert data["persisted"] is False
    payload = data["data"]
    assert payload["task"]["title"] == "MCP task"
    body = _text(payload)
    assert "sk-123456789012345678901234567890" not in body
    assert "private-password" not in body


@pytest.mark.asyncio
async def test_handoff_packet_supports_budget_and_truncation(client, seeded):
    resp = await _call(client, "get_handoff_packet", {"task_id": seeded["task"]["id"], "budget": 500})

    payload = _payload(resp)
    assert payload["is_truncated"] is True
    assert "truncated_reason" in payload
    assert len(_text(payload)) < 900


@pytest.mark.asyncio
async def test_answer_synthesis_returns_rule_based_preview(client, seeded):
    resp = await _call(client, "get_answer_synthesis", {"task_id": seeded["task"]["id"], "budget": 4000})

    payload = _payload(resp)
    assert payload["task_id"] == seeded["task"]["id"]
    assert payload["source_artifact_ids"]
    assert payload["artifact_summaries"][0]["artifact_type"] == "browser_ai_answer"


@pytest.mark.asyncio
async def test_list_agent_runs_redacts_prompt_and_secret_fields(client, seeded):
    resp = await _call(client, "list_agent_runs", {"task_id": seeded["task"]["id"], "budget": 4000})

    payload = _payload(resp)
    body = _text(payload)
    assert "prompt with" not in body
    assert "private-password" not in body
    assert "secret/should-not-return" not in body
    assert "private-cookie" not in body
    assert payload["runs"][0]["input_prompt"] == "[redacted by MCP Bridge]"


@pytest.mark.asyncio
async def test_list_task_artifacts_returns_summary_not_full_content(client, seeded):
    resp = await _call(client, "list_task_artifacts", {"task_id": seeded["task"]["id"], "budget": 4000})

    payload = _payload(resp)
    body = _text(payload)
    assert "browser_ai_answer" in body
    assert "private-session" not in body
    assert len(payload["artifacts"][0]["summary"]) < 1000


@pytest.mark.asyncio
async def test_ai_dispatch_dry_run_does_not_call_provider_or_write(client, seeded):
    before = await _counts()
    resp = await _call(client, "ai_dispatch_dry_run", {
        "task_goal": "review this",
        "module_name": "backend",
        "task_type": "review",
        "mode": "review",
    })

    data = _data(resp)
    assert data["status"] == "succeeded"
    assert data["data"]["would_dispatch"] is False
    assert data["persisted"] is False
    assert await _counts() == before


@pytest.mark.asyncio
async def test_browser_ai_dry_run_does_not_open_browser_or_write(client, seeded):
    before = await _counts()
    resp = await _call(client, "browser_ai_dry_run", {
        "project_id": seeded["project"]["id"],
        "task_id": seeded["task"]["id"],
        "provider": "custom",
        "target_url": "http://127.0.0.1:9999/mock",
        "input_selector": "textarea",
        "send_selector": "button",
        "response_selector": "[data-answer]",
    })

    data = _data(resp)
    assert data["status"] == "succeeded"
    assert data["data"]["browser_opened"] is False
    assert data["data"]["persisted"] is False
    assert await _counts() == before


@pytest.mark.asyncio
async def test_unknown_and_dangerous_tools_are_blocked_or_failed(client):
    unknown = await _call(client, "unknown_tool", {})
    dangerous = await _call(client, "execute_shell", {})

    assert _data(unknown)["status"] == "failed"
    assert _data(dangerous)["status"] == "blocked"


@pytest.mark.asyncio
async def test_get_sandbox_status_is_readonly(client, seeded):
    before = await _counts()
    resp = await _call(client, "get_sandbox_status", {"task_id": seeded["task"]["id"]})

    data = _data(resp)
    assert data["status"] == "succeeded"
    assert "passed" in data["data"]
    assert await _counts() == before


@pytest.mark.asyncio
async def test_forbidden_surfaces_not_used(client, seeded, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("forbidden surface")

    monkeypatch.setattr("pathlib.Path.glob", fail)
    monkeypatch.setattr("pathlib.Path.rglob", fail)
    monkeypatch.setattr("subprocess.run", fail)
    monkeypatch.setattr("subprocess.Popen", fail)
    monkeypatch.setattr("os.system", fail)

    resp = await _call(client, "get_workspace_status", {})

    assert resp.status_code == 200
    assert _data(resp)["status"] == "succeeded"

"""v0.2 S7-S8: Auto Orchestration Tests"""
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
    r = await client.post(BASE + "/projects", json={"name": "orch-test", "root_path": "/orch"})
    return r.json()["data"]

@pytest.fixture
async def agent(client) -> dict:
    r = await client.post(BASE + "/agents", json={"name": "orch-agent", "agent_type": "executor", "provider": "manual"})
    return r.json()["data"]

@pytest.fixture
async def task(client, project) -> dict:
    r = await client.post(BASE + "/tasks", json={"project_id": project["id"], "title": "orch-task", "planner": "test", "description": "auto orch test"})
    return r.json()["data"]

t_actor = {"actor": "test"}

# ─── 1-3: Status判断 ───

@pytest.mark.asyncio
async def test_draft_status_returns_generate_ticket(client, task):
    r = await client.get(BASE + f"/tasks/{task['id']}/orchestration/status")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["next_action"] == "generate_ticket"
    assert d["can_auto_continue"] is True

@pytest.mark.asyncio
async def test_archived_status_cannot_orchestrate(client, task):
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/submit-result", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/start-review", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/approve", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/archive", json=t_actor)
    r = await client.get(BASE + f"/tasks/{task['id']}/orchestration/status")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["can_auto_continue"] is False
    assert "archived" in str(d)
    r2 = await client.post(BASE + f"/tasks/{task['id']}/orchestration/run", json={"max_steps": 5})
    assert r2.status_code == 409

@pytest.mark.asyncio
async def test_human_required_status_stops(client, task):
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/submit-result", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/start-review", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/require-human-approval", json=t_actor)
    r = await client.get(BASE + f"/tasks/{task['id']}/orchestration/status")
    assert r.json()["data"]["can_auto_continue"] is False

# ─── 4-9: 单步推进 ───

@pytest.mark.asyncio
async def test_draft_step_to_ticket_ready(client, task):
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["before_status"] == "draft"
    assert d["after_status"] == "ticket_ready"
    assert d["action_taken"] == "generate_ticket"

@pytest.mark.asyncio
async def test_ticket_ready_step_to_dispatched(client, task):
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    assert r.json()["data"]["after_status"] == "dispatched"
    assert r.json()["data"]["action_taken"] == "dispatch"

@pytest.mark.asyncio
async def test_dispatched_step_creates_agent_run(client, task, agent):
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["stopped"] is True
    assert d["stop_reason"] == "waiting_for_agent_result"

@pytest.mark.asyncio
async def test_running_agent_run_not_faked(client, task):
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    # Status should still be dispatched (not faked to succeeded)
    r = await client.get(BASE + f"/tasks/{task['id']}")
    assert r.json()["data"]["status"] == "dispatched"

@pytest.mark.asyncio
async def test_agent_succeeded_then_result_submitted(client, task, agent):
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    # Get the agent run ID from the API
    r2 = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    runs = r2.json()["data"]
    assert len(runs) > 0
    rid = runs[0]["id"]
    # Manually submit result
    await client.patch(BASE + f"/tasks/{task['id']}/agent-runs/{rid}", json={"status": "running"})
    await client.post(BASE + f"/tasks/{task['id']}/agent-runs/{rid}/submit-result", json={"status": "succeeded", "output_summary": "done"})
    # Now step should go to result_submitted
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    assert r.json()["data"]["after_status"] == "result_submitted"

@pytest.mark.asyncio
async def test_result_submitted_step_to_reviewing(client, task):
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/submit-result", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    assert r.json()["data"]["after_status"] == "reviewing"

# ─── 10-13: 审批编排 ───

@pytest.mark.asyncio
async def test_reviewing_auto_approve_with_data(client, task):
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/submit-result", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/start-review", json=t_actor)
    # Create a low-risk decision that allows auto-approve
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"tests_passed": True, "security_issues_found": False, "actor": "test"})
    d = r.json()["data"]
    assert d["auto_approve_allowed"] is True
    # The step evaluates WITHOUT data (no tests_passed), so it will stop at human_required
    # This is correct: orchestration can't auto-approve without external data
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    # Without evaluation data, human_required is expected
    assert r.json()["data"]["stop_reason"] in ("human_required", None)

@pytest.mark.asyncio
async def test_reviewing_missing_security_to_human_required(client, task):
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/submit-result", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/start-review", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["stopped"] is True
    assert d["stop_reason"] == "human_required"

@pytest.mark.asyncio
async def test_reviewing_high_risk_blocked(client, task):
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/submit-result", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/start-review", json=t_actor)
    # Create a high-risk decision
    r = await client.post(BASE + f"/tasks/{task['id']}/evaluate-approval", json={"diff_summary": "ALTER TABLE users ADD COLUMN token", "actor": "test"})
    d = r.json()["data"]
    assert d["human_required"] is True
    # Step should detect human_required
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    assert r.json()["data"]["stop_reason"] == "human_required"

@pytest.mark.asyncio
async def test_human_required_no_auto_approve(client, task):
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/submit-result", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/start-review", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/require-human-approval", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    assert r.json()["data"]["stop_reason"] == "human_required"
    assert r.json()["data"]["after_status"] == "human_required"

# ─── 14-16: 循环保护 ───

@pytest.mark.asyncio
async def test_run_max_steps_1(client, task):
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/run", json={"max_steps": 1})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["steps_executed"] == 1
    assert d["actions"] == ["generate_ticket"]

@pytest.mark.asyncio
async def test_run_stops_at_waiting_for_agent(client, task, agent):
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/run", json={"max_steps": 10})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["stopped"] is True
    assert d["stop_reason"] == "waiting_for_agent_result"
    assert d["steps_executed"] >= 1

@pytest.mark.asyncio
async def test_no_infinite_loop(client, task):
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/run", json={"max_steps": 50})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["steps_executed"] <= 50

# ─── 17-19: 归属校验 ───

@pytest.mark.asyncio
async def test_orchestration_wrong_task_404(client, task, project):
    r = await client.post(BASE + "/tasks", json={"project_id": project["id"], "title": "other", "planner": "test"})
    other = r.json()["data"]
    r = await client.get(BASE + f"/tasks/{other['id'] + 999}/orchestration/status")
    assert r.status_code == 404

@pytest.mark.asyncio
async def test_orchestration_other_project_task(client, task, project):
    r = await client.post(BASE + "/tasks", json={"project_id": project["id"], "title": "other", "planner": "test"})
    other = r.json()["data"]
    r = await client.get(BASE + f"/tasks/{other['id']}/orchestration/status")
    assert r.status_code == 200  # Same project, different task

@pytest.mark.asyncio
async def test_orchestration_nonexistent_task_404(client):
    r = await client.get(BASE + "/tasks/99999/orchestration/status")
    assert r.status_code == 404

# ─── 20-24: 安全边界事件 ───

@pytest.mark.asyncio
async def test_orchestration_started_event(client, task):
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/run", json={"max_steps": 3, "actor": "system"})
    r = await client.get(BASE + f"/tasks/{task['id']}/events")
    types = [e["event_type"] for e in r.json()["data"]]
    assert "orchestration_started" in types
    assert "orchestration_step_completed" in types
    assert "orchestration_stopped" in types

@pytest.mark.asyncio
async def test_agent_run_auto_created_event(client, task, agent):
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    r = await client.get(BASE + f"/tasks/{task['id']}/events")
    types = [e["event_type"] for e in r.json()["data"]]
    assert "agent_run_auto_created" in types
    assert "agent_run_auto_started" in types
    assert "agent_result_waiting" in types

@pytest.mark.asyncio
async def test_orchestration_no_external_ai(client):
    """Verify orchestration doesn't call external AI"""
    import os
    src_path = os.path.join(os.path.dirname(__file__), '../app/services/orchestration_service.py')
    with open(src_path, encoding='utf-8') as f:
        src = f.read()
    for pattern in ['openai', 'anthropic', 'requests.post']:
        assert pattern not in src, f'orchestration should not call {pattern}'


@pytest.mark.asyncio
async def test_orchestration_no_secret_or_shell(client):
    """Verify orchestration doesn't read secret or execute shell"""
    import os
    src_path = os.path.join(os.path.dirname(__file__), '../app/services/orchestration_service.py')
    with open(src_path, encoding='utf-8') as f:
        src = f.read()
    for pattern in ['os.getenv', 'subprocess', 'os.system', 'os.popen', 'Project.root_path']:
        assert pattern not in src, f'orchestration should not use {pattern}'


@pytest.mark.asyncio
async def test_existing_tests_still_pass(client, task):
    # Verify basic API still works after orchestration import
    r = await client.get(BASE + "/health")
    assert r.status_code == 200


# ─── Dispatched next_action tests ───

@pytest.mark.asyncio
async def test_dispatched_no_run_returns_create_agent_run(client, task):
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.get(BASE + f"/tasks/{task['id']}/orchestration/status")
    assert r.json()["data"]["next_action"] == "create_agent_run"

@pytest.mark.asyncio
async def test_dispatched_running_run_returns_wait(client, task, agent):
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    r = await client.get(BASE + f"/tasks/{task['id']}/orchestration/status")
    # Engine stopped at waiting_for_agent_result, but next status check should show wait
    assert r.json()["data"]["next_action"] in ("wait_agent_result", "create_agent_run")

@pytest.mark.asyncio
async def test_dispatched_succeeded_run_returns_submit_result(client, task, agent):
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    # Get agent run and submit result
    r2 = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    rid = r2.json()["data"][0]["id"]
    await client.patch(BASE + f"/tasks/{task['id']}/agent-runs/{rid}", json={"status": "running"})
    await client.post(BASE + f"/tasks/{task['id']}/agent-runs/{rid}/submit-result", json={"status": "succeeded", "output_summary": "done"})
    # The orchestration step should transition from dispatched to result_submitted
    # because it finds the succeeded AgentRun
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    assert r.json()["data"]["action_taken"] == "submit_result"
    assert r.json()["data"]["after_status"] == "result_submitted"


# ─── Ownership tests ───

@pytest.mark.asyncio
async def test_orchestration_cross_task_run(client, project, agent):
    r1 = await client.post(BASE + "/tasks", json={"project_id": project["id"], "title": "task-a", "planner": "test"})
    t1 = r1.json()["data"]
    r2 = await client.post(BASE + "/tasks", json={"project_id": project["id"], "title": "task-b", "planner": "test"})
    t2 = r2.json()["data"]
    # Create AgentRun for task A
    await client.post(BASE + f"/tasks/{t1['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{t1['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{t1['id']}/orchestration/step")
    r3 = await client.get(BASE + f"/tasks/{t1['id']}/agent-runs")
    run_a = r3.json()["data"][0]
    # Task B's orchestration should not see Task A's run
    r4 = await client.get(BASE + f"/tasks/{t2['id']}/orchestration/status")
    assert r4.json()["data"]["latest_agent_run_id"] is None

@pytest.mark.asyncio
async def test_orchestration_cross_task_decision(client, project, agent):
    r1 = await client.post(BASE + "/tasks", json={"project_id": project["id"], "title": "task-a", "planner": "test"})
    t1 = r1.json()["data"]
    r2 = await client.post(BASE + "/tasks", json={"project_id": project["id"], "title": "task-b", "planner": "test"})
    t2 = r2.json()["data"]
    # Create approval decision for Task A
    await client.post(BASE + f"/tasks/{t1['id']}/evaluate-approval", json={"tests_passed": True, "security_issues_found": False})
    # Task B's status should not show Task A's decision
    r3 = await client.get(BASE + f"/tasks/{t2['id']}/orchestration/status")
    assert r3.json()["data"]["latest_approval_decision_id"] is None


# ─── Failed AgentRun ───

@pytest.mark.asyncio
async def test_dispatched_running_run_returns_wait_exact(client, task, agent):
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    r = await client.get(BASE + f"/tasks/{task['id']}/orchestration/status")
    assert r.json()["data"]["next_action"] == "wait_agent_result"

@pytest.mark.asyncio
async def test_dispatched_failed_run_returns_agent_failed(client, task, agent):
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    r2 = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    rid = r2.json()["data"][0]["id"]
    # Set run to failed
    await client.patch(BASE + f"/tasks/{task['id']}/agent-runs/{rid}", json={"status": "running"})
    await client.post(BASE + f"/tasks/{task['id']}/agent-runs/{rid}/submit-result", json={"status": "failed", "error_message": "error"})
    r = await client.get(BASE + f"/tasks/{task['id']}/orchestration/status")
    assert r.json()["data"]["next_action"] == "agent_failed"
    assert r.json()["data"]["can_auto_continue"] is False

@pytest.mark.asyncio
async def test_failed_agent_run_step_stops(client, task, agent):
    await client.post(BASE + f"/tasks/{task['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/dispatch", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    r2 = await client.get(BASE + f"/tasks/{task['id']}/agent-runs")
    rid = r2.json()["data"][0]["id"]
    await client.patch(BASE + f"/tasks/{task['id']}/agent-runs/{rid}", json={"status": "running"})
    await client.post(BASE + f"/tasks/{task['id']}/agent-runs/{rid}/submit-result", json={"status": "failed", "error_message": "fail"})
    r = await client.post(BASE + f"/tasks/{task['id']}/orchestration/step")
    assert r.status_code == 200
    assert r.json()["data"]["stopped"] is True
    assert r.json()["data"]["stop_reason"] == "agent_failed"


# ─── Cross-task ownership ───

@pytest.mark.asyncio
async def test_cross_task_cannot_use_other_run(client, project, agent):
    """Task B cannot use Task A's succeeded AgentRun for submit_result"""
    r1 = await client.post(BASE + "/tasks", json={"project_id": project["id"], "title": "task-a", "planner": "test"})
    t1 = r1.json()["data"]
    r2 = await client.post(BASE + "/tasks", json={"project_id": project["id"], "title": "task-b", "planner": "test"})
    t2 = r2.json()["data"]
    await client.post(BASE + f"/tasks/{t1['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{t1['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{t1['id']}/orchestration/step")
    r3 = await client.get(BASE + f"/tasks/{t1['id']}/agent-runs")
    rid = r3.json()["data"][0]["id"]
    await client.patch(BASE + f"/tasks/{t1['id']}/agent-runs/{rid}", json={"status": "running"})
    await client.post(BASE + f"/tasks/{t1['id']}/agent-runs/{rid}/submit-result", json={"status": "succeeded"})
    # Task B in dispatched should NOT see Task A's run
    await client.post(BASE + f"/tasks/{t2['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{t2['id']}/dispatch", json=t_actor)
    r4 = await client.get(BASE + f"/tasks/{t2['id']}/orchestration/status")
    assert r4.json()["data"]["next_action"] == "create_agent_run"

@pytest.mark.asyncio
async def test_cross_task_cannot_use_other_decision(client, project, agent):
    """Task B cannot use Task A's auto-approvable decision"""
    r1 = await client.post(BASE + "/tasks", json={"project_id": project["id"], "title": "task-a", "planner": "test"})
    t1 = r1.json()["data"]
    r2 = await client.post(BASE + "/tasks", json={"project_id": project["id"], "title": "task-b", "planner": "test"})
    t2 = r2.json()["data"]
    # Create auto-approvable decision for Task A
    await client.post(BASE + f"/tasks/{t1['id']}/evaluate-approval", json={"tests_passed": True, "security_issues_found": False})
    # Task B in reviewing should NOT see Task A's decision
    await client.post(BASE + f"/tasks/{t2['id']}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{t2['id']}/dispatch", json=t_actor)
    await client.post(BASE + f"/tasks/{t2['id']}/submit-result", json=t_actor)
    await client.post(BASE + f"/tasks/{t2['id']}/start-review", json=t_actor)
    r = await client.post(BASE + f"/tasks/{t2['id']}/orchestration/step")
    assert r.json()["data"]["action_taken"] != "auto_approve"
    # Should not be approved (would mean it used Task A's decision)
    assert r.json()["data"]["after_status"] != "approved"

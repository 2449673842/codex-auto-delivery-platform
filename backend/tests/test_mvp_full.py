"""
MVP 全链路测试。

覆盖：
- /api/health
- Project CRUD
- Task 完整状态流转（9 态）
- 非法状态跃迁 → 409
- Artifact 上传与查询
- Review 创建与查询
- TaskEvent 自动写入
- 安全边界（root_path / shell / stub）
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import init_db, get_session_factory
from app.main import app


# ─── Fixtures ──────────────────────────────────────────


@pytest.fixture(autouse=True)
async def _reset_db():
    """每个测试用例前重置数据库（清表 + 重建）"""
    from sqlalchemy import text
    from app.database import Base, get_engine

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
async def sample_project(client: AsyncClient) -> dict:
    body = {
        "name": "test-project",
        "display_name": "测试项目",
        "root_path": "/fake/path",
        "repo_url": "https://github.com/test/repo.git",
        "default_branch": "main",
        "package_manager": "pip",
    }
    resp = await client.post("/api/projects", json=body)
    assert resp.status_code == 201
    return resp.json()["data"]


@pytest.fixture
async def sample_task(client: AsyncClient, sample_project: dict) -> dict:
    body = {
        "project_id": sample_project["id"],
        "title": "测试任务",
        "description": "这是一个测试任务",
        "priority": "high",
        "planner": "ai1",
        "executor": "executor-01",
    }
    resp = await client.post("/api/tasks", json=body)
    assert resp.status_code == 201
    return resp.json()["data"]


transition_actor = {"actor": "ai1", "message": "auto test"}


# ═══════════════════════════════════════════════════════
# 1. /api/health
# ═══════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "codex-auto-delivery"
    assert "db" in data
    # agent field removed — verify it's NOT present
    assert "agent" not in data


# ═══════════════════════════════════════════════════════
# 2. Project CRUD
# ═══════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_project(client: AsyncClient):
    body = {
        "name": "my-project",
        "display_name": "我的项目",
        "root_path": "/data/my-project",
        "repo_url": "https://github.com/user/repo.git",
    }
    resp = await client.post("/api/projects", json=body)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["name"] == "my-project"
    assert data["root_path"] == "/data/my-project"
    assert data["default_branch"] == "main"
    assert data["task_count"] == 0


@pytest.mark.asyncio
async def test_create_project_duplicate_name(client: AsyncClient):
    body = {"name": "dup", "root_path": "/a"}
    await client.post("/api/projects", json=body)
    resp = await client.post("/api/projects", json=body)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_projects(client: AsyncClient, sample_project: dict):
    resp = await client.get("/api/projects")
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert len(items) >= 1


@pytest.mark.asyncio
async def test_get_project(client: AsyncClient, sample_project: dict):
    pid = sample_project["id"]
    resp = await client.get(f"/api/projects/{pid}")
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "test-project"


@pytest.mark.asyncio
async def test_update_project(client: AsyncClient, sample_project: dict):
    pid = sample_project["id"]
    resp = await client.patch(f"/api/projects/{pid}", json={"display_name": "改名了"})
    assert resp.status_code == 200
    assert resp.json()["data"]["display_name"] == "改名了"


@pytest.mark.asyncio
async def test_delete_project_with_tasks_fails(
    client: AsyncClient, sample_project: dict, sample_task: dict
):
    pid = sample_project["id"]
    resp = await client.delete(f"/api/projects/{pid}")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_branches(client: AsyncClient, sample_project: dict):
    pid = sample_project["id"]
    resp = await client.get(f"/api/projects/{pid}/branches")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["default_branch"] == "main"
    assert data["current_branch"] == "main"


@pytest.mark.asyncio
async def test_sync_git_info_stub(client: AsyncClient, sample_project: dict):
    pid = sample_project["id"]
    resp = await client.post(f"/api/projects/{pid}/sync-git-info")
    assert resp.status_code == 200
    assert resp.json()["success"] is False
    assert "not implemented" in resp.json()["message"]


# ═══════════════════════════════════════════════════════
# 3. Task 完整状态流转（9 态）
# ═══════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_task(client: AsyncClient, sample_project: dict):
    body = {
        "project_id": sample_project["id"],
        "title": "我的任务",
        "description": "任务描述",
        "planner": "user-01",
    }
    resp = await client.post("/api/tasks", json=body)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["title"] == "我的任务"
    assert data["status"] == "draft"
    assert data["project_id"] == sample_project["id"]


@pytest.mark.asyncio
async def test_full_state_machine(client: AsyncClient, sample_task: dict):
    """完整走一遍 9 态：draft → ticket_ready → dispatched → result_submitted → reviewing → approved → archived"""
    tid = sample_task["id"]
    t = transition_actor

    # draft → ticket_ready
    r = await client.post(f"/api/tasks/{tid}/generate-ticket", json=t)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["ticket_content"] is not None

    # ticket_ready → dispatched
    r = await client.post(f"/api/tasks/{tid}/dispatch", json=t)
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "dispatched"

    # dispatched → result_submitted
    r = await client.post(f"/api/tasks/{tid}/submit-result", json=t)
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "result_submitted"

    # result_submitted → reviewing
    r = await client.post(f"/api/tasks/{tid}/start-review", json=t)
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "reviewing"

    # reviewing → approved
    r = await client.post(f"/api/tasks/{tid}/approve", json=t)
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "approved"

    # approved → archived
    r = await client.post(f"/api/tasks/{tid}/archive", json=t)
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "archived"


@pytest.mark.asyncio
async def test_changes_requested_return_path(client: AsyncClient, sample_task: dict):
    """测试 changes_requested → dispatched 返工路径"""
    tid = sample_task["id"]
    t = transition_actor

    await client.post(f"/api/tasks/{tid}/generate-ticket", json=t)  # → ticket_ready
    await client.post(f"/api/tasks/{tid}/dispatch", json=t)  # → dispatched
    await client.post(f"/api/tasks/{tid}/submit-result", json=t)  # → result_submitted
    await client.post(f"/api/tasks/{tid}/start-review", json=t)  # → reviewing

    # reviewing → changes_requested
    r = await client.post(f"/api/tasks/{tid}/request-changes", json=t)
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "changes_requested"

    # changes_requested → dispatched（返工）
    r = await client.post(f"/api/tasks/{tid}/dispatch", json=t)
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "dispatched"


@pytest.mark.asyncio
async def test_reject_then_archive(client: AsyncClient, sample_task: dict):
    tid = sample_task["id"]
    t = transition_actor

    await client.post(f"/api/tasks/{tid}/generate-ticket", json=t)
    await client.post(f"/api/tasks/{tid}/dispatch", json=t)
    await client.post(f"/api/tasks/{tid}/submit-result", json=t)
    await client.post(f"/api/tasks/{tid}/start-review", json=t)

    r = await client.post(f"/api/tasks/{tid}/reject", json=t)
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "rejected"

    r = await client.post(f"/api/tasks/{tid}/archive", json=t)
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "archived"


# ═══════════════════════════════════════════════════════
# 4. 非法状态跃迁 → 409
# ═══════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_illegal_transition_returns_409(client: AsyncClient, sample_task: dict):
    tid = sample_task["id"]
    t = transition_actor

    # Cannot dispatch from draft (need ticket_ready first)
    r = await client.post(f"/api/tasks/{tid}/dispatch", json=t)
    assert r.status_code == 409

    # Cannot approve from draft
    r = await client.post(f"/api/tasks/{tid}/approve", json=t)
    assert r.status_code == 409

    # Cannot archive from draft
    r = await client.post(f"/api/tasks/{tid}/archive", json=t)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_archived_is_terminal(client: AsyncClient, sample_task: dict):
    tid = sample_task["id"]
    t = transition_actor

    # Go through full path to archived
    await client.post(f"/api/tasks/{tid}/generate-ticket", json=t)
    await client.post(f"/api/tasks/{tid}/dispatch", json=t)
    await client.post(f"/api/tasks/{tid}/submit-result", json=t)
    await client.post(f"/api/tasks/{tid}/start-review", json=t)
    await client.post(f"/api/tasks/{tid}/approve", json=t)
    await client.post(f"/api/tasks/{tid}/archive", json=t)

    # Cannot transition from archived
    r = await client.post(f"/api/tasks/{tid}/dispatch", json=t)
    assert r.status_code == 409

    r = await client.post(f"/api/tasks/{tid}/approve", json=t)
    assert r.status_code == 409


# ═══════════════════════════════════════════════════════
# 5. Artifact 上传与查询
# ═══════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_upload_artifact(client: AsyncClient, sample_task: dict):
    tid = sample_task["id"]
    body = {
        "artifact_type": "diff",
        "content": "--- a/file.py\n+++ b/file.py\n@@ -1,3 +1,4 @@\n+new line",
        "filename": "changes.diff",
    }
    resp = await client.post(f"/api/tasks/{tid}/artifacts", json=body)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["artifact_type"] == "diff"
    assert data["sha256"] is not None
    assert data["size_bytes"] > 0


@pytest.mark.asyncio
async def test_upload_artifact_archived_fails(
    client: AsyncClient, sample_task: dict
):
    tid = sample_task["id"]
    t = transition_actor

    await client.post(f"/api/tasks/{tid}/generate-ticket", json=t)
    await client.post(f"/api/tasks/{tid}/dispatch", json=t)
    await client.post(f"/api/tasks/{tid}/submit-result", json=t)
    await client.post(f"/api/tasks/{tid}/start-review", json=t)
    await client.post(f"/api/tasks/{tid}/approve", json=t)
    await client.post(f"/api/tasks/{tid}/archive", json=t)

    resp = await client.post(
        f"/api/tasks/{tid}/artifacts",
        json={"artifact_type": "diff", "content": "data"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_artifacts(client: AsyncClient, sample_task: dict):
    tid = sample_task["id"]
    await client.post(
        f"/api/tasks/{tid}/artifacts",
        json={"artifact_type": "execution_log", "content": "log line 1"},
    )
    await client.post(
        f"/api/tasks/{tid}/artifacts",
        json={"artifact_type": "diff", "content": "diff content"},
    )
    resp = await client.get(f"/api/tasks/{tid}/artifacts")
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert len(items) >= 2


# ═══════════════════════════════════════════════════════
# 6. Review 创建与查询
# ═══════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_submit_review(client: AsyncClient, sample_task: dict):
    tid = sample_task["id"]
    await client.post(f"/api/tasks/{tid}/generate-ticket", json=transition_actor)
    await client.post(f"/api/tasks/{tid}/dispatch", json=transition_actor)

    review_body = {
        "reviewer": "reviewer-01",
        "decision": "changes_requested",
        "comments": "需要修改变量命名",
        "issues": '[{"severity":"major","file":"src/main.py","line":42,"message":"Bad naming"}]',
    }
    resp = await client.post(f"/api/tasks/{tid}/reviews", json=review_body)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["decision"] == "changes_requested"
    assert data["reviewer"] == "reviewer-01"


@pytest.mark.asyncio
async def test_list_reviews(client: AsyncClient, sample_task: dict):
    tid = sample_task["id"]
    await client.post(f"/api/tasks/{tid}/generate-ticket", json=transition_actor)
    await client.post(f"/api/tasks/{tid}/dispatch", json=transition_actor)
    await client.post(
        f"/api/tasks/{tid}/reviews",
        json={"reviewer": "r1", "decision": "approved"},
    )
    resp = await client.get(f"/api/tasks/{tid}/reviews")
    assert resp.status_code == 200
    assert len(resp.json()["data"]) >= 1


# ═══════════════════════════════════════════════════════
# 7. TaskEvent 自动写入
# ═══════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_events_created_during_lifecycle(
    client: AsyncClient, sample_task: dict
):
    tid = sample_task["id"]
    t = transition_actor

    await client.post(f"/api/tasks/{tid}/generate-ticket", json=t)
    await client.post(f"/api/tasks/{tid}/dispatch", json=t)
    await client.post(f"/api/tasks/{tid}/submit-result", json=t)

    resp = await client.get(f"/api/tasks/{tid}/events")
    assert resp.status_code == 200
    events = resp.json()["data"]
    # Expect at least: status_changed (create), ticket_generated, status_changed (dispatch),
    #   status_changed (submit-result)
    assert len(events) >= 4
    types = [e["event_type"] for e in events]
    assert "status_changed" in types
    assert "ticket_generated" in types


# ═══════════════════════════════════════════════════════
# 8. 安全边界：Stub 端点
# ═══════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_pr_stub(client: AsyncClient, sample_task: dict):
    tid = sample_task["id"]
    resp = await client.post(f"/api/tasks/{tid}/create-pr", json={})
    # Stub 端点不走 body 校验（无 Depends），应返回 200
    assert resp.status_code == 200
    assert resp.json()["success"] is False
    assert "not implemented" in resp.json()["message"]


@pytest.mark.asyncio
async def test_trigger_ci_stub(client: AsyncClient, sample_task: dict):
    tid = sample_task["id"]
    resp = await client.post(f"/api/tasks/{tid}/trigger-ci", json={})
    assert resp.status_code == 200
    assert resp.json()["success"] is False
    assert "not implemented" in resp.json()["message"]


@pytest.mark.asyncio
async def test_trigger_deploy_stub(client: AsyncClient, sample_task: dict):
    tid = sample_task["id"]
    resp = await client.post(f"/api/tasks/{tid}/trigger-deploy", json={})
    assert resp.status_code == 200
    assert resp.json()["success"] is False
    assert "not implemented" in resp.json()["message"]


# ═══════════════════════════════════════════════════════
# 9. 删除任务
# ═══════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_delete_draft_task(client: AsyncClient, sample_task: dict):
    tid = sample_task["id"]
    resp = await client.delete(f"/api/tasks/{tid}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_delete_non_draft_task_fails(
    client: AsyncClient, sample_task: dict
):
    tid = sample_task["id"]
    await client.post(f"/api/tasks/{tid}/generate-ticket", json=transition_actor)
    resp = await client.delete(f"/api/tasks/{tid}")
    assert resp.status_code == 409


# ═══════════════════════════════════════════════════════
# 10. 404 处理
# ═══════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_nonexistent_task_returns_404(client: AsyncClient):
    resp = await client.get("/api/tasks/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_nonexistent_project_returns_404(client: AsyncClient):
    resp = await client.get("/api/projects/99999")
    assert resp.status_code == 404

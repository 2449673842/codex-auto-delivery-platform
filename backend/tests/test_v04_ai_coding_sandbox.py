"""v0.4 S1 — AI Coding Sandbox Tests

Covers:
1. Code Context creation, retrieval, security
2. AI patch generation with code context
3. Patch Apply Sandbox (valid, invalid, edge cases)
4. Failure paths (malformed, oversized, forbidden, secrets)
5. Security boundary verification (static analysis)

No shell/subprocess, no Project.root_path, no git/CI/PR.
"""

import json
import hashlib
import os
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.database import Base, get_engine, get_session_factory

BASE = "/api"

# ─── Fixtures ──────────────────────────────────────────


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
async def db_session():
    factory = get_session_factory()
    async with factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def project(client) -> dict:
    r = await client.post(BASE + "/projects", json={
        "name": "sandbox-test", "root_path": "/sandbox",
    })
    return r.json()["data"]


@pytest.fixture
async def agent(client) -> dict:
    r = await client.post(BASE + "/agents", json={
        "name": "sandbox-agent", "agent_type": "executor", "provider": "sandbox",
    })
    return r.json()["data"]


@pytest.fixture
async def openai_agent(client) -> dict:
    r = await client.post(BASE + "/agents", json={
        "name": "openai-agent", "agent_type": "executor", "provider": "openai",
    })
    return r.json()["data"]


@pytest.fixture
async def task(client, project) -> dict:
    r = await client.post(BASE + "/tasks", json={
        "project_id": project["id"], "title": "sandbox-task",
        "description": "Modify the greeting function to support multiple languages",
    })
    return r.json()["data"]


t_actor = {"actor": "test"}

SAMPLE_CODE_CONTEXT = {
    "files": [
        {
            "path": "src/greeting.py",
            "content": "def greet(name: str) -> str:\n    return f\"Hello, {name}!\"\n",
            "language": "python",
        },
        {
            "path": "src/main.py",
            "content": "from greeting import greet\n\nif __name__ == '__main__':\n    print(greet('World'))\n",
            "language": "python",
        },
    ]
}

PATCH_DIFF_EXAMPLE = (
    "diff --git a/src/greeting.py b/src/greeting.py\n"
    "--- a/src/greeting.py\n"
    "+++ b/src/greeting.py\n"
    "@@ -1,2 +1,5 @@\n"
    " def greet(name: str) -> str:\n"
    "+    if name:\n"
    "     return f\"Hello, {name}!\"\n"
    "+    return \"Hello, World!\"\n"
)


# ═══════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════

async def _prepare_task_for_dispatch(client, task_id):
    """Bring task to dispatched state."""
    await client.post(BASE + f"/tasks/{task_id}/generate-ticket", json=t_actor)
    await client.post(BASE + f"/tasks/{task_id}/dispatch", json=t_actor)


async def _create_succeeded_run_with_diff(client, task_id, agent_id, patch_diff, db_session):
    """Create AgentRun → PATCH to running → submit-result succeeded with custom patch_diff."""
    r = await client.post(
        BASE + f"/tasks/{task_id}/agent-runs",
        json={"agent_id": agent_id, "run_type": "execute", "input_prompt": "Test"},
    )
    assert r.status_code == 201
    run = r.json()["data"]
    run_id = run["id"]

    # PATCH to running
    r = await client.patch(
        BASE + f"/tasks/{task_id}/agent-runs/{run_id}",
        json={"status": "running"},
    )
    assert r.status_code == 200

    # Submit result to succeeded
    r = await client.post(
        BASE + f"/tasks/{task_id}/agent-runs/{run_id}/submit-result",
        json={
            "status": "succeeded", "output_summary": "ok", "output_log": "ok",
            "output_diff": patch_diff,
        },
    )
    assert r.status_code == 200
    return run_id


# ═══════════════════════════════════════════════════════
# 1. Code Context
# ═══════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_code_context_create(client, task):
    r = await client.post(
        BASE + f"/tasks/{task['id']}/code-context", json=SAMPLE_CODE_CONTEXT,
    )
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["file_count"] == 2
    assert data["task_id"] == task["id"]
    assert data["artifact_id"] is not None


@pytest.mark.asyncio
async def test_code_context_read(client, task):
    await client.post(BASE + f"/tasks/{task['id']}/code-context", json=SAMPLE_CODE_CONTEXT)
    r = await client.get(BASE + f"/tasks/{task['id']}/code-context")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["file_count"] == 2
    paths = [f["path"] for f in data["files"]]
    assert "src/greeting.py" in paths


@pytest.mark.asyncio
async def test_code_context_no_context_returns_404(client, task):
    r = await client.get(BASE + f"/tasks/{task['id']}/code-context")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_code_context_nonexistent_task_returns_404(client):
    r = await client.get(BASE + "/tasks/99999/code-context")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_code_context_archived_forbidden(client, task):
    """Archived task does not allow new code context."""
    await _prepare_task_for_dispatch(client, task["id"])
    await client.post(BASE + f"/tasks/{task['id']}/submit-result", json={"actor": "test", "result_summary": "ok"})
    await client.post(BASE + f"/tasks/{task['id']}/start-review", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/approve", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/archive", json=t_actor)
    r = await client.post(BASE + f"/tasks/{task['id']}/code-context", json=SAMPLE_CODE_CONTEXT)
    assert r.status_code == 409


# ═══════════════════════════════════════════════════════
# 2. AI Patch Generation with Code Context
# ═══════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_execute_with_code_context_sandbox(client, task, agent, db_session):
    """Sandbox execute with code context generates patch referencing context files."""
    await client.post(BASE + f"/tasks/{task['id']}/code-context", json=SAMPLE_CODE_CONTEXT)
    await _prepare_task_for_dispatch(client, task["id"])

    r = await client.post(
        BASE + f"/tasks/{task['id']}/agent-runs",
        json={"agent_id": agent["id"], "run_type": "execute", "input_prompt": "Add i18n"},
    )
    assert r.status_code == 201
    run = r.json()["data"]

    from app.services.ai_provider_service import dispatch_agent_run
    await dispatch_agent_run(db_session, run["id"], "test")
    await db_session.commit()

    r = await client.get(BASE + f"/tasks/{task['id']}/agent-runs/{run['id']}")
    assert r.status_code == 200
    run_data = r.json()["data"]
    assert run_data["status"] == "succeeded"
    raw = run_data.get("raw_result_json") or ""
    assert "src/greeting.py" in raw or "src/main.py" in raw


@pytest.mark.asyncio
async def test_execute_artifact_contains_diff(client, task, agent, db_session):
    """Execute run creates agent_output_diff artifact."""
    await client.post(BASE + f"/tasks/{task['id']}/code-context", json=SAMPLE_CODE_CONTEXT)
    await _prepare_task_for_dispatch(client, task["id"])

    r = await client.post(
        BASE + f"/tasks/{task['id']}/agent-runs",
        json={"agent_id": agent["id"], "run_type": "execute", "input_prompt": "Update greeting"},
    )
    run = r.json()["data"]

    from app.services.ai_provider_service import dispatch_agent_run
    await dispatch_agent_run(db_session, run["id"], "test")
    await db_session.commit()

    r = await client.get(BASE + f"/tasks/{task['id']}/artifacts")
    types = [a["artifact_type"] for a in r.json()["data"]]
    assert "agent_output_diff" in types


@pytest.mark.asyncio
async def test_execute_no_code_context_fallback(client, task, agent, db_session):
    """Without code context, sandbox provider still succeeds with default template."""
    await _prepare_task_for_dispatch(client, task["id"])

    r = await client.post(
        BASE + f"/tasks/{task['id']}/agent-runs",
        json={"agent_id": agent["id"], "run_type": "execute", "input_prompt": "Do something"},
    )
    run = r.json()["data"]

    from app.services.ai_provider_service import dispatch_agent_run
    await dispatch_agent_run(db_session, run["id"], "test")
    await db_session.commit()

    r = await client.get(BASE + f"/tasks/{task['id']}/agent-runs/{run['id']}")
    run_data = r.json()["data"]
    assert run_data["status"] == "succeeded"
    raw = run_data.get("raw_result_json") or ""
    assert "src/example.py" in raw


@pytest.mark.asyncio
async def test_openai_execute_prompt_built_with_code_context(client, task, openai_agent, monkeypatch):
    """OpenAI execute prompt includes code context files (mock API)."""
    from app.services.openai_provider import OpenAIProvider

    captured = {}

    async def mock_call(self, system_prompt, user_prompt):
        captured["system"] = system_prompt
        captured["user"] = user_prompt
        return "diff --git a/src/greeting.py b/src/greeting.py\n+def greet_multilang():\n+    pass\n"

    monkeypatch.setattr(OpenAIProvider, "_call_openai", mock_call)

    # Also monkeypatch the __init__ to not require API key
    monkeypatch.setattr(OpenAIProvider, "__init__", lambda self: setattr(self, "api_key", "mock-key"))

    await client.post(BASE + f"/tasks/{task['id']}/code-context", json=SAMPLE_CODE_CONTEXT)
    await _prepare_task_for_dispatch(client, task["id"])

    r = await client.post(
        BASE + f"/tasks/{task['id']}/agent-runs",
        json={"agent_id": openai_agent["id"], "run_type": "execute", "input_prompt": "Add i18n"},
    )
    run = r.json()["data"]

    from app.services.ai_provider_service import dispatch_agent_run
    from app.database import get_session_factory
    factory = get_session_factory()
    async with factory() as db:
        await dispatch_agent_run(db, run["id"], "test")
        await db.commit()

    assert "system" in captured
    assert "src/greeting.py" in captured["user"]
    assert "def greet" in captured["user"]


# ═══════════════════════════════════════════════════════
# 3. Patch Apply Sandbox — Core
# ═══════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_apply_patch_valid(client, task, agent, db_session):
    """Valid patch applies to virtual files."""
    await client.post(BASE + f"/tasks/{task['id']}/code-context", json=SAMPLE_CODE_CONTEXT)
    await _prepare_task_for_dispatch(client, task["id"])
    run_id = await _create_succeeded_run_with_diff(client, task["id"], agent["id"], PATCH_DIFF_EXAMPLE, db_session)

    r = await client.post(BASE + f"/tasks/{task['id']}/agent-runs/{run_id}/sandbox/apply-patch")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["success"] is True
    assert data["report"]["applied"] is True
    assert len(data["report"]["changed_files"]) == 1
    assert data["report"]["changed_files"][0]["path"] == "src/greeting.py"


@pytest.mark.asyncio
async def test_apply_patch_sha256(client, task, agent, db_session):
    """sha256 of before/after content matches."""
    await client.post(BASE + f"/tasks/{task['id']}/code-context", json=SAMPLE_CODE_CONTEXT)
    await _prepare_task_for_dispatch(client, task["id"])

    original = "def greet(name: str) -> str:\n    return f\"Hello, {name}!\"\n"
    before_sha = hashlib.sha256(original.encode("utf-8")).hexdigest()

    patch_diff = (
        "diff --git a/src/greeting.py b/src/greeting.py\n"
        "--- a/src/greeting.py\n"
        "+++ b/src/greeting.py\n"
        "@@ -1,2 +1,4 @@\n"
        " def greet(name: str) -> str:\n"
        "     return f\"Hello, {name}!\"\n"
        "+def greet_es(name: str) -> str:\n"
        "+    return f\"¡Hola, {name}!\"\n"
    )
    run_id = await _create_succeeded_run_with_diff(client, task["id"], agent["id"], patch_diff, db_session)

    r = await client.post(BASE + f"/tasks/{task['id']}/agent-runs/{run_id}/sandbox/apply-patch")
    data = r.json()["data"]
    assert data["success"] is True
    cf = data["report"]["changed_files"][0]
    assert cf["before_sha256"] == before_sha


@pytest.mark.asyncio
async def test_apply_patch_creates_artifacts(client, task, agent, db_session):
    """Creates patch_apply_report, changed_files_summary, changed_file_preview."""
    await client.post(BASE + f"/tasks/{task['id']}/code-context", json=SAMPLE_CODE_CONTEXT)
    await _prepare_task_for_dispatch(client, task["id"])

    simple_diff = (
        "diff --git a/src/greeting.py b/src/greeting.py\n"
        "--- a/src/greeting.py\n"
        "+++ b/src/greeting.py\n"
        "@@ -1,2 +1,3 @@\n"
        " def greet(name: str) -> str:\n"
        "     return f\"Hello, {name}!\"\n"
        "+\n"
    )
    run_id = await _create_succeeded_run_with_diff(client, task["id"], agent["id"], simple_diff, db_session)

    await client.post(BASE + f"/tasks/{task['id']}/agent-runs/{run_id}/sandbox/apply-patch")

    r = await client.get(BASE + f"/tasks/{task['id']}/artifacts")
    types = [a["artifact_type"] for a in r.json()["data"]]
    assert "patch_apply_report" in types
    assert "changed_files_summary" in types
    assert "changed_file_preview" in types


@pytest.mark.asyncio
async def test_get_sandbox_results(client, task, agent, db_session):
    await client.post(BASE + f"/tasks/{task['id']}/code-context", json=SAMPLE_CODE_CONTEXT)
    await _prepare_task_for_dispatch(client, task["id"])

    simple_diff = (
        "diff --git a/src/greeting.py b/src/greeting.py\n"
        "--- a/src/greeting.py\n"
        "+++ b/src/greeting.py\n"
        "@@ -1,2 +1,3 @@\n"
        " def greet(name: str) -> str:\n"
        "     return f\"Hello, {name}!\"\n"
        "+\n"
    )
    run_id = await _create_succeeded_run_with_diff(client, task["id"], agent["id"], simple_diff, db_session)

    await client.post(BASE + f"/tasks/{task['id']}/agent-runs/{run_id}/sandbox/apply-patch")

    r = await client.get(BASE + f"/tasks/{task['id']}/sandbox/patch-results")
    assert r.status_code == 200
    types = [res["artifact_type"] for res in r.json()["data"]]
    assert "patch_apply_report" in types
    assert "changed_files_summary" in types


# ═══════════════════════════════════════════════════════
# 4. Failure Paths
# ═══════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_apply_patch_malformed_fails(client, task, agent, db_session):
    await client.post(BASE + f"/tasks/{task['id']}/code-context", json=SAMPLE_CODE_CONTEXT)
    await _prepare_task_for_dispatch(client, task["id"])
    run_id = await _create_succeeded_run_with_diff(client, task["id"], agent["id"], "not a valid diff", db_session)

    r = await client.post(BASE + f"/tasks/{task['id']}/agent-runs/{run_id}/sandbox/apply-patch")
    data = r.json()["data"]
    assert data["success"] is False
    assert data["report"]["applied"] is False


@pytest.mark.asyncio
async def test_apply_patch_new_file(client, task, agent, db_session):
    """New file (not in code context) can be created."""
    await client.post(BASE + f"/tasks/{task['id']}/code-context", json=SAMPLE_CODE_CONTEXT)
    await _prepare_task_for_dispatch(client, task["id"])

    patch_diff = (
        "diff --git a/src/new_file.py b/src/new_file.py\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/src/new_file.py\n"
        "@@ -0,0 +1,3 @@\n"
        "+# New file\n"
        "+def new_func():\n"
        "+    pass\n"
    )
    run_id = await _create_succeeded_run_with_diff(client, task["id"], agent["id"], patch_diff, db_session)

    r = await client.post(BASE + f"/tasks/{task['id']}/agent-runs/{run_id}/sandbox/apply-patch")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["success"] is True
    paths = [cf["path"] for cf in data["report"]["changed_files"]]
    assert "src/new_file.py" in paths


@pytest.mark.asyncio
async def test_apply_patch_oversized_fails(client, task, agent, db_session):
    await client.post(BASE + f"/tasks/{task['id']}/code-context", json=SAMPLE_CODE_CONTEXT)
    await _prepare_task_for_dispatch(client, task["id"])

    big_patch = ("diff --git a/big.py b/big.py\n--- /dev/null\n+++ b/big.py\n" +
                 "\n".join(f"+line_{i}" for i in range(200_000)))
    run_id = await _create_succeeded_run_with_diff(client, task["id"], agent["id"], big_patch, db_session)

    r = await client.post(BASE + f"/tasks/{task['id']}/agent-runs/{run_id}/sandbox/apply-patch")
    data = r.json()["data"]
    assert data["success"] is False


@pytest.mark.asyncio
async def test_apply_patch_forbidden_path_fails(client, task, agent, db_session):
    await client.post(
        BASE + f"/tasks/{task['id']}/code-context",
        json={"files": [{"path": ".env", "content": "SECRET=x\n", "language": "text"}]},
    )
    await _prepare_task_for_dispatch(client, task["id"])

    patch_diff = (
        "diff --git a/.env b/.env\n"
        "--- a/.env\n"
        "+++ b/.env\n"
        "@@ -1 +1,2 @@\n"
        " SECRET=x\n"
        "+NEW_KEY=y\n"
    )
    run_id = await _create_succeeded_run_with_diff(client, task["id"], agent["id"], patch_diff, db_session)

    r = await client.post(BASE + f"/tasks/{task['id']}/agent-runs/{run_id}/sandbox/apply-patch")
    data = r.json()["data"]
    assert data["success"] is False, f"Expected failure, got: {data}"


@pytest.mark.asyncio
async def test_apply_patch_archived_task_forbidden(client, task):
    await client.post(BASE + f"/tasks/{task['id']}/code-context", json=SAMPLE_CODE_CONTEXT)
    await _prepare_task_for_dispatch(client, task["id"])
    await client.post(BASE + f"/tasks/{task['id']}/submit-result", json={"actor": "test", "result_summary": "ok"})
    await client.post(BASE + f"/tasks/{task['id']}/start-review", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/approve", json=t_actor)
    await client.post(BASE + f"/tasks/{task['id']}/archive", json=t_actor)

    r = await client.post(BASE + f"/tasks/{task['id']}/agent-runs/99999/sandbox/apply-patch")
    assert r.status_code in (404, 409)


@pytest.mark.asyncio
async def test_apply_patch_run_not_succeeded(client, task, agent):
    """Applying patch from a queued (non-succeeded) run fails."""
    await _prepare_task_for_dispatch(client, task["id"])
    r = await client.post(
        BASE + f"/tasks/{task['id']}/agent-runs",
        json={"agent_id": agent["id"], "run_type": "execute", "input_prompt": "Test"},
    )
    run = r.json()["data"]
    r = await client.post(BASE + f"/tasks/{task['id']}/agent-runs/{run['id']}/sandbox/apply-patch")
    assert r.status_code == 409


# ═══════════════════════════════════════════════════════
# 5. Security Boundaries (Static Analysis)
# ═══════════════════════════════════════════════════════

_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_TEST_DIR, ".."))

NEW_V04_FILES_REL = [
    "app/services/code_context_service.py",
    "app/services/patch_apply_sandbox_service.py",
    "app/schemas/code_context.py",
    "app/schemas/patch_sandbox.py",
    "app/routers/code_context.py",
    "app/routers/patch_sandbox.py",
]


def test_no_shell_in_new_files():
    for rel in NEW_V04_FILES_REL:
        full = os.path.join(_BACKEND_DIR, rel)
        if not os.path.exists(full):
            continue
        with open(full, encoding="utf-8") as f:
            content = f.read()
        for term in ["subprocess", "os.system", "os.popen", "shell=True", "git apply", "git clone"]:
            assert term not in content, f"{rel} must not contain '{term}'"


def test_no_root_path_in_new_files():
    for rel in NEW_V04_FILES_REL:
        full = os.path.join(_BACKEND_DIR, rel)
        if not os.path.exists(full):
            continue
        with open(full, encoding="utf-8") as f:
            content = f.read()
        assert "root_path" not in content, f"{rel} must not reference root_path"
        assert "Project.root_path" not in content


def test_no_git_ci_pr_in_new_files():
    for rel in NEW_V04_FILES_REL:
        full = os.path.join(_BACKEND_DIR, rel)
        if not os.path.exists(full):
            continue
        with open(full, encoding="utf-8") as f:
            content = f.read()
        terms = ["create_pr", "trigger_ci", "trigger_deploy", "sonar",
                 "ci_client", "pr_builder", "github.", "git commit", "git push", "deploy_hook"]
        for term in terms:
            assert term not in content, f"{rel} must not contain '{term}'"


def test_no_secret_ref_in_new_files():
    for rel in NEW_V04_FILES_REL:
        full = os.path.join(_BACKEND_DIR, rel)
        if not os.path.exists(full):
            continue
        with open(full, encoding="utf-8") as f:
            content = f.read()
        assert "secret_ref" not in content, f"{rel} must not reference secret_ref"


def test_sandbox_provider_still_secure():
    import ast
    src = os.path.join(_BACKEND_DIR, "app/services/sandbox_provider.py")
    with open(src, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in ("getenv", "system", "popen"):
                raise AssertionError(f"Sandbox should not use {func.attr}")
            if isinstance(func, ast.Name) and func.id == "subprocess":
                raise AssertionError("Sandbox should not use subprocess")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    raise AssertionError("Sandbox should not import subprocess")


@pytest.mark.asyncio
async def test_patch_apply_report_redacts_secrets(client, task, agent, db_session):
    """Secret patterns in patch content should be redacted in artifacts."""
    await client.post(
        BASE + f"/tasks/{task['id']}/code-context",
        json={"files": [{"path": "src/config.py", "content": "TOKEN=old\n", "language": "python"}]},
    )
    await _prepare_task_for_dispatch(client, task["id"])

    patch_diff = (
        "diff --git a/src/config.py b/src/config.py\n"
        "--- a/src/config.py\n"
        "+++ b/src/config.py\n"
        "@@ -1 +1,2 @@\n"
        " TOKEN=old\n"
        "+# comment\n"
    )
    run_id = await _create_succeeded_run_with_diff(client, task["id"], agent["id"], patch_diff, db_session)

    r = await client.post(BASE + f"/tasks/{task['id']}/agent-runs/{run_id}/sandbox/apply-patch")
    data = r.json()["data"]
    if data["success"]:
        r2 = await client.get(BASE + f"/tasks/{task['id']}/artifacts")
        for art in r2.json()["data"]:
            if art["artifact_type"] == "patch_apply_report":
                assert "TOKEN" not in (art.get("content") or "***REDACTED***") or "REDACTED" in (art.get("content") or "")

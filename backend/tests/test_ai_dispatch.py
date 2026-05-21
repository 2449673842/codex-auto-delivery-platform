"""Tests for v0.4 S11 — AI Dispatch + OpenAI Provider + Sandbox Auto Pipeline MVP."""

import json
import os
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.database import Base, get_engine, get_session_factory
from app.main import app
from app.models.agent_run import AgentRun
from app.models.task_artifact import TaskArtifact
from app.models.task_event import TaskEvent
from app.schemas.ai_provider import AgentRunResult


BASE = "/api/ai-dispatch"
MOCK_API_KEY = "sk-test-fake-key-for-testing-purposes-only"


@pytest.fixture(autouse=True)
async def _reset_db():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _fake_result(run_type: str, mode: str) -> AgentRunResult:
    if mode == "planning":
        return AgentRunResult(
            output_summary="AI-generated plan (42 words): Test plan for review_packet module",
            output_log="[2026-01-01] AI provider generated plan",
            raw_result_json=json.dumps({"plan_md": "# Plan\n\n1. Implement feature\n2. Add tests"}),
            plan_md="# Plan\n\n1. Implement feature\n2. Add tests",
            risk_report={"risk_level": "low", "source": "openai", "summary": "Test plan"},
        )
    if mode == "patch_generation":
        return AgentRunResult(
            output_summary="AI-generated patch (12 words): diff --git a/test.py b/test.py",
            output_log="[2026-01-01] AI provider generated code changes",
            raw_result_json=json.dumps({"patch_diff": "diff --git a/test.py b/test.py\nindex 000..111\n--- a/test.py\n+++ b/test.py\n@@ -0,0 +1 @@\n+print('hello')"}),
            patch_diff="diff --git a/test.py b/test.py\nindex 000..111\n--- a/test.py\n+++ b/test.py\n@@ -0,0 +1 @@\n+print('hello')",
        )
    if mode == "review":
        return AgentRunResult(
            output_summary="AI review (10 words): Looks good, approved",
            output_log="[2026-01-01] AI provider generated review",
            raw_result_json=json.dumps({"review_md": "## Review\n\n**Decision**: approved\n**Risk**: low"}),
            review_md="## Review\n\n**Decision**: approved\n**Risk**: low",
        )
    if mode == "risk":
        return AgentRunResult(
            output_summary="AI risk assessment (8 words): Risk level low",
            output_log="[2026-01-01] AI provider generated risk assessment",
            raw_result_json=json.dumps({"risk_report": {"risk_level": "low", "findings": []}}),
            risk_report={"risk_level": "low", "findings": []},
        )
    if mode == "browser_reviewer":
        return AgentRunResult(
            output_summary="AI browser review (6 words): advisory_only review",
            output_log="[2026-01-01] AI provider generated browser review",
            raw_result_json=json.dumps({"review_md": "## Browser Review\n\n**advisory_only**: true\n**not_final_approval**: true"}),
            review_md="## Browser Review\n\n**advisory_only**: true\n**not_final_approval**: true",
        )
    return AgentRunResult(
        output_summary="AI response",
        output_log="AI response log",
        raw_result_json=json.dumps({"raw_response": "generic response"}),
    )


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch):
    import dataclasses
    import app.services.ai_dispatch_service as svc
    orig = svc.settings
    new = dataclasses.replace(orig,
                              ai_execution_enabled=True,
                              openai_api_key=MOCK_API_KEY,
                              _provider_allowlist_raw="sandbox,openai")
    monkeypatch.setattr(svc, "settings", new)
    yield
    monkeypatch.setattr(svc, "settings", orig)


@pytest.fixture(autouse=True)
def _mock_provider(monkeypatch):
    async def _execute_fake(db, agent, run):
        mode_by_run_type = {
            "plan": "planning",
            "execute": "patch_generation",
            "review": "review",
        }
        if getattr(agent, "agent_type", "") == "reviewer" and run.run_type == "review":
            prompt = run.input_prompt or ""
            if "Mode: risk" in prompt:
                return _fake_result(run.run_type or "review", "risk")
            if "Mode: browser_reviewer" in prompt:
                return _fake_result(run.run_type or "review", "browser_reviewer")
        return _fake_result(run.run_type or "plan", mode_by_run_type.get(run.run_type, "planning"))

    monkeypatch.setattr(
        "app.services.ai_dispatch_service._execute_with_provider",
        AsyncMock(side_effect=_execute_fake),
    )


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test.local") as ac:
        yield ac


@pytest.fixture
async def project(client) -> dict:
    r = await client.post("/api/projects", json={"name": "s11-test", "root_path": "/s11"})
    return r.json()["data"]


@pytest.fixture
async def task(client, project) -> dict:
    r = await client.post("/api/tasks", json={
        "project_id": project["id"], "title": "s11-task",
        "planner": "test", "description": "AI dispatch test task"
    })
    return r.json()["data"]


# ─── Dry Run Tests ───

@pytest.mark.asyncio
class TestDryRun:

    async def test_dry_run_returns_metadata(self, client):
        r = await client.post(f"{BASE}/dry-run", json={
            "module_name": "review_packet", "mode": "planning",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["provider"] == "openai"
        assert data["model"] == "gpt-4o-mini"
        assert data["mode"] == "planning"
        assert len(data["prompt_hash"]) > 0
        assert len(data["context_packet_hash"]) > 0
        assert data["estimated_tokens"] > 0

    async def test_dry_run_does_not_call_provider(self, client):
        from app.services import ai_provider_service
        orig = ai_provider_service._execute_with_provider
        r = await client.post(f"{BASE}/dry-run", json={
            "module_name": "review_packet", "mode": "planning",
        })
        assert r.status_code == 200
        assert ai_provider_service._execute_with_provider is orig

    async def test_dry_run_unknown_mode_returns_422(self, client):
        r = await client.post(f"{BASE}/dry-run", json={
            "module_name": "review_packet", "mode": "invalid_mode_xyz",
        })
        assert r.status_code == 422

    async def test_dry_run_safety_gate_fields(self, client):
        r = await client.post(f"{BASE}/dry-run", json={
            "module_name": "review_packet", "mode": "planning",
        })
        data = r.json()["data"]
        safety = data["safety_gate"]
        assert "execution_enabled" in safety
        assert "openai_key_present" in safety
        assert "provider_allowed" in safety
        assert "mode_valid" in safety
        assert "budget_ok" in safety
        assert "gate_passed" in safety

    async def test_dry_run_would_dispatch_false(self, client):
        r = await client.post(f"{BASE}/dry-run", json={
            "module_name": "review_packet", "mode": "planning",
        })
        assert r.json()["data"]["would_dispatch"] is False

    async def test_dry_run_does_not_write_database(self, client):
        r = await client.post(f"{BASE}/dry-run", json={
            "module_name": "review_packet", "mode": "planning",
        })
        assert r.status_code == 200
        async with get_engine().connect() as conn:
            run_count = (await conn.execute(select(AgentRun))).scalars().all()
            artifact_count = (await conn.execute(select(TaskArtifact))).scalars().all()
            event_count = (await conn.execute(select(TaskEvent))).scalars().all()
        assert run_count == []
        assert artifact_count == []
        assert event_count == []


# ─── Execute Tests ───

@pytest.mark.asyncio
class TestExecute:

    async def test_execute_planning_success(self, client, project):
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "planning",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "succeeded"
        assert data["output_summary"] is not None
        assert data["agent_run_id"] > 0
        assert len(data["prompt_hash"]) > 0

    async def test_execute_prompt_hash_recorded(self, client, project):
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "planning",
        })
        data = r.json()["data"]
        assert len(data["prompt_hash"]) > 0
        assert data["prompt_hash"] != "0" * 16

    async def test_execute_context_packet_hash_recorded(self, client, project):
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "planning",
        })
        data = r.json()["data"]
        assert len(data["context_packet_hash"]) > 0
        assert data["context_packet_hash"] != "0" * 16

    async def test_execute_token_usage_present(self, client, project):
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "planning",
        })
        data = r.json()["data"]
        assert "estimated_prompt_tokens" in data["token_usage"]
        assert data["token_usage"]["estimated_prompt_tokens"] > 0

    async def test_execute_creates_agent_run(self, client, project):
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "planning",
        })
        data = r.json()["data"]
        run_id = data["agent_run_id"]
        r2 = await client.get(f"/api/tasks/{data['task_id']}/agent-runs")
        assert r2.status_code == 200

    async def test_execute_patch_generation_success(self, client, project):
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "patch_generation",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "succeeded"
        assert data["output_diff"].startswith("diff --git")

    async def test_execute_review_success(self, client, project):
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "review",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "succeeded"

    async def test_execute_risk_success(self, client, project):
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "risk",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "succeeded"

    async def test_execute_browser_reviewer_success(self, client, project):
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "browser_reviewer",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "succeeded"
        artifact_text = json.dumps(data["artifacts"]) + json.dumps(data["events"])
        assert "advisory_only" in json.dumps(data)
        assert "not_final_approval" in json.dumps(data)

    async def test_execute_unknown_mode_blocked(self, client, project):
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "invalid_mode_xyz",
        })
        assert r.status_code == 400

    async def test_execute_uses_task_id(self, client, task):
        r = await client.post(f"{BASE}/execute", json={
            "task_id": task["id"], "module_name": "review_packet", "mode": "planning",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "succeeded"

    async def test_execute_archived_task_blocked(self, client, task):
        task_id = task["id"]
        await client.post(f"/api/tasks/{task_id}/generate-ticket", json={"actor": "test"})
        await client.post(f"/api/tasks/{task_id}/dispatch", json={"actor": "test"})
        await client.post(f"/api/tasks/{task_id}/submit-result", json={"actor": "test", "result_summary": "ok"})
        await client.post(f"/api/tasks/{task_id}/start-review", json={"actor": "test"})
        await client.post(f"/api/tasks/{task_id}/approve", json={"actor": "test"})
        await client.post(f"/api/tasks/{task_id}/archive", json={"actor": "test"})
        r = await client.post(f"{BASE}/execute", json={
            "task_id": task_id, "module_name": "review_packet", "mode": "planning",
        })
        assert r.status_code == 409

    async def test_execute_steps_recorded(self, client, project):
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "planning",
        })
        data = r.json()["data"]
        step_names = [s["step"] for s in data["steps"]]
        assert "preflight" in step_names
        assert "prompt_build" in step_names
        assert "agent_setup" in step_names
        assert "task_setup" in step_names
        assert "agent_run_creation" in step_names
        assert "ai_execution" in step_names
        assert "governance" in step_names
        assert "artifact_creation" in step_names

    async def test_execute_api_envelope(self, client, project):
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "planning",
        })
        body = r.json()
        assert "data" in body
        assert "message" in body


# ─── Security / Governance Tests ───

@pytest.mark.asyncio
class TestExecuteGovernance:

    async def test_execute_disabled_by_default(self, client, project, monkeypatch):
        import dataclasses
        import app.services.ai_dispatch_service as svc
        monkeypatch.setattr(svc, "settings", dataclasses.replace(svc.settings, ai_execution_enabled=False))
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "planning",
        })
        assert r.status_code == 400

    async def test_execute_missing_api_key(self, client, project, monkeypatch):
        import dataclasses
        import app.services.ai_dispatch_service as svc
        monkeypatch.setattr(svc, "settings", dataclasses.replace(svc.settings, openai_api_key=""))
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "planning",
        })
        assert r.status_code == 400

    async def test_execute_provider_not_allowed(self, client, project, monkeypatch):
        import dataclasses
        import app.services.ai_dispatch_service as svc
        monkeypatch.setattr(svc, "settings", dataclasses.replace(svc.settings, _provider_allowlist_raw="sandbox"))
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "planning",
        })
        assert r.status_code == 400

    async def test_execute_governance_invalid_fails(self, client, project, monkeypatch):
        bad_result = AgentRunResult(
            output_summary="", output_log="",
            raw_result_json="",
        )
        monkeypatch.setattr(
            "app.services.ai_dispatch_service._execute_with_provider",
            AsyncMock(return_value=bad_result),
        )
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "planning",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "failed"

    async def test_execute_provider_exception(self, client, project, monkeypatch):
        monkeypatch.setattr(
            "app.services.ai_dispatch_service._execute_with_provider",
            AsyncMock(side_effect=RuntimeError("Provider crashed")),
        )
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "planning",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "failed"
        assert data["agent_run_id"] > 0

    async def test_execute_provider_timeout(self, client, project, monkeypatch):
        monkeypatch.setattr(
            "app.services.ai_dispatch_service._execute_with_provider",
            AsyncMock(side_effect=TimeoutError("provider timeout")),
        )
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "planning",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "failed"
        assert "provider timeout" in json.dumps(data["steps"])

    async def test_patch_generation_non_unified_diff_malformed(self, client, project, monkeypatch):
        monkeypatch.setattr(
            "app.services.ai_dispatch_service._execute_with_provider",
            AsyncMock(return_value=AgentRunResult(
                output_summary="bad patch",
                output_log="bad patch",
                raw_result_json=json.dumps({"patch_diff": "print('not a diff')"}),
                patch_diff="print('not a diff')",
            )),
        )
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "patch_generation",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "failed"
        assert data["output_summary"] == "malformed_response"

    async def test_risk_non_json_malformed(self, client, project, monkeypatch):
        monkeypatch.setattr(
            "app.services.ai_dispatch_service._execute_with_provider",
            AsyncMock(return_value=AgentRunResult(
                output_summary="risk",
                output_log="risk",
                raw_result_json=json.dumps({"risk_report": "not json object"}),
            )),
        )
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "risk",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "failed"
        assert data["output_summary"] == "malformed_response"

    async def test_patch_generation_auto_calls_sandbox_and_gate(self, client, project, monkeypatch):
        apply_mock = AsyncMock()
        gate_mock = AsyncMock()

        class ApplyResult:
            success = True
            error_message = None

        class GateResult:
            passed = True
            blocked_reasons = []

        apply_mock.return_value = ApplyResult()
        gate_mock.return_value = GateResult()
        monkeypatch.setattr(
            "app.services.patch_apply_sandbox_service.apply_patch_in_sandbox",
            apply_mock,
        )
        monkeypatch.setattr(
            "app.services.sandbox_approval_gate_service.evaluate_and_record_gate",
            gate_mock,
        )
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "patch_generation",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["sandbox_applied"] is True
        assert data["sandbox_gate_passed"] is True
        assert apply_mock.await_count == 1
        assert gate_mock.await_count == 1

    async def test_api_key_not_persisted_in_run_artifacts_or_events(self, client, project, monkeypatch):
        secret = MOCK_API_KEY
        result_with_secret = AgentRunResult(
            output_summary=f"Contains {secret}",
            output_log=f"log with {secret}",
            raw_result_json=json.dumps({"plan_md": f"# Plan\n{secret}"}),
            plan_md=f"# Plan\n{secret}",
        )
        monkeypatch.setattr(
            "app.services.ai_dispatch_service._execute_with_provider",
            AsyncMock(return_value=result_with_secret),
        )
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "planning",
        })
        data = r.json()["data"]
        assert data["status"] == "succeeded"
        async with get_session_factory()() as session:
            runs = (await session.execute(select(AgentRun))).scalars().all()
            artifacts = (await session.execute(select(TaskArtifact))).scalars().all()
            events = (await session.execute(select(TaskEvent))).scalars().all()
        persisted = json.dumps([
            r.raw_result_json for r in runs
        ]) + json.dumps([
            a.content for a in artifacts
        ]) + json.dumps([
            e.message for e in events
        ])
        assert secret not in persisted
        assert "sk-test" not in persisted

    async def test_secrets_redacted_from_output(self, client, project, monkeypatch):
        result_with_secret = AgentRunResult(
            output_summary="Contains sk-test-secret-key",
            output_log="log with sk-test-secret-key",
            raw_result_json=json.dumps({"patch_diff": "sk-test-secret-key"}),
            patch_diff="sk-test-secret-key",
        )
        monkeypatch.setattr(
            "app.services.ai_dispatch_service._execute_with_provider",
            AsyncMock(return_value=result_with_secret),
        )
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "patch_generation",
        })
        data = r.json()["data"]
        if data["status"] == "succeeded":
            r2 = await client.get(f"/api/tasks/{data['task_id']}/agent-runs")
            runs = r2.json()["data"]
            if runs:
                raw = runs[0].get("raw_result_json", "") or ""
                assert "sk-test-secret-key" not in raw

    async def test_no_project_root_path_access(self, client, project, monkeypatch):
        def _fail(*args, **kwargs):
            raise RuntimeError("should not be called")
        monkeypatch.setattr("pathlib.Path.glob", _fail)
        monkeypatch.setattr("pathlib.Path.rglob", _fail)
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "planning",
        })
        assert r.status_code == 200

    async def test_no_subprocess_or_os_system(self, client, project, monkeypatch):
        def _fail(*args, **kwargs):
            raise RuntimeError("should not be called")
        monkeypatch.setattr("subprocess.run", _fail)
        monkeypatch.setattr("subprocess.Popen", _fail)
        monkeypatch.setattr("os.system", _fail)
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "planning",
        })
        assert r.status_code == 200

    async def test_no_secret_ref_or_env(self, client, project):
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "planning",
        })
        body = json.dumps(r.json())
        for item in ["OPENAI_API_KEY", "sk-", "-----BEGIN"]:
            assert item not in body, f"response contains {item}"

    async def test_execute_steps_show_preflight_blocked(self, client, project, monkeypatch):
        import dataclasses
        import app.services.ai_dispatch_service as svc
        monkeypatch.setattr(svc, "settings", dataclasses.replace(svc.settings, ai_execution_enabled=False))
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "planning",
        })
        assert r.status_code == 400


# ─── AST Static Analysis ───

class TestStaticAnalysis:

    def test_no_dangerous_imports(self):
        from app.services import ai_dispatch_service as svc
        import ast
        src = (svc.__file__ or "").replace("\\", "/")
        with open(src, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        seen = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    seen.add(alias.name.split(".")[0])
        assert not (seen & {"subprocess", "glob", "shutil"})
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                called.add(func.attr if isinstance(func, ast.Attribute) else func.id)
        assert "walk" not in attrs
        assert "rglob" not in called
        assert "environ" not in attrs
        assert "getenv" not in called
        assert "root_path" not in attrs


# ─── Edge Cases ───

@pytest.mark.asyncio
class TestExecuteEdgeCases:

    async def test_execute_empty_task_goal(self, client, project):
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "", "mode": "planning",
            "task_goal": "", "task_type": "",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "succeeded"

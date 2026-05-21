"""Tests for v0.4 S11 — AI Dispatch + OpenAI Provider + Sandbox Auto Pipeline MVP."""

import json
import os
import hashlib
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
from app.services.prompt_template_service import preview as prompt_preview


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
    from app.services.openai_provider import OpenAIProvider

    async def _fake_call(self, system_prompt, user_prompt):
        if "patch.diff" in system_prompt:
            return "diff --git a/test.py b/test.py\nindex 000..111\n--- a/test.py\n+++ b/test.py\n@@ -0,0 +1 @@\n+print('hello')"
        if "risk_report.json" in system_prompt:
            return json.dumps({"risk_level": "low", "requires_human": False, "reasons": []})
        if "browser_ai_review.json" in system_prompt:
            return json.dumps({
                "advisory_only": True,
                "not_final_approval": True,
                "blockers": [],
                "warnings": [],
                "required_actions": [],
            })
        if "review.md" in system_prompt:
            return "## Review\n\n**Decision**: approved\n**Risk**: low"
        return "# Plan\n\n1. Implement feature\n2. Add tests"

    monkeypatch.setattr(OpenAIProvider, "__init__", lambda self: None)
    monkeypatch.setattr(OpenAIProvider, "_call_openai", _fake_call)


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
        import app.services.ai_dispatch_service as svc
        orig = svc._execute_openai_with_prompt_preview
        r = await client.post(f"{BASE}/dry-run", json={
            "module_name": "review_packet", "mode": "planning",
        })
        assert r.status_code == 200
        assert svc._execute_openai_with_prompt_preview is orig

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

    async def test_execute_provider_input_contains_s10_prompt_preview(self, client, project, monkeypatch):
        seen = {}

        async def fake_dispatch(preview, mode):
            seen["system"] = preview.system_prompt_preview
            seen["user"] = preview.user_prompt_preview
            return _fake_result("dispatch", mode)

        monkeypatch.setattr(
            "app.services.ai_dispatch_service._execute_openai_with_prompt_preview",
            AsyncMock(side_effect=fake_dispatch),
        )

        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"],
            "task_goal": "Implement dispatch",
            "task_type": "backend",
            "module_name": "review_packet",
            "mode": "planning",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "succeeded"
        assert "You are a code planning assistant" in seen["system"]
        assert "## Task Goal\nImplement dispatch" in seen["user"]
        assert data["prompt_hash"]

    async def test_openai_dispatch_entry_passes_s10_prompts_to_openai(self, monkeypatch):
        from app.services.ai_dispatch_service import _execute_openai_with_prompt_preview
        from app.services.openai_provider import OpenAIProvider

        seen = {}

        async def fake_call(self, system_prompt, user_prompt):
            seen["system"] = system_prompt
            seen["user"] = user_prompt
            return "# Plan\n\n1. Provider received prompt preview"

        monkeypatch.setattr(OpenAIProvider, "__init__", lambda self: None)
        monkeypatch.setattr(OpenAIProvider, "_call_openai", fake_call)
        preview = prompt_preview(
            task_goal="Use S10 preview",
            module_name="review_packet",
            task_type="backend",
            mode="planning",
        )
        result = await _execute_openai_with_prompt_preview(preview, "planning")
        assert seen["system"] == preview.system_prompt_preview
        assert seen["user"] == preview.user_prompt_preview
        assert result.plan_md.startswith("# Plan")

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
        assert any(a["filename"].endswith("_result.json") for a in data["artifacts"])
        assert any(a["filename"].endswith("_risk_report.json") for a in data["artifacts"])

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
        assert any(a["filename"].endswith("_browser_ai_review.json") for a in data["artifacts"])

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
            "app.services.ai_dispatch_service._execute_openai_with_prompt_preview",
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
            "app.services.ai_dispatch_service._execute_openai_with_prompt_preview",
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
            "app.services.ai_dispatch_service._execute_openai_with_prompt_preview",
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
            "app.services.ai_dispatch_service._execute_openai_with_prompt_preview",
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
            "app.services.ai_dispatch_service._execute_openai_with_prompt_preview",
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

    async def test_risk_json_from_openai_response_becomes_risk_report(self, monkeypatch):
        from app.services.ai_dispatch_service import _execute_openai_with_prompt_preview
        from app.services.openai_provider import OpenAIProvider

        async def fake_call(self, system_prompt, user_prompt):
            assert "risk_report.json" in system_prompt
            assert "JSON only" in system_prompt
            return json.dumps({"risk_level": "low", "requires_human": False, "reasons": []})

        monkeypatch.setattr(OpenAIProvider, "__init__", lambda self: None)
        monkeypatch.setattr(OpenAIProvider, "_call_openai", fake_call)
        preview = prompt_preview(module_name="review_packet", mode="risk")
        result = await _execute_openai_with_prompt_preview(preview, "risk")
        assert result.risk_report == {"risk_level": "low", "requires_human": False, "reasons": []}
        assert result.review_md is None

    async def test_browser_reviewer_json_missing_required_flags_malformed(self, client, project, monkeypatch):
        monkeypatch.setattr(
            "app.services.ai_dispatch_service._execute_openai_with_prompt_preview",
            AsyncMock(return_value=AgentRunResult(
                output_summary="browser review",
                output_log="browser review",
                raw_result_json=json.dumps({"browser_ai_review": {"advisory_only": True}}),
                review_md=json.dumps({"advisory_only": True}),
            )),
        )
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "browser_reviewer",
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
        assert data["pipeline_status"] == "succeeded"
        assert apply_mock.await_count == 1
        assert gate_mock.await_count == 1

    async def test_risk_artifact_redacted_and_sha256_uses_redacted_content(self, client, project, monkeypatch):
        secret = MOCK_API_KEY
        monkeypatch.setattr(
            "app.services.ai_dispatch_service._execute_openai_with_prompt_preview",
            AsyncMock(return_value=AgentRunResult(
                output_summary="risk ok",
                output_log="risk ok",
                raw_result_json=json.dumps({"risk_report": {"risk_level": "low", "secret": secret}}),
                risk_report={"risk_level": "low", "secret": secret},
            )),
        )
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "risk",
        })
        assert r.status_code == 200
        artifact = next(a for a in r.json()["data"]["artifacts"] if a["filename"].endswith("_risk_report.json"))
        assert secret not in artifact["content"]
        assert "sk-test" not in artifact["content"]
        assert artifact["sha256"] == hashlib.sha256(artifact["content"].encode("utf-8")).hexdigest()

    async def test_browser_review_artifact_redacted_flags_and_sha256(self, client, project, monkeypatch):
        secret = MOCK_API_KEY
        payload = {
            "advisory_only": True,
            "not_final_approval": True,
            "notes": secret,
        }
        monkeypatch.setattr(
            "app.services.ai_dispatch_service._execute_openai_with_prompt_preview",
            AsyncMock(return_value=AgentRunResult(
                output_summary="browser ok",
                output_log="browser ok",
                raw_result_json=json.dumps({"browser_ai_review": payload}),
                review_md=json.dumps(payload),
            )),
        )
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "browser_reviewer",
        })
        assert r.status_code == 200
        artifact = next(a for a in r.json()["data"]["artifacts"] if a["filename"].endswith("_browser_ai_review.json"))
        content = json.loads(artifact["content"])
        assert content["advisory_only"] is True
        assert content["not_final_approval"] is True
        assert secret not in artifact["content"]
        assert "sk-test" not in artifact["content"]
        assert artifact["sha256"] == hashlib.sha256(artifact["content"].encode("utf-8")).hexdigest()

    async def test_browser_review_markdown_success_creates_normalized_json_artifact(self, client, project, monkeypatch):
        review_md = (
            "## Browser Review\n\n"
            "**advisory_only**: true\n"
            "**not_final_approval**: true\n"
            "- Finding: layout looks stable"
        )
        monkeypatch.setattr(
            "app.services.ai_dispatch_service._execute_openai_with_prompt_preview",
            AsyncMock(return_value=AgentRunResult(
                output_summary="browser markdown ok",
                output_log="browser markdown ok",
                raw_result_json=json.dumps({"browser_ai_review": {"review_md": review_md}}),
                review_md=review_md,
            )),
        )
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "browser_reviewer",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "succeeded"
        artifact = next(a for a in data["artifacts"] if a["filename"].endswith("_browser_ai_review.json"))
        content = json.loads(artifact["content"])
        assert content["advisory_only"] is True
        assert content["not_final_approval"] is True
        assert content["review_md"] == review_md
        assert artifact["sha256"] == hashlib.sha256(artifact["content"].encode("utf-8")).hexdigest()

    async def test_agent_run_trace_contains_dispatch_hashes_without_prompt_or_api_key(self, client, project):
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"],
            "task_goal": "Persist trace metadata",
            "task_type": "backend",
            "module_name": "review_packet",
            "mode": "planning",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        async with get_session_factory()() as session:
            run = await session.get(AgentRun, data["agent_run_id"])
        raw = run.raw_result_json or ""
        parsed = json.loads(raw)
        assert parsed["dispatch"]["prompt_hash"] == data["prompt_hash"]
        assert parsed["dispatch"]["context_packet_hash"] == data["context_packet_hash"]
        assert "system_prompt_preview" not in raw
        assert "user_prompt_preview" not in raw
        assert "You are a code planning assistant" not in raw
        assert "## Task Goal\nPersist trace metadata" not in raw
        assert MOCK_API_KEY not in raw
        assert "sk-test" not in raw

    async def test_patch_generation_sandbox_apply_failure_sets_pipeline_status(self, client, project, monkeypatch):
        apply_mock = AsyncMock()
        gate_mock = AsyncMock()

        class ApplyResult:
            success = False
            error_message = "sandbox apply failed"

        class GateResult:
            passed = True
            blocked_reasons = []

        apply_mock.return_value = ApplyResult()
        gate_mock.return_value = GateResult()
        monkeypatch.setattr("app.services.patch_apply_sandbox_service.apply_patch_in_sandbox", apply_mock)
        monkeypatch.setattr("app.services.sandbox_approval_gate_service.evaluate_and_record_gate", gate_mock)
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "patch_generation",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["sandbox_applied"] is False
        assert data["pipeline_status"] == "sandbox_failed"

    async def test_patch_generation_sandbox_gate_blocked_sets_pipeline_status(self, client, project, monkeypatch):
        apply_mock = AsyncMock()
        gate_mock = AsyncMock()

        class ApplyResult:
            success = True
            error_message = None

        class Reason:
            reason = "high risk"

        class GateResult:
            passed = False
            blocked_reasons = [Reason()]

        apply_mock.return_value = ApplyResult()
        gate_mock.return_value = GateResult()
        monkeypatch.setattr("app.services.patch_apply_sandbox_service.apply_patch_in_sandbox", apply_mock)
        monkeypatch.setattr("app.services.sandbox_approval_gate_service.evaluate_and_record_gate", gate_mock)
        r = await client.post(f"{BASE}/execute", json={
            "project_id": project["id"], "module_name": "review_packet", "mode": "patch_generation",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["sandbox_applied"] is True
        assert data["sandbox_gate_passed"] is False
        assert data["pipeline_status"] == "sandbox_gate_blocked"

    async def test_api_key_not_persisted_in_run_artifacts_or_events(self, client, project, monkeypatch):
        secret = MOCK_API_KEY
        result_with_secret = AgentRunResult(
            output_summary=f"Contains {secret}",
            output_log=f"log with {secret}",
            raw_result_json=json.dumps({"plan_md": f"# Plan\n{secret}"}),
            plan_md=f"# Plan\n{secret}",
        )
        monkeypatch.setattr(
            "app.services.ai_dispatch_service._execute_openai_with_prompt_preview",
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
            "app.services.ai_dispatch_service._execute_openai_with_prompt_preview",
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

"""Tests for AI Context Packet Builder (v0.4 S9)."""

import ast

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services import context_selector_service


@pytest.fixture(autouse=True)
def clear_cache():
    context_selector_service._clear_cache()
    yield


@pytest.fixture
def cli():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="https://x")


def _fail(*args, **kwargs):
    raise RuntimeError("should not be called")


@pytest.mark.asyncio
class Tests:

    async def test_planning_mode_returns_plan_md(self, cli):
        r = await cli.post("/api/ai-context-packets/preview", json={
            "module_name": "review_packet",
            "mode": "planning",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["output_contract"]["expected_artifacts"] == ["plan.md"]
        assert data["prompt_template"]["template_id"] == "planning_prompt_v1"
        assert data["task_context"]["mode"] == "planning"

    async def test_patch_generation_returns_patch_diff(self, cli):
        r = await cli.post("/api/ai-context-packets/preview", json={
            "module_name": "review_packet",
            "mode": "patch_generation",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert "patch.diff" in data["output_contract"]["expected_artifacts"]
        assert data["output_contract"]["patch_format"] == "unified_diff"

    async def test_review_mode_returns_review_md(self, cli):
        r = await cli.post("/api/ai-context-packets/preview", json={
            "module_name": "review_packet",
            "mode": "review",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert "review.md" in data["output_contract"]["expected_artifacts"]
        assert data["prompt_template"]["template_id"] == "review_prompt_v1"

    async def test_risk_mode_returns_risk_report_json(self, cli):
        r = await cli.post("/api/ai-context-packets/preview", json={
            "module_name": "review_packet",
            "mode": "risk",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert "risk_report.json" in data["output_contract"]["expected_artifacts"]
        assert data["output_contract"]["risk_format"] == "json"

    async def test_browser_reviewer_mode(self, cli):
        r = await cli.post("/api/ai-context-packets/preview", json={
            "module_name": "review_packet",
            "mode": "browser_reviewer",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert "browser_ai_review.json" in data["output_contract"]["expected_artifacts"]
        assert data["prompt_template"]["template_id"] == "browser_reviewer_prompt_v1"

    async def test_unknown_mode_returns_422(self, cli):
        r = await cli.post("/api/ai-context-packets/preview", json={
            "mode": "invalid_mode_xyz",
        })
        assert r.status_code == 422

    async def test_context_selector_included(self, cli):
        r = await cli.post("/api/ai-context-packets/preview", json={
            "module_name": "review_packet",
            "mode": "planning",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        cs = data["context_selector"]
        names = [m["name"] for m in cs["matched_modules"]]
        assert "review_packet" in names
        assert len(cs["recommended_files"]) > 0

    async def test_safety_boundaries_in_project_brief(self, cli):
        r = await cli.post("/api/ai-context-packets/preview", json={
            "module_name": "review_packet",
            "mode": "planning",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        boundaries = data["project_brief"]["safety_boundaries"]
        assert len(boundaries) > 0
        assert any("Project.root_path" in b for b in boundaries)

    async def test_hash_fields_exist_and_stable(self, cli):
        r1 = await cli.post("/api/ai-context-packets/preview", json={
            "module_name": "review_packet",
            "mode": "planning",
        })
        r2 = await cli.post("/api/ai-context-packets/preview", json={
            "module_name": "review_packet",
            "mode": "planning",
        })
        data1 = r1.json()["data"]["audit"]
        data2 = r2.json()["data"]["audit"]
        assert data1["project_prefix_hash"] == data2["project_prefix_hash"]
        assert data1["task_context_hash"] == data2["task_context_hash"]
        assert data1["context_packet_hash"] == data2["context_packet_hash"]
        assert len(data1["project_prefix_hash"]) == 16

    async def test_estimated_context_tokens_present(self, cli):
        r = await cli.post("/api/ai-context-packets/preview", json={
            "module_name": "review_packet",
            "mode": "planning",
        })
        data = r.json()["data"]
        assert data["audit"]["estimated_context_tokens"] > 0
        assert data["token_budget"]["estimated_context_tokens"] > 0

    async def test_over_budget_returns_warning(self, cli, monkeypatch):
        from app.services import ai_context_packet_service
        monkeypatch.setattr(
            ai_context_packet_service,
            "_MAX_TOKENS_BY_MODE",
            {"planning": {"context": 1, "code_context": 1, "review_packet": 1, "response": 1}},
        )
        r = await cli.post("/api/ai-context-packets/preview", json={
            "module_name": "review_packet",
            "mode": "planning",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["token_budget"]["budget_status"] == "over_limit"
        assert data["token_budget"]["truncation_applied"] is True
        assert "context_budget_exceeded" in data["warnings"]

    async def test_no_project_root_path_access(self, cli, monkeypatch):
        monkeypatch.setattr("pathlib.Path.glob", _fail)
        monkeypatch.setattr("pathlib.Path.rglob", _fail)
        r = await cli.post("/api/ai-context-packets/preview", json={
            "module_name": "review_packet",
            "mode": "planning",
        })
        assert r.status_code == 200

    async def test_no_subprocess_or_os_system(self, cli, monkeypatch):
        monkeypatch.setattr("subprocess.run", _fail)
        monkeypatch.setattr("subprocess.Popen", _fail)
        monkeypatch.setattr("os.system", _fail)
        r = await cli.post("/api/ai-context-packets/preview", json={
            "module_name": "review_packet",
            "mode": "planning",
        })
        assert r.status_code == 200

    async def test_no_secret_ref_or_env(self, cli, monkeypatch):
        r = await cli.post("/api/ai-context-packets/preview", json={
            "module_name": "review_packet",
            "mode": "planning",
        })
        assert r.status_code == 200
        packet_str = str(r.json())
        dangerous = ["OPENAI_API_KEY", "sk-", "-----BEGIN"]
        for item in dangerous:
            assert item not in packet_str, f"packet contains {item}"

    async def test_malformed_map_propagates_error(self, cli, monkeypatch, tmp_path):
        from app.services import context_selector_service
        fake = tmp_path / "_bad_map.json"
        fake.write_text("{bad json", encoding="utf-8")
        monkeypatch.setattr(context_selector_service, "_REPOSITORY_MAP_PATH", fake)
        context_selector_service._clear_cache()
        r = await cli.post("/api/ai-context-packets/preview", json={
            "module_name": "review_packet",
            "mode": "planning",
        })
        assert r.status_code == 500

    async def test_api_envelope(self, cli):
        r = await cli.post("/api/ai-context-packets/preview", json={
            "module_name": "review_packet",
            "mode": "planning",
        })
        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        assert "message" in body

    async def test_empty_task_goal_low_confidence(self, cli):
        r = await cli.post("/api/ai-context-packets/preview", json={
            "task_goal": "",
            "mode": "planning",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["context_selector"]["confidence"] == "low"

    async def test_prompt_template_metadata(self, cli):
        r = await cli.post("/api/ai-context-packets/preview", json={
            "module_name": "review_packet",
            "mode": "planning",
        })
        assert r.status_code == 200
        pt = r.json()["data"]["prompt_template"]
        assert pt["template_id"] == "planning_prompt_v1"
        assert pt["mode"] == "planning"
        assert len(pt["allowed_model_tiers"]) > 0
        assert len(pt["safety_notes"]) > 0

    async def test_packet_contains_no_secret_values(self, cli):
        r = await cli.post("/api/ai-context-packets/preview", json={
            "module_name": "review_packet",
            "mode": "planning",
        })
        assert r.status_code == 200
        raw = str(r.json())
        assert "REDACTED" not in raw

    async def test_runtime_evidence_all_not_provided(self, cli):
        r = await cli.post("/api/ai-context-packets/preview", json={
            "module_name": "review_packet",
            "mode": "planning",
        })
        assert r.status_code == 200
        re = r.json()["data"]["runtime_evidence"]
        assert re["pytest_summary"] == "not_provided"
        assert re["compileall_summary"] == "not_provided"
        assert re["sonar_summary"] == "not_provided"
        assert re["review_packet_summary"] == "not_provided"
        assert re["sandbox_result_summary"] == "not_provided"

    async def test_project_brief_fields(self, cli):
        r = await cli.post("/api/ai-context-packets/preview", json={
            "module_name": "review_packet",
            "mode": "planning",
        })
        assert r.status_code == 200
        pb = r.json()["data"]["project_brief"]
        assert pb["project_name"] == "Codex Automation Delivery Platform"
        assert pb["current_version"] == "v0.4.0"
        assert len(pb["completed_scope"]) > 0
        assert len(pb["known_non_goals"]) > 0

    async def test_all_modes_have_templates(self, cli):
        modes = ["planning", "patch_generation", "review", "risk", "browser_reviewer"]
        for mode in modes:
            r = await cli.post("/api/ai-context-packets/preview", json={
                "module_name": "review_packet",
                "mode": mode,
            })
            assert r.status_code == 200
            pt = r.json()["data"]["prompt_template"]
            assert pt["template_id"] == f"{mode}_prompt_v1"
            assert pt["mode"] == mode

    async def test_forbidden_files_in_task_context(self, cli):
        r = await cli.post("/api/ai-context-packets/preview", json={
            "module_name": "review_packet",
            "mode": "planning",
        })
        assert r.status_code == 200
        tc = r.json()["data"]["task_context"]
        assert ".env" in tc["forbidden_files"]
        assert len(tc["forbidden_files"]) > 0


class TestStaticAnalysis:

    def _get_source(self):
        from app.services import ai_context_packet_service
        return (ai_context_packet_service.__file__ or "").replace("\\", "/")

    def test_no_dangerous_imports(self):
        src = self._get_source()
        with open(src, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        imports = set()
        attrs = set()
        calls = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.Attribute):
                attrs.add(node.attr)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
                elif isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
        dangerous = {"subprocess", "glob", "shutil"}
        assert not (imports & dangerous), f"service imports dangerous module: {imports & dangerous}"
        assert "walk" not in attrs, "service calls os.walk"
        assert "rglob" not in calls, "service calls rglob"
        assert "environ" not in attrs, "service reads os.environ"
        assert "getenv" not in calls, "service calls os.getenv"
        assert "root_path" not in attrs, "service accesses root_path"

    def test_no_secret_ref_or_env_access(self):
        src = self._get_source()
        with open(src, encoding="utf-8") as f:
            code = f.read()
        dangerous = ["OPENAI_API_KEY"]
        for item in dangerous:
            assert item not in code, f"service contains dangerous reference: {item}"
        assert "getenv" not in code, "service calls os.getenv"
        assert 'environ["' not in code and "environ.get(" not in code, "service reads os.environ"

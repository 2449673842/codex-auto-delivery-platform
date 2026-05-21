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


MODE_CASES = [
    pytest.param("planning",           ["plan.md"],                "planning_prompt_v1",           "",     "",         id="planning"),
    pytest.param("patch_generation",   ["patch.diff"],             "patch_generation_prompt_v1",   "unified_diff", "",  id="patch_generation"),
    pytest.param("review",             ["review.md"],              "review_prompt_v1",             "",     "",         id="review"),
    pytest.param("risk",               ["risk_report.json"],       "risk_prompt_v1",               "",     "json",     id="risk"),
    pytest.param("browser_reviewer",   ["browser_ai_review.json"], "browser_reviewer_prompt_v1",   "",     "",         id="browser_reviewer"),
]


@pytest.mark.asyncio
class Tests:

    async def _preview(self, cli, **overrides):
        body = {"module_name": "review_packet", "mode": "planning"}
        body.update(overrides)
        return await cli.post("/api/ai-context-packets/preview", json=body)

    async def _assert_data(self, r):
        assert r.status_code == 200
        return r.json()["data"]

    @pytest.mark.parametrize(
        "mode,expected_artifacts,template_id,patch_format,risk_format",
        MODE_CASES,
    )
    async def test_mode_contract(self, cli, mode, expected_artifacts, template_id, patch_format, risk_format):
        data = await self._assert_data(await self._preview(cli, mode=mode))
        oc = data["output_contract"]
        assert oc["expected_artifacts"] == expected_artifacts
        assert data["prompt_template"]["template_id"] == template_id
        assert data["task_context"]["mode"] == mode
        if patch_format:
            assert oc["patch_format"] == patch_format
        if risk_format:
            assert oc["risk_format"] == risk_format

    async def test_unknown_mode_returns_422(self, cli):
        r = await self._preview(cli, mode="invalid_mode_xyz")
        assert r.status_code == 422

    async def test_context_selector_included(self, cli):
        data = await self._assert_data(await self._preview(cli))
        cs = data["context_selector"]
        names = [m["name"] for m in cs["matched_modules"]]
        assert "review_packet" in names
        assert len(cs["recommended_files"]) > 0

    async def test_safety_boundaries_in_project_brief(self, cli):
        data = await self._assert_data(await self._preview(cli))
        boundaries = data["project_brief"]["safety_boundaries"]
        assert len(boundaries) > 0
        assert any("Project.root_path" in b for b in boundaries)

    async def test_hash_fields_exist_and_stable(self, cli):
        data1 = (await self._assert_data(await self._preview(cli)))["audit"]
        data2 = (await self._assert_data(await self._preview(cli)))["audit"]
        assert data1["project_prefix_hash"] == data2["project_prefix_hash"]
        assert data1["task_context_hash"] == data2["task_context_hash"]
        assert data1["context_packet_hash"] == data2["context_packet_hash"]
        assert len(data1["project_prefix_hash"]) == 16

    async def test_estimated_context_tokens_present(self, cli):
        data = await self._assert_data(await self._preview(cli))
        assert data["audit"]["estimated_context_tokens"] > 0
        assert data["token_budget"]["estimated_context_tokens"] > 0

    async def test_over_budget_returns_warning(self, cli, monkeypatch):
        from app.services import ai_context_packet_service
        monkeypatch.setattr(
            ai_context_packet_service,
            "_MAX_TOKENS_BY_MODE",
            {"planning": {"context": 1, "code_context": 1, "review_packet": 1, "response": 1}},
        )
        data = await self._assert_data(await self._preview(cli))
        assert data["token_budget"]["budget_status"] == "over_limit"
        assert data["token_budget"]["truncation_applied"] is True
        assert "context_budget_exceeded" in data["warnings"]

    async def test_no_project_root_path_access(self, cli, monkeypatch):
        monkeypatch.setattr("pathlib.Path.glob", _fail)
        monkeypatch.setattr("pathlib.Path.rglob", _fail)
        await self._assert_data(await self._preview(cli))

    async def test_no_subprocess_or_os_system(self, cli, monkeypatch):
        monkeypatch.setattr("subprocess.run", _fail)
        monkeypatch.setattr("subprocess.Popen", _fail)
        monkeypatch.setattr("os.system", _fail)
        await self._assert_data(await self._preview(cli))

    async def test_no_secret_ref_or_env(self, cli):
        r = await self._preview(cli)
        assert r.status_code == 200
        packet_str = str(r.json())
        for item in ["OPENAI_API_KEY", "sk-", "-----BEGIN"]:
            assert item not in packet_str, f"packet contains {item}"

    async def test_malformed_map_propagates_error(self, cli, monkeypatch, tmp_path):
        from app.services import context_selector_service
        fake = tmp_path / "_bad_map.json"
        fake.write_text("{bad json", encoding="utf-8")
        monkeypatch.setattr(context_selector_service, "_REPOSITORY_MAP_PATH", fake)
        context_selector_service._clear_cache()
        r = await self._preview(cli)
        assert r.status_code == 500

    async def test_api_envelope(self, cli):
        r = await self._preview(cli)
        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        assert "message" in body

    async def test_empty_task_goal_low_confidence(self, cli):
        data = await self._assert_data(await self._preview(cli, task_goal="", module_name=""))
        assert data["context_selector"]["confidence"] == "low"

    async def test_prompt_template_metadata(self, cli):
        data = await self._assert_data(await self._preview(cli))
        pt = data["prompt_template"]
        assert pt["template_id"] == "planning_prompt_v1"
        assert pt["mode"] == "planning"
        assert len(pt["allowed_model_tiers"]) > 0
        assert len(pt["safety_notes"]) > 0

    async def test_runtime_evidence_all_not_provided(self, cli):
        data = await self._assert_data(await self._preview(cli))
        re = data["runtime_evidence"]
        assert re["pytest_summary"] == "not_provided"
        assert re["compileall_summary"] == "not_provided"
        assert re["sonar_summary"] == "not_provided"
        assert re["review_packet_summary"] == "not_provided"
        assert re["sandbox_result_summary"] == "not_provided"

    async def test_project_brief_fields(self, cli):
        data = await self._assert_data(await self._preview(cli))
        pb = data["project_brief"]
        assert pb["project_name"] == "Codex Automation Delivery Platform"
        assert pb["current_version"] == "v0.4.0"
        assert len(pb["completed_scope"]) > 0
        assert len(pb["known_non_goals"]) > 0

    async def test_forbidden_files_in_task_context(self, cli):
        data = await self._assert_data(await self._preview(cli))
        tc = data["task_context"]
        assert ".env" in tc["forbidden_files"]
        assert len(tc["forbidden_files"]) > 0

    async def test_all_modes_have_templates(self, cli):
        for mode in ["planning", "patch_generation", "review", "risk", "browser_reviewer"]:
            data = await self._assert_data(await self._preview(cli, mode=mode))
            pt = data["prompt_template"]
            assert pt["template_id"] == f"{mode}_prompt_v1"
            assert pt["mode"] == mode

    async def test_packet_contains_no_secret_values(self, cli):
        r = await self._preview(cli)
        assert r.status_code == 200
        raw = str(r.json())
        assert "REDACTED" not in raw


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
        for item in ["OPENAI_API_KEY"]:
            assert item not in code, f"service contains dangerous reference: {item}"
        assert "getenv" not in code, "service calls os.getenv"
        assert 'environ["' not in code and "environ.get(" not in code, "service reads os.environ"

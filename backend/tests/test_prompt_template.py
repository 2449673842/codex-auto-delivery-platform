"""Tests for Prompt Template Preview (v0.4 S10)."""

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


def _blocked(*args, **kwargs):
    raise RuntimeError("should not be called")


MODE_CASES = [
    ("planning",          "planning_prompt_v1",          "plan.md",              "You are a code planning assistant"),
    ("patch_generation",  "patch_generation_prompt_v1",  "patch.diff",           "unified diff only"),
    ("review",            "review_prompt_v1",            "review.md",            "You are a code review assistant"),
    ("risk",              "risk_prompt_v1",              "risk_report.json",     "risk assessment assistant"),
    ("browser_reviewer",  "browser_reviewer_prompt_v1",  "browser_ai_review.json", "advisory_only: true"),
]


@pytest.mark.asyncio
class Tests:

    async def _preview(self, cli, **overrides):
        body = {"module_name": "review_packet", "mode": "planning"}
        body.update(overrides)
        return await cli.post("/api/prompt-templates/preview", json=body)

    @pytest.mark.parametrize("mode,template_id,artifact,expected_text", MODE_CASES)
    async def test_mode_returns_prompt(self, cli, mode, template_id, artifact, expected_text):
        r = await self._preview(cli, mode=mode)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["template_id"] == template_id
        assert data["mode"] == mode
        assert artifact in str(data["output_contract"]["expected_artifacts"])
        assert expected_text in data["system_prompt_preview"]

    async def test_unknown_mode_returns_422(self, cli):
        r = await self._preview(cli, mode="invalid_mode_xyz")
        assert r.status_code == 422

    async def test_system_prompt_contains_safety_boundaries(self, cli):
        r = await self._preview(cli)
        assert r.status_code == 200
        sys = r.json()["data"]["system_prompt_preview"]
        assert "Project.root_path" in sys
        assert "secret_ref" in sys
        assert ".env" in sys

    async def test_prompt_contains_no_secrets(self, cli):
        r = await self._preview(cli)
        assert r.status_code == 200
        body = str(r.json())
        for item in ["OPENAI_API_KEY", "sk-", "-----BEGIN"]:
            assert item not in body

    async def test_user_prompt_contains_recommended_files(self, cli):
        r = await self._preview(cli)
        assert r.status_code == 200
        user = r.json()["data"]["user_prompt_preview"]
        assert "Recommended Files" in user
        assert "backend/app/routers/review_packet.py" in user

    async def test_user_prompt_contains_expected_artifacts(self, cli):
        r = await self._preview(cli, mode="patch_generation")
        assert r.status_code == 200
        user = r.json()["data"]["user_prompt_preview"]
        assert "Expected Artifacts" in user
        assert "patch.diff" in user

    async def test_prompt_hash_stable(self, cli):
        r1 = (await self._preview(cli)).json()["data"]
        r2 = (await self._preview(cli)).json()["data"]
        assert r1["system_prompt_hash"] == r2["system_prompt_hash"]
        assert r1["user_prompt_hash"] == r2["user_prompt_hash"]
        assert r1["prompt_hash"] == r2["prompt_hash"]

    async def test_context_packet_hash_present(self, cli):
        r = await self._preview(cli)
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["context_packet_hash"]) > 0

    async def test_estimated_prompt_tokens_present(self, cli):
        r = await self._preview(cli)
        assert r.status_code == 200
        tb = r.json()["data"]["token_budget"]
        assert tb["estimated_prompt_tokens"] > 0

    async def test_over_budget_returns_warning(self, cli, monkeypatch):
        from app.services import prompt_template_service
        original = prompt_template_service._estimate_tokens
        monkeypatch.setattr(prompt_template_service, "_estimate_tokens", lambda t: 99999)
        r = await self._preview(cli)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["token_budget"]["budget_status"] == "over_limit"
        assert "prompt_budget_exceeded" in data["warnings"]
        monkeypatch.setattr(prompt_template_service, "_estimate_tokens", original)

    async def test_no_project_root_path_access(self, cli, monkeypatch):
        monkeypatch.setattr("pathlib.Path.glob", _blocked)
        monkeypatch.setattr("pathlib.Path.rglob", _blocked)
        r = await self._preview(cli)
        assert r.status_code == 200

    async def test_no_subprocess_or_os_system(self, cli, monkeypatch):
        monkeypatch.setattr("subprocess.run", _blocked)
        monkeypatch.setattr("subprocess.Popen", _blocked)
        monkeypatch.setattr("os.system", _blocked)
        r = await self._preview(cli)
        assert r.status_code == 200

    async def test_no_secret_ref_or_env(self, cli):
        r = await self._preview(cli)
        body = str(r.json())
        for item in ["OPENAI_API_KEY", "sk-", "-----BEGIN"]:
            assert item not in body, f"response contains {item}"

    async def test_api_envelope(self, cli):
        r = await self._preview(cli)
        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        assert "message" in body

    async def test_redaction_applied(self, cli):
        r = await self._preview(cli)
        assert r.status_code == 200
        assert r.json()["data"]["redaction_applied"] is True

    async def test_browser_reviewer_advisory_only(self, cli):
        r = await self._preview(cli, mode="browser_reviewer")
        assert r.status_code == 200
        sys = r.json()["data"]["system_prompt_preview"]
        assert "advisory_only" in sys
        assert "not_final_approval" in sys

    async def test_patch_generation_unified_diff_only(self, cli):
        r = await self._preview(cli, mode="patch_generation")
        assert r.status_code == 200
        sys = r.json()["data"]["system_prompt_preview"]
        assert "unified diff only" in sys

    async def test_user_prompt_contains_matched_modules(self, cli):
        r = await self._preview(cli)
        assert r.status_code == 200
        user = r.json()["data"]["user_prompt_preview"]
        assert "Matched Modules" in user

    async def test_user_prompt_contains_token_budget_summary(self, cli):
        r = await self._preview(cli)
        assert r.status_code == 200
        user = r.json()["data"]["user_prompt_preview"]
        assert "Token Budget Summary" in user


class TestStaticAnalysis:

    def test_no_dangerous_imports(self):
        from app.services import prompt_template_service as svc
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

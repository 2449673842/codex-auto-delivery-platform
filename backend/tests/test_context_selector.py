"""Tests for Context Selector API (v0.4 S8)."""

import ast
import os
import subprocess

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

    # ── Existing tests (1-15) ──

    async def test_module_name_review_packet(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "module_name": "review_packet",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        names = [m["name"] for m in data["matched_modules"]]
        assert "review_packet" in names
        assert any("review_packet" in f for f in data["recommended_files"])
        assert data["confidence"] == "high"

    async def test_task_goal_review_packet(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "task_goal": "review packet rule",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        names = [m["name"] for m in data["matched_modules"]]
        assert "review_packet" in names
        assert data["confidence"] == "high"

    async def test_task_goal_sandbox_gate(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "task_goal": "sandbox gate stale result",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        names = [m["name"] for m in data["matched_modules"]]
        assert "sandbox_gate" in names

    async def test_task_goal_frontend(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "task_goal": "frontend task detail sandbox display",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        names = [m["name"] for m in data["matched_modules"]]
        assert "frontend_pages" in names or "frontend_core" in names

    async def test_task_type_backend_router(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "task_type": "add a new backend router",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["task_hints_used"]) > 0
        assert any("router" in str(h).lower() for h in data["task_hints_used"])

    async def test_unknown_task_low_confidence(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "task_goal": "xyznonexistenttask12345",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["confidence"] == "low"
        assert "no_project_map_match" in data["warnings"]

    async def test_returns_safety_notes(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "module_name": "review_packet",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["safety_notes"]) > 0

    async def test_returns_recommended_tests(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "module_name": "review_packet",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["recommended_tests"]) > 0
        assert any("test_review_packet" in t for t in data["recommended_tests"])

    async def test_returns_recommended_api(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "module_name": "review_packet",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["recommended_api"]) > 0
        assert any("review-packets" in a for a in data["recommended_api"])

    async def test_malformed_repository_map(self, cli, monkeypatch, tmp_path):
        fake = tmp_path / "_test_malformed.json"
        fake.write_text("{bad json", encoding="utf-8")
        monkeypatch.setattr(context_selector_service, "_REPOSITORY_MAP_PATH", fake)
        context_selector_service._clear_cache()
        r = await cli.post("/api/context-selector/preview", json={
            "task_goal": "anything",
        })
        assert r.status_code == 500

    async def test_endpoint_returns_200(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "task_goal": "review packet",
        })
        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        assert "message" in body

    async def test_returns_task_hints_used(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "task_type": "add a new backend router",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["task_hints_used"]) > 0

    async def test_empty_request(self, cli):
        r = await cli.post("/api/context-selector/preview", json={})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["confidence"] == "low"
        assert len(data["matched_modules"]) == 0

    async def test_module_name_case_insensitive(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "module_name": "Review_Packet",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        names = [m["name"] for m in data["matched_modules"]]
        assert "review_packet" in names

    async def test_no_dangerous_imports(self):
        src = (context_selector_service.__file__ or "").replace("\\", "/")
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

    async def test_no_secret_ref_or_env_access(self):
        src = (context_selector_service.__file__ or "").replace("\\", "/")
        with open(src, encoding="utf-8") as f:
            code = f.read()
        dangerous = ["secret_ref", "OPENAI_API_KEY"]
        for item in dangerous:
            assert item not in code, f"service contains dangerous reference: {item}"

    # ── Security boundary tests (16-19) ──

    async def test_does_not_use_subprocess_or_os_system(self, cli, monkeypatch):
        monkeypatch.setattr(subprocess, "run", _fail)
        monkeypatch.setattr(subprocess, "Popen", _fail)
        monkeypatch.setattr(os, "system", _fail)
        r = await cli.post("/api/context-selector/preview", json={
            "module_name": "review_packet",
        })
        assert r.status_code == 200

    async def test_only_reads_configured_repository_map(self, cli, monkeypatch, tmp_path):
        fake_map = tmp_path / "_test_fake_map.json"
        fake_map.write_text("""
        {
            "version": "test",
            "modules": [
                {
                    "name": "fake_module",
                    "type": "backend_feature",
                    "description": "Fake module for testing",
                    "files": {
                        "router": ["backend/app/routers/fake.py"]
                    },
                    "api": ["GET /api/fake"],
                    "safety_notes": ["test only"]
                }
            ],
            "file_roles": {},
            "task_hints": []
        }
        """, encoding="utf-8")
        monkeypatch.setattr(context_selector_service, "_REPOSITORY_MAP_PATH", fake_map)
        context_selector_service._clear_cache()
        r = await cli.post("/api/context-selector/preview", json={
            "module_name": "fake_module",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        names = [m["name"] for m in data["matched_modules"]]
        assert "fake_module" in names
        assert not any("review_packet" in n for n in names)
        assert not any("sandbox_gate" in n for n in names)

    async def test_does_not_glob_walk_or_scan(self, cli, monkeypatch):
        monkeypatch.setattr(context_selector_service.Path, "glob",
                            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("glob called")))
        monkeypatch.setattr(context_selector_service.Path, "rglob",
                            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("rglob called")))
        r = await cli.post("/api/context-selector/preview", json={
            "module_name": "review_packet",
        })
        assert r.status_code == 200

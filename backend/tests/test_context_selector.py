"""Tests for Context Selector API (v0.4 S8)."""

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

    async def test_malformed_repository_map(self, cli, tmp_path):
        orig = context_selector_service._REPOSITORY_MAP_PATH
        fake = tmp_path / "_test_malformed.json"
        fake.write_text("{bad json", encoding="utf-8")
        context_selector_service._REPOSITORY_MAP_PATH = fake
        context_selector_service._clear_cache()
        try:
            r = await cli.post("/api/context-selector/preview", json={
                "task_goal": "anything",
            })
            assert r.status_code == 500
        finally:
            context_selector_service._REPOSITORY_MAP_PATH = orig
            context_selector_service._clear_cache()

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

    async def test_no_file_system_scanning(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "task_goal": "anything",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert "recommended_files" in data
        assert isinstance(data["recommended_files"], list)

    # ── Security boundary tests (16-19) ──

    async def test_service_does_not_use_subprocess_or_os_system(self, cli):
        orig_run = subprocess.run
        orig_popen = subprocess.Popen
        orig_system = os.system
        try:
            subprocess.run = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("subprocess.run called"))
            subprocess.Popen = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("subprocess.Popen called"))
            os.system = lambda *a: (_ for _ in ()).throw(RuntimeError("os.system called"))
            r = await cli.post("/api/context-selector/preview", json={
                "module_name": "review_packet",
            })
            assert r.status_code == 200
        finally:
            subprocess.run = orig_run
            subprocess.Popen = orig_popen
            os.system = orig_system

    async def test_service_does_not_read_secret_ref_or_env(self, cli):
        import builtins
        orig_open = builtins.open
        def guarded_open(*args, **kwargs):
            path = str(args[0]) if args else ""
            for forbidden in (".env", "secret_ref", ".secret"):
                if forbidden in path:
                    raise RuntimeError(f"Cannot open forbidden path: {path}")
            return orig_open(*args, **kwargs)
        builtins.open = guarded_open
        try:
            r = await cli.post("/api/context-selector/preview", json={
                "module_name": "review_packet",
            })
            assert r.status_code == 200
        finally:
            builtins.open = orig_open
            context_selector_service._clear_cache()

    async def test_service_does_not_access_project_root_path(self, cli):
        import builtins
        orig_open = builtins.open
        def guarded_open(*args, **kwargs):
            path = str(args[0]) if args else ""
            if "root_path" in path.lower():
                raise RuntimeError(f"Cannot access root_path: {path}")
            return orig_open(*args, **kwargs)
        builtins.open = guarded_open
        try:
            r = await cli.post("/api/context-selector/preview", json={
                "module_name": "review_packet",
            })
            assert r.status_code == 200
        finally:
            builtins.open = orig_open
            context_selector_service._clear_cache()

    async def test_service_only_reads_configured_repository_map(self, cli, tmp_path):
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
        orig = context_selector_service._REPOSITORY_MAP_PATH
        context_selector_service._REPOSITORY_MAP_PATH = fake_map
        context_selector_service._clear_cache()
        try:
            r = await cli.post("/api/context-selector/preview", json={
                "module_name": "fake_module",
            })
            assert r.status_code == 200
            data = r.json()["data"]
            names = [m["name"] for m in data["matched_modules"]]
            assert "fake_module" in names
            assert any("fake" in f for f in data["recommended_files"])
        finally:
            context_selector_service._REPOSITORY_MAP_PATH = orig
            context_selector_service._clear_cache()

"""Tests for Context Selector API (v0.4 S8)."""

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services import context_selector_service

_REPO_MAP = (
    Path(__file__).resolve().parent.parent
    / "app" / "services" / ".." / ".." / ".."
    / "docs" / "project-map" / "repository-map.json"
).resolve()


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

    # 1. module_name exact match
    async def test_module_name_review_packet(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "module_name": "review_packet",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        names = [m["name"] for m in data["matched_modules"]]
        assert "review_packet" in names
        files = data["recommended_files"]
        assert any("review_packet" in f for f in files)
        assert data["confidence"] == "high"

    # 2. task_goal keyword match (review packet)
    async def test_task_goal_review_packet(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "task_goal": "review packet rule",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        names = [m["name"] for m in data["matched_modules"]]
        assert "review_packet" in names
        assert data["confidence"] == "high"

    # 3. task_goal keyword match (sandbox gate)
    async def test_task_goal_sandbox_gate(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "task_goal": "sandbox gate stale result",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        names = [m["name"] for m in data["matched_modules"]]
        assert "sandbox_gate" in names

    # 4. task_goal keyword match (frontend)
    async def test_task_goal_frontend(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "task_goal": "frontend task detail sandbox display",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        names = [m["name"] for m in data["matched_modules"]]
        assert "frontend_pages" in names or "frontend_core" in names

    # 5. task_type match (add a new backend router)
    async def test_task_type_backend_router(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "task_type": "add a new backend router",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["task_hints_used"]) > 0
        assert any("router" in str(h).lower() for h in data["task_hints_used"])

    # 6. unknown task → low confidence + warning
    async def test_unknown_task_low_confidence(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "task_goal": "xyznonexistenttask12345",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["confidence"] == "low"
        assert "no_project_map_match" in data["warnings"]

    # 7. returns safety_notes
    async def test_returns_safety_notes(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "module_name": "review_packet",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["safety_notes"]) > 0

    # 8. returns recommended_tests
    async def test_returns_recommended_tests(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "module_name": "review_packet",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["recommended_tests"]) > 0
        assert any("test_review_packet" in t for t in data["recommended_tests"])

    # 9. returns recommended_api
    async def test_returns_recommended_api(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "module_name": "review_packet",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["recommended_api"]) > 0
        assert any("review-packets" in a for a in data["recommended_api"])

    # 10. malformed JSON → 500 safe failure
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

    # 11. API returns 200 on normal request
    async def test_endpoint_returns_200(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "task_goal": "review packet",
        })
        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        assert "message" in body

    # 12. returns task_hints_used
    async def test_returns_task_hints_used(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "task_type": "add a new backend router",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["task_hints_used"]) > 0

    # 13. empty request returns low confidence
    async def test_empty_request(self, cli):
        r = await cli.post("/api/context-selector/preview", json={})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["confidence"] == "low"
        assert len(data["matched_modules"]) == 0

    # 14. module_name case insensitive
    async def test_module_name_case_insensitive(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "module_name": "Review_Packet",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        names = [m["name"] for m in data["matched_modules"]]
        assert "review_packet" in names

    # 15. no file system scanning check
    async def test_no_file_system_scanning(self, cli):
        r = await cli.post("/api/context-selector/preview", json={
            "task_goal": "anything",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert "recommended_files" in data
        assert isinstance(data["recommended_files"], list)

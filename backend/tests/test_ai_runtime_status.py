import dataclasses
import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _install_runtime_settings(monkeypatch, **overrides):
    import app.routers.ai_runtime as router

    current = router.settings
    updated = dataclasses.replace(current, **overrides)
    monkeypatch.setattr(router, "settings", updated)
    return updated


@pytest.mark.asyncio
async def test_runtime_status_reports_credential_presence_without_secret(client, monkeypatch):
    fake_secret = "test-runtime-secret"
    _install_runtime_settings(
        monkeypatch,
        ai_execution_enabled=True,
        openai_api_key=fake_secret,
        _provider_allowlist_raw="sandbox,openai",
        openai_model="gpt-5.5",
        openai_base_url="http://localhost:8081",
        openai_wire_api="responses",
    )

    resp = await client.get("/api/ai-runtime/status")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["ai_execution_enabled"] is True
    assert data["openai_credential_configured"] is True
    assert data["openai_allowed"] is True
    assert data["provider_allowlist"] == ["sandbox", "openai"]
    assert data["model"] == "gpt-5.5"
    assert data["base_url_configured"] is True
    assert data["wire_api"] == "responses"
    body = json.dumps(resp.json())
    assert fake_secret not in body


@pytest.mark.asyncio
async def test_runtime_status_reports_missing_credential(client, monkeypatch):
    _install_runtime_settings(
        monkeypatch,
        ai_execution_enabled=False,
        openai_api_key="",
        _provider_allowlist_raw="sandbox",
    )

    resp = await client.get("/api/ai-runtime/status")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["ai_execution_enabled"] is False
    assert data["openai_credential_configured"] is False
    assert data["openai_allowed"] is False


@pytest.mark.asyncio
async def test_runtime_status_does_not_touch_forbidden_surfaces(client, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("forbidden call")

    monkeypatch.setattr("pathlib.Path.glob", fail)
    monkeypatch.setattr("pathlib.Path.rglob", fail)
    monkeypatch.setattr("subprocess.run", fail)
    monkeypatch.setattr("subprocess.Popen", fail)
    monkeypatch.setattr("os.system", fail)
    fake_secret = "test-runtime-secret"
    _install_runtime_settings(monkeypatch, openai_api_key=fake_secret)

    resp = await client.get("/api/ai-runtime/status")

    assert resp.status_code == 200
    body = json.dumps(resp.json())
    assert "secret_ref" not in body
    assert ".env" not in body
    assert fake_secret not in body

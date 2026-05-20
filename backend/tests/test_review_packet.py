"""Tests for Review Packet preview API (v0.4 S4)."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def cli():
    t = ASGITransport(app=app)
    async with AsyncClient(transport=t, base_url="https://x") as c:
        yield c


def _action_names(items: list) -> list[str]:
    if items is None:
        return []
    return [x["action"] for x in items]


@pytest.mark.asyncio
class Tests:

    PR300_SHA = "jkl345mno678jkl345mno678jkl345mno678jkl3"

    async def post(self, cli, pr_number=300, **overrides):
        body = {"repo": "owner/repo", "pr_number": pr_number, **overrides}
        return await cli.post("/api/review-packets/preview", json=body)

    # ── Approved scenarios ──

    async def test_approved_no_reported(self, cli):
        r = await self.post(cli, 300)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["review_status"] == "approved"
        assert d["merge_allowed"] is True
        assert d["blockers"] == []
        assert d["warnings"] == []

    async def test_approved_with_matching_reported(self, cli):
        r = await self.post(cli, 300,
                            reported_head=self.PR300_SHA,
                            reported_pytest="260 passed, 0 failed",
                            reported_compileall="Passed",
                            reported_npm_build="Passed")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["review_status"] == "approved"
        assert d["merge_allowed"] is True

    # ── Blocked: data mismatch ──

    async def test_blocked_head_mismatch(self, cli):
        r = await self.post(cli, 300, reported_head="deadbeef")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["review_status"] == "blocked"
        assert "head_mismatch" in _action_names(d["blockers"])

    async def test_blocked_pytest_mismatch(self, cli):
        r = await self.post(cli, 300, reported_pytest="999 passed")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["review_status"] == "blocked"
        assert "pytest_count_mismatch" in _action_names(d["blockers"])

    async def test_blocked_stale_sonar(self, cli):
        r = await self.post(cli, 100)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["review_status"] == "blocked"
        names = _action_names(d["blockers"])
        assert "stale_sonar_status" in names
        assert "sonar_failed" in names
        assert "duplication_exceeded" in names

    async def test_blocked_na_sonar(self, cli):
        r = await self.post(cli, 150)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["review_status"] == "blocked"
        names = _action_names(d["blockers"])
        assert "na_sonar_stale" in names
        assert "sonar_failed" in names

    async def test_blocked_sonar_failed(self, cli):
        r = await self.post(cli, 200)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["review_status"] == "blocked"
        names = _action_names(d["blockers"])
        assert "sonar_failed" in names
        assert "duplication_exceeded" in names
        warns = _action_names(d["warnings"])
        assert "missing_sonar_results" in warns

    async def test_blocked_suspicious_phrase(self, cli):
        r = await self.post(cli, 400)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["review_status"] == "blocked"
        names = _action_names(d["blockers"])
        assert "suspicious_phrase" in names
        assert "sonar_failed" in names

    # ── Blocked: security / hotspot ──

    async def test_blocked_hotspots_and_blockers(self, cli):
        r = await self.post(cli, 500)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["review_status"] == "blocked"
        names = _action_names(d["blockers"])
        assert "security_hotspots_found" in names
        assert "blocker_issues_found" in names
        assert "unreported_pr_entry" in names
        assert "unreported_ci_entry" in names
        warns = _action_names(d["warnings"])
        assert "code_smells_found" in warns

    # ── Needs update ──

    async def test_already_merged_needs_update(self, cli):
        r = await self.post(cli, 15)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["review_status"] == "needs_update"
        assert d["merge_allowed"] is False
        warns = _action_names(d["warnings"])
        assert "already_merged" in warns

    async def test_needs_update_missing_safety_and_short(self, cli):
        r = await self.post(cli, 600)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["review_status"] == "needs_update"
        warns = _action_names(d["warnings"])
        assert "missing_safety_boundary" in warns
        assert "missing_sonar_results" in warns
        assert "short_head_hash" in warns

    # ── NotFound ──

    async def test_not_found(self, cli):
        r = await self.post(cli, 999)
        assert r.status_code == 404

    # ── Compound: multiple blockers from various sources ──

    async def test_blocked_compound_mismatch_and_sonar(self, cli):
        r = await self.post(cli, 100,
                            reported_head="abc123",
                            reported_pytest="250 passed")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["review_status"] == "blocked"
        names = _action_names(d["blockers"])
        assert "head_mismatch" in names
        assert "pytest_count_mismatch" in names
        assert "stale_sonar_status" in names
        assert "sonar_failed" in names
        assert "duplication_exceeded" in names

    async def test_blocked_compound_mismatch_only(self, cli):
        r = await self.post(cli, 300,
                            reported_head="dead",
                            reported_pytest="999 passed")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["review_status"] == "blocked"
        names = _action_names(d["blockers"])
        assert "head_mismatch" in names
        assert "pytest_count_mismatch" in names
        # no sonar issues for PR #300
        assert "sonar_failed" not in names

    # ── Edge / boundary scenarios ──

    async def test_blocked_reported_on_merged_pr(self, cli):
        r = await self.post(cli, 15, reported_head="deadbeef")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["review_status"] == "blocked"
        assert "head_mismatch" in _action_names(d["blockers"])
        assert "already_merged" in _action_names(d["warnings"])

    async def test_approved_with_empty_reported_fields(self, cli):
        r = await self.post(cli, 300,
                            reported_head="",
                            reported_pytest="",
                            reported_compileall="",
                            reported_npm_build="")
        assert r.status_code == 200
        assert r.json()["data"]["review_status"] == "approved"

    async def test_summary_contains_keywords(self, cli):
        r = await self.post(cli, 100)
        d = r.json()["data"]
        assert "blocked" in d["summary"].lower()
        assert "issue" in d["summary"].lower()
        r2 = await self.post(cli, 300)
        d2 = r2.json()["data"]
        assert d2["summary"].startswith("All checks passed")

    # ── Required actions match blockers ──

    async def test_required_actions_match_blockers(self, cli):
        r = await self.post(cli, 100,
                            reported_head="abc123")
        assert r.status_code == 200
        d = r.json()["data"]
        assert len(d["required_actions"]) == len(d["blockers"])
        for ra in d["required_actions"]:
            assert ra["detail"].startswith("Fix:")

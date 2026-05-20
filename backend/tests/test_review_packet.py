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

    def _dec(self, r):
        return r.json()["data"]["decision"]

    def _pkt(self, r):
        return r.json()["data"]["packet"]

    # ── Approved scenarios ──

    async def test_approved_no_reported(self, cli):
        r = await self.post(cli, 300)
        assert r.status_code == 200
        d = self._dec(r)
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
        d = self._dec(r)
        assert d["review_status"] == "approved"

    # ── Packet field completeness ──

    async def test_packet_contains_all_fields(self, cli):
        r = await self.post(cli, 300)
        p = self._pkt(r)
        assert p["repo"] == "owner/repo"
        assert p["pr_number"] == 300
        assert p["pr_url"] == "https://github.com/owner/repo/pull/300"
        assert p["pr_state"] == "OPEN"
        assert p["head_commit"] == self.PR300_SHA
        assert p["base_commit"] == "c26da770e0febc09b1de7cf975275cbd2c5a9e02"
        assert p["changed_file_count"] == 2
        assert p["sonar_quality_gate"] == "OK"
        assert p["sonar_security_hotspots"] == 0
        assert p["pytest_from_pr_body"] == "260 passed, 0 failed"
        assert p["has_frontend_changes"] is True
        assert p["has_backend_changes"] is True
        assert p["has_db_migration"] is False
        assert p["has_github_pr_entry"] is False
        assert p["head_matches"] is True
        assert p["pytest_matches"] is True

    async def test_packet_contains_both_sections(self, cli):
        r = await self.post(cli, 300)
        data = r.json()["data"]
        assert "packet" in data
        assert "decision" in data

    async def test_packet_head_mismatch_field(self, cli):
        r = await self.post(cli, 300, reported_head="deadbeef")
        p = self._pkt(r)
        assert p["head_matches"] is False

    async def test_packet_pytest_mismatch_field(self, cli):
        r = await self.post(cli, 300, reported_pytest="999 passed")
        p = self._pkt(r)
        assert p["pytest_matches"] is False

    # ── Blocked: data mismatch ──

    async def test_blocked_head_mismatch(self, cli):
        r = await self.post(cli, 300, reported_head="deadbeef")
        d = self._dec(r)
        assert d["review_status"] == "blocked"
        assert "head_mismatch" in _action_names(d["blockers"])

    async def test_blocked_pytest_mismatch(self, cli):
        r = await self.post(cli, 300, reported_pytest="999 passed")
        d = self._dec(r)
        assert d["review_status"] == "blocked"
        assert "pytest_count_mismatch" in _action_names(d["blockers"])

    async def test_blocked_stale_sonar(self, cli):
        r = await self.post(cli, 100)
        d = self._dec(r)
        assert d["review_status"] == "blocked"
        names = _action_names(d["blockers"])
        assert "stale_sonar_status" in names
        assert "sonar_failed" in names
        assert "duplication_exceeded" in names

    async def test_blocked_na_sonar(self, cli):
        r = await self.post(cli, 150)
        d = self._dec(r)
        assert d["review_status"] == "blocked"
        names = _action_names(d["blockers"])
        assert "na_sonar_stale" in names
        assert "sonar_failed" in names

    async def test_blocked_sonar_failed(self, cli):
        r = await self.post(cli, 200)
        d = self._dec(r)
        assert d["review_status"] == "blocked"
        names = _action_names(d["blockers"])
        assert "sonar_failed" in names
        assert "duplication_exceeded" in names
        warns = _action_names(d["warnings"])
        assert "missing_sonar_results" in warns

    async def test_blocked_suspicious_phrase(self, cli):
        r = await self.post(cli, 400)
        d = self._dec(r)
        assert d["review_status"] == "blocked"
        names = _action_names(d["blockers"])
        assert "suspicious_phrase" in names
        assert "sonar_failed" in names

    # ── Blocked: security / hotspot ──

    async def test_blocked_hotspots_and_blockers(self, cli):
        r = await self.post(cli, 500)
        d = self._dec(r)
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
        d = self._dec(r)
        assert d["review_status"] == "needs_update"
        assert d["merge_allowed"] is False
        warns = _action_names(d["warnings"])
        assert "already_merged" in warns

    async def test_needs_update_missing_safety_and_short(self, cli):
        r = await self.post(cli, 600)
        d = self._dec(r)
        assert d["review_status"] == "needs_update"
        warns = _action_names(d["warnings"])
        assert "missing_safety_boundary" in warns
        assert "missing_sonar_results" in warns
        assert "short_head_hash" in warns

    # ── New rules: compileall / npm / Playwright failed ──

    async def test_blocked_compileall_failed(self, cli):
        r = await self.post(cli, 300, reported_compileall="Failed")
        d = self._dec(r)
        assert d["review_status"] == "blocked"
        assert "compileall_failed" in _action_names(d["blockers"])

    async def test_blocked_npm_build_failed(self, cli):
        r = await self.post(cli, 300, reported_npm_build="error")
        d = self._dec(r)
        assert d["review_status"] == "blocked"
        assert "npm_build_failed" in _action_names(d["blockers"])

    async def test_blocked_playwright_failed(self, cli):
        r = await self.post(cli, 700, reported_playwright="failed")
        d = self._dec(r)
        assert d["review_status"] == "blocked"
        assert "playwright_failed" in _action_names(d["blockers"])

    # ── New rules: frontend no npm build ──

    async def test_needs_update_frontend_no_npm_build(self, cli):
        r = await self.post(cli, 800)
        d = self._dec(r)
        assert d["review_status"] == "needs_update"
        warns = _action_names(d["warnings"])
        assert "frontend_missing_npm_build" in warns

    # ── New rules: Playwright not reported ──

    async def test_needs_update_playwright_not_reported(self, cli):
        r = await self.post(cli, 700)
        d = self._dec(r)
        assert d["review_status"] == "needs_update"
        warns = _action_names(d["warnings"])
        assert "playwright_not_reported" in warns

    # ── New rules: changed file count mismatch ──

    async def test_warning_changed_file_count_small_mismatch(self, cli):
        r = await self.post(cli, 300, reported_changed_file_count=3)
        d = self._dec(r)
        assert d["review_status"] == "needs_update"
        warns = _action_names(d["warnings"])
        assert "changed_file_count_mismatch" in warns
        blockers = _action_names(d["blockers"])
        assert "changed_file_count_mismatch" not in blockers

    async def test_blocked_changed_file_count_large_mismatch(self, cli):
        r = await self.post(cli, 15, reported_changed_file_count=1)
        d = self._dec(r)
        assert d["review_status"] == "blocked"
        blockers = _action_names(d["blockers"])
        assert "changed_file_count_mismatch" in blockers

    # ── New rules: compileall / npm body mismatch ──

    async def test_warning_compileall_body_mismatch(self, cli):
        r = await self.post(cli, 300, reported_compileall="Failed")
        d = self._dec(r)
        # compileall_failed is blocker, body mismatch is also detected
        warns = _action_names(d["warnings"])
        assert "compileall_body_mismatch" in warns

    # ── NotFound ──

    async def test_not_found(self, cli):
        r = await self.post(cli, 999)
        assert r.status_code == 404

    # ── Compound ──

    async def test_blocked_compound_mismatch_and_sonar(self, cli):
        r = await self.post(cli, 100,
                            reported_head="abc123",
                            reported_pytest="250 passed")
        d = self._dec(r)
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
        d = self._dec(r)
        assert d["review_status"] == "blocked"
        names = _action_names(d["blockers"])
        assert "head_mismatch" in names
        assert "pytest_count_mismatch" in names
        assert "sonar_failed" not in names

    # ── Edge / boundary ──

    async def test_blocked_reported_on_merged_pr(self, cli):
        r = await self.post(cli, 15, reported_head="deadbeef")
        d = self._dec(r)
        assert d["review_status"] == "blocked"
        assert "head_mismatch" in _action_names(d["blockers"])
        assert "already_merged" in _action_names(d["warnings"])

    async def test_approved_with_empty_reported_fields(self, cli):
        r = await self.post(cli, 300,
                            reported_head="",
                            reported_pytest="",
                            reported_compileall="",
                            reported_npm_build="")
        assert self._dec(r)["review_status"] == "approved"

    async def test_summary_contains_keywords(self, cli):
        r = await self.post(cli, 100)
        d = self._dec(r)
        assert "blocked" in d["summary"].lower()
        assert "issue" in d["summary"].lower()
        r2 = await self.post(cli, 300)
        d2 = self._dec(r2)
        assert d2["summary"].startswith("All checks passed")

    # ── Required actions ──

    async def test_required_actions_match_blockers(self, cli):
        r = await self.post(cli, 100, reported_head="abc123")
        d = self._dec(r)
        assert len(d["required_actions"]) == len(d["blockers"])
        for ra in d["required_actions"]:
            assert ra["detail"].startswith("Fix:")

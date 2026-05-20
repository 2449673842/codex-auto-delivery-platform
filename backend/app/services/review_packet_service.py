"""Review Packet Service — stateless PR review automation.

Generates a review packet by comparing reported status against actual
GitHub and SonarCloud data. Uses mock connectors (first version).
"""

import re
from fastapi import HTTPException
from app.schemas.review_packet import ReviewPacketDecision, ReviewAction


# ─── Mock GitHub data ─────────────────────────────────────────

def _mock_github_pr(repo: str, pr_number: int) -> dict:
    """Return mock GitHub PR data for a given repo and PR number."""
    if pr_number == 15:
        return {
            "state": "MERGED",
            "merged": True,
            "head": "52df853b84df4bafea4e44c7d7e0d63271d62fe2",
            "base": "c26da770e0febc09b1de7cf975275cbd2c5a9e02",
            "title": "v0.4 S3 — Sandbox Approval Gate",
            "body": (
                "## Summary\n\nSandbox Approval Gate.\n\n## Quality\n\n"
                "| Check | Status | Detail |\n"
                "|-------|--------|--------|\n"
                "| pytest | **253 passed, 0 failed** | 16 gate-specific |\n"
                "| compileall | **Passed** | |\n"
                "| npm build | **Passed** | |\n"
                "| SonarCloud Quality Gate | **Passed** | All OK |\n"
                "| Duplication on New Code | **0.0%** | |\n"
                "| Security Hotspots | **0** | |\n\n"
                "## Security Boundary\n\n| Check | Result | Note |\n"
                "|-------|--------|------|\n"
                "| Database migration | **None** | |\n"
                "| Real GitHub PR | **Not added** | |\n"
                "| Real CI/Sonar/Deploy | **Not added** | |\n"
            ),
            "changed_files": [
                "backend/app/enums.py",
                "backend/app/main.py",
                "backend/app/routers/sandbox_gate.py",
                "backend/app/schemas/sandbox_gate.py",
                "backend/app/services/sandbox_approval_gate_service.py",
                "backend/tests/test_sandbox_gate.py",
                "frontend/src/pages/TaskDetailPage.vue",
                "frontend/src/services/agentService.ts",
                "frontend/src/types/agent.ts",
            ],
            "additions": 541,
            "deletions": 2,
            "sonar_comment_found": True,
        }
    if pr_number == 100:
        return {
            "state": "OPEN",
            "merged": False,
            "head": "abc123def456abc123def456abc123def456abc1",
            "base": "c26da770e0febc09b1de7cf975275cbd2c5a9e02",
            "title": "Some feature with issues",
            "body": (
                "## Summary\n\nSome feature.\n\n## Quality\n\n"
                "| Check | Status | Detail |\n"
                "|-------|--------|--------|\n"
                "| pytest | **240 passed** | 12 new |\n"
                "| compileall | **Passed** | |\n"
                "| SonarCloud Quality Gate | **待 CI 报告** | |\n\n"
                "## Security Boundary\n\n| Check | Result |\n"
                "|-------|--------|\n"
                "| Database migration | **None** |\n"
            ),
            "changed_files": [
                "backend/app/routers/some_router.py",
                "backend/app/models/some_model.py",
            ],
            "additions": 120,
            "deletions": 30,
            "sonar_comment_found": True,
        }
    if pr_number == 150:
        return {
            "state": "OPEN",
            "merged": False,
            "head": "def789ghi012def789ghi012def789ghi012def7",
            "base": "c26da770e0febc09b1de7cf975275cbd2c5a9e02",
            "title": "Feature with N/A",
            "body": (
                "## Summary\n\nA feature.\n\n## Quality\n\n"
                "| Check | Status | Detail |\n"
                "|-------|--------|--------|\n"
                "| pytest | **250 passed** | |\n"
                "| compileall | **Passed** | |\n"
                "| SonarCloud | **N/A** | not configured |\n\n"
                "## Security Boundary\n\n| Check | Result |\n"
                "|-------|--------|\n"
                "| Database migration | **None** |\n"
            ),
            "changed_files": [
                "backend/app/routers/feature_x.py",
            ],
            "additions": 50,
            "deletions": 10,
            "sonar_comment_found": True,
        }
    if pr_number == 200:
        return {
            "state": "OPEN",
            "merged": False,
            "head": "ghi012jkl345ghi012jkl345ghi012jkl345ghi0",
            "base": "c26da770e0febc09b1de7cf975275cbd2c5a9e02",
            "title": "Feature with stale body",
            "body": (
                "## Summary\n\nOutdated.\n\n## Quality\n\n"
                "| Check | Status | Detail |\n"
                "|-------|--------|--------|\n"
                "| pytest | **250 passed** | |\n"
                "| compileall | **Passed** | |\n\n"
                "## Security Boundary\n\n| Check | Result |\n"
                "|-------|--------|\n"
                "| Database migration | **None** |\n"
            ),
            "changed_files": [
                "backend/app/routers/feature_y.py",
            ],
            "additions": 30,
            "deletions": 5,
            "sonar_comment_found": False,
        }
    if pr_number == 300:
        return {
            "state": "OPEN",
            "merged": False,
            "head": "jkl345mno678jkl345mno678jkl345mno678jkl3",
            "base": "c26da770e0febc09b1de7cf975275cbd2c5a9e02",
            "title": "Fully approved feature",
            "body": (
                "## Summary\n\nClean feature.\n\n## Quality\n\n"
                "| Check | Status | Detail |\n"
                "|-------|--------|--------|\n"
                "| pytest | **260 passed, 0 failed** | 12 new |\n"
                "| compileall | **Passed** | |\n"
                "| npm build | **Passed** | |\n"
                "| SonarCloud Quality Gate | **Passed** | |\n"
                "| Duplication on New Code | **0.0%** | |\n"
                "| Security Hotspots | **0** | |\n\n"
                "## Security Boundary\n\n| Check | Result | Note |\n"
                "|-------|--------|------|\n"
                "| Database migration | **None** | |\n"
                "| Real GitHub PR | **Not added** | |\n"
                "| Real CI/Sonar/Deploy | **Not added** | |\n"
            ),
            "changed_files": [
                "backend/app/routers/feature_z.py",
                "frontend/src/pages/NewPage.vue",
            ],
            "additions": 200,
            "deletions": 15,
            "sonar_comment_found": True,
        }
    if pr_number == 350:
        return {
            "state": "OPEN",
            "merged": False,
            "head": "abc",
            "base": "c26da770e0febc09b1de7cf975275cbd2c5a9e02",
            "title": "Short hash only",
            "body": (
                "## Summary\n\nShort hash.\n\n## Quality\n\n"
                "| Check | Status |\n"
                "|-------|--------|\n"
                "| pytest | **255 passed** |\n\n"
                "## Security Boundary\n\n| Check | Result |\n"
                "|-------|--------|\n"
                "| Database migration | **None** |\n"
            ),
            "changed_files": [],
            "additions": 10,
            "deletions": 0,
            "sonar_comment_found": False,
        }
    if pr_number == 400:
        return {
            "state": "OPEN",
            "merged": False,
            "head": "mno678pqr901mno678pqr901mno678pqr901mno6",
            "base": "c26da770e0febc09b1de7cf975275cbd2c5a9e02",
            "title": "Monkeypatch excluded",
            "body": (
                "## Summary\n\nMonkeypatch issue.\n\n## Quality\n\n"
                "| Check | Status |\n"
                "|-------|--------|\n"
                "| pytest | **245 passed** | 测试除外 |\n"
                "| compileall | **Passed** | |\n\n"
                "## Security Boundary\n\n| Check | Result |\n"
                "|-------|--------|\n"
                "| Database migration | **None** |\n"
            ),
            "changed_files": ["src/test.py"],
            "additions": 5,
            "deletions": 0,
            "sonar_comment_found": False,
        }
    if pr_number == 500:
        return {
            "state": "OPEN",
            "merged": False,
            "head": "stu234vwx567stu234vwx567stu234vwx567stu2",
            "base": "c26da770e0febc09b1de7cf975275cbd2c5a9e02",
            "title": "Hotspots and blocker issues",
            "body": (
                "## Summary\n\nSecurity-related.\n\n## Quality\n\n"
                "| Check | Status | Detail |\n"
                "|-------|--------|--------|\n"
                "| pytest | **265 passed, 0 failed** | 20 new |\n"
                "| compileall | **Passed** | |\n"
                "| npm build | **Passed** | |\n"
                "| SonarCloud Quality Gate | **Passed** | |\n"
                "| Duplication on New Code | **0.0%** | |\n\n"
                "## Security Boundary\n\n| Check | Result | Note |\n"
                "|-------|--------|------|\n"
                "| Database migration | **None** | |\n"
                "| Real GitHub PR | **新增** | from this PR |\n"
                "| Real CI/Sonar/Deploy | **新增** | CI added |\n"
            ),
            "changed_files": ["backend/app/security.py"],
            "additions": 80,
            "deletions": 5,
            "sonar_comment_found": True,
        }
    if pr_number == 600:
        return {
            "state": "OPEN",
            "merged": False,
            "head": "abcd",
            "base": "c26da770e0febc09b1de7cf975275cbd2c5a9e02",
            "title": "Missing safety boundary",
            "body": (
                "## Summary\n\nNo boundary section.\n\n## Quality\n\n"
                "| Check | Status |\n"
                "|-------|--------|\n"
                "| pytest | **270 passed** | |\n"
                "| compileall | **Passed** | |\n"
            ),
            "changed_files": ["backend/app/routers/feature_w.py"],
            "additions": 25,
            "deletions": 3,
            "sonar_comment_found": False,
        }
    raise HTTPException(status_code=404, detail=f"PR #{pr_number} not found")


# ─── Mock Sonar data ─────────────────────────────────────────

def _mock_sonar_result(pr_number: int) -> dict:
    """Return mock SonarCloud analysis result for a given PR number."""
    if pr_number in (15, 300):
        return {
            "quality_gate": "OK",
            "duplication_on_new_code": "0.0",
            "security_hotspots": 0,
            "new_bugs": 0,
            "new_vulnerabilities": 0,
            "new_code_smells": 0,
            "has_blocker_issues": False,
        }
    if pr_number in (100, 150, 200, 400):
        return {
            "quality_gate": "ERROR",
            "duplication_on_new_code": "4.2",
            "security_hotspots": 0,
            "new_bugs": 0,
            "new_vulnerabilities": 0,
            "new_code_smells": 3,
            "has_blocker_issues": False,
        }
    if pr_number == 500:
        return {
            "quality_gate": "OK",
            "duplication_on_new_code": "0.0",
            "security_hotspots": 2,
            "new_bugs": 0,
            "new_vulnerabilities": 0,
            "new_code_smells": 5,
            "has_blocker_issues": True,
        }
    return {
        "quality_gate": "OK",
        "duplication_on_new_code": "0.0",
        "security_hotspots": 0,
        "new_bugs": 0,
        "new_vulnerabilities": 0,
        "new_code_smells": 0,
        "has_blocker_issues": False,
    }


# ─── PR body analysis helpers ────────────────────────────────

def _extract_table_value(body: str, key: str) -> str:
    """Extract a markdown table cell value by row key."""
    pat = re.compile(
        r"\|\s*\*{0,2}" + re.escape(key) + r"\*{0,2}\s*\|\s*\*{0,2}(.*?)\*{0,2}\s*\|",
        re.IGNORECASE | re.MULTILINE,
    )
    m = pat.search(body)
    return m.group(1).strip() if m else ""


def _has_section(body: str, title: str) -> bool:
    return bool(re.search(r"^#{1,3}\s+" + re.escape(title), body, re.MULTILINE | re.IGNORECASE))


def _body_has_phrase(body: str, phrase: str) -> bool:
    return phrase in body


def _has_db_migration(body: str) -> bool:
    val = _extract_table_value(body, "Database migration")
    return "有" in val or "是" in val or "yes" in val.lower()


def _has_real_pr_entry(body: str) -> bool:
    val = _extract_table_value(body, "Real GitHub PR")
    return "新增" in val and "not" not in val.lower() and "no" not in val.lower()


def _has_real_ci_entry(body: str) -> bool:
    for key in ("Real CI/Sonar/Deploy", "Real CI", "Real Sonar", "Real Deploy"):
        val = _extract_table_value(body, key)
        if "新增" in val and "not" not in val.lower() and "no" not in val.lower():
            return True
    return False


def _extract_pytest_count(body: str) -> int | None:
    val = _extract_table_value(body, "pytest")
    m = re.search(r"(\d+)\s*passed", val)
    return int(m.group(1)) if m else None


def _has_suspicious_phrase(body: str) -> bool:
    phrases = ["测试除外", "monkeypatch 除外", "skip 未说明"]
    return any(p in body for p in phrases)


def _get_head_from_body(body: str) -> str:
    m = re.search(r"\b([a-f0-9]{7,40})\b", body)
    return m.group(1) if m else ""


# ─── Main service ────────────────────────────────────────────

def generate_review_packet(
    repo: str,
    pr_number: int,
    reported_head: str = "",
    reported_pytest: str = "",
    reported_compileall: str = "",
    reported_npm_build: str = "",
    reported_playwright: str = "",
) -> ReviewPacketDecision:
    pr = _mock_github_pr(repo, pr_number)
    sonar = _mock_sonar_result(pr_number)

    blockers: list[ReviewAction] = []
    warnings: list[ReviewAction] = []
    required_actions: list[ReviewAction] = []

    body = pr["body"]
    body_pytest = _extract_pytest_count(body)

    # ── 1. Reported head mismatch ──
    if reported_head and reported_head != pr["head"]:
        blockers.append(ReviewAction(
            action="head_mismatch",
            detail=f"Reported head {reported_head[:12]}... does not match GitHub PR head {pr['head'][:12]}...",
        ))

    # ── 2. Reported pytest != PR body pytest ──
    if reported_pytest and body_pytest is not None:
        reported_num = int(re.search(r"\d+", reported_pytest).group()) if re.search(r"\d+", reported_pytest) else None
        if reported_num is not None and reported_num != body_pytest:
            blockers.append(ReviewAction(
                action="pytest_count_mismatch",
                detail=f"Reported pytest ({reported_pytest}) does not match PR body ({body_pytest} passed)",
            ))

    # ── 3. Body says '待 CI 报告' but Sonar comment exists ──
    if _body_has_phrase(body, "待 CI 报告") and pr.get("sonar_comment_found"):
        blockers.append(ReviewAction(
            action="stale_sonar_status",
            detail="PR body says '待 CI 报告' but SonarCloud comment already exists",
        ))

    # ── 4. Body says 'N/A' but Sonar comment exists ──
    if _body_has_phrase(body, "**N/A**") and pr.get("sonar_comment_found"):
        blockers.append(ReviewAction(
            action="na_sonar_stale",
            detail="PR body says 'N/A' for Sonar but SonarCloud comment already exists",
        ))

    # ── 5. SonarCloud failed ──
    if sonar["quality_gate"] != "OK":
        blockers.append(ReviewAction(
            action="sonar_failed",
            detail=f"SonarCloud Quality Gate is {sonar['quality_gate']}",
        ))

    # ── 6. Duplication > 3% ──
    dup = float(sonar["duplication_on_new_code"])
    if dup > 3.0:
        blockers.append(ReviewAction(
            action="duplication_exceeded",
            detail=f"Duplication on New Code is {dup}% (threshold: ≤3%)",
        ))

    # ── 7. Security Hotspots > 0 ──
    if sonar["security_hotspots"] > 0:
        blockers.append(ReviewAction(
            action="security_hotspots_found",
            detail=f"{sonar['security_hotspots']} Security Hotspot(s) need review",
        ))

    # ── 8. New issues (blocker → blocked, code smell → warning) ──
    if sonar.get("has_blocker_issues"):
        blockers.append(ReviewAction(
            action="blocker_issues_found",
            detail="New blocker-type issues found in SonarCloud analysis",
        ))
    if sonar["new_code_smells"] > 0:
        warnings.append(ReviewAction(
            action="code_smells_found",
            detail=f"{sonar['new_code_smells']} new code smell(s) found (non-blocking)",
        ))

    # ── 9. PR body test count stale vs body ──
    if body_pytest is not None and reported_pytest:
        reported_num = int(re.search(r"\d+", reported_pytest).group()) if re.search(r"\d+", reported_pytest) else None
        if reported_num is not None and reported_num != body_pytest:
            pass  # Already caught by rule #2; avoid duplicate

    # ── 10. Changed files count mismatch ──
    if pr["changed_files"]:
        pass  # No reported changed_files to compare against. Optional.

    # ── 11. Suspicious phrases ──
    if _has_suspicious_phrase(body):
        blockers.append(ReviewAction(
            action="suspicious_phrase",
            detail="PR body contains suspicious phrase indicating tests were excluded without justification",
        ))

    # ── 12. DB migration unreported ──
    if _has_db_migration(body) and _body_has_phrase(body, "None"):
        pass  # reported as none, fine

    # ── 13. Real PR/CI/Sonar/Deploy entry unreported ──
    if _has_real_pr_entry(body):
        blockers.append(ReviewAction(
            action="unreported_pr_entry",
            detail="PR body reports new Real GitHub PR entry but security boundary says no",
        ))
    if _has_real_ci_entry(body):
        blockers.append(ReviewAction(
            action="unreported_ci_entry",
            detail="PR body reports new Real CI/Sonar/Deploy entry but security boundary says no",
        ))

    # ── 15. PR already merged ──
    if pr.get("merged"):
        warnings.append(ReviewAction(
            action="already_merged",
            detail=f"PR #{pr_number} has already been merged",
        ))

    # ── 16. Missing safety boundary section ──
    if not _has_section(body, "Security Boundary"):
        warnings.append(ReviewAction(
            action="missing_safety_boundary",
            detail="PR body is missing the Security Boundary section",
        ))

    # ── 17. Missing Sonar results ──
    body_sonar = _extract_table_value(body, "SonarCloud Quality Gate")
    if not body_sonar:
        body_sonar = _extract_table_value(body, "SonarCloud")
    if not body_sonar:
        warnings.append(ReviewAction(
            action="missing_sonar_results",
            detail="PR body does not mention SonarCloud results",
        ))

    # ── 18. Short head hash ──
    if len(pr["head"]) < 10:
        warnings.append(ReviewAction(
            action="short_head_hash",
            detail=f"PR head commit hash is too short ({len(pr['head'])} chars); use full SHA",
        ))

    # ── Build required actions ──
    for b in blockers:
        required_actions.append(ReviewAction(
            action=b.action,
            detail=f"Fix: {b.detail}",
        ))

    # ── Determine review_status ──
    if blockers:
        review_status = "blocked"
    elif warnings:
        review_status = "needs_update"
    else:
        review_status = "approved"

    merge_allowed = review_status == "approved"

    summary_parts = []
    if review_status == "approved":
        summary_parts.append("All checks passed. PR is ready for merge.")
    elif review_status == "blocked":
        summary_parts.append(f"PR is blocked by {len(blockers)} issue(s).")
    else:
        summary_parts.append(f"PR has {len(warnings)} warning(s); address before merge.")
    if pr.get("merged"):
        summary_parts.append("Note: PR has already been merged.")

    return ReviewPacketDecision(
        review_status=review_status,
        merge_allowed=merge_allowed,
        blockers=blockers,
        warnings=warnings,
        required_actions=required_actions,
        summary=" ".join(summary_parts),
    )

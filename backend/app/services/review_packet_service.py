"""Review Packet Service — stateless PR review automation.

Generates a review packet by comparing reported status against actual
GitHub and SonarCloud data. Uses mock connectors (first version).
"""

from fastapi import HTTPException
from app.schemas.review_packet import (
    ReviewPacketDecision,
    ReviewPacketData,
    ReviewPacketPreviewResponse,
    ReviewAction,
)


# ─── Mock GitHub data ─────────────────────────────────────────

def _mock_github_pr(repo: str, pr_number: int) -> dict:
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
                "backend/app/enums.py", "backend/app/main.py",
                "backend/app/routers/sandbox_gate.py",
                "backend/app/schemas/sandbox_gate.py",
                "backend/app/services/sandbox_approval_gate_service.py",
                "backend/tests/test_sandbox_gate.py",
                "frontend/src/pages/TaskDetailPage.vue",
                "frontend/src/services/agentService.ts",
                "frontend/src/types/agent.ts",
            ],
            "additions": 541, "deletions": 2,
            "sonar_comment_found": True,
        }
    if pr_number == 100:
        return {
            "state": "OPEN", "merged": False,
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
            "additions": 120, "deletions": 30,
            "sonar_comment_found": True,
        }
    if pr_number == 150:
        return {
            "state": "OPEN", "merged": False,
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
            "changed_files": ["backend/app/routers/feature_x.py"],
            "additions": 50, "deletions": 10,
            "sonar_comment_found": True,
        }
    if pr_number == 200:
        return {
            "state": "OPEN", "merged": False,
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
            "changed_files": ["backend/app/routers/feature_y.py"],
            "additions": 30, "deletions": 5,
            "sonar_comment_found": False,
        }
    if pr_number == 300:
        return {
            "state": "OPEN", "merged": False,
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
            "additions": 200, "deletions": 15,
            "sonar_comment_found": True,
        }
    if pr_number == 350:
        return {
            "state": "OPEN", "merged": False,
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
            "additions": 10, "deletions": 0,
            "sonar_comment_found": False,
        }
    if pr_number == 400:
        return {
            "state": "OPEN", "merged": False,
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
            "additions": 5, "deletions": 0,
            "sonar_comment_found": False,
        }
    if pr_number == 500:
        return {
            "state": "OPEN", "merged": False,
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
            "additions": 80, "deletions": 5,
            "sonar_comment_found": True,
        }
    if pr_number == 600:
        return {
            "state": "OPEN", "merged": False,
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
            "additions": 25, "deletions": 3,
            "sonar_comment_found": False,
        }
    if pr_number == 700:
        return {
            "state": "OPEN", "merged": False,
            "head": "vwx567yza123vwx567yza123vwx567yza123vwx5",
            "base": "c26da770e0febc09b1de7cf975275cbd2c5a9e02",
            "title": "Playwright and e2e test PR",
            "body": (
                "## Summary\n\nE2E tests.\n\n## Quality\n\n"
                "| Check | Status |\n"
                "|-------|--------|\n"
                "| pytest | **270 passed** | |\n"
                "| compileall | **Passed** | |\n"
                "| Playwright | **Passed** | |\n\n"
                "## Security Boundary\n\n| Check | Result |\n"
                "|-------|--------|\n"
                "| Database migration | **None** |\n"
            ),
            "changed_files": [
                "backend/app/routers/feature_e2e.py",
                "e2e/test_login.spec.ts",
            ],
            "additions": 100, "deletions": 20,
            "sonar_comment_found": False,
        }
    if pr_number == 800:
        return {
            "state": "OPEN", "merged": False,
            "head": "yza123bcd456yza123bcd456yza123bcd456yza1",
            "base": "c26da770e0febc09b1de7cf975275cbd2c5a9e02",
            "title": "Frontend only PR",
            "body": (
                "## Summary\n\nFrontend-only.\n\n## Quality\n\n"
                "| Check | Status |\n"
                "|-------|--------|\n"
                "| pytest | **280 passed** | |\n"
                "| compileall | **Passed** | |\n\n"
                "## Security Boundary\n\n| Check | Result |\n"
                "|-------|--------|\n"
                "| Database migration | **None** |\n"
            ),
            "changed_files": [
                "frontend/src/pages/NewPage.vue",
                "frontend/src/components/Button.tsx",
            ],
            "additions": 150, "deletions": 10,
            "sonar_comment_found": False,
        }
    raise HTTPException(status_code=404, detail=f"PR #{pr_number} not found")


# ─── Mock Sonar data ─────────────────────────────────────────

def _mock_sonar_result(pr_number: int) -> dict:
    if pr_number in (15, 300):
        return {
            "quality_gate": "OK", "duplication_on_new_code": "0.0",
            "security_hotspots": 0, "new_bugs": 0,
            "new_vulnerabilities": 0, "new_code_smells": 0,
            "has_blocker_issues": False,
        }
    if pr_number in (100, 150, 200, 400):
        return {
            "quality_gate": "ERROR", "duplication_on_new_code": "4.2",
            "security_hotspots": 0, "new_bugs": 0,
            "new_vulnerabilities": 0, "new_code_smells": 3,
            "has_blocker_issues": False,
        }
    if pr_number == 500:
        return {
            "quality_gate": "OK", "duplication_on_new_code": "0.0",
            "security_hotspots": 2, "new_bugs": 0,
            "new_vulnerabilities": 0, "new_code_smells": 5,
            "has_blocker_issues": True,
        }
    return {
        "quality_gate": "OK", "duplication_on_new_code": "0.0",
        "security_hotspots": 0, "new_bugs": 0,
        "new_vulnerabilities": 0, "new_code_smells": 0,
        "has_blocker_issues": False,
    }


# ─── PR body analysis helpers (no regex — Security Hotspot fix) ─

def _extract_table_value(body: str, key: str) -> str:
    for line in body.split("\n"):
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.split("|")]
        for i, cell in enumerate(cells):
            if cell.strip("*").strip() == key and i + 1 < len(cells):
                return cells[i + 1].strip("*").strip()
    return ""


def _has_section(body: str, title: str) -> bool:
    for line in body.split("\n"):
        if line.strip().startswith("#") and title.lower() in line.lower():
            return True
    return False


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
    if not val:
        return None
    for word in val.split():
        w = word.rstrip(",")
        if w.isdigit():
            return int(w)
    return None


def _extract_number(text: str) -> int | None:
    for word in text.split():
        w = word.rstrip(",")
        if w.isdigit():
            return int(w)
    return None


def _has_suspicious_phrase(body: str) -> list[str]:
    phrases = ["测试除外", "monkeypatch 除外", "skip 未说明"]
    return [p for p in phrases if p in body]


def _has_frontend_changes(files: list[str]) -> bool:
    fe_exts = (".vue", ".tsx", ".jsx", ".css", ".scss", ".less")
    return any(f.startswith("frontend/") or f.endswith(fe_exts) for f in files)


def _body_mentions_playwright(body: str) -> bool:
    return "playwright" in body.lower() or "e2e" in body.lower()


def _reported_failed(value: str) -> bool:
    return any(w in value.lower() for w in ("failed", "fail", "error"))


def _reported_passed(value: str) -> bool:
    return "passed" in value.lower() or "pass" in value.lower()


def _count_mismatch_blocker(actual: int, reported: int) -> bool:
    return abs(actual - reported) > 2


# ─── Main service ────────────────────────────────────────────

def generate_review_packet_preview(
    repo: str,
    pr_number: int,
    reported_head: str = "",
    reported_pytest: str = "",
    reported_compileall: str = "",
    reported_npm_build: str = "",
    reported_playwright: str = "",
    reported_changed_file_count: int | None = None,
) -> ReviewPacketPreviewResponse:
    pr = _mock_github_pr(repo, pr_number)
    sonar = _mock_sonar_result(pr_number)

    body = pr["body"]
    files = pr["changed_files"]
    actual_count = len(files)

    # Extract body values
    body_pytest_val = _extract_table_value(body, "pytest")
    body_pytest_num = _extract_pytest_count(body)
    body_compileall = _extract_table_value(body, "compileall")
    body_npm_build = _extract_table_value(body, "npm build")
    body_pw = _extract_table_value(body, "Playwright")
    body_sonar_val = _extract_table_value(body, "SonarCloud Quality Gate")
    if not body_sonar_val:
        body_sonar_val = _extract_table_value(body, "SonarCloud")

    # Build packet
    is_frontend = _has_frontend_changes(files)
    is_backend = any(f.startswith("backend/") or f.endswith(".py") for f in files)
    suspicious = _has_suspicious_phrase(body)

    head_matches = True
    if reported_head and reported_head != pr["head"]:
        head_matches = False

    pytest_matches = True
    if reported_pytest and body_pytest_num is not None:
        rn = _extract_number(reported_pytest)
        if rn is not None and rn != body_pytest_num:
            pytest_matches = False

    compileall_matches = True
    if reported_compileall and body_compileall:
        if _reported_passed(reported_compileall) != _reported_passed(body_compileall):
            compileall_matches = False

    npm_build_matches = True
    if reported_npm_build and body_npm_build:
        if _reported_passed(reported_npm_build) != _reported_passed(body_npm_build):
            npm_build_matches = False

    packet = ReviewPacketData(
        repo=repo,
        pr_number=pr_number,
        pr_url=f"https://github.com/{repo}/pull/{pr_number}",
        pr_state=pr["state"],
        merged=pr.get("merged", False),
        head_commit=pr["head"],
        base_commit=pr["base"],
        reported_head=reported_head,
        head_matches=head_matches,
        changed_files=files,
        changed_file_count=actual_count,
        additions=pr.get("additions", 0),
        deletions=pr.get("deletions", 0),
        pr_body=body,
        sonar_comment_found=pr.get("sonar_comment_found", False),
        sonar_quality_gate=sonar["quality_gate"],
        sonar_security_hotspots=sonar["security_hotspots"],
        sonar_new_bugs=sonar.get("new_bugs", 0),
        sonar_new_vulnerabilities=sonar.get("new_vulnerabilities", 0),
        sonar_new_code_smells=sonar.get("new_code_smells", 0),
        sonar_duplication_on_new_code=float(sonar["duplication_on_new_code"]),
        pytest_from_pr_body=body_pytest_val,
        pytest_reported=reported_pytest,
        pytest_matches=pytest_matches,
        compileall_reported=reported_compileall,
        compileall_from_pr_body=body_compileall,
        compileall_matches=compileall_matches,
        npm_build_reported=reported_npm_build,
        npm_build_from_pr_body=body_npm_build,
        npm_build_matches=npm_build_matches,
        playwright_reported=reported_playwright,
        has_frontend_changes=is_frontend,
        has_backend_changes=is_backend,
        has_db_migration=_has_db_migration(body),
        has_github_pr_entry=_has_real_pr_entry(body),
        has_ci_entry=_has_real_ci_entry(body),
        has_deploy_entry=False,
        reported_changed_file_count=reported_changed_file_count,
        suspicious_phrases=suspicious,
    )

    # ─── Run checks ──

    blockers: list[ReviewAction] = []
    warnings: list[ReviewAction] = []

    # 1. Reported head mismatch
    if reported_head and reported_head != pr["head"]:
        blockers.append(ReviewAction(
            action="head_mismatch",
            detail=f"Reported head {reported_head[:12]}... != actual {pr['head'][:12]}...",
        ))

    # 2. Reported pytest != PR body pytest
    if reported_pytest and body_pytest_num is not None:
        rn = _extract_number(reported_pytest)
        if rn is not None and rn != body_pytest_num:
            blockers.append(ReviewAction(
                action="pytest_count_mismatch",
                detail=f"Reported ({reported_pytest}) != PR body ({body_pytest_num} passed)",
            ))

    # 3. Body says '待 CI 报告' but Sonar comment exists
    if _body_has_phrase(body, "待 CI 报告") and pr.get("sonar_comment_found"):
        blockers.append(ReviewAction(
            action="stale_sonar_status",
            detail="PR body says '待 CI 报告' but SonarCloud comment exists",
        ))

    # 4. Body says 'N/A' but Sonar comment exists
    if _body_has_phrase(body, "**N/A**") and pr.get("sonar_comment_found"):
        blockers.append(ReviewAction(
            action="na_sonar_stale",
            detail="PR body says 'N/A' for Sonar but SonarCloud comment exists",
        ))

    # 5. SonarCloud failed
    if sonar["quality_gate"] != "OK":
        blockers.append(ReviewAction(
            action="sonar_failed",
            detail=f"SonarCloud Quality Gate is {sonar['quality_gate']}",
        ))

    # 6. Duplication > 3%
    dup = float(sonar["duplication_on_new_code"])
    if dup > 3.0:
        blockers.append(ReviewAction(
            action="duplication_exceeded",
            detail=f"Duplication on New Code is {dup}% (threshold: ≤3%)",
        ))

    # 7. Security Hotspots > 0
    if sonar["security_hotspots"] > 0:
        blockers.append(ReviewAction(
            action="security_hotspots_found",
            detail=f"{sonar['security_hotspots']} Security Hotspot(s) need review",
        ))

    # 8. New issues
    if sonar.get("has_blocker_issues"):
        blockers.append(ReviewAction(
            action="blocker_issues_found",
            detail="New blocker-type issues found in SonarCloud analysis",
        ))
    if sonar.get("new_code_smells", 0) > 0:
        warnings.append(ReviewAction(
            action="code_smells_found",
            detail=f"{sonar['new_code_smells']} new code smell(s) found (non-blocking)",
        ))

    # 9. Reported compileall failed
    if reported_compileall and _reported_failed(reported_compileall):
        blockers.append(ReviewAction(
            action="compileall_failed",
            detail=f"Reported compileall: {reported_compileall}",
        ))

    # 10. Reported npm build failed
    if reported_npm_build and _reported_failed(reported_npm_build):
        blockers.append(ReviewAction(
            action="npm_build_failed",
            detail=f"Reported npm build: {reported_npm_build}",
        ))

    # 11. Reported Playwright failed
    if reported_playwright and _reported_failed(reported_playwright):
        blockers.append(ReviewAction(
            action="playwright_failed",
            detail=f"Reported Playwright: {reported_playwright}",
        ))

    # 12. Frontend changes but no npm build in PR body
    if is_frontend and not body_npm_build:
        warnings.append(ReviewAction(
            action="frontend_missing_npm_build",
            detail="PR modifies frontend files but body has no npm build result",
        ))

    # 13. Playwright 口径不一致
    body_has_pw = body_pw or _body_mentions_playwright(body)
    if body_has_pw and not reported_playwright:
        warnings.append(ReviewAction(
            action="playwright_not_reported",
            detail="PR body mentions Playwright/e2e but no reported Playwright result",
        ))

    # 14. compileall body vs reported mismatch
    if reported_compileall and body_compileall and not compileall_matches:
        warnings.append(ReviewAction(
            action="compileall_body_mismatch",
            detail=f"Reported ({reported_compileall}) != body ({body_compileall})",
        ))

    # 15. npm build body vs reported mismatch
    if reported_npm_build and body_npm_build and not npm_build_matches:
        warnings.append(ReviewAction(
            action="npm_build_body_mismatch",
            detail=f"Reported ({reported_npm_build}) != body ({body_npm_build})",
        ))

    # 16. Changed file count mismatch
    if reported_changed_file_count is not None and reported_changed_file_count != actual_count:
        diff = abs(actual_count - reported_changed_file_count)
        act = ReviewAction(
            action="changed_file_count_mismatch",
            detail=f"Reported {reported_changed_file_count} files, actual {actual_count} (diff={diff})",
        )
        if _count_mismatch_blocker(actual_count, reported_changed_file_count):
            blockers.append(act)
        else:
            warnings.append(act)

    # 17. Suspicious phrases
    if suspicious:
        blockers.append(ReviewAction(
            action="suspicious_phrase",
            detail="Body contains: " + ", ".join(suspicious),
        ))

    # 18. Real PR/CI/Sonar/Deploy entry unreported
    if packet.has_github_pr_entry:
        blockers.append(ReviewAction(
            action="unreported_pr_entry",
            detail="PR body reports new Real GitHub PR but security boundary says no",
        ))
    if packet.has_ci_entry:
        blockers.append(ReviewAction(
            action="unreported_ci_entry",
            detail="PR body reports new Real CI entry but security boundary says no",
        ))

    # 19. PR already merged
    if pr.get("merged"):
        warnings.append(ReviewAction(
            action="already_merged",
            detail=f"PR #{pr_number} has already been merged",
        ))

    # 20. Missing safety boundary section
    if not _has_section(body, "Security Boundary"):
        warnings.append(ReviewAction(
            action="missing_safety_boundary",
            detail="PR body is missing the Security Boundary section",
        ))

    # 21. Missing Sonar results
    if not body_sonar_val:
        warnings.append(ReviewAction(
            action="missing_sonar_results",
            detail="PR body does not mention SonarCloud results",
        ))

    # 22. Short head hash
    if len(pr["head"]) < 10:
        warnings.append(ReviewAction(
            action="short_head_hash",
            detail=f"Head commit hash too short ({len(pr['head'])} chars); use full SHA",
        ))

    # Build required actions
    required_actions = [
        ReviewAction(action=b.action, detail=f"Fix: {b.detail}")
        for b in blockers
    ]

    # Determine review_status
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

    decision = ReviewPacketDecision(
        review_status=review_status,
        merge_allowed=merge_allowed,
        blockers=blockers,
        warnings=warnings,
        required_actions=required_actions,
        summary=" ".join(summary_parts),
    )

    return ReviewPacketPreviewResponse(packet=packet, decision=decision)

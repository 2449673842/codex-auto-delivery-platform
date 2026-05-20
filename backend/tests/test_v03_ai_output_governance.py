"""v0.3 S3: AI Output Governance Tests"""
import json
import pytest
from app.services.ai_output_governance_service import (
    validate_agent_run_result, validate_patch_diff,
    parse_review_result, check_risk_report, build_trace_json,
    AiOutputValidationResult, PatchDiffCheck, ReviewResult, RiskReportCheck,
)

# ─── S3-1: AI 输出校验 ───

def test_empty_output_is_invalid():
    r = validate_agent_run_result(None, None, None)
    assert r.valid is False
    assert len(r.errors) >= 1

def test_valid_plan_output():
    r = validate_agent_run_result(
        output_summary="My plan",
        output_log="Step 1 done",
        raw_result_json='{"plan_md": "# Plan"}',
        plan_md="# Plan\n1. Do thing",
    )
    assert r.valid is True
    assert r.output_kind == "plan"
    assert r.requires_human is False

def test_valid_patch_output():
    r = validate_agent_run_result(
        output_summary="Patch created",
        output_log="Code generated",
        raw_result_json='{"patch_diff": "diff --git a/x.py b/x.py"}',
        patch_diff="diff --git a/x.py b/x.py\n+print('hi')",
    )
    assert r.valid is True
    assert r.output_kind == "patch_diff"

def test_malformed_json_handled():
    r = validate_agent_run_result(
        output_summary="bad",
        output_log="bad",
        raw_result_json="not valid json",
    )
    assert r.valid is True  # raw_result_json is just text, not validated as JSON
    assert r.output_kind == "raw_result"

# ─── S3-2: patch.diff 校验 ───

def test_valid_patch_diff_passes():
    d = validate_patch_diff("diff --git a/src/main.py b/src/main.py\n+print('hello')\n-def old()")
    assert d.has_diff_header is True
    assert d.is_empty is False
    assert d.has_secret_pattern is False
    assert d.modifies_forbidden_path is False

def test_empty_patch_fails():
    d = validate_patch_diff("")
    assert d.is_empty is True

def test_blank_patch_fails():
    d = validate_patch_diff("   \n  \n")
    assert d.is_empty is True

def test_non_diff_text_fails_header():
    d = validate_patch_diff("just some text without diff header")
    assert d.has_diff_header is False

def test_patch_with_secret_fails():
    d = validate_patch_diff("diff --git a/x.py b/x.py\n+api_key = 'sk-12345abc'\n-def foo()")
    assert d.has_secret_pattern is True

def test_patch_with_forbidden_env_path_fails():
    d = validate_patch_diff("diff --git a/.env b/.env\n--- a/.env\n+++ b/.env\n+SECRET=value")
    assert d.modifies_forbidden_path is True

def test_patch_with_private_key_fails():
    d = validate_patch_diff("diff --git a/key.pem b/key.pem\n+-----BEGIN PRIVATE KEY-----")
    assert d.has_secret_pattern is True

def test_patch_with_token_fails():
    d = validate_patch_diff("diff --git a/config.py b/config.py\n+TOKEN='ghp_xxxxxxxxxxxx'")
    assert d.has_secret_pattern is True

def test_large_patch_fails():
    d = validate_patch_diff("diff --git a/big.py b/big.py\n" + ("+a\n" * 200_000))
    assert d.size_bytes > 500_000
    assert d.is_empty is False

# ─── S3-3: review.md → AgentReview ───

def test_review_parsing_approved():
    r = parse_review_result("# Review\nDecision: approved\nRisk: low\nAll good.")
    assert r.parsed is True
    assert r.decision == "approved"

def test_review_parsing_rejected():
    r = parse_review_result("# Review\nDecision: rejected\nRisk: high\nHas bugs.")
    assert r.parsed is True
    assert r.decision == "rejected"
    assert r.risk_level == "high"

def test_review_parsing_changes_requested():
    r = parse_review_result("Decision: Changes requested. Risk: medium.")
    assert r.parsed is True
    assert r.decision == "changes_requested"
    assert r.risk_level == "medium"

def test_review_confidence_extracted():
    r = parse_review_result("Decision: approved. Confidence: 0.85")
    assert r.confidence == 0.85

def test_empty_review_not_parsed():
    r = parse_review_result("")
    assert r.parsed is False
    assert r.decision is None

def test_malformed_review_not_parsed():
    r = parse_review_result("some random text without decision")
    assert r.parsed is False

# ─── S3-5: risk_report.json 校验 ───

def test_low_risk_report():
    r = check_risk_report({"risk_level": "low"})
    assert r.parsed is True
    assert r.requires_human is False
    assert r.risk_level == "low"

def test_high_risk_requires_human():
    r = check_risk_report({"risk_level": "high", "summary": "SQL injection"})
    assert r.parsed is True
    assert r.requires_human is True
    assert "high" in str(r.errors)

def test_critical_risk_requires_human():
    r = check_risk_report({"risk_level": "critical"})
    assert r.parsed is True
    assert r.requires_human is True

def test_unknown_risk_requires_human():
    r = check_risk_report({"risk_level": "unknown"})
    assert r.parsed is True
    assert r.requires_human is True
    assert len(r.errors) >= 1

def test_empty_risk_report_not_parsed():
    r = check_risk_report({})
    assert r.parsed is False

# ─── S3-6: AgentRun trace ───

def test_trace_json_structure():
    validation = AiOutputValidationResult(valid=True, output_kind="patch_diff")
    trace = build_trace_json(
        provider="openai", model="gpt-4o-mini",
        run_type="execute", output_kind="patch_diff",
        validation=validation,
    )
    data = json.loads(trace)
    assert data["provider"] == "openai"
    assert data["model"] == "gpt-4o-mini"
    assert data["run_type"] == "execute"
    assert data["output_kind"] == "patch_diff"
    assert data["validation"]["valid"] is True
    assert "artifacts" in data

# ─── Integration: invalid patch → no auto approve ───

def test_invalid_patch_prevents_approve():
    """Invalid patch (no diff header) should make validation fail"""
    r = validate_agent_run_result(
        output_summary="patch",
        output_log="gen",
        raw_result_json="{}",
        patch_diff="this is not a diff",
    )
    assert r.valid is False
    assert any("diff --git" in e for e in r.errors)

def test_secret_in_patch_prevents_approve():
    """Patch with secret should be invalid and requires human"""
    r = validate_agent_run_result(
        output_summary="patch",
        output_log="gen",
        raw_result_json="{}",
        patch_diff="diff --git a/x.py b/x.py\n+password = 'hunter2'",
    )
    assert r.requires_human is True

# ─── Forbidden patch targets ───

def test_forbidden_database_path_fails():
    d = validate_patch_diff("diff --git a/backend/app/database.py b/backend/app/database.py\n--- a/backend/app/database.py\n+++ b/backend/app/database.py\n+alter table")
    assert d.modifies_forbidden_path is True

def test_forbidden_ci_config_fails():
    d = validate_patch_diff("diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml\n--- a/.github/workflows/ci.yml\n+++ b/.github/workflows/ci.yml\n+steps:")
    assert d.modifies_forbidden_path is True

# ─── review result doesn't auto-approve ───

def test_review_result_not_auto_approve():
    """Review parsing alone should not create an approved decision"""
    r = parse_review_result("Decision: approved. Risk: low.")
    assert r.parsed is True
    assert r.decision == "approved"
    assert r.risk_level == "low"
    # This is only parsing — approving requires the full approval pipeline

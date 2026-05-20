"""v0.3 S3: AI Output Governance Tests"""
import json
import pytest
from app.services.ai_output_governance_service import (
    validate_agent_run_result, validate_patch_diff,
    parse_review_result, check_risk_report, build_trace_json,
    AiOutputValidationResult, redact_secrets,
)

# ─── S3-1: AI 输出校验 ───

def test_empty_output_is_invalid():
    r = validate_agent_run_result(None, None, None)
    assert r.valid is False
    assert len(r.errors) >= 1

def test_valid_plan_output():
    r = validate_agent_run_result(
        output_summary="My plan", output_log="Step 1 done",
        raw_result_json='{"plan_md": "# Plan"}',
        plan_md="# Plan\n1. Do thing",
    )
    assert r.valid is True
    assert r.output_kind == "plan"
    assert r.requires_human is False

def test_valid_patch_output():
    r = validate_agent_run_result(
        output_summary="Patch", output_log="done",
        raw_result_json='{"patch_diff": "diff --git a/x.py b/x.py"}',
        patch_diff="diff --git a/x.py b/x.py\n+print('hi')",
    )
    assert r.valid is True
    assert r.output_kind == "patch_diff"

def test_malformed_json_is_invalid():
    r = validate_agent_run_result(
        output_summary="bad", output_log="bad",
        raw_result_json="not valid json",
    )
    assert r.valid is False
    assert r.requires_human is True
    assert any("not valid JSON" in e for e in r.errors)

# ─── S3-2: patch.diff 校验 (fnmatch) ───

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

def test_patch_with_private_key_fails():
    d = validate_patch_diff("diff --git a/x.py b/x.py\n+-----BEGIN PRIVATE KEY-----")
    assert d.has_secret_pattern is True

def test_patch_with_token_fails():
    d = validate_patch_diff("diff --git a/config.py b/config.py\n+TOKEN='ghp_xxxxxxxxxxxx'")
    assert d.has_secret_pattern is True

def test_large_patch_detected():
    d = validate_patch_diff("diff --git a/big.py b/big.py\n" + ("+a\n" * 200_000))
    assert d.size_bytes > 500_000
    assert d.is_empty is False

# ─── fnmatch forbidden path matching ───

def test_forbidden_env_path_fails():
    d = validate_patch_diff("diff --git a/.env b/.env\n--- a/.env\n+++ b/.env\n+SECRET=value")
    assert d.modifies_forbidden_path is True

def test_forbidden_migration_path_fnmatch():
    d = validate_patch_diff("diff --git a/app/migrations/001_init.py b/app/migrations/001_init.py\n--- a/app/migrations/001_init.py\n+++ b/app/migrations/001_init.py")
    assert d.modifies_forbidden_path is True, f"paths: {d.forbidden_paths}"

def test_forbidden_pem_path_fnmatch():
    d = validate_patch_diff("diff --git a/certs/priv.pem b/certs/priv.pem")
    assert d.modifies_forbidden_path is True

def test_forbidden_key_path_fnmatch():
    d = validate_patch_diff("diff --git a/ssh/id_rsa b/ssh/id_rsa")
    assert d.modifies_forbidden_path is True

def test_safe_path_not_blocked():
    d = validate_patch_diff("diff --git a/src/main.py b/src/main.py")
    assert d.modifies_forbidden_path is False

# ─── S3-3: review.md parsing ───

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

# ─── S3-5: risk_report 校验 ───

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

# ─── S3-5 integration: risk → human_required ───

def test_low_risk_valid():
    r = validate_agent_run_result(
        output_summary="ok", output_log="ok", raw_result_json="{}",
        risk_report={"risk_level": "low"},
    )
    assert r.valid is True

def test_high_risk_integration():
    r = validate_agent_run_result(
        output_summary="ok", output_log="ok", raw_result_json="{}",
        risk_report={"risk_level": "high"},
    )
    assert r.requires_human is True

def test_critical_risk_integration():
    r = validate_agent_run_result(
        output_summary="ok", output_log="ok", raw_result_json="{}",
        risk_report={"risk_level": "critical"},
    )
    assert r.requires_human is True

def test_malformed_risk_integration():
    r = validate_agent_run_result(
        output_summary="ok", output_log="ok", raw_result_json="{}",
        risk_report={"risk_level": "unknown"},
    )
    assert r.requires_human is True

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

# ─── Integration: invalid patch → prevent auto approve ───

def test_invalid_patch_prevents_approve():
    r = validate_agent_run_result(
        output_summary="patch", output_log="gen",
        raw_result_json="{}", patch_diff="this is not a diff",
    )
    assert r.valid is False
    assert any("diff --git" in e for e in r.errors)

def test_secret_in_patch_prevents_approve():
    r = validate_agent_run_result(
        output_summary="patch", output_log="gen",
        raw_result_json="{}",
        patch_diff="diff --git a/x.py b/x.py\n+password = 'hunter2'",
    )
    assert r.requires_human is True

def test_forbidden_database_path_fails():
    d = validate_patch_diff("diff --git a/backend/app/database.py b/backend/app/database.py\n--- a/backend/app/database.py\n+++ b/backend/app/database.py\n+alter table")
    assert d.modifies_forbidden_path is True

def test_forbidden_ci_config_fails():
    d = validate_patch_diff("diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml\n--- a/.github/workflows/ci.yml\n+++ b/.github/workflows/ci.yml\n+steps:")
    assert d.modifies_forbidden_path is True

# ─── review result doesn't auto-approve ───

def test_review_result_not_auto_approve():
    r = parse_review_result("Decision: approved. Risk: low.")
    assert r.parsed is True
    assert r.decision == "approved"
    assert r.risk_level == "low"

# ─── Secret redaction ───

def test_redact_sk_pattern():
    text = "key = 'sk-abcdefghijklmnopqrstuvwxyz1234567890'"
    out = redact_secrets(text)
    assert "***REDACTED***" in out
    assert "abcdefghijklmnopqrstuvwxyz" not in out

def test_redact_ghp_pattern():
    text = "token = 'ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890abc'"
    out = redact_secrets(text)
    assert "***REDACTED***" in out
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in out

def test_redact_gho_pattern():
    text = "token = 'gho_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890abc'"
    out = redact_secrets(text)
    assert "***REDACTED***" in out

def test_redact_ghu_pattern():
    text = "token = 'ghu_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890abc'"
    out = redact_secrets(text)
    assert "***REDACTED***" in out

def test_redact_ghs_pattern():
    text = "token = 'ghs_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890abc'"
    out = redact_secrets(text)
    assert "***REDACTED***" in out

def test_redact_akia_pattern():
    text = "key = 'AKIAIOSFODNN7EXAMPLE'"
    out = redact_secrets(text)
    assert "***REDACTED***" in out
    assert "IOSFODNN7EXAMPLE" not in out

def test_redact_private_key_block():
    text = "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFA\n-----END PRIVATE KEY-----"
    out = redact_secrets(text)
    assert "***REDACTED***" in out
    assert "MIIEvQIBADANBgkqhkiG9w0BAQEFA" not in out

def test_redact_password_pattern():
    text = "password = 'supersecret123'"
    out = redact_secrets(text)
    assert "***REDACTED***" in out
    assert "supersecret123" not in out

def test_redact_token_pattern():
    text = "token = 'mysecrettoken'"
    out = redact_secrets(text)
    assert "***REDACTED***" in out
    assert "mysecrettoken" not in out

def test_redact_api_key_pattern():
    text = "api_key = 'mykey12345'"
    out = redact_secrets(text)
    assert "***REDACTED***" in out
    assert "mykey12345" not in out

def test_redact_no_false_positive():
    text = "This is a normal text with no secrets"
    out = redact_secrets(text)
    assert out == text

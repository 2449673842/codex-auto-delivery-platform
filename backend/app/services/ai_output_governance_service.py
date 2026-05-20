from pydantic import BaseModel, Field
from typing import Any


class AiOutputValidationResult(BaseModel):
    valid: bool
    output_kind: str | None = None
    risk_level: str | None = None
    requires_human: bool = False
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PatchDiffCheck(BaseModel):
    has_diff_header: bool = False
    is_empty: bool = True
    size_bytes: int = 0
    has_secret_pattern: bool = False
    modifies_forbidden_path: bool = False
    forbidden_paths: list[str] = Field(default_factory=list)


class ReviewResult(BaseModel):
    decision: str | None = None
    risk_level: str | None = None
    summary: str | None = None
    findings: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float | None = None
    parsed: bool = False


class RiskReportCheck(BaseModel):
    parsed: bool = False
    risk_level: str | None = None
    requires_human: bool = False
    errors: list[str] = Field(default_factory=list)


SECRET_PATTERNS = [
    "sk-", "pk-", "-----BEGIN", "ghp_", "gho_", "ghu_", "ghs_",
    "AKIA", "eyJ", "api_key", "apikey", "password", "PASSWORD",
    "SECRET", "secret", "token", "TOKEN",
]

FORBIDDEN_DIFF_PATHS = [
    ".env", ".env.local", ".env.production",
    "**/config/credentials*", "**/secrets*",
    "**/*.pem", "**/*.key", "**/id_rsa*",
]

MAX_PATCH_SIZE_BYTES = 500_000  # 500KB
FORBIDDEN_DIFF_TARGETS = [
    "backend/app/database.py",
    "backend/app/config.py",
    "**/migrations/*",
    "**/ci.yml", "**/ci.yaml",
]


def validate_agent_run_result(
    output_summary: str | None,
    output_log: str | None,
    raw_result_json: str | None,
    plan_md: str | None = None,
    patch_diff: str | None = None,
    review_md: str | None = None,
    risk_report: dict[str, Any] | None = None,
) -> AiOutputValidationResult:
    """Validate AI provider output for governance compliance."""
    errors = []
    warnings = []
    risk_level = "low"
    requires_human = False
    output_kind = None

    # Determine output kind
    if patch_diff:
        output_kind = "patch_diff"
    elif review_md:
        output_kind = "review"
    elif plan_md:
        output_kind = "plan"
    elif raw_result_json:
        output_kind = "raw_result"

    # 1. Check for empty output
    has_content = bool(
        (output_summary or "").strip()
        or (output_log or "").strip()
        or (raw_result_json or "").strip()
        or (plan_md or "").strip()
        or (patch_diff or "").strip()
        or (review_md or "").strip()
        or risk_report
    )
    if not has_content:
        errors.append("Output is empty")

    # 2. Validate patch.diff if present
    if patch_diff:
        diff_validation = validate_patch_diff(patch_diff)
        if not diff_validation.has_diff_header:
            errors.append("patch.diff missing diff --git header")
        if diff_validation.is_empty:
            errors.append("patch.diff is empty")
        if diff_validation.size_bytes > MAX_PATCH_SIZE_BYTES:
            errors.append(f"patch.diff exceeds {MAX_PATCH_SIZE_BYTES} bytes")
            requires_human = True
        if diff_validation.has_secret_pattern:
            errors.append("patch.diff contains potential secret pattern")
            requires_human = True
            risk_level = "high"
        if diff_validation.modifies_forbidden_path:
            errors.append("patch.diff modifies forbidden path")
            requires_human = True
            risk_level = "high"

    # 3. Check raw_result_json size
    if raw_result_json and len(raw_result_json) > MAX_PATCH_SIZE_BYTES:
        errors.append("raw_result_json exceeds size limit")
        requires_human = True

    # 4. Check risk_report if present
    if risk_report:
        risk_check = check_risk_report(risk_report)
        if not risk_check.parsed:
            warnings.append("risk_report could not be parsed")
            requires_human = True
        if risk_check.risk_level in ("high", "critical"):
            requires_human = True
            risk_level = risk_check.risk_level
        if risk_check.requires_human:
            requires_human = True

    # 5. Determine final risk level
    if requires_human and risk_level == "low":
        risk_level = "medium"

    return AiOutputValidationResult(
        valid=len(errors) == 0,
        output_kind=output_kind,
        risk_level=risk_level,
        requires_human=requires_human,
        errors=errors,
        warnings=warnings,
    )


def validate_patch_diff(patch_diff: str) -> PatchDiffCheck:
    """Validate a patch.diff string for governance rules."""
    if not patch_diff or not patch_diff.strip():
        return PatchDiffCheck(is_empty=True)

    check = PatchDiffCheck(
        has_diff_header="diff --git" in patch_diff,
        is_empty=False,
        size_bytes=len(patch_diff.encode("utf-8")),
    )

    # Check secret patterns in diff content
    for pattern in SECRET_PATTERNS:
        for line in patch_diff.split("\n"):
            if line.startswith("+") and pattern.lower() in line.lower():
                check.has_secret_pattern = True
                break
        if check.has_secret_pattern:
            break

    # Check forbidden paths
    for line in patch_diff.split("\n"):
        if line.startswith("+++") or line.startswith("---"):
            for forbidden in FORBIDDEN_DIFF_PATHS:
                if forbidden.replace("**/", "") in line:
                    check.modifies_forbidden_path = True
                    check.forbidden_paths.append(forbidden)
                    break

    # Check forbidden targets
    for line in patch_diff.split("\n"):
        if line.startswith("+++") or line.startswith("---"):
            for target in FORBIDDEN_DIFF_TARGETS:
                if target.replace("**/", "") in line:
                    check.modifies_forbidden_path = True
                    check.forbidden_paths.append(target)
                    break

    return check


def parse_review_result(review_md: str) -> ReviewResult:
    """Parse review.md and extract structured review data."""
    result = ReviewResult()
    if not review_md or not review_md.strip():
        return result

    lower = review_md.lower()

    # Extract decision
    for keyword in ["approved", "rejected", "changes_requested", "changes requested"]:
        if keyword in lower:
            result.decision = keyword.replace(" ", "_")
            break

    # Extract risk level
    for level in ["critical", "high", "medium", "low"]:
        if f"risk" in lower and level in lower:
            result.risk_level = level
            break

    result.parsed = result.decision is not None

    # Mark confidence if found
    import re as _re
    conf_match = _re.search(r"confidence[:\s]*([0-9.]+)", lower)
    if conf_match:
        try:
            result.confidence = float(conf_match.group(1))
        except ValueError:
            pass

    result.summary = review_md[:200].replace("\n", " ") if review_md else None
    return result


def check_risk_report(risk_report: dict) -> RiskReportCheck:
    """Validate risk_report.json content."""
    result = RiskReportCheck()
    if not risk_report:
        return result

    result.parsed = True
    result.risk_level = risk_report.get("risk_level", "unknown")

    if result.risk_level in ("high", "critical"):
        result.requires_human = True
        result.errors.append(f"Risk level is {result.risk_level}")

    if result.risk_level not in ("low", "medium", "high", "critical"):
        result.errors.append(f"Unknown risk level: {result.risk_level}")
        result.requires_human = True

    return result


def build_trace_json(
    provider: str,
    model: str | None,
    run_type: str,
    output_kind: str | None,
    validation: AiOutputValidationResult,
) -> str:
    """Build standardized AgentRun raw_result_json trace."""
    import json
    trace = {
        "provider": provider,
        "model": model or "unknown",
        "run_type": run_type,
        "output_kind": output_kind,
        "validation": {
            "valid": validation.valid,
            "warnings": validation.warnings,
            "errors": validation.errors,
        },
        "artifacts": [],
    }
    return json.dumps(trace, ensure_ascii=False)

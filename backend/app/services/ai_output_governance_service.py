import json
import fnmatch
import re
from pydantic import BaseModel, Field
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession


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

MAX_PATCH_SIZE_BYTES = 500_000
FORBIDDEN_DIFF_TARGETS = [
    "**/database.py", "**/config.py",
    "**/migrations/*",
    "**/ci.yml", "**/ci.yaml",
]


def _extract_diff_path(line: str) -> str | None:
    """Extract the file path from a diff line (+++, ---, or diff --git)."""
    line = line.strip()
    if line.startswith("diff --git"):
        parts = line.split()
        if len(parts) >= 3:
            return parts[2][2:]
    elif line.startswith("--- ") or line.startswith("+++ "):
        path = line[4:].strip()
        if path.startswith("a/") or path.startswith("b/"):
            path = path[2:]
        if path == "/dev/null":
            return None
        return path
    return None


def _matches_forbidden(path: str | None) -> bool:
    """Check if a path matches any forbidden pattern using fnmatch."""
    if not path:
        return False
    for pattern in FORBIDDEN_DIFF_PATHS + FORBIDDEN_DIFF_TARGETS:
        if fnmatch.fnmatch(path, pattern):
            return True
    return False


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

    if patch_diff:
        output_kind = "patch_diff"
    elif review_md:
        output_kind = "review"
    elif plan_md:
        output_kind = "plan"
    elif raw_result_json:
        output_kind = "raw_result"

    if not any([
        (output_summary or "").strip(),
        (output_log or "").strip(),
        (raw_result_json or "").strip(),
        (plan_md or "").strip(),
        (patch_diff or "").strip(),
        (review_md or "").strip(),
        risk_report,
    ]):
        errors.append("Output is empty")

    # raw_result_json must be valid JSON
    if raw_result_json and raw_result_json.strip():
        try:
            json.loads(raw_result_json)
        except (json.JSONDecodeError, ValueError):
            errors.append("raw_result_json is not valid JSON")
            requires_human = True
            risk_level = "high"

    if raw_result_json and len(raw_result_json) > MAX_PATCH_SIZE_BYTES:
        errors.append("raw_result_json exceeds size limit")
        requires_human = True

    if patch_diff:
        dv = validate_patch_diff(patch_diff)
        if not dv.has_diff_header:
            errors.append("patch.diff missing diff --git header")
        if dv.is_empty:
            errors.append("patch.diff is empty")
        if dv.size_bytes > MAX_PATCH_SIZE_BYTES:
            errors.append(f"patch.diff exceeds {MAX_PATCH_SIZE_BYTES} bytes")
            requires_human = True
        if dv.has_secret_pattern:
            warnings.append("patch.diff contains potential secret pattern")
            requires_human = True
            risk_level = "high"
        if dv.modifies_forbidden_path:
            warnings.append("patch.diff modifies forbidden path")
            requires_human = True
            risk_level = "high"

    if risk_report:
        rc = check_risk_report(risk_report)
        if not rc.parsed:
            errors.append("risk_report could not be parsed")
            requires_human = True
        if rc.risk_level in ("high", "critical"):
            requires_human = True
            risk_level = rc.risk_level
        if rc.requires_human:
            requires_human = True

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
    """Validate a patch.diff string for governance rules using fnmatch."""
    if not patch_diff or not patch_diff.strip():
        return PatchDiffCheck(is_empty=True)

    check = PatchDiffCheck(
        has_diff_header="diff --git" in patch_diff,
        is_empty=False,
        size_bytes=len(patch_diff.encode("utf-8")),
    )

    for line in patch_diff.split("\n"):
        if line.startswith("+"):
            for pattern in SECRET_PATTERNS:
                if pattern.lower() in line.lower():
                    check.has_secret_pattern = True
                    break
        if check.has_secret_pattern:
            break

    for line in patch_diff.split("\n"):
        path = _extract_diff_path(line)
        if path and _matches_forbidden(path):
            check.modifies_forbidden_path = True
            check.forbidden_paths.append(path)

    return check


def parse_review_result(review_md: str) -> ReviewResult:
    """Parse review.md and extract structured review data."""
    result = ReviewResult()
    if not review_md or not review_md.strip():
        return result

    lower = review_md.lower()
    for keyword in ["approved", "rejected", "changes_requested", "changes requested"]:
        if keyword in lower:
            result.decision = keyword.replace(" ", "_")
            break

    for level in ["critical", "high", "medium", "low"]:
        if "risk" in lower and level in lower:
            result.risk_level = level
            break

    result.parsed = result.decision is not None
    conf_match = re.search(r"confidence[:\s]*([0-9.]+)", lower)
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


SECRET_REDACT_PATTERNS: list[tuple[str, str]] = [
    (r'(sk-)[A-Za-z0-9]{20,}', r'\1***REDACTED***'),
    (r'(ghp_|gho_|ghu_|ghs_)[A-Za-z0-9]{20,}', r'\1***REDACTED***'),
    (r'(AKIA)[A-Z0-9]{16,}', r'\1***REDACTED***'),
    (r'-----BEGIN\s*PRIVATE\s*KEY-----.*?-----END\s*PRIVATE\s*KEY-----', '-----BEGIN PRIVATE KEY-----***REDACTED***-----END PRIVATE KEY-----'),
    (r'password\s*=\s*\S+', 'password=***REDACTED***'),
    (r'token\s*=\s*\S+', 'token=***REDACTED***'),
    (r'api_key\s*=\s*\S+', 'api_key=***REDACTED***'),
]


def redact_secrets(text: str) -> str:
    """Redact known secret patterns from text."""
    import re
    for i, (pat, repl) in enumerate(SECRET_REDACT_PATTERNS):
        flags = re.IGNORECASE
        if i == 3:
            flags |= re.DOTALL
        text = re.sub(pat, repl, text, flags=flags)
    return text


def build_trace_json(
    provider: str, model: str | None, run_type: str,
    output_kind: str | None, validation: AiOutputValidationResult,
) -> str:
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


async def create_agent_review_from_ai_output(
    db: AsyncSession, task_id: int, agent_id: int, run_id: int,
    review_result: ReviewResult, actor: str = "system",
) -> Any:
    """Create AgentReview from AI review output. Does NOT approve the task."""
    from app.models.agent_review import AgentReview
    from app.services.event_service import create_event

    review = AgentReview(
        task_id=task_id,
        agent_id=agent_id,
        agent_run_id=run_id,
        decision=review_result.decision or "unknown",
        risk_level=review_result.risk_level or "medium",
        confidence_score=review_result.confidence,
        comments=review_result.summary or "AI-generated review",
        issues_json=json.dumps(review_result.findings, ensure_ascii=False) if review_result.findings else None,
    )
    db.add(review)
    await db.flush()
    await db.refresh(review)

    await create_event(
        db, task_id=task_id, event_type="agent_review_submitted",
        actor=actor,
        message=f"AI review #{review.id} recorded (decision={review_result.decision}, risk={review_result.risk_level})",
    )
    return review

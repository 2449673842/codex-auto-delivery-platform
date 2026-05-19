import re
from typing import Any


HIGH_RISK_KEYWORDS = [
    r"\bmodel\b", r"\bmigration\b", r"\bALTER TABLE\b", r"\bCREATE TABLE\b",
    r"\bauth\b", r"\blogin\b", r"\bpermission\b", r"\btoken\b", r"\bsecret\b", r"\bapi.?key\b",
    r"\bdeploy\b", r"\bDockerfile\b", r"docker-compose", r"\bk8s\b", r"Jenkinsfile",
    r"\bCI\b", r"\bcd\.ya?ml\b", r"workflows"
]

CRITICAL_KEYWORDS = [
    r"\bproduction\b", r"\bprod\b", r"\bmain\b", r"\bmerge\b",
    r"\bpayment\b", r"\btrade\b", r"\bfund\b", r"\bmoney\b", r"\border\b",
    r"subprocess", r"os\.system", r"os\.popen", r"shutil\.run",
    r"Project\.root_path", r"os\.path\.exists", r"os\.scandir", r"os\.listdir"
]


def assess_risk(
    diff: str | None = None,
    raw_result_json: str | None = None,
    confidence_score: float | None = None,
    tests_passed: bool | None = None,
    sonar_passed: bool | None = None,
    security_issues_found: bool | None = None,
    changed_files: str | None = None,
) -> dict[str, Any]:
    """启发式风险评估。返回 risk_level, risk_reasons, human_required"""
    content = (diff or "") + "\n" + (changed_files or "")
    reasons: list[str] = []
    human_required = False
    risk_level = "low"

    for kw in CRITICAL_KEYWORDS:
        if re.search(kw, content, re.IGNORECASE):
            risk_level = "critical"
            reasons.append(f"Critical: matches '{kw}'")
            human_required = True
            break

    if risk_level != "critical":
        for kw in HIGH_RISK_KEYWORDS:
            if re.search(kw, content, re.IGNORECASE):
                risk_level = "high"
                reasons.append(f"High risk: matches '{kw}'")
                human_required = True
                break

    if confidence_score is not None and confidence_score < 0.8:
        if risk_level == "low":
            risk_level = "medium"
        reasons.append(f"Low confidence: {confidence_score}")
        human_required = True

    if tests_passed is False:
        if risk_level == "low":
            risk_level = "high"
        reasons.append("Tests failed")
        human_required = True
    elif tests_passed is None:
        human_required = True
        reasons.append("Test results missing")

    if security_issues_found is True:
        if risk_level == "low":
            risk_level = "medium"
        reasons.append("Security issues found")
        human_required = True

    if sonar_passed is False:
        if risk_level == "low":
            risk_level = "medium"
        reasons.append("Sonar check failed")
        human_required = True

    if risk_level == "low" and not reasons:
        if diff and len(diff) > 500:
            risk_level = "medium"
            reasons.append("Large diff needs review")

    if raw_result_json is not None:
        try:
            import json
            if isinstance(raw_result_json, str):
                json.loads(raw_result_json)
        except (json.JSONDecodeError, TypeError):
            risk_level = "medium"
            reasons.append("raw_result_json parse failed")
            human_required = True

    return {
        "risk_level": risk_level,
        "risk_reasons": reasons if reasons else ["No risk detected"],
        "human_required": human_required,
        "security_issues_found": security_issues_found is True,
        "tests_passed": tests_passed,
        "sonar_passed": sonar_passed,
    }

import hashlib
import math

from fastapi import HTTPException

from app.schemas.ai_context_packet import VALID_MODES
from app.schemas.prompt_template import (
    PromptOutputContract,
    PromptTemplatePreviewResponse,
    PromptTokenBudget,
)
from app.schemas.common import ApiEnvelope
from app.services import ai_context_packet_service


_GLOBAL_PROHIBITED = [
    "access Project.root_path",
    "read secret_ref or .env files",
    "execute shell, subprocess, or os.system",
    "create real GitHub PRs",
    "call real CI, Sonar, or Deploy APIs",
    "approve human_required or high/critical risk tasks without authorization",
    "write to the database or create TaskArtifacts/TaskEvents",
]

_MODE_PROHIBITED = {
    "planning": [
        "execute code",
        "include file contents",
    ],
    "patch_generation": [
        "output explanatory text",
        "modify forbidden files",
        "add real external API calls",
    ],
    "review": [
        "auto-approve",
        "merge",
    ],
    "risk": [
        "output text outside JSON",
    ],
    "browser_reviewer": [
        "comment on PRs",
        "merge",
        "approve",
    ],
}

_PREFIX = "Do NOT"

def _build_template(role: str, format_spec: str, *items: str) -> str:
    return (
        f"You are a {role}.\n\n"
        "## Safety Boundaries\n{safety}\n\n"
        "## Prohibited\n{prohibited}\n\n"
        "## Output Requirements\n"
        f"- Format: {format_spec}\n"
        + "\n".join(f"- {item}" for item in items)
    )

_MODE_SYSTEM_TEMPLATES = {
    "planning": _build_template(
        "code planning assistant",
        "plan.md (Markdown)",
        "Include: implementation steps, files to touch, tests to add, risks, safety notes",
    ),
    "patch_generation": _build_template(
        "code generation assistant",
        "patch.diff (unified diff only)",
    ),
    "review": _build_template(
        "code review assistant",
        "review.md (Markdown)",
        "Include: approve/changes_requested, blockers, warnings, required_actions",
        "Include: test quality review, security boundary review",
    ),
    "risk": _build_template(
        "risk assessment assistant",
        "risk_report.json (JSON only)",
        "Include: risk_level, requires_human, reasons",
        "Include: security_findings, scope_findings, test_findings",
    ),
    "browser_reviewer": _build_template(
        "browser review assistant",
        "browser_ai_review.json (JSON only)",
        "advisory_only: true",
        "not_final_approval: true",
        "Include: blockers, warnings, required_actions, confidence",
    ),
}


def _validate_mode(mode: str) -> None:
    if mode not in VALID_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown mode '{mode}'. Valid modes: {', '.join(sorted(VALID_MODES))}",
        )


def _build_system_prompt(mode: str, safety_boundaries: list[str]) -> str:
    template = _MODE_SYSTEM_TEMPLATES.get(
        mode,
        _MODE_SYSTEM_TEMPLATES["planning"],
    )
    safety_text = "\n".join(f"- {b}" for b in safety_boundaries) if safety_boundaries else "- None specified"
    mode_rules = _MODE_PROHIBITED.get(mode, [])
    all_prohibited = _GLOBAL_PROHIBITED + mode_rules
    prohibited_text = "\n".join(f"- {_PREFIX} {p}" for p in all_prohibited)
    return template.format(safety=safety_text, prohibited=prohibited_text)


def _build_user_prompt(
    task_goal: str,
    task_type: str,
    module_name: str,
    context_packet: dict,
) -> str:
    cs = context_packet.get("context_selector", {})
    oc = context_packet.get("output_contract", {})
    tb = context_packet.get("token_budget", {})

    _NONE = "- (none)"
    _NOT_SPECIFIED = "(not specified)"

    matched = cs.get("matched_modules", [])
    matched_lines = [
        f"- {m.get('name', '?')} ({m.get('module_type', '?')})"
        for m in matched
    ]
    matched_summary = "\n".join(matched_lines) if matched else _NONE

    def _fmt(items):
        return "\n".join(f"- {x}" for x in items) if items else _NONE

    return (
        f"## Task Goal\n{task_goal or _NOT_SPECIFIED}\n\n"
        f"## Task Type\n{task_type or _NOT_SPECIFIED}\n\n"
        f"## Module\n{module_name or _NOT_SPECIFIED}\n\n"
        f"## Matched Modules\n{matched_summary}\n\n"
        f"## Recommended Files\n{_fmt(cs.get('recommended_files', []))}\n\n"
        f"## Recommended Tests\n{_fmt(cs.get('recommended_tests', []))}\n\n"
        f"## Recommended APIs\n{_fmt(cs.get('recommended_api', []))}\n\n"
        f"## Safety Notes\n{_fmt(cs.get('safety_notes', []))}\n\n"
        f"## Expected Artifacts\n{_fmt(oc.get('expected_artifacts', []))}\n\n"
        f"## Token Budget Summary\n"
        f"- Estimated context tokens: {tb.get('estimated_context_tokens', 0)}\n"
        f"- Budget status: {tb.get('budget_status', 'ok')}"
    )


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def _build_output_contract(packet_dict: dict) -> PromptOutputContract:
    oc = packet_dict.get("output_contract", {})
    return PromptOutputContract(
        expected_artifacts=list(oc.get("expected_artifacts", [])),
        format=oc.get("format", ""),
    )


def preview(
    task_goal: str = "",
    module_name: str = "",
    task_type: str = "",
    mode: str = "planning",
) -> PromptTemplatePreviewResponse:
    _validate_mode(mode)

    context_packet = ai_context_packet_service.preview(
        task_goal=task_goal,
        module_name=module_name,
        task_type=task_type,
        mode=mode,
    )
    packet_dict = context_packet.model_dump()

    safety_boundaries = packet_dict.get("project_brief", {}).get("safety_boundaries", [])
    system_prompt = _build_system_prompt(mode, safety_boundaries)
    user_prompt = _build_user_prompt(task_goal, task_type, module_name, packet_dict)

    combined = system_prompt + "\n" + user_prompt
    system_hash = _hash_text(system_prompt)
    user_hash = _hash_text(user_prompt)
    prompt_hash = _hash_text(combined)
    estimated = _estimate_tokens(combined)

    template_meta = packet_dict.get("prompt_template", {})
    output_contract = _build_output_contract(packet_dict)

    warnings = list(packet_dict.get("warnings", []))

    total_budget = 32000
    ratio = estimated / total_budget
    budget_status = "ok"
    if ratio >= 1.0:
        budget_status = "over_limit"
        warnings.append("prompt_budget_exceeded")
    elif ratio >= 0.85:
        budget_status = "near_limit"

    context_packet_hash = packet_dict.get("audit", {}).get("context_packet_hash", "")

    return PromptTemplatePreviewResponse(
        template_id=template_meta.get("template_id", ""),
        mode=mode,
        system_prompt_preview=system_prompt,
        user_prompt_preview=user_prompt,
        output_contract=output_contract,
        context_packet_hash=context_packet_hash,
        system_prompt_hash=system_hash,
        user_prompt_hash=user_hash,
        prompt_hash=prompt_hash,
        token_budget=PromptTokenBudget(
            estimated_prompt_tokens=estimated,
            budget_status=budget_status,
        ),
        redaction_applied=True,
        warnings=warnings,
    )

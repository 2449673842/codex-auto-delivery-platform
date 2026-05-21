import hashlib
import math

from fastapi import HTTPException

from app.schemas.ai_context_packet import MODE_ARTIFACTS, PROMPT_TEMPLATES, VALID_MODES
from app.schemas.prompt_template import (
    PromptOutputContract,
    PromptTemplatePreviewResponse,
    PromptTokenBudget,
)
from app.schemas.common import ApiEnvelope
from app.services import ai_context_packet_service


_PROHIBITED = [
    "Do NOT access Project.root_path",
    "Do NOT read secret_ref or .env files",
    "Do NOT execute shell, subprocess, or os.system",
    "Do NOT create real GitHub PRs",
    "Do NOT call real CI, Sonar, or Deploy APIs",
    "Do NOT approve human_required or high/critical risk tasks without authorization",
    "Do NOT write to the database or create TaskArtifacts/TaskEvents",
]

_MODE_SYSTEM_TEMPLATES = {
    "planning": (
        "You are a code planning assistant.\n\n"
        "## Safety Boundaries\n{safety}\n\n"
        "## Prohibited\n{prohibited}\n\n"
        "## Output Requirements\n"
        "- Format: plan.md (Markdown)\n"
        "- Include: implementation steps, files to touch, tests to add, risks, safety notes\n"
        "- Do NOT execute code\n"
        "- Do NOT include file contents"
    ),
    "patch_generation": (
        "You are a code generation assistant.\n\n"
        "## Safety Boundaries\n{safety}\n\n"
        "## Prohibited\n{prohibited}\n\n"
        "## Output Requirements\n"
        "- Format: patch.diff (unified diff only)\n"
        "- Do NOT output explanatory text\n"
        "- Do NOT modify forbidden files\n"
        "- Do NOT add real external API calls"
    ),
    "review": (
        "You are a code review assistant.\n\n"
        "## Safety Boundaries\n{safety}\n\n"
        "## Prohibited\n{prohibited}\n\n"
        "## Output Requirements\n"
        "- Format: review.md (Markdown)\n"
        "- Include: approve/changes_requested, blockers, warnings, required_actions\n"
        "- Include: test quality review, security boundary review\n"
        "- Do NOT auto-approve\n"
        "- Do NOT merge"
    ),
    "risk": (
        "You are a risk assessment assistant.\n\n"
        "## Safety Boundaries\n{safety}\n\n"
        "## Prohibited\n{prohibited}\n\n"
        "## Output Requirements\n"
        "- Format: risk_report.json (JSON only)\n"
        "- Include: risk_level, requires_human, reasons\n"
        "- Include: security_findings, scope_findings, test_findings\n"
        "- Do NOT output text outside JSON"
    ),
    "browser_reviewer": (
        "You are a browser review assistant.\n\n"
        "## Safety Boundaries\n{safety}\n\n"
        "## Prohibited\n{prohibited}\n\n"
        "## Output Requirements\n"
        "- Format: browser_ai_review.json (JSON only)\n"
        "- advisory_only: true\n"
        "- not_final_approval: true\n"
        "- Include: blockers, warnings, required_actions, confidence\n"
        "- Do NOT comment on PRs\n"
        "- Do NOT merge\n"
        "- Do NOT approve"
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
    prohibited_text = "\n".join(f"- {p}" for p in _PROHIBITED)
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

    matched = cs.get("matched_modules", [])
    matched_summary = "\n".join(
        f"- {m.get('name', '?')} ({m.get('module_type', '?')})"
        for m in matched
    ) if matched else "- (none)"

    files = "\n".join(f"- {f}" for f in cs.get("recommended_files", [])) or "- (none)"
    tests = "\n".join(f"- {t}" for t in cs.get("recommended_tests", [])) or "- (none)"
    apis = "\n".join(f"- {a}" for a in cs.get("recommended_api", [])) or "- (none)"
    safety = "\n".join(f"- {s}" for s in cs.get("safety_notes", [])) or "- (none)"
    artifacts = "\n".join(f"- {a}" for a in oc.get("expected_artifacts", [])) or "- (none)"

    return (
        f"## Task Goal\n{task_goal or '(not specified)'}\n\n"
        f"## Task Type\n{task_type or '(not specified)'}\n\n"
        f"## Module\n{module_name or '(not specified)'}\n\n"
        f"## Matched Modules\n{matched_summary}\n\n"
        f"## Recommended Files\n{files}\n\n"
        f"## Recommended Tests\n{tests}\n\n"
        f"## Recommended APIs\n{apis}\n\n"
        f"## Safety Notes\n{safety}\n\n"
        f"## Expected Artifacts\n{artifacts}\n\n"
        f"## Token Budget Summary\n"
        f"- Estimated context tokens: {tb.get('estimated_context_tokens', 0)}\n"
        f"- Budget status: {tb.get('budget_status', 'ok')}"
    )


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def _build_output_contract(mode: str) -> PromptOutputContract:
    artifacts, fmt = MODE_ARTIFACTS.get(mode, ([], ""))
    return PromptOutputContract(expected_artifacts=list(artifacts), format=fmt)


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

    template = PROMPT_TEMPLATES.get(mode, {})
    output_contract = _build_output_contract(mode)

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
        template_id=template.get("template_id", ""),
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

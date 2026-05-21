import hashlib
import json
import math

from fastapi import HTTPException

from app.schemas.ai_context_packet import (
    MODE_ARTIFACTS,
    PROMPT_TEMPLATES,
    VALID_MODES,
    Audit,
    AiContextPacketResponse,
    ContextSelectorInfo,
    OutputContract,
    ProjectBrief,
    PromptTemplate,
    RuntimeEvidence,
    TaskContext,
    TokenBudget,
)
from app.schemas.context_selector import ContextSelectorRequest
from app.services import context_selector_service


_PROJECT_BRIEF = ProjectBrief(
    project_name="Codex Automation Delivery Platform",
    current_version="v0.4.0",
    project_goal="AI自动代码交付平台 — Agent编排、AI Provider、Patch Sandbox、Sandbox Gate、Review Packet 自动化",
    completed_scope=[
        "v0.1.0 MVP baseline — Project/Task CRUD, 9-state machine",
        "v0.2.0 Agent core + approval + orchestration",
        "v0.3.0 AI Provider + Output Governance + TaskDetail Display",
        "v0.4.0 Patch Sandbox + Sandbox Gate + Review Packet",
        "v0.4.0 S6-S7 Browser AI Provider Design + Project Map & Codebase Index",
        "v0.4.0 S8 Context Selector from Project Map",
    ],
    safety_boundaries=[
        "No Project.root_path access",
        "No shell/subprocess/os.system for business operations",
        "No secret_ref or .env file reading",
        "No git clone/commit/push (except via controlled PR flow)",
        "No direct master push",
        "No real GitHub PR creation",
        "No real CI/Sonar/Deploy API calls",
        "No auto-approve for human_required or high/critical risk tasks",
        "No Browser AI Provider (not yet designed)",
        "No real GitHub PR Adapter (not yet designed)",
    ],
    known_non_goals=[
        "Real GitHub PR integration (stubs only)",
        "Real CI integration (stubs only)",
        "Real Sonar integration (stubs only)",
        "Browser AI Provider implementation",
        "Browser AI Reviewer implementation",
        "Real deploy automation",
    ],
)

_FORBIDDEN_FILES = [
    ".env",
    ".env.*",
    "**/secret*",
    "**/*.pem",
    "**/*.key",
    "**/credentials*",
    "**/tokens*",
]

_MAX_TOKENS_BY_MODE = {
    "planning": {"context": 8000, "code_context": 12000, "review_packet": 0, "response": 4000},
    "patch_generation": {"context": 12000, "code_context": 16000, "review_packet": 0, "response": 4000},
    "review": {"context": 8000, "code_context": 4000, "review_packet": 12000, "response": 2000},
    "risk": {"context": 8000, "code_context": 4000, "review_packet": 8000, "response": 2000},
    "browser_reviewer": {"context": 4000, "code_context": 2000, "review_packet": 8000, "response": 2000},
}


def _validate_mode(mode: str) -> None:
    if mode not in VALID_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown mode '{mode}'. Valid modes: {', '.join(sorted(VALID_MODES))}",
        )


def _build_project_brief() -> ProjectBrief:
    return _PROJECT_BRIEF.model_copy(deep=True)


def _build_task_context(
    task_goal: str,
    module_name: str,
    task_type: str,
    mode: str,
    recommended_files: list[str],
) -> TaskContext:
    allowed = [f for f in recommended_files if not any(
        forbid.replace("*", "") in f for forbid in _FORBIDDEN_FILES
    )] if recommended_files else []

    artifacts = []
    format_name = ""
    if mode in MODE_ARTIFACTS:
        artifacts = list(MODE_ARTIFACTS[mode][0])
        format_name = MODE_ARTIFACTS[mode][1]

    return TaskContext(
        task_goal=task_goal,
        module_name=module_name,
        task_type=task_type,
        mode=mode,
        allowed_files=allowed,
        forbidden_files=list(_FORBIDDEN_FILES),
        expected_artifacts=artifacts,
    )


def _build_output_contract(mode: str) -> OutputContract:
    artifacts, fmt = MODE_ARTIFACTS.get(mode, ([], ""))
    patch = "unified_diff" if mode == "patch_generation" else ""
    risk = "json" if mode == "risk" else ""
    return OutputContract(
        expected_artifacts=list(artifacts),
        format=fmt,
        patch_format=patch,
        risk_format=risk,
    )


def _build_prompt_template(mode: str) -> PromptTemplate:
    template = PROMPT_TEMPLATES.get(mode, {})
    expected_output_map = {
        "planning": "plan.md — structured markdown plan with steps, files, and safety notes",
        "patch_generation": "patch.diff — unified diff of code changes",
        "review": "review.md — structured review report with findings and risk assessment",
        "risk": "risk_report.json — structured risk assessment with severity levels",
        "browser_reviewer": "browser_ai_review.json — structured browser review with visual evidence references",
    }
    return PromptTemplate(
        template_id=template.get("template_id", ""),
        mode=mode,
        purpose=template.get("purpose", ""),
        expected_output=expected_output_map.get(mode, ""),
        allowed_model_tiers=template.get("allowed_model_tiers", []),
        safety_notes=template.get("safety_notes", []),
    )


def _estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def _hash_dict(data: dict, sort_keys: bool = True) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=sort_keys)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _estimate_packet_size(packet: AiContextPacketResponse) -> int:
    raw = json.dumps(packet.model_dump(), ensure_ascii=False, sort_keys=True)
    return _estimate_tokens(raw)


def _check_budget(mode: str, estimated: int) -> TokenBudget:
    limits = _MAX_TOKENS_BY_MODE.get(mode, _MAX_TOKENS_BY_MODE["planning"])
    budget = TokenBudget(
        max_context_tokens=limits["context"],
        max_code_context_tokens=limits["code_context"],
        max_review_packet_tokens=limits["review_packet"],
        max_response_tokens=limits["response"],
        estimated_context_tokens=estimated,
    )
    total_budget = sum(limits.values())
    ratio = estimated / total_budget if total_budget > 0 else 0
    if ratio >= 1.0:
        budget.budget_status = "over_limit"
        budget.truncation_applied = True
        budget.omitted_sections = ["runtime_evidence", "output_contract"]
    elif ratio >= 0.85:
        budget.budget_status = "near_limit"
    return budget


def _get_selector_summary(
    task_goal: str,
    module_name: str,
    task_type: str,
) -> ContextSelectorInfo:
    req = ContextSelectorRequest(
        task_goal=task_goal,
        module_name=module_name,
        task_type=task_type,
    )
    result = context_selector_service.preview(req)
    return ContextSelectorInfo(
        matched_modules=[
            {
                "name": m.name,
                "module_type": m.module_type,
                "description": m.description,
                "files": m.files,
                "api": m.api,
                "safety_notes": m.safety_notes,
            }
            for m in result.matched_modules
        ],
        recommended_files=result.recommended_files,
        recommended_tests=result.recommended_tests,
        recommended_api=result.recommended_api,
        safety_notes=result.safety_notes,
        confidence=result.confidence,
        warnings=result.warnings,
    )


def _build_audit(
    project_brief: ProjectBrief,
    task_context: TaskContext,
    selector: ContextSelectorInfo,
    packet: AiContextPacketResponse,
    prompt_template_id: str,
    estimated: int,
) -> Audit:
    return Audit(
        project_prefix_hash=_hash_dict(project_brief.model_dump()),
        task_context_hash=_hash_dict(task_context.model_dump()),
        selected_context_hash=_hash_dict(selector.model_dump()),
        context_packet_hash=_hash_dict(packet.model_dump()),
        prompt_template_id=prompt_template_id,
        redaction_applied=False,
        context_file_count=len(selector.recommended_files),
        estimated_context_tokens=estimated,
    )


def _build_runtime_evidence() -> RuntimeEvidence:
    return RuntimeEvidence()


def preview(
    task_goal: str = "",
    module_name: str = "",
    task_type: str = "",
    mode: str = "planning",
) -> AiContextPacketResponse:
    _validate_mode(mode)

    project_brief = _build_project_brief()
    selector = _get_selector_summary(task_goal, module_name, task_type)
    task_context = _build_task_context(
        task_goal, module_name, task_type, mode, selector.recommended_files,
    )
    output_contract = _build_output_contract(mode)
    prompt_template = _build_prompt_template(mode)
    runtime_evidence = _build_runtime_evidence()

    packet = AiContextPacketResponse(
        project_brief=project_brief,
        task_context=task_context,
        context_selector=selector,
        runtime_evidence=runtime_evidence,
        output_contract=output_contract,
        prompt_template=prompt_template,
    )
    estimated = _estimate_packet_size(packet)
    token_budget = _check_budget(mode, estimated)
    audit = _build_audit(
        project_brief, task_context, selector, packet,
        prompt_template.template_id, estimated,
    )

    warnings = list(selector.warnings)
    if token_budget.budget_status == "over_limit":
        warnings.append("context_budget_exceeded")

    packet.token_budget = token_budget
    packet.audit = audit
    packet.warnings = warnings
    return packet

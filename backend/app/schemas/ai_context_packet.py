from pydantic import BaseModel, Field


MODE_PLANNING = "planning"
MODE_PATCH_GENERATION = "patch_generation"
MODE_REVIEW = "review"
MODE_RISK = "risk"
MODE_BROWSER_REVIEWER = "browser_reviewer"

VALID_MODES = {
    MODE_PLANNING,
    MODE_PATCH_GENERATION,
    MODE_REVIEW,
    MODE_RISK,
    MODE_BROWSER_REVIEWER,
}

MODE_ARTIFACTS = {
    MODE_PLANNING: (["plan.md"], "markdown"),
    MODE_PATCH_GENERATION: (["patch.diff"], "unified_diff"),
    MODE_REVIEW: (["review.md"], "markdown"),
    MODE_RISK: (["risk_report.json"], "json"),
    MODE_BROWSER_REVIEWER: (["browser_ai_review.json"], "json"),
}

PROMPT_TEMPLATES = {
    MODE_PLANNING: {
        "template_id": "planning_prompt_v1",
        "purpose": "Generate structured plan.md for AI executor",
        "allowed_model_tiers": ["codex_planner", "openai_gpt4", "claude"],
        "safety_notes": ["no code execution", "paths only", "no file content"],
    },
    MODE_PATCH_GENERATION: {
        "template_id": "patch_generation_prompt_v1",
        "purpose": "Generate unified diff patch from task context",
        "allowed_model_tiers": ["codex_executor", "openai_gpt4"],
        "safety_notes": ["diff only", "no file system write", "review required before apply"],
    },
    MODE_REVIEW: {
        "template_id": "review_prompt_v1",
        "purpose": "Review patch diff for correctness and safety",
        "allowed_model_tiers": ["codex_reviewer", "openai_gpt4"],
        "safety_notes": ["read-only review", "no auto-approve", "human_required for high risk"],
    },
    MODE_RISK: {
        "template_id": "risk_prompt_v1",
        "purpose": "Assess risk level of proposed changes",
        "allowed_model_tiers": ["codex_reviewer", "openai_gpt4"],
        "safety_notes": ["read-only assessment", "no auto-escalation", "high/critical require human"],
    },
    MODE_BROWSER_REVIEWER: {
        "template_id": "browser_reviewer_prompt_v1",
        "purpose": "Review browser rendered output for visual correctness",
        "allowed_model_tiers": ["codex_browser_reviewer"],
        "safety_notes": ["read-only review", "no screenshot capture", "no DOM mutation"],
    },
}


class AiContextPacketRequest(BaseModel):
    task_goal: str = ""
    module_name: str = ""
    task_type: str = ""
    mode: str = "planning"


class ProjectBrief(BaseModel):
    project_name: str = ""
    current_version: str = ""
    project_goal: str = ""
    completed_scope: list[str] = Field(default_factory=list)
    safety_boundaries: list[str] = Field(default_factory=list)
    known_non_goals: list[str] = Field(default_factory=list)


class TaskContext(BaseModel):
    task_goal: str = ""
    module_name: str = ""
    task_type: str = ""
    mode: str = ""
    allowed_files: list[str] = Field(default_factory=list)
    forbidden_files: list[str] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)


class ContextSelectorInfo(BaseModel):
    matched_modules: list[dict] = Field(default_factory=list)
    recommended_files: list[str] = Field(default_factory=list)
    recommended_tests: list[str] = Field(default_factory=list)
    recommended_api: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    confidence: str = "low"
    warnings: list[str] = Field(default_factory=list)


class RuntimeEvidence(BaseModel):
    pytest_summary: str = "not_provided"
    compileall_summary: str = "not_provided"
    sonar_summary: str = "not_provided"
    review_packet_summary: str = "not_provided"
    sandbox_result_summary: str = "not_provided"


class OutputContract(BaseModel):
    expected_artifacts: list[str] = Field(default_factory=list)
    format: str = ""
    patch_format: str = ""
    risk_format: str = ""


class TokenBudget(BaseModel):
    max_context_tokens: int = 0
    max_code_context_tokens: int = 0
    max_review_packet_tokens: int = 0
    max_response_tokens: int = 0
    estimated_context_tokens: int = 0
    budget_status: str = "ok"
    truncation_applied: bool = False
    omitted_sections: list[str] = Field(default_factory=list)


class PromptTemplate(BaseModel):
    template_id: str = ""
    mode: str = ""
    purpose: str = ""
    expected_output: str = ""
    allowed_model_tiers: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)


class Audit(BaseModel):
    project_prefix_hash: str = ""
    task_context_hash: str = ""
    selected_context_hash: str = ""
    context_packet_hash: str = ""
    prompt_template_id: str = ""
    redaction_applied: bool = False
    context_file_count: int = 0
    estimated_context_tokens: int = 0


class AiContextPacketResponse(BaseModel):
    project_brief: ProjectBrief = Field(default_factory=ProjectBrief)
    task_context: TaskContext = Field(default_factory=TaskContext)
    context_selector: ContextSelectorInfo = Field(default_factory=ContextSelectorInfo)
    runtime_evidence: RuntimeEvidence = Field(default_factory=RuntimeEvidence)
    output_contract: OutputContract = Field(default_factory=OutputContract)
    token_budget: TokenBudget = Field(default_factory=TokenBudget)
    prompt_template: PromptTemplate = Field(default_factory=PromptTemplate)
    audit: Audit = Field(default_factory=Audit)
    warnings: list[str] = Field(default_factory=list)

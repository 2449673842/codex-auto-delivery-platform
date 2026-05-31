from typing import Any

from pydantic import BaseModel, Field


class MastermindReviewVerificationResults(BaseModel):
    targeted_backend_pytest: str = ""
    full_backend_pytest: str = ""
    compileall: str = ""
    npm_build: str = ""
    frontend_smoke: str = ""
    git_diff_check: str = ""


class MastermindReviewSonarCloudSummary(BaseModel):
    quality_gate: str = ""
    security_hotspots: int | str | None = None
    duplication_on_new_code: str = ""
    new_issues: int | str | None = None


class MastermindReviewRedactionStatus(BaseModel):
    redaction_applied: bool = True
    truncated: bool = False
    max_chars: int = 12000


class MastermindReviewPacketPreviewRequest(BaseModel):
    pr_url: str = ""
    pr_number: int | None = None
    head_commit: str = ""
    base_commit: str = ""
    changed_files: list[str] = Field(default_factory=list)
    pr_body: str = ""
    verification_results: MastermindReviewVerificationResults = Field(
        default_factory=MastermindReviewVerificationResults
    )
    sonarcloud: MastermindReviewSonarCloudSummary = Field(default_factory=MastermindReviewSonarCloudSummary)
    include_evidence_board: bool = True
    include_timeline: bool = True
    include_project_memory: bool = True
    include_handoff_context: bool = True
    packet_budget: int = Field(default=12000, ge=1000, le=30000)


class MastermindReviewSourceRef(BaseModel):
    source_type: str
    id: int | None = None
    path: str | None = None
    note: str | None = None


class MastermindReviewPacketPreviewResponse(BaseModel):
    task_id: int
    project_id: int
    packet_type: str = "mastermind_review_packet"
    packet: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[MastermindReviewSourceRef] = Field(default_factory=list)
    redaction_status: MastermindReviewRedactionStatus = Field(default_factory=MastermindReviewRedactionStatus)
    read_only: bool = True
    persisted: bool = False
    safety_notes: list[str] = Field(default_factory=list)


class MastermindReviewBrowserAiOptions(BaseModel):
    provider_profile: str = "chatgpt_web"
    target_url: str = ""
    prompt_selector: str = ""
    submit_selector: str = ""
    response_selector: str = ""
    scroll_container_selector: str = ""
    copy_button_selector: str = ""
    login_hint_selector: str = ""
    stable_response_timeout_seconds: int | None = Field(default=120, ge=1, le=600)
    stable_polls: int = Field(default=3, ge=1, le=50)
    stable_interval_ms: int = Field(default=1000, ge=100, le=10000)


class MastermindReviewExecuteRequest(BaseModel):
    packet: MastermindReviewPacketPreviewRequest = Field(default_factory=MastermindReviewPacketPreviewRequest)
    browser_ai: MastermindReviewBrowserAiOptions = Field(default_factory=MastermindReviewBrowserAiOptions)
    save_artifact: bool = True


class MastermindReviewParsedVerdict(BaseModel):
    verdict: str = "invalid_review"
    summary: str = ""
    blocking_items: list[dict[str, Any]] = Field(default_factory=list)
    recommended_actions: list[Any] = Field(default_factory=list)
    safety_notes: list[Any] = Field(default_factory=list)
    confidence: str = "low"
    review_scope_confirmed: bool = False
    parse_errors: list[str] = Field(default_factory=list)


class MastermindReviewExecuteResponse(BaseModel):
    task_id: int
    project_id: int
    status: str
    agent_run_id: int | None = None
    artifact_id: int | None = None
    verdict: str = "invalid_review"
    summary: str = ""
    blocking_items: list[dict[str, Any]] = Field(default_factory=list)
    recommended_actions: list[Any] = Field(default_factory=list)
    safety_notes: list[Any] = Field(default_factory=list)
    raw_excerpt: str = ""
    failure_reason: str = ""
    read_only: bool = True
    persisted: bool = False
    advisory_only: bool = True
    human_confirmation_required: bool = True
    no_auto_merge: bool = True
    parse_errors: list[str] = Field(default_factory=list)


class MastermindReviewGatePreviewRequest(BaseModel):
    source_artifact_id: int | None = None
    current_head_commit: str = ""
    pr_url: str = ""
    pr_number: int | None = None
    verification_results: MastermindReviewVerificationResults = Field(
        default_factory=MastermindReviewVerificationResults
    )
    sonarcloud: MastermindReviewSonarCloudSummary = Field(default_factory=MastermindReviewSonarCloudSummary)


class MastermindReviewGatePreviewResponse(BaseModel):
    task_id: int
    project_id: int
    gate_status: str
    source_artifact_id: int | None = None
    source_agent_run_id: int | None = None
    pr_url: str = ""
    pr_number: int | None = None
    head_commit: str = ""
    reviewed_head_commit: str = ""
    summary: str = ""
    blocking_reasons: list[str] = Field(default_factory=list)
    recommended_actions: list[Any] = Field(default_factory=list)
    human_confirmation_required: bool = True
    advisory_only: bool = True
    no_auto_merge: bool = True
    read_only: bool = True
    persisted: bool = False
    safety_notes: list[str] = Field(default_factory=list)

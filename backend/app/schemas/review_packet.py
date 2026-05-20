"""Review Packet schemas — Mastermind Review Packet / PR Review Automation."""

from pydantic import BaseModel, Field


class ReviewPacketRequest(BaseModel):
    repo: str
    pr_number: int
    reported_head: str = ""
    reported_pytest: str = ""
    reported_compileall: str = ""
    reported_npm_build: str = ""
    reported_playwright: str = ""
    reported_changed_file_count: int | None = None


class ReviewAction(BaseModel):
    action: str
    detail: str = ""


class ReviewPacketDecision(BaseModel):
    review_status: str = "needs_update"
    merge_allowed: bool = False
    blockers: list[ReviewAction] = Field(default_factory=list)
    warnings: list[ReviewAction] = Field(default_factory=list)
    required_actions: list[ReviewAction] = Field(default_factory=list)
    summary: str = ""


class ReviewPacketData(BaseModel):
    repo: str = ""
    pr_number: int = 0
    pr_url: str = ""
    pr_state: str = ""
    merged: bool = False
    head_commit: str = ""
    base_commit: str = ""
    reported_head: str = ""
    head_matches: bool = True
    changed_files: list[str] = Field(default_factory=list)
    changed_file_count: int = 0
    additions: int = 0
    deletions: int = 0
    pr_body: str = ""
    sonar_comment_found: bool = False
    sonar_quality_gate: str = ""
    sonar_security_hotspots: int = 0
    sonar_new_bugs: int = 0
    sonar_new_vulnerabilities: int = 0
    sonar_new_code_smells: int = 0
    sonar_duplication_on_new_code: float = 0.0
    pytest_from_pr_body: str = ""
    pytest_reported: str = ""
    pytest_matches: bool = True
    compileall_reported: str = ""
    compileall_from_pr_body: str = ""
    compileall_matches: bool = True
    npm_build_reported: str = ""
    npm_build_from_pr_body: str = ""
    npm_build_matches: bool = True
    playwright_reported: str = ""
    has_frontend_changes: bool = False
    has_backend_changes: bool = True
    has_db_migration: bool = False
    has_github_pr_entry: bool = False
    has_ci_entry: bool = False
    has_sonar_entry: bool = False
    has_deploy_entry: bool = False
    reported_changed_file_count: int | None = None
    suspicious_phrases: list[str] = Field(default_factory=list)


class ReviewPacketPreviewResponse(BaseModel):
    packet: ReviewPacketData
    decision: ReviewPacketDecision

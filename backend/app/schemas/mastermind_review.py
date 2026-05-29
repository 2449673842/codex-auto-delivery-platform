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

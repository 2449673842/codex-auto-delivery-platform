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

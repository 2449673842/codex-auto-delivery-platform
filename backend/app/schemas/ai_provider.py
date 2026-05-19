from pydantic import BaseModel, Field
from typing import Any


class AgentRunResult(BaseModel):
    """Result produced by an AI provider execution."""
    output_summary: str
    output_log: str
    raw_result_json: str | None = None
    plan_md: str | None = None
    patch_diff: str | None = None
    review_md: str | None = None
    risk_report: dict[str, Any] | None = None

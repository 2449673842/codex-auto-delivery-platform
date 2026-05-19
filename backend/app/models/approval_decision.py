from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ApprovalDecision(Base):
    __tablename__ = "approval_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False)
    agent_run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("agent_runs.id"), nullable=True)
    agent_review_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("agent_reviews.id"), nullable=True)
    policy_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("approval_policies.id"), nullable=True)
    risk_level: Mapped[str] = mapped_column(String(16), default="low")
    auto_approve_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    human_required: Mapped[bool] = mapped_column(Boolean, default=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocked_reasons_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

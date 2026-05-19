from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class AgentReview(Base):
    __tablename__ = "agent_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False)
    agent_run_id: Mapped[int] = mapped_column(Integer, ForeignKey("agent_runs.id"), nullable=False)
    reviewer_agent_id: Mapped[int] = mapped_column(Integer, ForeignKey("agent_profiles.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), default="low")
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    issues_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    task = relationship("Task", backref="agent_reviews")
    agent_run = relationship("AgentRun", backref="reviews")

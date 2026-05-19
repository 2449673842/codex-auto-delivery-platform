from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    priority: Mapped[str] = mapped_column(String(16), default="medium")
    source: Mapped[str] = mapped_column(String(32), default="manual")
    planner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    executor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(64), nullable=True)
    human_approver: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ticket_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    pr_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ci_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    deploy_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_branch: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    project = relationship("Project", back_populates="tasks")
    artifacts = relationship(
        "TaskArtifact", back_populates="task", cascade="all, delete-orphan"
    )
    events = relationship(
        "TaskEvent", back_populates="task", cascade="all, delete-orphan"
    )
    reviews = relationship(
        "ReviewRecord", back_populates="task", cascade="all, delete-orphan"
    )

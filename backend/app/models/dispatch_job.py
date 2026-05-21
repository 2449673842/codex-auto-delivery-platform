from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DispatchJob(Base):
    __tablename__ = "dispatch_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(Integer, ForeignKey("dispatch_batches.id"), nullable=False)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, default=1)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="openai")
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="gpt-4o-mini")
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    context_packet_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("agent_runs.id"), nullable=True)
    artifact_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_artifact_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    batch = relationship("DispatchBatch", back_populates="jobs")
    task = relationship("Task")
    agent_run = relationship("AgentRun")

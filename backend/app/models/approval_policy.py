from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ApprovalPolicy(Base):
    __tablename__ = "approval_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    project_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("projects.id"), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    max_risk_level_for_auto_approve: Mapped[str] = mapped_column(String(16), default="low")
    require_tests_passed: Mapped[bool] = mapped_column(Boolean, default=True)
    require_sonar_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    require_no_security_issues: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_auto_approve_docs_only: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_auto_approve_frontend_style_only: Mapped[bool] = mapped_column(Boolean, default=True)
    forbid_auto_merge_main: Mapped[bool] = mapped_column(Boolean, default=True)
    forbid_auto_deploy_prod: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

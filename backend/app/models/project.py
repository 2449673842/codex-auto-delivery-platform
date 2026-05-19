from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    root_path: Mapped[str] = mapped_column(Text, nullable=False)
    repo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_branch: Mapped[str] = mapped_column(String(64), default="main")
    current_branch: Mapped[str] = mapped_column(String(64), default="main")
    frontend_path: Mapped[str | None] = mapped_column(String(256), nullable=True)
    backend_path: Mapped[str | None] = mapped_column(String(256), nullable=True)
    package_manager: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dev_command: Mapped[str | None] = mapped_column(Text, nullable=True)
    build_command: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_command: Mapped[str | None] = mapped_column(Text, nullable=True)
    docker_compose_path: Mapped[str | None] = mapped_column(String(256), nullable=True)
    ci_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ci_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    deploy_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    deploy_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")

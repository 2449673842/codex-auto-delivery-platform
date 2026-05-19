from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    display_name: str | None = None
    root_path: str = Field(..., min_length=1)
    repo_url: str | None = None
    default_branch: str = "main"
    current_branch: str = "main"
    frontend_path: str | None = None
    backend_path: str | None = None
    package_manager: str | None = None
    dev_command: str | None = None
    build_command: str | None = None
    test_command: str | None = None
    docker_compose_path: str | None = None
    ci_provider: str | None = None
    ci_url: str | None = None
    deploy_provider: str | None = None
    deploy_url: str | None = None


class ProjectUpdate(BaseModel):
    display_name: str | None = None
    root_path: str | None = None
    repo_url: str | None = None
    default_branch: str | None = None
    current_branch: str | None = None
    frontend_path: str | None = None
    backend_path: str | None = None
    package_manager: str | None = None
    dev_command: str | None = None
    build_command: str | None = None
    test_command: str | None = None
    docker_compose_path: str | None = None
    ci_provider: str | None = None
    ci_url: str | None = None
    deploy_provider: str | None = None
    deploy_url: str | None = None
    is_active: bool | None = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    display_name: str | None
    root_path: str
    repo_url: str | None
    default_branch: str
    current_branch: str
    frontend_path: str | None
    backend_path: str | None
    package_manager: str | None
    dev_command: str | None
    build_command: str | None
    test_command: str | None
    docker_compose_path: str | None
    ci_provider: str | None
    ci_url: str | None
    deploy_provider: str | None
    deploy_url: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    task_count: int = 0

    model_config = {"from_attributes": True}

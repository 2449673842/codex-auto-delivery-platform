from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiEnvelope
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.services import project_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
async def list_projects(db: AsyncSession = Depends(get_session)):
    projects = await project_service.list_projects(db)
    items = []
    for p in projects:
        count = await project_service.get_project_task_count(db, p.id)
        resp = ProjectResponse.model_validate(p, from_attributes=True)
        resp.task_count = count
        items.append(resp)
    return ApiEnvelope(data=items)


@router.post("", status_code=201)
async def create_project(body: ProjectCreate, db: AsyncSession = Depends(get_session)):
    project = await project_service.create_project(db, body)
    return ApiEnvelope(
        data=ProjectResponse.model_validate(project, from_attributes=True)
    )


@router.get("/{project_id}")
async def get_project(project_id: int, db: AsyncSession = Depends(get_session)):
    project = await project_service.get_project(db, project_id)
    count = await project_service.get_project_task_count(db, project_id)
    resp = ProjectResponse.model_validate(project, from_attributes=True)
    resp.task_count = count
    return ApiEnvelope(data=resp)


@router.patch("/{project_id}")
async def update_project(
    project_id: int, body: ProjectUpdate, db: AsyncSession = Depends(get_session)
):
    project = await project_service.update_project(db, project_id, body)
    return ApiEnvelope(
        data=ProjectResponse.model_validate(project, from_attributes=True)
    )


@router.delete("/{project_id}")
async def delete_project(project_id: int, db: AsyncSession = Depends(get_session)):
    await project_service.delete_project(db, project_id)
    return ApiEnvelope(data=None, message="Project deleted")


@router.get("/{project_id}/branches")
async def get_branches(project_id: int, db: AsyncSession = Depends(get_session)):
    project = await project_service.get_project(db, project_id)
    return ApiEnvelope(
        data={
            "default_branch": project.default_branch,
            "current_branch": project.current_branch,
        }
    )


@router.post("/{project_id}/sync-git-info")
async def sync_git_info(project_id: int, db: AsyncSession = Depends(get_session)):
    await project_service.get_project(db, project_id)
    return ApiEnvelope(
        success=False, data=None, message="git info sync not implemented in MVP"
    )

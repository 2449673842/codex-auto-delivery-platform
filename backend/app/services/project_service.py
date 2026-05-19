from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.task import Task
from app.schemas.project import ProjectCreate, ProjectUpdate


async def list_projects(db: AsyncSession) -> list[Project]:
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    return list(result.scalars().all())


async def get_project(db: AsyncSession, project_id: int) -> Project:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def create_project(db: AsyncSession, data: ProjectCreate) -> Project:
    existing = await db.execute(select(Project).where(Project.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Project name already exists")
    project = Project(**data.model_dump())
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return project


async def update_project(
    db: AsyncSession, project_id: int, data: ProjectUpdate
) -> Project:
    project = await get_project(db, project_id)
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(project, key, val)
    await db.flush()
    await db.refresh(project)
    return project


async def delete_project(db: AsyncSession, project_id: int) -> None:
    project = await get_project(db, project_id)
    task_count = await db.scalar(
        select(func.count(Task.id)).where(Task.project_id == project_id)
    )
    if task_count and task_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete project with {task_count} associated task(s)",
        )
    await db.delete(project)
    await db.flush()


async def get_project_task_count(db: AsyncSession, project_id: int) -> int:
    count = await db.scalar(
        select(func.count(Task.id)).where(Task.project_id == project_id)
    )
    return count or 0

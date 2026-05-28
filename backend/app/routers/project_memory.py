from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiEnvelope
from app.services import project_memory_service


router = APIRouter(tags=["project_memory"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/api/projects/{project_id}/memory")
async def get_project_memory(project_id: int, db: SessionDep) -> ApiEnvelope:
    result = await project_memory_service.get_project_memory(db, project_id)
    return ApiEnvelope(data=result.model_dump(), message="Project Memory listed")


@router.get("/api/projects/{project_id}/memory/summary")
async def get_project_memory_summary(project_id: int, db: SessionDep) -> ApiEnvelope:
    result = await project_memory_service.get_project_memory_summary(db, project_id)
    return ApiEnvelope(data=result.model_dump(), message="Project Memory summary")

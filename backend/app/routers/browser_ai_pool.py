from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.browser_ai_pool import BrowserAiPoolRequest
from app.schemas.common import ApiEnvelope
from app.services import browser_ai_pool_service


router = APIRouter(tags=["browser_ai_pool"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/api/tasks/{task_id}/browser-ai-pool/preview")
async def preview_browser_ai_pool(
    task_id: int,
    body: BrowserAiPoolRequest,
    db: SessionDep,
) -> ApiEnvelope:
    result = await browser_ai_pool_service.preview(db, task_id, body)
    return ApiEnvelope(data=result.model_dump(), message="Browser AI pool preview generated")


@router.post("/api/tasks/{task_id}/browser-ai-pool/execute")
async def execute_browser_ai_pool(
    task_id: int,
    body: BrowserAiPoolRequest,
    db: SessionDep,
) -> ApiEnvelope:
    result = await browser_ai_pool_service.execute(db, task_id, body)
    return ApiEnvelope(data=result.model_dump(), message="Browser AI pool execute finished")

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.browser_ai import BrowserAiRequest
from app.schemas.common import ApiEnvelope
from app.services import browser_ai_service


router = APIRouter(prefix="/api/browser-ai", tags=["browser_ai"])


@router.get("/provider-profiles")
async def provider_profiles() -> ApiEnvelope:
    return ApiEnvelope(data=[profile.model_dump() for profile in browser_ai_service.list_provider_profiles()])


@router.post("/dry-run")
async def dry_run(body: BrowserAiRequest, db: AsyncSession = Depends(get_session)) -> ApiEnvelope:
    result = await browser_ai_service.dry_run(db, body)
    return ApiEnvelope(data=result.model_dump())


@router.post("/execute")
async def execute(body: BrowserAiRequest, db: AsyncSession = Depends(get_session)) -> ApiEnvelope:
    result = await browser_ai_service.execute(db, body)
    return ApiEnvelope(data=result.model_dump())

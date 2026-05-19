from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiEnvelope
from app.schemas.event import EventResponse
from app.services import event_service

router = APIRouter(tags=["events"])


@router.get("/api/tasks/{task_id}/events")
async def list_events(task_id: int, db: AsyncSession = Depends(get_session)):
    events = await event_service.list_events(db, task_id)
    return ApiEnvelope(
        data=[EventResponse.model_validate(e, from_attributes=True) for e in events]
    )

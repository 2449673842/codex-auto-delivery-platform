"""Context Selector API Router — stateless module recommendation from Project Map."""

from fastapi import APIRouter

from app.schemas.common import ApiEnvelope
from app.schemas.context_selector import ContextSelectorRequest
from app.services import context_selector_service

router = APIRouter(tags=["context_selector"])


@router.post("/api/context-selector/preview")
async def preview_context_selector(body: ContextSelectorRequest):
    result = context_selector_service.preview(body)
    return ApiEnvelope(
        data=result.model_dump(),
        message="Context selector preview generated",
    )

from fastapi import APIRouter
from fastapi.params import Body

from app.schemas.ai_context_packet import AiContextPacketRequest
from app.schemas.common import ApiEnvelope
from app.services import ai_context_packet_service

router = APIRouter(tags=["ai_context_packet"])


@router.post("/api/ai-context-packets/preview", status_code=200)
async def preview_context_packet(body: AiContextPacketRequest = Body(...)):
    result = ai_context_packet_service.preview(
        task_goal=body.task_goal,
        module_name=body.module_name,
        task_type=body.task_type,
        mode=body.mode,
    )
    return ApiEnvelope(data=result.model_dump(), message="AI context packet preview generated")

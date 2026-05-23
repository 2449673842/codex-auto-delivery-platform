from fastapi import APIRouter

from app.config import settings
from app.schemas.ai_runtime import AIRuntimeStatusResponse
from app.schemas.common import ApiEnvelope

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"

router = APIRouter(prefix="/api/ai-runtime", tags=["ai-runtime"])


@router.get("/status")
async def get_ai_runtime_status():
    provider_allowlist = settings.provider_allowlist
    data = AIRuntimeStatusResponse(
        ai_execution_enabled=settings.ai_execution_enabled,
        openai_credential_configured=bool(settings.openai_api_key),
        provider_allowlist=provider_allowlist,
        openai_allowed="openai" in provider_allowlist,
        model=settings.openai_model,
        base_url_configured=settings.openai_base_url != DEFAULT_OPENAI_BASE_URL,
        wire_api=settings.openai_wire_api,
    )
    return ApiEnvelope(data=data)

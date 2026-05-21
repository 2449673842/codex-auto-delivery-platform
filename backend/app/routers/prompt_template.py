from fastapi import APIRouter
from fastapi.params import Body

from app.schemas.common import ApiEnvelope
from app.schemas.prompt_template import PromptTemplatePreviewRequest
from app.services import prompt_template_service

router = APIRouter(tags=["prompt_template"])


@router.post("/api/prompt-templates/preview", status_code=200)
async def preview_prompt_template(body: PromptTemplatePreviewRequest = Body(...)):
    result = prompt_template_service.preview(
        task_goal=body.task_goal,
        module_name=body.module_name,
        task_type=body.task_type,
        mode=body.mode,
    )
    return ApiEnvelope(data=result.model_dump(), message="Prompt template preview generated")

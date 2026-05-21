from pydantic import BaseModel, Field


class PromptTemplatePreviewRequest(BaseModel):
    task_goal: str = ""
    module_name: str = ""
    task_type: str = ""
    mode: str = "planning"


class PromptOutputContract(BaseModel):
    expected_artifacts: list[str] = Field(default_factory=list)
    format: str = ""


class PromptTokenBudget(BaseModel):
    estimated_prompt_tokens: int = 0
    budget_status: str = "ok"


class PromptTemplatePreviewResponse(BaseModel):
    template_id: str = ""
    mode: str = ""
    system_prompt_preview: str = ""
    user_prompt_preview: str = ""
    output_contract: PromptOutputContract = Field(default_factory=PromptOutputContract)
    context_packet_hash: str = ""
    system_prompt_hash: str = ""
    user_prompt_hash: str = ""
    prompt_hash: str = ""
    token_budget: PromptTokenBudget = Field(default_factory=PromptTokenBudget)
    redaction_applied: bool = False
    warnings: list[str] = Field(default_factory=list)

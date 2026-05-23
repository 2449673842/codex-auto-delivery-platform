from pydantic import BaseModel


class AIRuntimeStatusResponse(BaseModel):
    ai_execution_enabled: bool
    openai_key_present: bool
    provider_allowlist: list[str]
    openai_allowed: bool
    model: str
    base_url_configured: bool
    wire_api: str

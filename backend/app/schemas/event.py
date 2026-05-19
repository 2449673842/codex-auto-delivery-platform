from datetime import datetime

from pydantic import BaseModel


class EventResponse(BaseModel):
    id: int
    task_id: int
    event_type: str
    actor: str | None
    from_status: str | None
    to_status: str | None
    message: str | None
    payload_json: str | None
    created_at: datetime

    model_config = {"from_attributes": True}

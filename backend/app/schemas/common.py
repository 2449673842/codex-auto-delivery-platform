from pydantic import BaseModel


class ApiEnvelope(BaseModel):
    success: bool = True
    data: object = None
    message: str = "ok"


class Pagination(BaseModel):
    page: int = 1
    size: int = 20
    total: int = 0

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiEnvelope
from app.schemas.mcp_bridge import McpCallRequest
from app.services import mcp_bridge_service


router = APIRouter(prefix="/api/mcp", tags=["mcp_bridge"])


@router.get("/tools")
async def tools() -> ApiEnvelope:
    return ApiEnvelope(data=[tool.model_dump() for tool in mcp_bridge_service.list_tools()])


@router.post("/call")
async def call(body: McpCallRequest, db: Annotated[AsyncSession, Depends(get_session)]) -> ApiEnvelope:
    result = await mcp_bridge_service.call_tool(db, body)
    return ApiEnvelope(data=result.model_dump())

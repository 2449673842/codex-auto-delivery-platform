from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.schemas.agent_profile import AgentProfileCreate, AgentProfileResponse, AgentProfileUpdate
from app.schemas.common import ApiEnvelope
from app.services import agent_profile_service

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("")
async def list_agents(db: AsyncSession = Depends(get_session)):
    agents = await agent_profile_service.list_agents(db)
    return ApiEnvelope(data=[AgentProfileResponse.model_validate(a, from_attributes=True) for a in agents])


@router.post("", status_code=201)
async def create_agent(body: AgentProfileCreate, db: AsyncSession = Depends(get_session)):
    agent = await agent_profile_service.create_agent(db, body)
    return ApiEnvelope(data=AgentProfileResponse.model_validate(agent, from_attributes=True))


@router.get("/{agent_id}")
async def get_agent(agent_id: int, db: AsyncSession = Depends(get_session)):
    agent = await agent_profile_service.get_agent(db, agent_id)
    return ApiEnvelope(data=AgentProfileResponse.model_validate(agent, from_attributes=True))


@router.patch("/{agent_id}")
async def update_agent(agent_id: int, body: AgentProfileUpdate, db: AsyncSession = Depends(get_session)):
    agent = await agent_profile_service.update_agent(db, agent_id, body)
    return ApiEnvelope(data=AgentProfileResponse.model_validate(agent, from_attributes=True))


@router.delete("/{agent_id}")
async def delete_agent(agent_id: int, db: AsyncSession = Depends(get_session)):
    await agent_profile_service.delete_agent(db, agent_id)
    return ApiEnvelope(data=None, message="Agent deleted")

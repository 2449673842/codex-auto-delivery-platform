from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.agent_profile import AgentProfile
from app.schemas.agent_profile import AgentProfileCreate, AgentProfileUpdate


async def list_agents(db: AsyncSession) -> list[AgentProfile]:
    result = await db.execute(select(AgentProfile).order_by(AgentProfile.created_at.desc()))
    return list(result.scalars().all())


async def get_agent(db: AsyncSession, agent_id: int) -> AgentProfile:
    agent = await db.get(AgentProfile, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


async def create_agent(db: AsyncSession, data: AgentProfileCreate) -> AgentProfile:
    existing = await db.execute(select(AgentProfile).where(AgentProfile.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Agent name already exists")
    agent = AgentProfile(**data.model_dump())
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return agent


async def update_agent(db: AsyncSession, agent_id: int, data: AgentProfileUpdate) -> AgentProfile:
    agent = await get_agent(db, agent_id)
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(agent, key, val)
    await db.flush()
    await db.refresh(agent)
    return agent


async def delete_agent(db: AsyncSession, agent_id: int) -> None:
    agent = await get_agent(db, agent_id)
    await db.delete(agent)
    await db.flush()

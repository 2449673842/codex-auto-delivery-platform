from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.approval_policy import ApprovalPolicy
from app.schemas.approval_policy import ApprovalPolicyCreate, ApprovalPolicyUpdate


async def list_policies(db: AsyncSession) -> list[ApprovalPolicy]:
    result = await db.execute(select(ApprovalPolicy).order_by(ApprovalPolicy.created_at.desc()))
    return list(result.scalars().all())


async def get_policy(db: AsyncSession, policy_id: int) -> ApprovalPolicy:
    policy = await db.get(ApprovalPolicy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="ApprovalPolicy not found")
    return policy


async def create_policy(db: AsyncSession, data: ApprovalPolicyCreate) -> ApprovalPolicy:
    policy = ApprovalPolicy(**data.model_dump())
    db.add(policy)
    await db.flush()
    await db.refresh(policy)
    return policy


async def update_policy(db: AsyncSession, policy_id: int, data: ApprovalPolicyUpdate) -> ApprovalPolicy:
    policy = await get_policy(db, policy_id)
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(policy, key, val)
    await db.flush()
    await db.refresh(policy)
    return policy


async def delete_policy(db: AsyncSession, policy_id: int) -> None:
    policy = await get_policy(db, policy_id)
    await db.delete(policy)
    await db.flush()

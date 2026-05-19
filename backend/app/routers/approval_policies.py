from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.schemas.approval_policy import ApprovalPolicyCreate, ApprovalPolicyResponse, ApprovalPolicyUpdate
from app.schemas.common import ApiEnvelope
from app.services import approval_policy_service

router = APIRouter(prefix="/api/approval-policies", tags=["approval_policies"])


@router.get("")
async def list_policies(db: AsyncSession = Depends(get_session)):
    policies = await approval_policy_service.list_policies(db)
    return ApiEnvelope(data=[ApprovalPolicyResponse.model_validate(p, from_attributes=True) for p in policies])


@router.post("", status_code=201)
async def create_policy(body: ApprovalPolicyCreate, db: AsyncSession = Depends(get_session)):
    policy = await approval_policy_service.create_policy(db, body)
    return ApiEnvelope(data=ApprovalPolicyResponse.model_validate(policy, from_attributes=True))


@router.get("/{policy_id}")
async def get_policy(policy_id: int, db: AsyncSession = Depends(get_session)):
    policy = await approval_policy_service.get_policy(db, policy_id)
    return ApiEnvelope(data=ApprovalPolicyResponse.model_validate(policy, from_attributes=True))


@router.patch("/{policy_id}")
async def update_policy(policy_id: int, body: ApprovalPolicyUpdate, db: AsyncSession = Depends(get_session)):
    policy = await approval_policy_service.update_policy(db, policy_id, body)
    return ApiEnvelope(data=ApprovalPolicyResponse.model_validate(policy, from_attributes=True))


@router.delete("/{policy_id}")
async def delete_policy(policy_id: int, db: AsyncSession = Depends(get_session)):
    await approval_policy_service.delete_policy(db, policy_id)
    return ApiEnvelope(data=None, message="ApprovalPolicy deleted")

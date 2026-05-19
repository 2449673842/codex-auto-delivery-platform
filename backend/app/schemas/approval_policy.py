from datetime import datetime
from pydantic import BaseModel, Field


class ApprovalPolicyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    project_id: int | None = None
    enabled: bool = True
    max_risk_level_for_auto_approve: str = "low"
    require_tests_passed: bool = True
    require_sonar_passed: bool = False
    require_no_security_issues: bool = True
    allow_auto_approve_docs_only: bool = True
    allow_auto_approve_frontend_style_only: bool = True
    forbid_auto_merge_main: bool = True
    forbid_auto_deploy_prod: bool = True


class ApprovalPolicyUpdate(BaseModel):
    name: str | None = None
    project_id: int | None = None
    enabled: bool | None = None
    max_risk_level_for_auto_approve: str | None = None
    require_tests_passed: bool | None = None
    require_sonar_passed: bool | None = None
    require_no_security_issues: bool | None = None
    allow_auto_approve_docs_only: bool | None = None
    allow_auto_approve_frontend_style_only: bool | None = None
    forbid_auto_merge_main: bool | None = None
    forbid_auto_deploy_prod: bool | None = None


class ApprovalPolicyResponse(BaseModel):
    id: int
    name: str
    project_id: int | None
    enabled: bool
    max_risk_level_for_auto_approve: str
    require_tests_passed: bool
    require_sonar_passed: bool
    require_no_security_issues: bool
    allow_auto_approve_docs_only: bool
    allow_auto_approve_frontend_style_only: bool
    forbid_auto_merge_main: bool
    forbid_auto_deploy_prod: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

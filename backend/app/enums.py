from enum import Enum


class TaskStatus(str, Enum):
    """任务 10 态（v0.2 新增 human_required）"""

    DRAFT = "draft"
    TICKET_READY = "ticket_ready"
    DISPATCHED = "dispatched"
    RESULT_SUBMITTED = "result_submitted"
    REVIEWING = "reviewing"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"
    HUMAN_REQUIRED = "human_required"


class ArtifactType(str, Enum):
    """任务产物类型"""
    EXECUTION_LOG = "execution_log"
    DIFF = "diff"
    REVIEW_NOTE = "review_note"
    CI_LOG = "ci_log"
    SCREENSHOT = "screenshot"
    AGENT_OUTPUT_LOG = "agent_output_log"
    AGENT_OUTPUT_DIFF = "agent_output_diff"
    AGENT_RAW_RESULT = "agent_raw_result"
    AGENT_REVIEW_REPORT = "agent_review_report"
    RISK_ASSESSMENT_REPORT = "risk_assessment_report"
    APPROVAL_SNAPSHOT = "approval_snapshot"
    TEST_REPORT = "test_report"
    SONAR_REPORT = "sonar_report"
    PLAYWRIGHT_REPORT = "playwright_report"
    PLAYWRIGHT_TRACE = "playwright_trace"
    BROWSER_CONSOLE = "browser_console"
    NETWORK_LOG = "network_log"
    TEST_VIDEO = "test_video"
    CODE_CONTEXT = "code_context"
    CODE_CONTEXT_FILE = "code_context_file"
    CODE_CONTEXT_BUNDLE = "code_context_bundle"
    PATCH_APPLY_REPORT = "patch_apply_report"
    CHANGED_FILES_SUMMARY = "changed_files_summary"
    CHANGED_FILE_PREVIEW = "changed_file_preview"
    SANDBOX_AFTER_FILE = "sandbox_after_file"


class EventType(str, Enum):
    """审计日志事件类型"""
    STATUS_CHANGED = "status_changed"
    ARTIFACT_UPLOADED = "artifact_uploaded"
    REVIEW_SUBMITTED = "review_submitted"
    TICKET_GENERATED = "ticket_generated"
    NOTE_ADDED = "note_added"
    TEST_RUN_CREATED = "test_run_created"
    TEST_RUN_UPDATED = "test_run_updated"
    TEST_RUN_PASSED = "test_run_passed"
    TEST_RUN_FAILED = "test_run_failed"
    AGENT_RUN_CREATED = "agent_run_created"
    AGENT_RUN_STARTED = "agent_run_started"
    AGENT_RUN_SUCCEEDED = "agent_run_succeeded"
    AGENT_RUN_FAILED = "agent_run_failed"
    AGENT_REVIEW_SUBMITTED = "agent_review_submitted"
    RISK_ASSESSED = "risk_assessed"
    AUTO_APPROVAL_GRANTED = "auto_approval_granted"
    AUTO_APPROVAL_BLOCKED = "auto_approval_blocked"
    HUMAN_APPROVAL_REQUIRED = "human_approval_required"
    ORCHESTRATION_STARTED = "orchestration_started"
    ORCHESTRATION_STEP_COMPLETED = "orchestration_step_completed"
    ORCHESTRATION_STOPPED = "orchestration_stopped"
    ORCHESTRATION_BLOCKED = "orchestration_blocked"
    AGENT_RUN_AUTO_CREATED = "agent_run_auto_created"
    AGENT_RUN_AUTO_STARTED = "agent_run_auto_started"
    AGENT_RESULT_WAITING = "agent_result_waiting"
    AGENT_REVIEW_WAITING = "agent_review_waiting"
    APPROVAL_AUTO_EVALUATED = "approval_auto_evaluated"
    APPROVAL_AUTO_APPLIED = "approval_auto_applied"
    REMEDIATION_STARTED = "remediation_started"
    CODE_CONTEXT_UPLOADED = "code_context_uploaded"
    PATCH_SANDBOX_APPLIED = "patch_sandbox_applied"
    PATCH_SANDBOX_FAILED = "patch_sandbox_failed"


class ReviewDecision(str, Enum):
    """审查决策"""
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


class AgentType(str, Enum):
    """Agent 类型"""
    PLANNER = "planner"
    EXECUTOR = "executor"
    REVIEWER = "reviewer"
    TEST = "test"


class AgentProvider(str, Enum):
    """Agent 服务商"""
    CODEX = "codex"
    OPENAI = "openai"
    CLAUDE = "claude"
    LOCAL = "local"
    SANDBOX = "sandbox"
    MANUAL = "manual"


class AgentRunType(str, Enum):
    """Agent 运行类型"""
    PLAN = "plan"
    EXECUTE = "execute"
    REVIEW = "review"
    TEST = "test"
    REMEDIATE = "remediate"


class AgentRunStatus(str, Enum):
    """Agent 运行状态"""
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    HUMAN_REQUIRED = "human_required"


class RiskLevel(str, Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ─── 状态跃迁白名单 ────────────────────────────────────

ALLOWED_TRANSITIONS: dict[TaskStatus, list[TaskStatus]] = {
    TaskStatus.DRAFT: [TaskStatus.TICKET_READY],
    TaskStatus.TICKET_READY: [TaskStatus.DISPATCHED],
    TaskStatus.DISPATCHED: [TaskStatus.RESULT_SUBMITTED],
    TaskStatus.RESULT_SUBMITTED: [TaskStatus.REVIEWING],
    TaskStatus.REVIEWING: [
        TaskStatus.APPROVED,
        TaskStatus.REJECTED,
        TaskStatus.CHANGES_REQUESTED,
        TaskStatus.HUMAN_REQUIRED,
    ],
    TaskStatus.CHANGES_REQUESTED: [TaskStatus.DISPATCHED],
    TaskStatus.APPROVED: [TaskStatus.ARCHIVED],
    TaskStatus.REJECTED: [TaskStatus.ARCHIVED],
    TaskStatus.HUMAN_REQUIRED: [TaskStatus.APPROVED, TaskStatus.REJECTED, TaskStatus.CHANGES_REQUESTED],
    TaskStatus.ARCHIVED: [],
}

ALLOWED_AGENT_RUN_TRANSITIONS: dict[AgentRunStatus, list[AgentRunStatus]] = {
    AgentRunStatus.QUEUED: [AgentRunStatus.RUNNING, AgentRunStatus.CANCELED],
    AgentRunStatus.RUNNING: [AgentRunStatus.SUCCEEDED, AgentRunStatus.FAILED, AgentRunStatus.CANCELED, AgentRunStatus.HUMAN_REQUIRED],
    AgentRunStatus.SUCCEEDED: [],
    AgentRunStatus.FAILED: [],
    AgentRunStatus.CANCELED: [],
    AgentRunStatus.HUMAN_REQUIRED: [],
}

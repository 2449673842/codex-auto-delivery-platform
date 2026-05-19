from enum import Enum


class TaskStatus(str, Enum):
    """任务 9 态"""

    DRAFT = "draft"
    TICKET_READY = "ticket_ready"
    DISPATCHED = "dispatched"
    RESULT_SUBMITTED = "result_submitted"
    REVIEWING = "reviewing"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class ArtifactType(str, Enum):
    """任务产物类型"""

    EXECUTION_LOG = "execution_log"
    DIFF = "diff"
    REVIEW_NOTE = "review_note"
    CI_LOG = "ci_log"
    SCREENSHOT = "screenshot"


class EventType(str, Enum):
    """审计日志事件类型"""

    STATUS_CHANGED = "status_changed"
    ARTIFACT_UPLOADED = "artifact_uploaded"
    REVIEW_SUBMITTED = "review_submitted"
    TICKET_GENERATED = "ticket_generated"
    NOTE_ADDED = "note_added"


class ReviewDecision(str, Enum):
    """审查决策"""

    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


# ─── 状态跃迁白名单 ────────────────────────────────────
# 每个状态允许跃迁到的下一个状态列表。
# 代码层校验，非法跃迁返回 409 Conflict。

ALLOWED_TRANSITIONS: dict[TaskStatus, list[TaskStatus]] = {
    TaskStatus.DRAFT: [TaskStatus.TICKET_READY],
    TaskStatus.TICKET_READY: [TaskStatus.DISPATCHED],
    TaskStatus.DISPATCHED: [TaskStatus.RESULT_SUBMITTED],
    TaskStatus.RESULT_SUBMITTED: [TaskStatus.REVIEWING],
    TaskStatus.REVIEWING: [
        TaskStatus.APPROVED,
        TaskStatus.REJECTED,
        TaskStatus.CHANGES_REQUESTED,
    ],
    TaskStatus.CHANGES_REQUESTED: [TaskStatus.DISPATCHED],  # 返工重新分派
    TaskStatus.APPROVED: [TaskStatus.ARCHIVED],
    TaskStatus.REJECTED: [TaskStatus.ARCHIVED],
    TaskStatus.ARCHIVED: [],  # 终态，不可再变更
}

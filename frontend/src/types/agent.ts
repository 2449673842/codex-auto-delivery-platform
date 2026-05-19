export const AGENT_TYPES = ['planner', 'executor', 'reviewer', 'test'] as const
export type AgentType = (typeof AGENT_TYPES)[number]

export const AGENT_PROVIDERS = ['codex', 'openai', 'claude', 'local', 'manual'] as const
export type AgentProvider = (typeof AGENT_PROVIDERS)[number]

export const AGENT_RUN_TYPES = ['plan', 'execute', 'review', 'test', 'remediate'] as const
export type AgentRunType = (typeof AGENT_RUN_TYPES)[number]

export const AGENT_RUN_STATUSES = ['queued', 'running', 'succeeded', 'failed', 'canceled', 'human_required'] as const
export type AgentRunStatus = (typeof AGENT_RUN_STATUSES)[number]

export const RISK_LEVELS = ['low', 'medium', 'high', 'critical'] as const
export type RiskLevel = (typeof RISK_LEVELS)[number]

export const AGENT_RUN_STATUS_LABELS: Record<string, string> = {
  queued: '已排队',
  running: '运行中',
  succeeded: '已成功',
  failed: '已失败',
  canceled: '已取消',
  human_required: '需要人工介入',
}

export const AGENT_RUN_TYPE_LABELS: Record<string, string> = {
  plan: '规划',
  execute: '执行',
  review: '审查',
  test: '测试',
  remediate: '修复',
}

export interface AgentProfile {
  id: number
  name: string
  agent_type: AgentType
  provider: AgentProvider
  model_name: string | null
  secret_ref: string | null
  enabled: boolean
  max_runtime_seconds: number
  max_attempts: number
  allowed_projects: string | null
  created_at: string
  updated_at: string
}

export interface AgentProfileCreate {
  name: string
  agent_type: string
  provider: string
  model_name?: string | null
  secret_ref?: string | null
  enabled?: boolean
  max_runtime_seconds?: number
  max_attempts?: number
  allowed_projects?: string | null
}

export interface AgentProfileUpdate {
  name?: string
  agent_type?: string
  provider?: string
  model_name?: string | null
  secret_ref?: string | null
  enabled?: boolean
  max_runtime_seconds?: number
  max_attempts?: number
  allowed_projects?: string | null
}

export interface AgentRun {
  id: number
  task_id: number
  project_id: number
  agent_id: number
  run_type: AgentRunType
  status: AgentRunStatus
  input_prompt: string | null
  output_summary: string | null
  output_diff: string | null
  output_log: string | null
  branch: string | null
  commit_sha: string | null
  pr_url: string | null
  risk_level: string
  attempt_no: number
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  error_message: string | null
  raw_result_json: string | null
  created_at: string
  updated_at: string
}

export interface AgentRunCreate {
  agent_id: number
  run_type: string
  input_prompt?: string | null
  branch?: string | null
  commit_sha?: string | null
  attempt_no?: number
}

export interface AgentRunUpdate {
  status?: string
  output_summary?: string | null
  output_diff?: string | null
  output_log?: string | null
  branch?: string | null
  commit_sha?: string | null
  pr_url?: string | null
  risk_level?: string | null
  started_at?: string | null
  finished_at?: string | null
  duration_ms?: number | null
  error_message?: string | null
  raw_result_json?: string | null
}

export interface AgentRunSubmitResult {
  status: 'succeeded' | 'failed'
  output_summary?: string | null
  output_diff?: string | null
  output_log?: string | null
  raw_result_json?: string | null
  duration_ms?: number | null
  error_message?: string | null
}

export interface AgentReview {
  id: number
  task_id: number
  agent_run_id: number
  reviewer_agent_id: number
  decision: string
  risk_level: string
  comments: string | null
  issues_json: string | null
  confidence_score: number | null
  created_at: string
}

export interface AgentReviewCreate {
  reviewer_agent_id: number
  decision: string
  risk_level?: string
  comments?: string | null
  issues_json?: string | null
  confidence_score?: number | null
}

export interface ApprovalPolicy {
  id: number
  name: string
  project_id: number | null
  enabled: boolean
  max_risk_level_for_auto_approve: string
  require_tests_passed: boolean
  require_sonar_passed: boolean
  require_no_security_issues: boolean
  allow_auto_approve_docs_only: boolean
  allow_auto_approve_frontend_style_only: boolean
  forbid_auto_merge_main: boolean
  forbid_auto_deploy_prod: boolean
  created_at: string
  updated_at: string
}

export interface ApprovalPolicyCreate {
  name: string
  project_id?: number | null
  enabled?: boolean
  max_risk_level_for_auto_approve?: string
  require_tests_passed?: boolean
  require_sonar_passed?: boolean
  require_no_security_issues?: boolean
  allow_auto_approve_docs_only?: boolean
  allow_auto_approve_frontend_style_only?: boolean
  forbid_auto_merge_main?: boolean
  forbid_auto_deploy_prod?: boolean
}

export interface ApprovalPolicyUpdate {
  name?: string
  project_id?: number | null
  enabled?: boolean
  max_risk_level_for_auto_approve?: string
  require_tests_passed?: boolean
  require_sonar_passed?: boolean
  require_no_security_issues?: boolean
  allow_auto_approve_docs_only?: boolean
  allow_auto_approve_frontend_style_only?: boolean
  forbid_auto_merge_main?: boolean
  forbid_auto_deploy_prod?: boolean
}

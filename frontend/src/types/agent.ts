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

export interface ApprovalDecision {
  id: number
  task_id: number
  agent_run_id: number | null
  agent_review_id: number | null
  policy_id: number | null
  risk_level: string
  auto_approve_allowed: boolean
  human_required: boolean
  decision_reason: string | null
  blocked_reasons_json: string | null
  policy_snapshot_json: string | null
  created_at: string
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

// ── Code Context ──
export interface CodeContextFile {
  path: string
  content: string
  language: string | null
}

export interface CodeContextResponse {
  files: CodeContextFile[]
  artifact_id: number | null
  task_id: number
  file_count: number
  total_size_bytes: number
}

// ── Patch Sandbox ──
export interface ChangedFileEntry {
  path: string
  status: string
  additions: number
  deletions: number
  before_sha256: string | null
  after_sha256: string | null
}

export interface PatchApplyReport {
  applied: boolean
  changed_files: ChangedFileEntry[]
  warnings: string[]
  errors: string[]
}

export interface PatchApplyResult {
  success: boolean
  report: PatchApplyReport
  message: string
  before_after_previews: Record<string, { before: string; after: string }>
}

export interface SandboxArtifactEntry {
  id: number
  artifact_type: string
  filename: string
  content: string | null
  size_bytes: number | null
  sha256: string | null
  metadata_json: string | null
  created_at: string | null
}

export interface SandboxGateBlockedReason {
  reason: string
  detail: string | null
}

export interface SandboxGateDecision {
  passed: boolean
  blocked_reasons: SandboxGateBlockedReason[]
  can_prepare_pr: boolean
  message: string
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
// ── Dispatch Batch / Multi-AI Workspace ──
export type DispatchBatchMode = 'broadcast' | 'routed' | 'pipeline'
export type DispatchJobStatus = 'preview' | 'queued' | 'running' | 'succeeded' | 'failed' | 'blocked' | string

export interface DispatchJobPreview {
  dispatch_job_id: number | null
  sequence_no: number
  question: string
  provider: string
  model: string
  mode: string
  status: DispatchJobStatus
  prompt_hash: string
  context_packet_hash: string
  expected_artifact_type: string
  safety_boundary: Record<string, unknown>
  agent_run_id: number | null
  artifact_ids: number[]
  error_message: string | null
}

export interface DispatchJob extends DispatchJobPreview {}

export interface DispatchBatchResponse {
  dispatch_batch_id: number
  task_id: number
  batch_mode: DispatchBatchMode | string
  status: string
  task_goal: string
  jobs: DispatchJobPreview[]
  summary: Record<string, unknown>
}

export interface DispatchBatch extends DispatchBatchResponse {}
// ── Answer Synthesis / Multi-AI Decision Support ──
export interface AnswerSynthesisPreviewRequest {
  task_id: number
  dispatch_batch_id?: number | null
  include_artifacts?: boolean
  max_artifact_chars?: number
}

export interface ArtifactSummary {
  artifact_id: number
  filename: string | null
  artifact_type: string
  summary: string
  is_truncated: boolean
}

export interface AnswerSynthesisPreviewResponse {
  task_id: number
  dispatch_batch_id: number | null
  synthesis_status: string
  job_count: number
  succeeded_jobs: number
  failed_jobs: number
  blocked_jobs: number
  common_findings: string[]
  disagreements: string[]
  risks: string[]
  recommended_actions: string[]
  next_questions: string[]
  artifact_summaries: ArtifactSummary[]
  source_job_ids: number[]
  source_agent_run_ids: number[]
  source_artifact_ids: number[]
  confidence: number
  safety_notes: string[]
}

// ── AI Handoff Packet / Next AI Onboarding ──
export interface AiHandoffPreviewRequest {
  project_id: number
  task_id?: number | null
  include_recent_batches?: boolean
  include_answer_synthesis?: boolean
  include_safety_rules?: boolean
  max_chars?: number
}

export interface AiHandoffSourceIds {
  project_id: number
  task_id: number | null
  dispatch_batch_ids: number[]
  dispatch_job_ids: number[]
  agent_run_ids: number[]
  artifact_ids: number[]
}

export interface AiHandoffPreviewResponse {
  project_id: number
  task_id: number | null
  handoff_status: string
  project_snapshot: Record<string, unknown>
  current_task_summary: Record<string, unknown>
  recent_capabilities: string[]
  current_master_commit_hint: string
  current_pr_summary: Record<string, unknown>
  recent_dispatch_summary: Record<string, unknown>
  answer_synthesis_summary: Record<string, unknown>
  safety_rules: string[]
  next_recommended_steps: string[]
  next_ai_prompt: string
  source_ids: AiHandoffSourceIds
  redaction_applied: boolean
  safety_notes: string[]
}

// ── Real AI Dispatch Run ──
export type AiDispatchMode = 'planning' | 'review' | 'risk' | 'patch_generation'

export interface AiDispatchRequest {
  task_goal: string
  module_name?: string
  task_type?: string
  mode: AiDispatchMode
  task_id?: number | null
  project_id: number
}

export interface AiDispatchSafetyGate {
  execution_enabled: boolean
  openai_key_present: boolean
  provider_allowed: boolean
  mode_valid: boolean
  budget_ok: boolean
  gate_passed: boolean
}

export interface AiDispatchDryRunResponse {
  provider: string
  model: string
  mode: string
  prompt_hash: string
  context_packet_hash: string
  estimated_tokens: number
  safety_gate: AiDispatchSafetyGate
  would_dispatch: boolean
}

export interface AiExecuteStep {
  step: string
  status: string
  details?: string | null
}

export interface AiDispatchExecuteResponse {
  agent_run_id: number
  task_id: number | null
  status: string
  output_summary?: string | null
  output_diff?: string | null
  artifacts: Record<string, unknown>[]
  events: Record<string, unknown>[]
  sandbox_applied: boolean
  sandbox_gate_passed: boolean
  sandbox_gate_blocked_reasons: string[]
  pipeline_status: string
  prompt_hash: string
  context_packet_hash: string
  token_usage: Record<string, unknown>
  steps: AiExecuteStep[]
}

// ── MCP Bridge / Read-only dry-run tool preview ──
export interface McpToolDescriptor {
  name: string
  description: string
  read_only: boolean
  dry_run_only: boolean
  safety_notes: string[]
}

export interface McpCallRequest {
  tool: string
  arguments: Record<string, any>
}

export interface McpCallResponse {
  tool: string
  status: string
  data: Record<string, any>
  error_message: string
  read_only: boolean
  persisted: boolean
  safety_notes: string[]
}

// ── Browser AI / Local Web AI Provider ──
export type BrowserAiPromptSource = 'task_goal' | 'handoff_packet' | 'answer_synthesis' | 'custom_prompt'
export type BrowserAiProvider = 'custom' | 'chatgpt_web' | 'claude_web' | 'gemini_web' | 'deepseek_web' | 'kimi_web'

export interface BrowserAiRequest {
  project_id: number
  task_id: number
  provider: BrowserAiProvider
  target_url: string
  prompt_source: BrowserAiPromptSource
  custom_prompt?: string
  input_selector: string
  send_selector: string
  response_selector: string
  scroll_container_selector?: string
  copy_button_selector?: string
  login_hint_selector?: string
  timeout_seconds: number
}

export interface BrowserAiProviderProfile {
  provider: BrowserAiProvider
  display_name: string
  target_url: string
  target_url_hint: string
  input_selector: string
  send_selector: string
  response_selector: string
  scroll_container_selector: string
  copy_button_selector: string
  login_hint_selector: string
  login_hint_text: string
  selectors_configured: boolean
  login_required_hint: boolean
  editable: boolean
  best_effort_note: string
}

export interface BrowserAiSafetyGate {
  browser_ai_enabled: boolean
  provider_allowed: boolean
  provider_valid: boolean
  prompt_source_valid: boolean
  selectors_present: boolean
  target_url_present: boolean
  timeout_ok: boolean
  gate_passed: boolean
  blocked_reasons: string[]
}

export interface BrowserAiStep {
  name: string
  status: string
  message: string
  sensitive: boolean
}

export interface BrowserAiResponse {
  status: string
  provider: string
  prompt_hash: string
  answer_preview: string
  agent_run_id: number | null
  artifact_id: number | null
  error_message: string | null
  safety_gate: BrowserAiSafetyGate
  browser_opened: boolean
  persisted: boolean
  steps: BrowserAiStep[]
}

// ── Multi-AI Evidence Run / Evidence collection only ──
export type MultiAiEvidenceRunMode = 'broadcast' | 'routed'
export type MultiAiEvidencePromptSource = 'task_goal' | 'handoff_packet' | 'answer_synthesis' | 'custom_prompt'

export interface MultiAiEvidenceRoleRequest {
  role: string
  provider: BrowserAiProvider
  prompt?: string
}

export interface MultiAiEvidenceRunRequest {
  task_id: number
  mode: MultiAiEvidenceRunMode
  providers: BrowserAiProvider[]
  roles: MultiAiEvidenceRoleRequest[]
  prompt_source: MultiAiEvidencePromptSource
  custom_prompt?: string
  concurrency_limit: number
  timeout_seconds?: number | null
  target_url?: string
  input_selector?: string
  send_selector?: string
  response_selector?: string
  scroll_container_selector?: string
  copy_button_selector?: string
  login_hint_selector?: string
}

export interface MultiAiEvidenceSafetyGate {
  mode_valid: boolean
  prompt_source_valid: boolean
  providers_known: boolean
  providers_allowed: boolean
  job_count_ok: boolean
  browser_ai_enabled: boolean
  gate_passed: boolean
  blocked_reasons: string[]
  safety_notes: string[]
}

export interface MultiAiEvidenceJobResponse {
  dispatch_job_id: number | null
  sequence_no: number
  provider: string
  role: string
  status: string
  prompt_source: string
  prompt_hash: string
  question: string
  error_message: string | null
  agent_run_id: number | null
  artifact_id: number | null
  artifact_ids: number[]
  answer_preview: string
}

export interface MultiAiEvidenceRunResponse {
  evidence_run_id: number | null
  dispatch_batch_id: number | null
  task_id: number
  mode: string
  prompt_source: string
  providers: string[]
  jobs: MultiAiEvidenceJobResponse[]
  estimated_job_count: number
  concurrency_limit: number
  concurrency_note: string
  overall_status: string
  safety_gate: MultiAiEvidenceSafetyGate
  read_only: boolean
  persisted: boolean
  synthesis_refreshed: boolean
  synthesis_status: string
  source_artifact_ids: number[]
  error_message: string
}

// ── Repair Loop / Failure Evidence preview only ──
export type RepairFailureType =
  | 'sandbox_failed'
  | 'sandbox_gate_blocked'
  | 'verification_failed'
  | 'ci_failed'
  | 'sonar_failed'
  | 'review_blocked'
  | 'browser_ai_failed'
  | 'multi_ai_evidence_partial'

export interface FailureEvidenceSource {
  agent_run_id?: number | null
  artifact_id?: number | null
  dispatch_batch_id?: number | null
  dispatch_job_id?: number | null
}

export interface FailureEvidencePreviewRequest {
  task_id: number
  failure_type: RepairFailureType
  source: FailureEvidenceSource
  max_excerpt_chars: number
}

export interface FailureEvidenceRedactionStatus {
  redaction_applied: boolean
  truncated: boolean
  max_chars: number
}

export interface FailureEvidencePacketResponse {
  task_id: number
  project_id: number
  failure_type: RepairFailureType
  failed_step: string
  failed_command_summary: string
  stdout_excerpt: string
  stderr_excerpt: string
  blocked_reasons: string[]
  related_agent_run_ids: number[]
  related_artifact_ids: number[]
  related_dispatch_batch_id: number | null
  related_dispatch_job_ids: number[]
  source_commit_hint: string
  safety_notes: string[]
  redaction_status: FailureEvidenceRedactionStatus
  read_only: boolean
  persisted: boolean
}

export interface RepairPacketGenerateRequest {
  task_id: number
  failure_evidence: FailureEvidencePacketResponse
  analysis_mode: 'broadcast' | 'routed'
  providers: string[]
  roles: MultiAiEvidenceRoleRequest[]
  max_attempts: number
}

export interface RepairEvidenceBySource {
  source: string
  summary: string
  artifact_ids: number[]
  agent_run_ids: number[]
  dispatch_batch_id: number | null
  dispatch_job_ids: number[]
}

export interface RepairPacketResponse {
  task_id: number
  project_id: number
  failure_summary: string
  suspected_root_causes: string[]
  evidence_by_source: RepairEvidenceBySource[]
  multi_ai_findings: string[]
  disagreements: string[]
  recommended_fix_strategy: string
  files_likely_involved: string[]
  commands_to_verify: string[]
  risks: string[]
  human_decision_required: boolean
  codex_handoff_prompt: string
  max_attempts: number
  do_not_do: string[]
  repair_packet_artifact_id: number | null
  source_failure_type: RepairFailureType
  source_artifact_ids: number[]
  source_agent_run_ids: number[]
  source_dispatch_batch_id: number | null
  source_dispatch_job_ids: number[]
  analysis_dispatch_batch_id: number | null
  analysis_status: string
  read_only: boolean
  persisted: boolean
  safety_notes: string[]
}

export interface RepairHandoffPreviewRequest {
  task_id: number
  repair_packet_artifact_id: number
  target: 'codex' | 'omx' | 'generic_ai'
}

export interface RepairHandoffPreviewResponse {
  task_id: number
  project_id: number
  target: 'codex' | 'omx' | 'generic_ai'
  handoff_prompt: string
  safety_notes: string[]
  source_repair_packet_artifact_id: number
  requires_master_verification: boolean
  read_only: boolean
  persisted: boolean
}

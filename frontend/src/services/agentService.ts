import client from './api'
import type {
  AgentProfile, AgentProfileCreate, AgentProfileUpdate,
  AgentRun, AgentRunCreate, AgentRunUpdate, AgentRunSubmitResult,
  AgentReview, AgentReviewCreate,
  ApprovalPolicy, ApprovalPolicyCreate, ApprovalPolicyUpdate,
  CodeContextResponse, PatchApplyResult, SandboxArtifactEntry,
  SandboxGateDecision, DispatchBatchResponse, AnswerSynthesisPreviewRequest, AnswerSynthesisPreviewResponse,
  AiHandoffPreviewRequest, AiHandoffPreviewResponse,
  AiDispatchRequest, AiDispatchDryRunResponse, AiDispatchExecuteResponse,
} from '../types/agent'

// ── AgentProfile ──
export async function fetchAgents(): Promise<AgentProfile[]> {
  const { data } = await client.get('/agents')
  return data.data || []
}

export async function createAgent(body: AgentProfileCreate): Promise<AgentProfile> {
  const { data } = await client.post('/agents', body)
  return data.data
}

export async function fetchAgent(id: number): Promise<AgentProfile> {
  const { data } = await client.get(`/agents/${id}`)
  return data.data
}

export async function updateAgent(id: number, body: AgentProfileUpdate): Promise<AgentProfile> {
  const { data } = await client.patch(`/agents/${id}`, body)
  return data.data
}

export async function deleteAgent(id: number): Promise<void> {
  await client.delete(`/agents/${id}`)
}

// ── AgentRun ──
export async function createAgentRun(taskId: number, body: AgentRunCreate): Promise<AgentRun> {
  const { data } = await client.post(`/tasks/${taskId}/agent-runs`, body)
  return data.data
}

export async function fetchAgentRuns(taskId: number): Promise<AgentRun[]> {
  const { data } = await client.get(`/tasks/${taskId}/agent-runs`)
  return data.data || []
}

export async function fetchAgentRun(taskId: number, runId: number): Promise<AgentRun> {
  const { data } = await client.get(`/tasks/${taskId}/agent-runs/${runId}`)
  return data.data
}

export async function updateAgentRun(taskId: number, runId: number, body: AgentRunUpdate): Promise<AgentRun> {
  const { data } = await client.patch(`/tasks/${taskId}/agent-runs/${runId}`, body)
  return data.data
}

export async function submitAgentRunResult(taskId: number, runId: number, body: AgentRunSubmitResult): Promise<AgentRun> {
  const { data } = await client.post(`/tasks/${taskId}/agent-runs/${runId}/submit-result`, body)
  return data.data
}

// ── AgentReview ──
export async function createAgentReview(taskId: number, runId: number, body: AgentReviewCreate): Promise<AgentReview> {
  const { data } = await client.post(`/tasks/${taskId}/agent-runs/${runId}/review`, body)
  return data.data
}

export async function fetchAgentReviews(taskId: number): Promise<AgentReview[]> {
  const { data } = await client.get(`/tasks/${taskId}/agent-reviews`)
  return data.data || []
}

// ── ApprovalPolicy ──
export async function fetchApprovalPolicies(): Promise<ApprovalPolicy[]> {
  const { data } = await client.get('/approval-policies')
  return data.data || []
}

export async function createApprovalPolicy(body: ApprovalPolicyCreate): Promise<ApprovalPolicy> {
  const { data } = await client.post('/approval-policies', body)
  return data.data
}

export async function fetchApprovalPolicy(id: number): Promise<ApprovalPolicy> {
  const { data } = await client.get(`/approval-policies/${id}`)
  return data.data
}

export async function updateApprovalPolicy(id: number, body: ApprovalPolicyUpdate): Promise<ApprovalPolicy> {
  const { data } = await client.patch(`/approval-policies/${id}`, body)
  return data.data
}

export async function deleteApprovalPolicy(id: number): Promise<void> {
  await client.delete(`/approval-policies/${id}`)
}

export async function fetchApprovalDecisions(taskId: number): Promise<any[]> {
  const { data } = await client.get(`/tasks/${taskId}/approval-decisions`)
  return data.data || data || []
}

// ── Code Context ──
export async function fetchCodeContext(taskId: number): Promise<CodeContextResponse | null> {
  try {
    const { data } = await client.get(`/tasks/${taskId}/code-context`)
    return data.data || null
  } catch {
    return null
  }
}

// ── Patch Sandbox ──
export async function applyPatchInSandbox(taskId: number, runId: number): Promise<PatchApplyResult> {
  const { data } = await client.post(`/tasks/${taskId}/agent-runs/${runId}/sandbox/apply-patch`)
  return data.data
}

export async function fetchSandboxResults(taskId: number): Promise<SandboxArtifactEntry[]> {
  const { data } = await client.get(`/tasks/${taskId}/sandbox/patch-results`)
  return data.data || []
}

// ── Sandbox Gate ──
export async function fetchSandboxGate(taskId: number): Promise<SandboxGateDecision> {
  const { data } = await client.get(`/tasks/${taskId}/sandbox/gate`)
  return data.data
}

export async function evaluateSandboxGate(taskId: number): Promise<SandboxGateDecision> {
  const { data } = await client.post(`/tasks/${taskId}/sandbox/evaluate-gate`)
  return data.data
}
// ── Dispatch Batches / Multi-AI Workspace ──
export async function fetchDispatchBatches(taskId: number): Promise<DispatchBatchResponse[]> {
  const { data } = await client.get(`/tasks/${taskId}/dispatch-batches`)
  return data.data || []
}
// ── Answer Synthesis / Multi-AI Decision Support ──
export async function previewAnswerSynthesis(body: AnswerSynthesisPreviewRequest): Promise<AnswerSynthesisPreviewResponse> {
  const { data } = await client.post('/answer-synthesis/preview', body)
  return data.data
}

// ── AI Handoff Packet / Next AI Onboarding ──
export async function previewAiHandoff(body: AiHandoffPreviewRequest): Promise<AiHandoffPreviewResponse> {
  const { data } = await client.post('/ai-handoff/preview', body)
  return data.data
}

// ── Real AI Dispatch Run ──
export async function dryRunAiDispatch(body: AiDispatchRequest): Promise<AiDispatchDryRunResponse> {
  const { data } = await client.post('/ai-dispatch/dry-run', body)
  return data.data
}

export async function executeAiDispatch(body: AiDispatchRequest): Promise<AiDispatchExecuteResponse> {
  const { data } = await client.post('/ai-dispatch/execute', body)
  return data.data
}

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
  BrowserAiProviderProfile, BrowserAiRequest, BrowserAiResponse,
  McpToolDescriptor, McpCallRequest, McpCallResponse,
  MultiAiEvidenceRunRequest, MultiAiEvidenceRunResponse,
  FailureEvidencePreviewRequest, FailureEvidencePacketResponse,
  RepairAttemptCreateRequest, RepairAttemptResponse, RepairHandoffPreviewRequest,
  RepairHandoffPreviewResponse, RepairPacketGenerateRequest, RepairPacketResponse,
  RepairVerificationResultRequest,
  TimelineResponse, EvidenceBoardResponse,
  ProjectMemoryResponse, ProjectMemorySummaryResponse,
  MastermindReviewPacketPreviewRequest, MastermindReviewPacketPreviewResponse,
  MastermindReviewExecuteRequest, MastermindReviewExecuteResponse,
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

// ── Browser AI / Local Web AI Provider ──
export async function fetchBrowserAiProviderProfiles(): Promise<BrowserAiProviderProfile[]> {
  const { data } = await client.get('/browser-ai/provider-profiles')
  return data.data || []
}

export async function dryRunBrowserAi(body: BrowserAiRequest): Promise<BrowserAiResponse> {
  const { data } = await client.post('/browser-ai/dry-run', body)
  return data.data
}

export async function executeBrowserAi(body: BrowserAiRequest): Promise<BrowserAiResponse> {
  const { data } = await client.post('/browser-ai/execute', body)
  return data.data
}

// ── Multi-AI Evidence Run / Evidence collection only ──
export async function previewMultiAiEvidenceRun(body: MultiAiEvidenceRunRequest): Promise<MultiAiEvidenceRunResponse> {
  const { data } = await client.post('/multi-ai-evidence-runs/preview', body)
  return data.data
}

export async function executeMultiAiEvidenceRun(body: MultiAiEvidenceRunRequest): Promise<MultiAiEvidenceRunResponse> {
  const { data } = await client.post('/multi-ai-evidence-runs/execute', body)
  return data.data
}

export async function fetchMultiAiEvidenceRuns(taskId: number): Promise<MultiAiEvidenceRunResponse[]> {
  const { data } = await client.get(`/tasks/${taskId}/multi-ai-evidence-runs`)
  return data.data || []
}

// ── Repair Loop / Failure Evidence preview only ──
export async function previewFailureEvidencePacket(body: FailureEvidencePreviewRequest): Promise<FailureEvidencePacketResponse> {
  const { data } = await client.post('/repair-loop/failure-evidence/preview', body)
  return data.data
}

export async function generateRepairPacket(body: RepairPacketGenerateRequest): Promise<RepairPacketResponse> {
  const { data } = await client.post('/repair-loop/repair-packet/generate', body)
  return data.data
}

export async function previewRepairHandoff(body: RepairHandoffPreviewRequest): Promise<RepairHandoffPreviewResponse> {
  const { data } = await client.post('/repair-loop/codex-handoff/preview', body)
  return data.data
}

export async function createRepairAttempt(body: RepairAttemptCreateRequest): Promise<RepairAttemptResponse> {
  const { data } = await client.post('/repair-loop/attempts', body)
  return data.data
}

export async function fetchRepairAttempts(taskId: number): Promise<RepairAttemptResponse[]> {
  const { data } = await client.get(`/tasks/${taskId}/repair-attempts`)
  return data.data || []
}

export async function markRepairHandoffCreated(attemptId: number): Promise<RepairAttemptResponse> {
  const { data } = await client.post(`/repair-loop/attempts/${attemptId}/handoff-created`)
  return data.data
}

export async function importRepairVerificationResult(
  attemptId: number,
  body: RepairVerificationResultRequest,
): Promise<RepairAttemptResponse> {
  const { data } = await client.post(`/repair-loop/attempts/${attemptId}/verification-result`, body)
  return data.data
}

export async function stopRepairAttempt(attemptId: number): Promise<RepairAttemptResponse> {
  const { data } = await client.post(`/repair-loop/attempts/${attemptId}/stop`)
  return data.data
}

// ── Evidence Board / Run Timeline read-only summaries ──
export async function fetchTaskTimeline(taskId: number): Promise<TimelineResponse> {
  const { data } = await client.get(`/tasks/${taskId}/timeline`)
  return data.data
}

export async function fetchTaskEvidenceBoard(taskId: number): Promise<EvidenceBoardResponse> {
  const { data } = await client.get(`/tasks/${taskId}/evidence-board`)
  return data.data
}

// ── Project Memory read-only project context ──
export async function fetchProjectMemory(projectId: number): Promise<ProjectMemoryResponse> {
  const { data } = await client.get(`/projects/${projectId}/memory`)
  return data.data
}

export async function fetchProjectMemorySummary(projectId: number): Promise<ProjectMemorySummaryResponse> {
  const { data } = await client.get(`/projects/${projectId}/memory/summary`)
  return data.data
}

// ── Mastermind Review / advisory Browser AI review trial ──
export async function previewMastermindReviewPacket(
  taskId: number,
  body: MastermindReviewPacketPreviewRequest,
): Promise<MastermindReviewPacketPreviewResponse> {
  const { data } = await client.post(`/tasks/${taskId}/mastermind-review/packet-preview`, body)
  return data.data
}

export async function executeMastermindReview(
  taskId: number,
  body: MastermindReviewExecuteRequest,
): Promise<MastermindReviewExecuteResponse> {
  const { data } = await client.post(`/tasks/${taskId}/mastermind-review/execute`, body)
  return data.data
}

// ── MCP Bridge / read-only + dry-run tool semantics ──
export async function fetchMcpTools(): Promise<McpToolDescriptor[]> {
  const { data } = await client.get('/mcp/tools')
  return data.data || []
}

export async function callMcpTool(body: McpCallRequest): Promise<McpCallResponse> {
  const { data } = await client.post('/mcp/call', body)
  return data.data
}

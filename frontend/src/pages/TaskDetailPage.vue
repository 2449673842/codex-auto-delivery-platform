<template>
  <div class="page" v-if="task">
    <header class="detail-header">
      <div>
        <h1>{{ task.title }}</h1>
        <p class="meta">
          {{ task.project_name }} · #{{ task.id }}
          <StatusBadge :status="task.status" />
          <span class="priority" :class="task.priority">{{ task.priority }}</span>
        </p>
      </div>
      <router-link :to="`/tasks?project_id=${task.project_id}`" class="back-link">← 返回列表</router-link>
    </header>

    <div class="action-bar card">
      <button
        v-for="act in availableActions"
        :key="act.action"
        class="btn btn-sm"
        :class="act.cls"
        @click="handleAction(act.action)"
        :disabled="actionLoading"
      >
        {{ act.label }}
      </button>
      <span v-if="isArchived" class="archived-label">已归档，不可操作</span>
    </div>

    <div v-if="showResultForm" class="result-form card">
      <h3>提交执行结果</h3>
      <label>
        执行摘要
        <textarea v-model="resultSummary" placeholder="描述执行结果，如遇问题请说明..." rows="5"></textarea>
      </label>
      <div class="form-actions">
        <button class="btn btn-primary" @click="confirmSubmitResult">确认提交</button>
        <button class="btn" @click="showResultForm = false">取消</button>
      </div>
    </div>

    <div class="detail-body">
      <section class="card">
        <h2>需求描述</h2>
        <pre class="description-text">{{ task.description || '（无描述）' }}</pre>
      </section>

      <section v-if="task.result_summary" class="card">
        <h2>执行结果</h2>
        <pre class="description-text">{{ task.result_summary }}</pre>
      </section>

      <section v-if="task.ticket_content" class="card">
        <h2>执行任务单</h2>
        <TicketPreview :content="task.ticket_content" />
      </section>

      <section class="card">
        <h2>角色信息</h2>
        <div class="roles">
          <div><strong>Planner:</strong> {{ task.planner || '-' }}</div>
          <div><strong>Executor:</strong> {{ task.executor || '-' }}</div>
          <div><strong>Reviewer:</strong> {{ task.reviewer || '-' }}</div>
          <div><strong>Approver:</strong> {{ task.human_approver || '-' }}</div>
        </div>
      </section>

      <!-- Agent Runs -->
      <section class="card">
        <div class="section-header">
          <h2>Agent 运行</h2>
          <button class="btn btn-sm btn-primary" @click="showAgentRunForm = true">+ 创建 AgentRun</button>
        </div>

        <div v-if="showAgentRunForm" class="inline-form">
          <label>
            Agent
            <select v-model="agentRunForm.agent_id">
              <option value="">请选择</option>
              <option v-for="a in agents" :key="a.id" :value="a.id" :disabled="!a.enabled">
                {{ a.name }} ({{ a.agent_type }})
              </option>
            </select>
          </label>
          <label>
            运行类型
            <select v-model="agentRunForm.run_type">
              <option value="plan">规划 (Plan)</option>
              <option value="execute">执行 (Execute)</option>
              <option value="review">审查 (Review)</option>
              <option value="test">测试 (Test)</option>
              <option value="remediate">修复 (Remediate)</option>
            </select>
          </label>
          <label>
            输入提示
            <textarea v-model="agentRunForm.input_prompt" rows="4" placeholder="输入 prompt..."></textarea>
          </label>
          <label>分支<input v-model="agentRunForm.branch" placeholder="可选" /></label>
          <div class="form-actions">
            <button class="btn btn-primary btn-sm" @click="handleCreateAgentRun" :disabled="!agentRunForm.agent_id">创建</button>
            <button class="btn btn-sm" @click="showAgentRunForm = false">取消</button>
          </div>
        </div>

        <div v-if="agentRuns.length === 0" class="empty-state" style="margin-top: 12px;">
          <p>暂无 Agent 运行记录</p>
        </div>
        <div v-for="r in agentRuns" :key="r.id" class="agent-run-item">
          <div class="agent-run-header">
            <strong>{{ runTypeLabel(r.run_type) }}</strong>
            <span class="run-status-badge" :class="r.status">{{ AGENT_RUN_STATUS_LABELS[r.status] || r.status }}</span>
            <span class="run-risk" :class="r.risk_level">风险: {{ r.risk_level }}</span>
            <span class="run-attempt">#{{ r.attempt_no }}</span>
          </div>
          <div class="agent-run-meta">
            Agent #{{ r.agent_id }} · {{ r.branch || '无分支' }}
            <span v-if="r.duration_ms"> · {{ Math.round(r.duration_ms / 1000) }}s</span>
          </div>
          <p v-if="r.input_prompt" class="run-prompt">{{ r.input_prompt }}</p>
          <p v-if="r.output_summary" class="run-output">{{ r.output_summary }}</p>
          <p v-if="r.error_message" class="run-error">{{ r.error_message }}</p>
          <div v-if="r.output_diff" class="run-diff">
            <DiffViewer :content="r.output_diff" />
          </div>
          <div class="agent-run-actions">
            <button v-if="r.status === 'queued'" class="btn btn-sm btn-primary" @click="startAgentRun(r)">Start</button>
            <button v-if="r.status === 'queued' || r.status === 'running'" class="btn btn-sm btn-warn" @click="cancelAgentRun(r)">Cancel</button>
            <button v-if="r.status === 'running'" class="btn btn-sm" @click="showSubmitResult(r)">提交结果</button>
          </div>

          <div v-if="submitFormRunId === r.id" class="inline-form">
            <label>
              结果状态
              <select v-model="submitForm.status">
                <option value="succeeded">成功 (Succeeded)</option>
                <option value="failed">失败 (Failed)</option>
              </select>
            </label>
            <label>输出摘要<textarea v-model="submitForm.output_summary" rows="3"></textarea></label>
            <label>错误信息<textarea v-model="submitForm.error_message" rows="2"></textarea></label>
            <label>Diff 输出<textarea v-model="submitForm.output_diff" rows="3"></textarea></label>
            <label>日志输出<textarea v-model="submitForm.output_log" rows="3"></textarea></label>
            <div class="form-actions">
              <button class="btn btn-primary btn-sm" @click="confirmSubmitRunResult(r)">确认</button>
              <button class="btn btn-sm" @click="submitFormRunId = null">取消</button>
            </div>
          </div>
        </div>
      </section>

      <!-- Agent Review -->
      <section class="card">
        <div class="section-header">
          <h2>Agent 审查</h2>
          <button v-if="agentRuns.length > 0" class="btn btn-sm btn-primary" @click="showAgentReviewForm = true">+ 提交 AI 审查</button>
        </div>
        <p class="section-note">AgentReview 是 AI 预审建议，不等同于人类最终审批</p>

        <div v-if="showAgentReviewForm" class="inline-form">
          <label>
            审查 Agent
            <select v-model="agentReviewForm.reviewer_agent_id">
              <option value="">请选择</option>
              <option v-for="a in agents" :key="a.id" :value="a.id" :disabled="!a.enabled">
                {{ a.name }} ({{ a.agent_type }})
              </option>
            </select>
          </label>
          <label>
            决策
            <select v-model="agentReviewForm.decision">
              <option value="approved">通过 (Approved)</option>
              <option value="changes_requested">要求修改 (Changes Requested)</option>
              <option value="rejected">拒绝 (Rejected)</option>
              <option value="human_required">需要人工审批 (Human Required)</option>
            </select>
          </label>
          <label>
            风险等级
            <select v-model="agentReviewForm.risk_level">
              <option value="low">低 (Low)</option>
              <option value="medium">中 (Medium)</option>
              <option value="high">高 (High)</option>
              <option value="critical">严重 (Critical)</option>
            </select>
          </label>
          <label>置信度 (0-1)<input v-model.number="agentReviewForm.confidence_score" type="number" min="0" max="1" step="0.1" /></label>
          <label>审查意见<textarea v-model="agentReviewForm.comments" rows="3"></textarea></label>
          <div class="form-actions">
            <button class="btn btn-primary btn-sm" @click="handleCreateAgentReview" :disabled="!agentReviewForm.reviewer_agent_id">提交</button>
            <button class="btn btn-sm" @click="showAgentReviewForm = false">取消</button>
          </div>
        </div>

        <div v-if="agentReviews.length === 0" class="empty-state" style="margin-top: 12px;">
          <p>暂无 AI 审查记录</p>
        </div>
        <div v-for="r in agentReviews" :key="r.id" class="agent-review-item">
          <div class="agent-review-header">
            <span class="review-decision" :class="r.decision">{{ r.decision }}</span>
            <span class="review-risk" :class="r.risk_level">风险: {{ r.risk_level }}</span>
            <span v-if="r.confidence_score !== null" class="review-confidence">置信度: {{ r.confidence_score }}</span>
            <span class="review-time">{{ new Date(r.created_at).toLocaleString() }}</span>
          </div>
          <p class="review-meta">审查 Agent #{{ r.reviewer_agent_id }} · AgentRun #{{ r.agent_run_id }}</p>
          <p v-if="r.comments" class="review-comments">{{ r.comments }}</p>
        </div>
      </section>

      <section class="card">
        <h2>产物</h2>
        <ArtifactTab :task-id="task.id" :task-status="task.status" />
      </section>

      <section class="card">
        <h2>审查记录</h2>
        <ReviewPanel :task-id="task.id" :task-status="task.status" @review-submitted="refresh" />
      </section>

      <section class="card">
        <h2>审计日志</h2>
        <EventTimeline :task-id="task.id" />
      </section>

      <section class="card stub-section">
        <h2>集成（预留）</h2>
        <div class="stub-actions">
          <button class="btn btn-sm" @click="handleStub('create-pr')">创建 PR (Stub)</button>
          <button class="btn btn-sm" @click="handleStub('trigger-ci')">触发 CI (Stub)</button>
          <button class="btn btn-sm" @click="handleStub('trigger-deploy')">部署 (Stub)</button>
        </div>
      </section>
    </div>
  </div>
  <div v-else class="loading">加载中...</div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useTaskStore } from '../stores/taskStore'
import {
  fetchAgents,
  fetchAgentRuns, createAgentRun, updateAgentRun, submitAgentRunResult,
  fetchAgentReviews, createAgentReview,
} from '../services/agentService'
import type { AgentProfile, AgentRun, AgentReview } from '../types/agent'
import { AGENT_RUN_STATUS_LABELS, AGENT_RUN_TYPE_LABELS } from '../types/agent'
import StatusBadge from '../components/StatusBadge.vue'
import TicketPreview from '../components/TicketPreview.vue'
import ArtifactTab from '../components/ArtifactTab.vue'
import ReviewPanel from '../components/ReviewPanel.vue'
import EventTimeline from '../components/EventTimeline.vue'
import DiffViewer from '../components/DiffViewer.vue'

const route = useRoute()
const taskStore = useTaskStore()
const task = ref<any>(null)
const actionLoading = ref(false)
const showResultForm = ref(false)
const resultSummary = ref('')

const agents = ref<AgentProfile[]>([])
const agentRuns = ref<AgentRun[]>([])
const agentReviews = ref<AgentReview[]>([])
const showAgentRunForm = ref(false)
const showAgentReviewForm = ref(false)
const submitFormRunId = ref<number | null>(null)

const agentRunForm = ref({ agent_id: 0, run_type: 'plan', input_prompt: '', branch: '' })
const agentReviewForm = ref({ reviewer_agent_id: 0, decision: 'approved', risk_level: 'low', comments: '', confidence_score: null as number | null })
const submitForm = ref({ status: 'succeeded', output_summary: '', error_message: '', output_diff: '', output_log: '' })

const ACTION_MAP: Record<string, { action: string; label: string; cls: string }[]> = {
  draft: [{ action: 'generate-ticket', label: '生成任务单', cls: 'btn-primary' }],
  ticket_ready: [{ action: 'dispatch', label: '分派给 Executor', cls: 'btn-primary' }],
  dispatched: [{ action: 'submit-result', label: '提交执行结果', cls: 'btn-primary' }],
  result_submitted: [{ action: 'start-review', label: '开始审查', cls: 'btn-primary' }],
  reviewing: [
    { action: 'require-human-approval', label: '需要人工审批', cls: 'btn-warn' },
    { action: 'approve', label: '通过 (Approve)', cls: 'btn-approve' },
    { action: 'reject', label: '拒绝 (Reject)', cls: 'btn-reject' },
    { action: 'request-changes', label: '要求修改', cls: 'btn-warn' },
  ],
  human_required: [
    { action: 'approve', label: '通过 (Approve)', cls: 'btn-approve' },
    { action: 'reject', label: '拒绝 (Reject)', cls: 'btn-reject' },
    { action: 'request-changes', label: '要求修改', cls: 'btn-warn' },
  ],
  changes_requested: [{ action: 'dispatch', label: '重新分派', cls: 'btn-primary' }],
  approved: [{ action: 'archive', label: '归档', cls: 'btn-archive' }],
  rejected: [{ action: 'archive', label: '归档', cls: 'btn-archive' }],
}

const isArchived = computed(() => task.value?.status === 'archived')

const availableActions = computed(() => {
  if (!task.value || isArchived.value) return []
  return ACTION_MAP[task.value.status] || []
})

function runTypeLabel(t: string) {
  return AGENT_RUN_TYPE_LABELS[t] || t
}

onMounted(async () => {
  agents.value = await fetchAgents()
  await refresh()
})

async function refresh() {
  const id = Number(route.params.id)
  task.value = await taskStore.fetchTask(id)
  agentRuns.value = await fetchAgentRuns(id)
  agentReviews.value = await fetchAgentReviews(id)
}

async function handleAction(action: string) {
  if (action === 'submit-result') {
    showResultForm.value = true
    return
  }
  await doTransition(action)
}

async function confirmSubmitResult() {
  await doTransition('submit-result', { result_summary: resultSummary.value })
  showResultForm.value = false
  resultSummary.value = ''
}

async function doTransition(action: string, extra: Record<string, any> = {}) {
  actionLoading.value = true
  try {
    await taskStore.transitionTask(task.value.id, action, { actor: 'human', ...extra })
    await refresh()
  } catch (e: any) {
    alert(e.message)
  } finally {
    actionLoading.value = false
  }
}

async function handleStub(action: string) {
  try {
    const { data } = await (await import('../services/api')).default.post(`/tasks/${task.value.id}/${action}`)
    alert(data.message || 'Stub endpoint called')
  } catch (e: any) {
    alert(e.message)
  }
}

// Agent Run actions
async function handleCreateAgentRun() {
  if (!agentRunForm.value.agent_id) return
  try {
    await createAgentRun(task.value.id, agentRunForm.value)
    agentRunForm.value = { agent_id: 0, run_type: 'plan', input_prompt: '', branch: '' }
    showAgentRunForm.value = false
    agentRuns.value = await fetchAgentRuns(task.value.id)
  } catch (e: any) {
    alert(e.message)
  }
}

async function startAgentRun(r: AgentRun) {
  try {
    await updateAgentRun(task.value.id, r.id, { status: 'running' })
    agentRuns.value = await fetchAgentRuns(task.value.id)
  } catch (e: any) {
    alert(e.message)
  }
}

async function cancelAgentRun(r: AgentRun) {
  try {
    await updateAgentRun(task.value.id, r.id, { status: 'canceled' })
    agentRuns.value = await fetchAgentRuns(task.value.id)
  } catch (e: any) {
    alert(e.message)
  }
}

function showSubmitResult(r: AgentRun) {
  submitFormRunId.value = r.id
  submitForm.value = { status: 'succeeded', output_summary: '', error_message: '', output_diff: '', output_log: '' }
}

async function confirmSubmitRunResult(r: AgentRun) {
  try {
    await submitAgentRunResult(task.value.id, r.id, submitForm.value)
    submitFormRunId.value = null
    agentRuns.value = await fetchAgentRuns(task.value.id)
  } catch (e: any) {
    alert(e.message)
  }
}

// Agent Review actions
async function handleCreateAgentReview() {
  if (!agentReviewForm.value.reviewer_agent_id) return
  try {
    const runId = agentRuns.value.length > 0 ? agentRuns.value[agentRuns.value.length - 1].id : 0
    await createAgentReview(task.value.id, runId, agentReviewForm.value)
    agentReviewForm.value = { reviewer_agent_id: 0, decision: 'approved', risk_level: 'low', comments: '', confidence_score: null }
    showAgentReviewForm.value = false
    agentReviews.value = await fetchAgentReviews(task.value.id)
  } catch (e: any) {
    alert(e.message)
  }
}
</script>

<style scoped>
.page { max-width: 900px; margin: 0 auto; padding: 32px 24px; }
.detail-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.detail-header h1 { font-size: 24px; font-weight: 700; }
.meta { display: flex; gap: 8px; align-items: center; margin-top: 4px; color: var(--color-text-secondary); font-size: 14px; flex-wrap: wrap; }
.back-link { color: var(--color-text-secondary); font-size: 14px; }
.action-bar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; padding: 16px; }
.archived-label { color: var(--color-text-secondary); font-size: 13px; font-style: italic; }
.result-form { margin-bottom: 16px; padding: 20px; }
.result-form h3 { font-size: 16px; font-weight: 600; margin-bottom: 12px; }
.result-form textarea { width: 100%; padding: 8px 12px; border: 1px solid var(--color-border); border-radius: var(--radius); font-size: 14px; font-family: inherit; resize: vertical; }
.form-actions { display: flex; gap: 8px; margin-top: 8px; }
.detail-body { display: flex; flex-direction: column; gap: 20px; }
.detail-body section h2 { font-size: 16px; font-weight: 600; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--color-border); }
.description-text { white-space: pre-wrap; font-family: inherit; font-size: 14px; line-height: 1.6; color: var(--color-text-secondary); }
.roles { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; font-size: 14px; }
.stub-actions { display: flex; gap: 8px; }
.stub-section { opacity: 0.7; }
.loading { text-align: center; padding: 60px; color: var(--color-text-secondary); }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--color-border); }
.section-header h2 { font-size: 16px; font-weight: 600; margin-bottom: 0; padding-bottom: 0; border-bottom: none; }
.section-note { font-size: 12px; color: var(--color-text-secondary); font-style: italic; margin-bottom: 12px; }
.inline-form { background: var(--color-bg); border-radius: var(--radius); padding: 16px; display: flex; flex-direction: column; gap: 10px; margin-bottom: 16px; }
.inline-form label { font-size: 13px; }
.inline-form input, .inline-form select, .inline-form textarea { width: 100%; }
.agent-run-item { padding: 12px; margin-top: 8px; border: 1px solid var(--color-border); border-radius: var(--radius); }
.agent-run-header { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 4px; }
.agent-run-header strong { font-size: 14px; }
.run-status-badge { padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 500; }
.run-status-badge.queued { background: #f5f5f5; color: #616161; }
.run-status-badge.running { background: #e3f2fd; color: #1565c0; }
.run-status-badge.succeeded { background: #e8f5e9; color: #2e7d32; }
.run-status-badge.failed { background: #ffebee; color: #c62828; }
.run-status-badge.canceled { background: #f5f5f5; color: #9e9e9e; }
.run-status-badge.human_required { background: #fce4ec; color: #c62828; }
.run-risk { padding: 2px 8px; border-radius: 10px; font-size: 11px; }
.run-risk.low { background: #e8f5e9; color: #2e7d32; }
.run-risk.medium { background: #fff3e0; color: #e65100; }
.run-risk.high { background: #ffebee; color: #c62828; }
.run-risk.critical { background: #fce4ec; color: #b71c1c; }
.run-attempt { font-size: 12px; color: var(--color-text-secondary); margin-left: auto; }
.agent-run-meta { font-size: 12px; color: var(--color-text-secondary); margin-bottom: 4px; }
.run-prompt { font-size: 13px; color: var(--color-text-secondary); background: #f5f5f5; padding: 8px; border-radius: 6px; margin: 4px 0; white-space: pre-wrap; }
.run-output { font-size: 13px; color: var(--color-text); margin: 4px 0; white-space: pre-wrap; }
.run-error { font-size: 13px; color: var(--color-danger); margin: 4px 0; white-space: pre-wrap; }
.run-diff { margin: 4px 0; }
.agent-run-actions { display: flex; gap: 6px; margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--color-border); }
.agent-review-item { padding: 10px 0; border-bottom: 1px solid var(--color-border); }
.agent-review-item:last-child { border-bottom: none; }
.agent-review-header { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 4px; }
.review-decision { padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; }
.review-decision.approved { background: #e8f5e9; color: #2e7d32; }
.review-decision.rejected { background: #ffebee; color: #c62828; }
.review-decision.changes_requested { background: #fff3e0; color: #e65100; }
.review-decision.human_required { background: #fce4ec; color: #c62828; }
.review-risk { padding: 2px 8px; border-radius: 10px; font-size: 11px; }
.review-risk.low { background: #e8f5e9; color: #2e7d32; }
.review-risk.medium { background: #fff3e0; color: #e65100; }
.review-risk.high { background: #ffebee; color: #c62828; }
.review-risk.critical { background: #fce4ec; color: #b71c1c; }
.review-confidence { font-size: 12px; color: var(--color-text-secondary); }
.review-time { font-size: 12px; color: var(--color-text-secondary); margin-left: auto; }
.review-meta { font-size: 12px; color: var(--color-text-secondary); }
.review-comments { font-size: 13px; color: var(--color-text-secondary); margin-top: 4px; }
.btn-primary { background: var(--color-primary); color: #fff; border-color: var(--color-primary); }
.btn-approve { background: #4caf50; color: #fff; border-color: #4caf50; }
.btn-reject { background: #f44336; color: #fff; border-color: #f44336; }
.btn-warn { background: #ff9800; color: #fff; border-color: #ff9800; }
.btn-archive { background: #607d8b; color: #fff; border-color: #607d8b; }
.btn-sm { padding: 6px 14px; font-size: 13px; }
</style>

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
import StatusBadge from '../components/StatusBadge.vue'
import TicketPreview from '../components/TicketPreview.vue'
import ArtifactTab from '../components/ArtifactTab.vue'
import ReviewPanel from '../components/ReviewPanel.vue'
import EventTimeline from '../components/EventTimeline.vue'

const route = useRoute()
const taskStore = useTaskStore()
const task = ref<any>(null)
const actionLoading = ref(false)
const showResultForm = ref(false)
const resultSummary = ref('')

const ACTION_MAP: Record<string, { action: string; label: string; cls: string }[]> = {
  draft: [{ action: 'generate-ticket', label: '生成任务单', cls: 'btn-primary' }],
  ticket_ready: [{ action: 'dispatch', label: '分派给 Executor', cls: 'btn-primary' }],
  dispatched: [{ action: 'submit-result', label: '提交执行结果', cls: 'btn-primary' }],
  result_submitted: [{ action: 'start-review', label: '开始审查', cls: 'btn-primary' }],
  reviewing: [
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

onMounted(refresh)

async function refresh() {
  const id = Number(route.params.id)
  task.value = await taskStore.fetchTask(id)
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
</style>

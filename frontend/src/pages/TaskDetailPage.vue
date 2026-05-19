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

    <div class="action-bar">
      <button
        v-for="act in availableActions"
        :key="act.action"
        class="btn btn-sm"
        :class="act.cls"
        @click="handleAction(act.action)"
      >
        {{ act.label }}
      </button>
    </div>

    <div class="detail-body">
      <section class="description">
        <h2>需求描述</h2>
        <pre>{{ task.description || '（无描述）' }}</pre>
      </section>

      <section v-if="task.ticket_content" class="ticket">
        <h2>执行任务单</h2>
        <TicketPreview :content="task.ticket_content" />
      </section>

      <section>
        <h2>角色信息</h2>
        <div class="roles">
          <div><strong>Planner:</strong> {{ task.planner || '-' }}</div>
          <div><strong>Executor:</strong> {{ task.executor || '-' }}</div>
          <div><strong>Reviewer:</strong> {{ task.reviewer || '-' }}</div>
          <div><strong>Approver:</strong> {{ task.human_approver || '-' }}</div>
        </div>
      </section>

      <section>
        <h2>产物</h2>
        <ArtifactTab :task-id="task.id" />
      </section>

      <section>
        <h2>审查记录</h2>
        <ReviewPanel :task-id="task.id" :task-status="task.status" @review-submitted="refresh" />
      </section>

      <section>
        <h2>审计日志</h2>
        <EventTimeline :task-id="task.id" />
      </section>

      <section class="stub-section">
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
import { useTaskStore, STATUS_LABELS } from '../stores/taskStore'
import StatusBadge from '../components/StatusBadge.vue'
import TicketPreview from '../components/TicketPreview.vue'
import ArtifactTab from '../components/ArtifactTab.vue'
import ReviewPanel from '../components/ReviewPanel.vue'
import EventTimeline from '../components/EventTimeline.vue'

const route = useRoute()
const taskStore = useTaskStore()
const task = ref<any>(null)

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

const availableActions = computed(() => {
  if (!task.value) return []
  return ACTION_MAP[task.value.status] || []
})

onMounted(refresh)

async function refresh() {
  const id = Number(route.params.id)
  task.value = await taskStore.fetchTask(id)
}

async function handleAction(action: string) {
  try {
    const result = await taskStore.transitionTask(task.value.id, action, { actor: 'human' })
    task.value.status = result.data?.status || task.value.status
    if (action === 'generate-ticket') {
      task.value.ticket_content = result.data?.ticket_content
    }
  } catch (e: any) {
    alert(e.message)
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
.page { max-width: 900px; margin: 0 auto; padding: 24px; }
.detail-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.meta { display: flex; gap: 8px; align-items: center; margin-top: 4px; color: var(--color-text-secondary); font-size: 14px; }
.priority { padding: 2px 8px; border-radius: 12px; font-size: 12px; background: #fff3e0; }
.priority.high { background: #ffebee; color: #d32f2f; }
.back-link { color: var(--color-text-secondary); font-size: 14px; }
.action-bar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 24px; padding: 16px; background: var(--color-surface); border-radius: var(--radius); border: 1px solid var(--color-border); }
.detail-body { display: flex; flex-direction: column; gap: 24px; }
.detail-body section { background: var(--color-surface); border-radius: var(--radius); padding: 20px; border: 1px solid var(--color-border); }
.detail-body section h2 { font-size: 16px; margin-bottom: 12px; color: var(--color-text); }
.description pre { white-space: pre-wrap; font-family: inherit; font-size: 14px; line-height: 1.6; color: var(--color-text-secondary); }
.roles { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; font-size: 14px; }
.stub-actions { display: flex; gap: 8px; }
.stub-section { opacity: 0.7; }
.loading { text-align: center; padding: 40px; color: var(--color-text-secondary); }
.btn { padding: 6px 14px; border: 1px solid var(--color-border); border-radius: var(--radius); background: var(--color-surface); cursor: pointer; font-size: 13px; }
.btn-sm { padding: 6px 14px; font-size: 13px; }
.btn-primary { background: var(--color-primary); color: #fff; border-color: var(--color-primary); }
.btn-approve { background: #4caf50; color: #fff; border-color: #4caf50; }
.btn-reject { background: #f44336; color: #fff; border-color: #f44336; }
.btn-warn { background: #ff9800; color: #fff; border-color: #ff9800; }
.btn-archive { background: #607d8b; color: #fff; border-color: #607d8b; }
</style>

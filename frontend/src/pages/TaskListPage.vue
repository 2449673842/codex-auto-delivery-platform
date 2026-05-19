<template>
  <div class="page">
    <header class="page-header">
      <div>
        <h1>{{ projectName }} 任务列表</h1>
        <router-link to="/" class="back-link">← 返回仪表盘</router-link>
      </div>
      <router-link :to="`/tasks/new?project_id=${projectId}`" class="btn btn-primary" v-if="projectId">
        + 新建任务
      </router-link>
    </header>

    <div class="status-tabs">
      <button
        v-for="s in statuses"
        :key="s.value"
        :class="{ active: filterStatus === s.value }"
        @click="filterStatus = s.value"
      >
        {{ s.label }}
      </button>
    </div>

    <div class="task-list">
      <div
        v-for="t in taskStore.tasks"
        :key="t.id"
        class="task-card"
        @click="$router.push(`/tasks/${t.id}`)"
      >
        <div class="task-header">
          <span class="status-badge" :class="t.status">{{ STATUS_LABELS[t.status] || t.status }}</span>
          <span class="priority" :class="t.priority">{{ t.priority }}</span>
        </div>
        <h3>{{ t.title }}</h3>
        <p class="meta">{{ t.project_name }} · {{ new Date(t.created_at).toLocaleDateString() }}</p>
      </div>
      <div v-if="taskStore.tasks.length === 0" class="empty">暂无任务</div>
    </div>

    <div class="pagination" v-if="taskStore.total > 20">
      <button :disabled="page <= 1" @click="page--">上一页</button>
      <span>{{ page }} / {{ Math.ceil(taskStore.total / 20) }}</span>
      <button :disabled="page * 20 >= taskStore.total" @click="page++">下一页</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useTaskStore, STATUS_LABELS } from '../stores/taskStore'

const route = useRoute()
const taskStore = useTaskStore()
const filterStatus = ref('')
const page = ref(1)
const projectId = ref<number | ''>('')

const statuses = [
  { value: '', label: '全部' },
  { value: 'draft', label: '草稿' },
  { value: 'ticket_ready', label: '任务单就绪' },
  { value: 'dispatched', label: '已分派' },
  { value: 'result_submitted', label: '结果已提交' },
  { value: 'reviewing', label: '审查中' },
  { value: 'changes_requested', label: '要求修改' },
  { value: 'approved', label: '已通过' },
  { value: 'rejected', label: '已拒绝' },
  { value: 'archived', label: '已归档' },
]

const projectName = computed(() => {
  if (!projectId.value) return '全局'
  const p = taskStore.tasks.find((t) => t.project_id === projectId.value)
  return p?.project_name || `项目 #${projectId.value}`
})

onMounted(() => {
  if (route.query.project_id) {
    projectId.value = Number(route.query.project_id)
  }
  load()
})

watch([filterStatus, page, projectId], () => load())

async function load() {
  const params: Record<string, any> = { page: page.value, size: 20 }
  if (projectId.value) params.project_id = projectId.value
  if (filterStatus.value) params.status = filterStatus.value
  await taskStore.fetchTasks(params)
}
</script>

<style scoped>
.page { max-width: 1000px; margin: 0 auto; padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.back-link { color: var(--color-text-secondary); font-size: 14px; }
.status-tabs { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 16px; }
.status-tabs button { padding: 6px 14px; border: 1px solid var(--color-border); border-radius: 16px; background: var(--color-surface); cursor: pointer; font-size: 13px; color: var(--color-text-secondary); }
.status-tabs button.active { background: var(--color-primary); color: #fff; border-color: var(--color-primary); }
.task-list { display: flex; flex-direction: column; gap: 8px; }
.task-card { background: var(--color-surface); border-radius: var(--radius); padding: 16px; cursor: pointer; border: 1px solid var(--color-border); }
.task-card:hover { border-color: var(--color-primary); }
.task-header { display: flex; gap: 8px; margin-bottom: 8px; }
.status-badge { padding: 2px 8px; border-radius: 12px; font-size: 12px; background: #e3f2fd; }
.status-badge.approved { background: #e8f5e9; }
.status-badge.rejected { background: #ffebee; }
.status-badge.archived { background: #f5f5f5; }
.priority { padding: 2px 8px; border-radius: 12px; font-size: 12px; background: #fff3e0; }
.priority.high { background: #ffebee; color: #d32f2f; }
.task-card h3 { font-size: 16px; margin-bottom: 4px; }
.meta { color: var(--color-text-secondary); font-size: 13px; }
.empty { text-align: center; padding: 40px; color: var(--color-text-secondary); }
.pagination { display: flex; justify-content: center; align-items: center; gap: 16px; margin-top: 24px; }
.pagination button { padding: 6px 16px; border: 1px solid var(--color-border); border-radius: var(--radius); background: var(--color-surface); cursor: pointer; }
.pagination button:disabled { opacity: 0.5; cursor: not-allowed; }
.btn { padding: 8px 16px; border: 1px solid var(--color-border); border-radius: var(--radius); background: var(--color-surface); cursor: pointer; font-size: 14px; text-decoration: none; display: inline-block; }
.btn-primary { background: var(--color-primary); color: #fff; border-color: var(--color-primary); }
</style>

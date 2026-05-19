<template>
  <div class="page">
    <header class="page-header">
      <div>
        <h1>{{ projectName }} 任务列表</h1>
        <router-link to="/" class="back-link">← 返回仪表盘</router-link>
      </div>
      <router-link :to="`/tasks/new?project_id=${projectId}`" class="btn btn-primary btn-sm" v-if="projectId">
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
        class="task-card card"
        @click="$router.push(`/tasks/${t.id}`)"
      >
        <div class="task-header">
          <StatusBadge :status="t.status" />
          <span class="priority" :class="t.priority">{{ t.priority }}</span>
        </div>
        <h3>{{ t.title }}</h3>
        <p class="task-meta">{{ t.project_name }} · {{ new Date(t.created_at).toLocaleDateString() }}</p>
      </div>
      <div v-if="taskStore.tasks.length === 0" class="empty-state">
        <p>暂无任务</p>
        <router-link v-if="projectId" :to="`/tasks/new?project_id=${projectId}`" class="btn btn-primary btn-sm" style="margin-top: 12px;">
          新建任务
        </router-link>
      </div>
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
import StatusBadge from '../components/StatusBadge.vue'

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
.page { max-width: 1000px; margin: 0 auto; padding: 32px 24px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.page-header h1 { font-size: 24px; font-weight: 700; }
.back-link { color: var(--color-text-secondary); font-size: 14px; }
.status-tabs { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 20px; }
.status-tabs button { padding: 6px 16px; border: 1px solid var(--color-border); border-radius: 16px; background: var(--color-surface); cursor: pointer; font-size: 13px; color: var(--color-text-secondary); transition: all 0.15s; }
.status-tabs button:hover { border-color: var(--color-primary); color: var(--color-primary); }
.status-tabs button.active { background: var(--color-primary); color: #fff; border-color: var(--color-primary); }
.task-list { display: flex; flex-direction: column; gap: 8px; }
.task-card { cursor: pointer; transition: border-color 0.15s, box-shadow 0.15s; }
.task-card:hover { border-color: var(--color-primary); box-shadow: var(--shadow-sm); }
.task-header { display: flex; gap: 8px; margin-bottom: 8px; }
.task-card h3 { font-size: 16px; font-weight: 600; margin-bottom: 4px; }
.task-meta { color: var(--color-text-secondary); font-size: 13px; }
.pagination { display: flex; justify-content: center; align-items: center; gap: 16px; margin-top: 24px; }
.pagination button { padding: 6px 16px; border: 1px solid var(--color-border); border-radius: var(--radius); background: var(--color-surface); cursor: pointer; }
.pagination button:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: var(--color-primary); color: #fff; border-color: var(--color-primary); }
.btn-sm { padding: 6px 14px; font-size: 13px; }
</style>

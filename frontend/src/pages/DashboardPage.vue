<template>
  <div class="dashboard">
    <header class="header">
      <div>
        <h1>Codex 自动化代码交付平台</h1>
        <p class="subtitle">开发运维控制台</p>
      </div>
      <div class="project-selector">
        <select v-model="selectedProjectId" @change="onProjectChange">
          <option value="">所有项目</option>
          <option v-for="p in projectStore.activeProjects" :key="p.id" :value="p.id">
            {{ p.display_name || p.name }}
          </option>
        </select>
        <router-link to="/projects" class="btn btn-primary btn-sm">项目管理</router-link>
      </div>
    </header>

    <section class="stats" v-if="stats">
      <div class="stat-card">
        <span class="stat-value">{{ stats.total }}</span>
        <span class="stat-label">总任务</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{{ stats.pending }}</span>
        <span class="stat-label">待处理</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{{ stats.reviewing }}</span>
        <span class="stat-label">审查中</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{{ stats.approved }}</span>
        <span class="stat-label">已通过</span>
      </div>
    </section>

    <section class="projects-overview">
      <h2 class="section-title">项目概览</h2>
      <div class="project-grid" v-if="projectStore.activeProjects.length > 0">
        <div
          v-for="p in projectStore.activeProjects"
          :key="p.id"
          class="project-card card"
          @click="$router.push(`/projects/${p.id}`)"
        >
          <h3>{{ p.display_name || p.name }}</h3>
          <p class="branch">{{ p.current_branch }}</p>
          <p class="meta">{{ p.task_count }} 个任务</p>
        </div>
      </div>
      <div v-else class="empty-state">
        <p>暂无项目</p>
        <router-link to="/projects" class="btn btn-primary btn-sm" style="margin-top: 12px; display: inline-block;">创建项目</router-link>
      </div>
    </section>

    <section class="recent-activity" v-if="recentEvents.length">
      <h2 class="section-title">最近活动</h2>
      <div class="card">
        <div v-for="e in recentEvents" :key="e.id" class="event-item">
          <span class="event-type">{{ e.event_type }}</span>
          <span class="event-msg">{{ e.message }}</span>
          <span class="event-time">{{ new Date(e.created_at).toLocaleString() }}</span>
        </div>
        <div v-if="recentEvents.length === 0" class="empty-state">暂无活动</div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useProjectStore } from '../stores/projectStore'
import { useTaskStore } from '../stores/taskStore'
import client from '../services/api'

const projectStore = useProjectStore()
const taskStore = useTaskStore()
const selectedProjectId = ref<number | ''>('')
const recentEvents = ref<any[]>([])
const stats = ref<{ total: number; pending: number; reviewing: number; approved: number } | null>(null)

onMounted(async () => {
  await projectStore.fetchProjects()
  await loadStats()
  await loadRecentEvents()
})

async function loadStats() {
  await taskStore.fetchTasks({ size: 1 })
  const total = taskStore.total
  const pendingTasks = await client.get('/tasks', { params: { status: 'draft', size: 1 } })
  const reviewingTasks = await client.get('/tasks', { params: { status: 'reviewing', size: 1 } })
  const approvedTasks = await client.get('/tasks', { params: { status: 'approved', size: 1 } })
  stats.value = {
    total,
    pending: pendingTasks.data.message?.total || 0,
    reviewing: reviewingTasks.data.message?.total || 0,
    approved: approvedTasks.data.message?.total || 0,
  }
}

async function loadRecentEvents() {
  try {
    const { data } = await client.get('/tasks?size=10')
    const tasks = data.data || []
    const allEvents: any[] = []
    for (const t of tasks.slice(0, 5)) {
      const ev = await taskStore.fetchEvents(t.id)
      allEvents.push(...ev)
    }
    allEvents.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    recentEvents.value = allEvents.slice(0, 10)
  } catch {
    recentEvents.value = []
  }
}

function onProjectChange() {
  if (selectedProjectId.value) {
    const p = projectStore.projects.find((p) => p.id === selectedProjectId.value)
    if (p) projectStore.currentProject = p
  }
}
</script>

<style scoped>
.dashboard { max-width: 1200px; margin: 0 auto; padding: 32px 24px; }
.header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 32px; gap: 16px; }
.header h1 { font-size: 28px; font-weight: 700; }
.subtitle { color: var(--color-text-secondary); font-size: 14px; margin-top: 2px; }
.project-selector { display: flex; gap: 12px; align-items: center; }
.project-selector select { padding: 8px 12px; border: 1px solid var(--color-border); border-radius: var(--radius); font-size: 14px; min-width: 160px; }
.section-title { font-size: 18px; font-weight: 600; margin-bottom: 16px; }
.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 40px; }
.stat-card { background: var(--color-surface); border-radius: var(--radius-lg); padding: 24px 16px; text-align: center; box-shadow: var(--shadow-sm); border: 1px solid var(--color-border); }
.stat-value { display: block; font-size: 32px; font-weight: 700; color: var(--color-primary); }
.stat-label { display: block; margin-top: 4px; color: var(--color-text-secondary); font-size: 14px; }
.project-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.project-card { cursor: pointer; transition: border-color 0.15s, box-shadow 0.15s; }
.project-card:hover { border-color: var(--color-primary); box-shadow: var(--shadow-md); }
.project-card h3 { margin-bottom: 8px; font-size: 16px; }
.branch { color: var(--color-primary); font-size: 13px; font-family: monospace; }
.meta { color: var(--color-text-secondary); font-size: 13px; margin-top: 8px; }
.recent-activity { margin-top: 40px; }
.event-item { display: flex; gap: 16px; padding: 10px 0; border-bottom: 1px solid var(--color-border); font-size: 14px; }
.event-item:last-child { border-bottom: none; }
.event-type { font-weight: 600; min-width: 100px; text-transform: capitalize; }
.event-msg { flex: 1; color: var(--color-text-secondary); }
.event-time { color: var(--color-text-secondary); font-size: 12px; white-space: nowrap; }
.btn-primary { background: var(--color-primary); color: #fff; border-color: var(--color-primary); }
.btn-sm { padding: 6px 14px; font-size: 13px; }
</style>

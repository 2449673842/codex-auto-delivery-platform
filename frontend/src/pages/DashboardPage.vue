<template>
  <div class="dashboard">
    <header class="header">
      <h1>Codex 自动化代码交付平台</h1>
      <div class="project-selector">
        <select v-model="selectedProjectId" @change="onProjectChange">
          <option value="">所有项目</option>
          <option v-for="p in projectStore.activeProjects" :key="p.id" :value="p.id">
            {{ p.display_name || p.name }}
          </option>
        </select>
        <router-link to="/projects" class="btn-link">项目管理</router-link>
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
      <h2>项目概览</h2>
      <div class="project-grid">
        <div
          v-for="p in projectStore.activeProjects"
          :key="p.id"
          class="project-card"
          @click="$router.push(`/projects/${p.id}`)"
        >
          <h3>{{ p.display_name || p.name }}</h3>
          <p class="branch">{{ p.current_branch }}</p>
          <p class="meta">{{ p.task_count }} 个任务</p>
        </div>
        <div v-if="projectStore.activeProjects.length === 0" class="empty">
          暂无项目，去<router-link to="/projects">创建项目</router-link>
        </div>
      </div>
    </section>

    <section class="recent-activity" v-if="recentEvents.length">
      <h2>最近活动</h2>
      <div class="timeline">
        <div v-for="e in recentEvents" :key="e.id" class="event-item">
          <span class="event-type">{{ e.event_type }}</span>
          <span class="event-msg">{{ e.message }}</span>
          <span class="event-time">{{ new Date(e.created_at).toLocaleString() }}</span>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
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
.dashboard { max-width: 1200px; margin: 0 auto; padding: 24px; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.project-selector { display: flex; gap: 12px; align-items: center; }
.project-selector select { padding: 8px 12px; border: 1px solid var(--color-border); border-radius: var(--radius); }
.btn-link { color: var(--color-primary); text-decoration: none; }
.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 32px; }
.stat-card { background: var(--color-surface); border-radius: var(--radius); padding: 20px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.stat-value { display: block; font-size: 32px; font-weight: 700; color: var(--color-primary); }
.stat-label { display: block; margin-top: 4px; color: var(--color-text-secondary); font-size: 14px; }
.project-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.project-card { background: var(--color-surface); border-radius: var(--radius); padding: 20px; cursor: pointer; border: 1px solid var(--color-border); }
.project-card:hover { border-color: var(--color-primary); }
.project-card h3 { margin-bottom: 8px; }
.branch { color: var(--color-text-secondary); font-size: 13px; font-family: monospace; }
.meta { color: var(--color-text-secondary); font-size: 13px; margin-top: 8px; }
.empty { grid-column: 1 / -1; text-align: center; padding: 40px; color: var(--color-text-secondary); }
.recent-activity { margin-top: 32px; }
.timeline { background: var(--color-surface); border-radius: var(--radius); padding: 16px; }
.event-item { display: flex; gap: 16px; padding: 8px 0; border-bottom: 1px solid var(--color-border); font-size: 14px; }
.event-item:last-child { border-bottom: none; }
.event-type { font-weight: 600; min-width: 100px; }
.event-msg { flex: 1; color: var(--color-text-secondary); }
.event-time { color: var(--color-text-secondary); font-size: 12px; white-space: nowrap; }
</style>

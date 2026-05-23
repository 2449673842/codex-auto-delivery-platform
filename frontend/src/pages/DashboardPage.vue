<template>
  <div class="dashboard">
    <header class="header">
      <div>
        <h1>个人多 AI 编码工作台</h1>
        <p class="subtitle">创建项目和任务后，直接在 TaskDetail 使用 Real AI Run 调用 AI、保存结果，并查看 Patch Sandbox / Gate。</p>
      </div>
      <div class="project-selector">
        <select v-model="selectedProjectId" @change="onProjectChange">
          <option value="">所有项目</option>
          <option v-for="p in projectStore.activeProjects" :key="p.id" :value="p.id">
            {{ p.display_name || p.name }}
          </option>
        </select>
        <router-link to="/projects" class="btn btn-sm">项目管理</router-link>
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

    <section class="runtime-panel card">
      <div class="section-heading">
        <div>
          <h2>AI Runtime Status / AI 运行状态</h2>
          <p>只显示非敏感配置状态。API key 永远只显示 configured / missing。</p>
        </div>
        <button class="btn btn-sm" @click="loadAiRuntimeStatus" :disabled="runtimeLoading">刷新状态</button>
      </div>
      <p v-if="runtimeError" class="error-text">{{ runtimeError }}</p>
      <div v-if="aiRuntimeStatus" class="runtime-grid">
        <div>
          <span>AI_EXECUTION_ENABLED</span>
          <strong :class="aiRuntimeStatus.ai_execution_enabled ? 'ok' : 'warn'">
            {{ aiRuntimeStatus.ai_execution_enabled ? 'enabled' : 'disabled' }}
          </strong>
        </div>
        <div>
          <span>OPENAI_API_KEY</span>
          <strong :class="aiRuntimeStatus.openai_credential_configured ? 'ok' : 'warn'">
            {{ aiRuntimeStatus.openai_credential_configured ? 'configured' : 'missing' }}
          </strong>
        </div>
        <div>
          <span>openai in allowlist</span>
          <strong :class="aiRuntimeStatus.openai_allowed ? 'ok' : 'warn'">
            {{ aiRuntimeStatus.openai_allowed ? 'yes' : 'no' }}
          </strong>
        </div>
        <div>
          <span>Model</span>
          <strong>{{ aiRuntimeStatus.model || '-' }}</strong>
        </div>
        <div>
          <span>Base URL</span>
          <strong>{{ aiRuntimeStatus.base_url_configured ? 'configured' : 'default' }}</strong>
        </div>
        <div>
          <span>Wire API</span>
          <strong>{{ aiRuntimeStatus.wire_api || 'chat_completions' }}</strong>
        </div>
      </div>
      <div v-else-if="!runtimeError" class="runtime-grid muted">
        <div><span>AI runtime status</span><strong>loading</strong></div>
      </div>
    </section>

    <section class="starter card" v-if="projectStore.activeProjects.length === 0">
      <div class="starter-copy">
        <h2>开始第一个可用流程</h2>
        <p>创建项目后添加任务，进入 TaskDetail，就能点击 Real AI Run：dry-run 检查 prompt / token / safety gate，execute 通过后端门控真实调用 AI 并保存 AgentRun 与 TaskArtifact。</p>
      </div>
      <div class="starter-actions">
        <button class="btn btn-primary" @click="showProjectForm = true">创建第一个项目</button>
        <button class="btn" @click="createDemoAndOpen" :disabled="creatingDemo">
          {{ creatingDemo ? '创建中...' : '创建演示项目并打开' }}
        </button>
      </div>
      <p v-if="workflowError" class="error-text">{{ workflowError }}</p>
    </section>

    <section class="quick-create card">
      <div class="section-heading">
        <div>
          <h2>创建任务并进入 AI 工作台</h2>
          <p>最短路径：选项目，写任务，创建后自动进入 TaskDetail。</p>
        </div>
        <button class="btn" @click="createDemoAndOpen" :disabled="creatingDemo">
          {{ creatingDemo ? '创建中...' : '创建演示项目并打开' }}
        </button>
      </div>
      <form class="quick-form" @submit.prevent="createTaskAndOpen">
        <label>
          项目
          <select v-model="taskForm.project_id" required>
            <option value="">请选择项目</option>
            <option v-for="p in projectStore.activeProjects" :key="p.id" :value="p.id">
              {{ p.display_name || p.name }}
            </option>
          </select>
        </label>
        <label>
          task title
          <input v-model="taskForm.title" required maxlength="256" placeholder="例如：验证 Real AI Run 是否可用" />
        </label>
        <label class="wide">
          task description
          <textarea v-model="taskForm.description" rows="4" placeholder="补充任务背景、期望输出和边界"></textarea>
        </label>
        <div class="form-actions wide">
        <button class="btn btn-primary" type="submit" :disabled="creatingTask || !taskForm.project_id">
            {{ creatingTask ? '创建中...' : '创建任务并打开 TaskDetail' }}
          </button>
          <button class="btn" type="button" @click="showProjectForm = true">创建第一个项目</button>
        </div>
      </form>
      <p v-if="workflowError" class="error-text">{{ workflowError }}</p>
    </section>

    <section class="continue-row" v-if="recentTasks.length > 0">
      <div class="section-heading">
        <div>
          <h2>继续最近任务</h2>
          <p>直接回到 TaskDetail，继续 Real AI Run、Artifact 和 Answer Synthesis。</p>
        </div>
      </div>
      <div class="recent-task-list">
        <button
          v-for="t in recentTasks"
          :key="t.id"
          class="recent-task"
          @click="router.push(`/tasks/${t.id}`)"
        >
          <strong>{{ t.title }}</strong>
          <span>#{{ t.id }} · {{ t.status }} · {{ t.project_name || `Project ${t.project_id}` }}</span>
        </button>
      </div>
    </section>

    <section class="projects-overview">
      <h2 class="section-title">项目概览</h2>
      <div class="project-grid" v-if="projectStore.activeProjects.length > 0">
        <div
          v-for="p in projectStore.activeProjects"
          :key="p.id"
          class="project-card card"
        >
          <h3>{{ p.display_name || p.name }}</h3>
          <p class="branch">{{ p.current_branch }}</p>
          <p class="meta">{{ p.task_count }} 个任务</p>
          <div class="card-actions">
            <button class="btn btn-sm" @click="prepareTaskForProject(p.id)">添加任务</button>
            <router-link :to="`/tasks?project_id=${p.id}`" class="btn btn-sm">查看任务</router-link>
          </div>
        </div>
      </div>
      <div v-else class="empty-state">
        <h3>暂无项目</h3>
        <p>先创建项目，随后添加任务并进入 TaskDetail 使用 Real AI Run。</p>
        <div class="empty-actions">
          <button class="btn btn-primary" @click="showProjectForm = true">创建第一个项目</button>
          <button class="btn" @click="createDemoAndOpen" :disabled="creatingDemo">创建演示项目并打开</button>
        </div>
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
      </div>
    </section>

    <div v-if="showProjectForm" class="form-overlay" @click.self="showProjectForm = false">
      <div class="form-panel card">
        <div class="section-heading">
          <div>
            <h2>创建项目</h2>
            <p>只需要名称和可选描述。不会访问 Project.root_path 做真实仓库修改。</p>
          </div>
        </div>
        <form class="modal-form" @submit.prevent="createProjectFromDashboard">
          <label>
            项目名称
            <input v-model="projectForm.name" required maxlength="128" placeholder="My Workbench Project" />
          </label>
          <label>
            项目描述，可选
            <textarea v-model="projectForm.description" rows="3" placeholder="这个项目要交给 AI 处理的背景"></textarea>
          </label>
          <div class="form-actions">
            <button class="btn btn-primary" type="submit" :disabled="creatingProject">
              {{ creatingProject ? '创建中...' : '创建项目' }}
            </button>
            <button class="btn" type="button" @click="showProjectForm = false" :disabled="creatingProject">取消</button>
          </div>
        </form>
        <p v-if="projectError" class="error-text">{{ projectError }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectStore } from '../stores/projectStore'
import { useTaskStore, type Task } from '../stores/taskStore'
import client from '../services/api'

interface AiRuntimeStatus {
  ai_execution_enabled: boolean
  openai_credential_configured: boolean
  provider_allowlist: string[]
  openai_allowed: boolean
  model: string
  base_url_configured: boolean
  wire_api: string
}

const router = useRouter()
const projectStore = useProjectStore()
const taskStore = useTaskStore()
const selectedProjectId = ref<number | ''>('')
const recentEvents = ref<any[]>([])
const recentTasks = ref<Task[]>([])
const stats = ref<{ total: number; pending: number; reviewing: number; approved: number } | null>(null)
const aiRuntimeStatus = ref<AiRuntimeStatus | null>(null)
const runtimeLoading = ref(false)
const runtimeError = ref('')
const workflowError = ref('')
const projectError = ref('')
const showProjectForm = ref(false)
const creatingProject = ref(false)
const creatingTask = ref(false)
const creatingDemo = ref(false)
const projectForm = ref({ name: '', description: '' })
const taskForm = ref({
  project_id: '' as number | '',
  title: '',
  description: '',
})

onMounted(async () => {
  await projectStore.fetchProjects()
  preselectProject()
  await Promise.all([loadStats(), loadRecentEvents(), loadAiRuntimeStatus()])
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
  const { data } = await client.get('/tasks', { params: { size: 5 } })
  recentTasks.value = data.data || []
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

async function loadAiRuntimeStatus() {
  runtimeLoading.value = true
  runtimeError.value = ''
  try {
    const { data } = await client.get('/ai-runtime/status')
    aiRuntimeStatus.value = data.data
  } catch (e: any) {
    aiRuntimeStatus.value = null
    runtimeError.value = e.message || 'AI runtime status unavailable'
  } finally {
    runtimeLoading.value = false
  }
}

function preselectProject() {
  const first = projectStore.activeProjects[0]
  if (first && !taskForm.value.project_id) {
    taskForm.value.project_id = first.id
    selectedProjectId.value = first.id
  }
}

function onProjectChange() {
  if (selectedProjectId.value) {
    const p = projectStore.projects.find((item) => item.id === Number(selectedProjectId.value))
    if (p) {
      projectStore.currentProject = p
      taskForm.value.project_id = p.id
    }
  }
}

function prepareTaskForProject(projectId: number) {
  taskForm.value.project_id = projectId
  taskForm.value.title = taskForm.value.title || 'Test real AI run'
  taskForm.value.description = taskForm.value.description || 'Use TaskDetail Real AI Run to test dry-run, execute, artifacts, and Patch Sandbox / Gate display.'
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

async function createProjectFromDashboard() {
  projectError.value = ''
  workflowError.value = ''
  creatingProject.value = true
  try {
    const project = await createProject(projectForm.value.name, projectForm.value.description)
    taskForm.value.project_id = project.id
    selectedProjectId.value = project.id
    showProjectForm.value = false
    projectForm.value = { name: '', description: '' }
    await refreshDashboard()
  } catch (e: any) {
    projectError.value = e.message || '创建项目失败'
  } finally {
    creatingProject.value = false
  }
}

async function createTaskAndOpen() {
  workflowError.value = ''
  if (!taskForm.value.project_id) {
    workflowError.value = '请先选择或创建项目'
    return
  }
  creatingTask.value = true
  try {
    const task = await taskStore.createTask({
      project_id: Number(taskForm.value.project_id),
      title: taskForm.value.title,
      description: taskForm.value.description,
      planner: 'user',
      source: 'manual',
    })
    router.push(`/tasks/${task.id}`)
  } catch (e: any) {
    workflowError.value = e.message || '创建任务失败'
  } finally {
    creatingTask.value = false
  }
}

async function createDemoAndOpen() {
  workflowError.value = ''
  creatingDemo.value = true
  try {
    const project = await createProject(`Demo AI Workbench ${Date.now()}`, 'Demo project for Real AI Run smoke testing')
    const task = await taskStore.createTask({
      project_id: project.id,
      title: 'Test real AI run',
      description: [
        'Verify Real AI Run from TaskDetail.',
        '1. Run review dry-run and inspect prompt_hash, context_packet_hash, estimated_tokens, and safety gate.',
        '2. Run review execute and confirm AgentRun / TaskArtifact are saved.',
        '3. Run patch_generation execute and inspect Patch Sandbox / Gate fields.',
      ].join('\n'),
      planner: 'user',
      source: 'demo',
    })
    router.push(`/tasks/${task.id}`)
  } catch (e: any) {
    workflowError.value = e.message || '创建演示项目失败'
  } finally {
    creatingDemo.value = false
  }
}

async function createProject(name: string, description: string) {
  const project = await projectStore.createProject({
    name: name.trim(),
    display_name: description.trim() || null,
    root_path: `/workspace/${name.trim().replace(/\s+/g, '-').toLowerCase()}`,
  })
  return project
}

async function refreshDashboard() {
  await projectStore.fetchProjects()
  preselectProject()
  await loadStats()
}
</script>

<style scoped>
.dashboard { max-width: 1200px; margin: 0 auto; padding: 32px 24px; }
.header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 28px; gap: 16px; }
.header h1 { font-size: 28px; font-weight: 700; }
.subtitle { color: var(--color-text-secondary); font-size: 14px; margin-top: 4px; max-width: 760px; }
.project-selector { display: flex; gap: 12px; align-items: center; }
.project-selector select { min-width: 180px; }
.section-heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 16px; }
.section-heading h2, .section-title { font-size: 18px; font-weight: 600; margin-bottom: 4px; }
.section-heading p { color: var(--color-text-secondary); font-size: 13px; }
.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }
.stat-card { background: var(--color-surface); border-radius: var(--radius); padding: 18px 16px; border: 1px solid var(--color-border); }
.stat-value { display: block; font-size: 30px; font-weight: 700; color: var(--color-primary); line-height: 1.1; }
.stat-label { display: block; margin-top: 4px; color: var(--color-text-secondary); font-size: 13px; }
.runtime-panel, .starter, .quick-create { margin-bottom: 20px; }
.runtime-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.runtime-grid div { border: 1px solid var(--color-border); border-radius: var(--radius); padding: 12px; min-height: 70px; background: #fafbfc; }
.runtime-grid span { display: block; color: var(--color-text-secondary); font-size: 12px; margin-bottom: 6px; }
.runtime-grid strong { font-size: 14px; overflow-wrap: anywhere; }
.runtime-grid.muted strong { color: var(--color-text-secondary); }
.ok { color: var(--color-success); }
.warn { color: var(--color-warning); }
.starter { display: flex; justify-content: space-between; gap: 24px; align-items: center; }
.starter-copy h2 { font-size: 20px; margin-bottom: 8px; }
.starter-copy p { color: var(--color-text-secondary); max-width: 700px; font-size: 14px; }
.starter-actions, .empty-actions, .form-actions, .card-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.quick-form { display: grid; grid-template-columns: minmax(180px, 260px) 1fr; gap: 14px; align-items: end; }
.quick-form .wide { grid-column: 1 / -1; }
.quick-form textarea { resize: vertical; }
.continue-row { margin-bottom: 28px; }
.recent-task-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.recent-task { text-align: left; border: 1px solid var(--color-border); border-radius: var(--radius); background: var(--color-surface); padding: 14px; cursor: pointer; }
.recent-task:hover { border-color: var(--color-primary); }
.recent-task strong, .recent-task span { display: block; }
.recent-task span { margin-top: 4px; color: var(--color-text-secondary); font-size: 12px; }
.projects-overview { margin-top: 28px; }
.project-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.project-card h3 { margin-bottom: 8px; font-size: 16px; }
.branch { color: var(--color-primary); font-size: 13px; font-family: monospace; }
.meta { color: var(--color-text-secondary); font-size: 13px; margin-top: 8px; }
.empty-state h3 { color: var(--color-text); margin-bottom: 6px; }
.empty-actions { justify-content: center; margin-top: 16px; }
.recent-activity { margin-top: 40px; }
.event-item { display: flex; gap: 16px; padding: 10px 0; border-bottom: 1px solid var(--color-border); font-size: 14px; }
.event-item:last-child { border-bottom: none; }
.event-type { font-weight: 600; min-width: 100px; text-transform: capitalize; }
.event-msg { flex: 1; color: var(--color-text-secondary); }
.event-time { color: var(--color-text-secondary); font-size: 12px; white-space: nowrap; }
.form-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; z-index: 100; padding: 20px; }
.form-panel { width: 520px; max-width: 100%; }
.modal-form { display: flex; flex-direction: column; gap: 14px; }
.error-text { color: var(--color-danger); background: var(--color-danger-bg); border: 1px solid #ffcdd2; border-radius: var(--radius); padding: 10px 12px; margin-top: 12px; font-size: 13px; }
.btn-primary { background: var(--color-primary); color: #fff; border-color: var(--color-primary); }
.btn-sm { padding: 6px 14px; font-size: 13px; }
@media (max-width: 760px) {
  .header, .starter, .section-heading { flex-direction: column; align-items: stretch; }
  .stats, .runtime-grid, .quick-form { grid-template-columns: 1fr; }
  .quick-form .wide { grid-column: auto; }
  .project-selector { flex-direction: column; align-items: stretch; }
}
</style>

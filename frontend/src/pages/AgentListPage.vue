<template>
  <div class="page">
    <header class="page-header">
      <div>
        <h1>Agent 管理</h1>
        <router-link to="/" class="back-link">← 返回仪表盘</router-link>
      </div>
      <button class="btn btn-primary" @click="showForm = true">+ 新建 Agent</button>
    </header>

    <div v-if="showForm" class="form-overlay" @click.self="showForm = false">
      <div class="form-panel card">
        <h2>{{ editingId ? '编辑 Agent' : '新建 Agent' }}</h2>
        <p class="form-note">此处只保存 secret 引用名（环境变量名），不保存真实 API key</p>
        <form @submit.prevent="handleSubmit">
          <label>名称 *<input v-model="form.name" required /></label>
          <label>
            类型 *
            <select v-model="form.agent_type" required>
              <option value="planner">规划 (Planner)</option>
              <option value="executor">执行 (Executor)</option>
              <option value="reviewer">审查 (Reviewer)</option>
              <option value="test">测试 (Test)</option>
            </select>
          </label>
          <label>
            提供商 *
            <select v-model="form.provider" required>
              <option value="codex">Codex</option>
              <option value="openai">OpenAI</option>
              <option value="claude">Claude</option>
              <option value="local">Local</option>
              <option value="manual">Manual</option>
            </select>
          </label>
          <label>模型名称<input v-model="form.model_name" placeholder="如 gpt-4" /></label>
          <label>
            Secret 引用名
            <input v-model="form.secret_ref" placeholder="环境变量名，如 OPENAI_API_KEY" />
            <span class="field-hint">仅环境变量名，不填真实 key</span>
          </label>
          <label>最大运行秒数<input v-model.number="form.max_runtime_seconds" type="number" min="1" /></label>
          <label>最大重试次数<input v-model.number="form.max_attempts" type="number" min="1" /></label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="form.enabled" /> 启用
          </label>
          <div class="form-actions">
            <button type="submit" class="btn btn-primary">{{ editingId ? '保存' : '创建' }}</button>
            <button type="button" class="btn" @click="showForm = false">取消</button>
          </div>
        </form>
      </div>
    </div>

    <div class="agent-list" v-if="agents.length > 0">
      <div v-for="a in agents" :key="a.id" class="agent-card card">
        <div class="agent-header">
          <h3>{{ a.name }}</h3>
          <span class="agent-type-badge" :class="a.agent_type">{{ a.agent_type }}</span>
          <span class="provider-badge">{{ a.provider }}</span>
          <span class="status-dot" :class="{ active: a.enabled }" :title="a.enabled ? '已启用' : '已禁用'"></span>
        </div>
        <p class="agent-meta">模型: {{ a.model_name || '-' }} · Secret: {{ a.secret_ref || '-' }}</p>
        <p class="agent-meta">超时: {{ a.max_runtime_seconds }}s · 最大重试: {{ a.max_attempts }}次</p>
        <p class="agent-meta" v-if="a.allowed_projects">限定项目: {{ a.allowed_projects }}</p>
        <div class="card-actions">
          <button class="btn btn-sm" @click="editAgent(a)">编辑</button>
          <button class="btn btn-sm" :class="a.enabled ? 'btn-warn' : 'btn-primary'" @click="toggleEnabled(a)">
            {{ a.enabled ? '禁用' : '启用' }}
          </button>
          <button class="btn btn-sm btn-danger" @click="handleDelete(a.id)">删除</button>
        </div>
      </div>
    </div>
    <div v-else class="empty-state">
      <p>暂无 Agent</p>
      <button class="btn btn-primary btn-sm" style="margin-top: 12px;" @click="showForm = true">创建第一个 Agent</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchAgents, createAgent, updateAgent, deleteAgent } from '../services/agentService'
import type { AgentProfile, AgentProfileCreate, AgentProfileUpdate } from '../types/agent'

const agents = ref<AgentProfile[]>([])
const showForm = ref(false)
const editingId = ref<number | null>(null)
const form = ref<AgentProfileCreate>({
  name: '',
  agent_type: 'planner',
  provider: 'codex',
  model_name: '',
  secret_ref: '',
  enabled: true,
  max_runtime_seconds: 300,
  max_attempts: 3,
  allowed_projects: null,
})

onMounted(load)

async function load() {
  agents.value = await fetchAgents()
}

function resetForm() {
  form.value = {
    name: '',
    agent_type: 'planner',
    provider: 'codex',
    model_name: '',
    secret_ref: '',
    enabled: true,
    max_runtime_seconds: 300,
    max_attempts: 3,
    allowed_projects: null,
  }
  editingId.value = null
}

function editAgent(a: AgentProfile) {
  editingId.value = a.id
  form.value = {
    name: a.name,
    agent_type: a.agent_type,
    provider: a.provider,
    model_name: a.model_name || '',
    secret_ref: a.secret_ref || '',
    enabled: a.enabled,
    max_runtime_seconds: a.max_runtime_seconds,
    max_attempts: a.max_attempts,
    allowed_projects: a.allowed_projects,
  }
  showForm.value = true
}

async function handleSubmit() {
  try {
    if (editingId.value) {
      await updateAgent(editingId.value, form.value as AgentProfileUpdate)
    } else {
      await createAgent(form.value)
    }
    showForm.value = false
    resetForm()
    await load()
  } catch (e: any) {
    alert(e.message)
  }
}

async function toggleEnabled(a: AgentProfile) {
  try {
    await updateAgent(a.id, { enabled: !a.enabled })
    await load()
  } catch (e: any) {
    alert(e.message)
  }
}

async function handleDelete(id: number) {
  if (!confirm('确定删除此 Agent？')) return
  try {
    await deleteAgent(id)
    await load()
  } catch (e: any) {
    alert(e.message)
  }
}
</script>

<style scoped>
.page { max-width: 1100px; margin: 0 auto; padding: 32px 24px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; }
.page-header h1 { font-size: 24px; font-weight: 700; }
.back-link { color: var(--color-text-secondary); font-size: 14px; }
.form-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; z-index: 100; pointer-events: none; }
.form-panel { padding: 32px; width: 520px; max-width: 90vw; max-height: 90vh; overflow-y: auto; pointer-events: auto; }
.form-panel h2 { font-size: 18px; margin-bottom: 8px; }
.form-note { color: var(--color-text-secondary); font-size: 12px; margin-bottom: 16px; font-style: italic; }
.form-panel form { display: flex; flex-direction: column; gap: 12px; }
.field-hint { font-size: 11px; color: var(--color-text-secondary); margin-top: 2px; }
.form-actions { display: flex; gap: 8px; margin-top: 8px; }
.checkbox-label { display: flex; flex-direction: row; align-items: center; gap: 8px; font-size: 14px; }
.agent-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 16px; }
.agent-card { display: flex; flex-direction: column; gap: 6px; }
.agent-header { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.agent-header h3 { font-size: 16px; font-weight: 600; }
.agent-type-badge { padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 500; text-transform: capitalize; }
.agent-type-badge.planner { background: #e3f2fd; color: #1565c0; }
.agent-type-badge.executor { background: #f3e5f5; color: #7b1fa2; }
.agent-type-badge.reviewer { background: #fff3e0; color: #e65100; }
.agent-type-badge.test { background: #e0f7fa; color: #00838f; }
.provider-badge { padding: 2px 8px; border-radius: 10px; font-size: 11px; background: #f5f5f5; color: #616161; }
.status-dot { width: 10px; height: 10px; border-radius: 50%; background: #e0e0e0; margin-left: auto; }
.status-dot.active { background: #4caf50; }
.agent-meta { color: var(--color-text-secondary); font-size: 13px; }
.card-actions { display: flex; gap: 8px; margin-top: 8px; padding-top: 12px; border-top: 1px solid var(--color-border); }
.btn-primary { background: var(--color-primary); color: #fff; border-color: var(--color-primary); }
.btn-danger { color: var(--color-danger); border-color: var(--color-danger); }
.btn-warn { color: #e65100; border-color: #e65100; }
.btn-sm { padding: 4px 12px; font-size: 13px; }
</style>

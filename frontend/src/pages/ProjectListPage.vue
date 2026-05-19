<template>
  <div class="page">
    <header class="page-header">
      <h1>项目管理</h1>
      <router-link to="/" class="back-link">← 返回仪表盘</router-link>
    </header>

    <button class="btn btn-primary" @click="showForm = true">+ 新建项目</button>

    <div v-if="showForm" class="form-overlay" @click.self="showForm = false">
      <div class="form-panel card">
        <h2>{{ editingId ? '编辑项目' : '新建项目' }}</h2>
        <form @submit.prevent="handleSubmit">
          <label>项目名称 *<input v-model="form.name" required /></label>
          <label>展示名<input v-model="form.display_name" /></label>
          <label>根目录路径 *<input v-model="form.root_path" required /></label>
          <label>Git 仓库地址<input v-model="form.repo_url" /></label>
          <label>包管理器<input v-model="form.package_manager" placeholder="npm / pnpm / pip" /></label>
          <label>构建命令<input v-model="form.build_command" /></label>
          <label>测试命令<input v-model="form.test_command" /></label>
          <div class="form-actions">
            <button type="submit" class="btn btn-primary">{{ editingId ? '保存' : '创建' }}</button>
            <button type="button" class="btn" @click="showForm = false">取消</button>
          </div>
        </form>
      </div>
    </div>

    <div class="project-grid">
      <div
        v-for="p in projectStore.projects"
        :key="p.id"
        class="project-card card"
      >
        <h3>{{ p.display_name || p.name }}</h3>
        <p class="branch">{{ p.current_branch }}</p>
        <p class="meta">路径: {{ p.root_path }}</p>
        <p class="meta">{{ p.task_count }} 个任务</p>
        <div class="card-actions">
          <button class="btn btn-sm" @click="editProject(p)">编辑</button>
          <button class="btn btn-sm btn-danger" @click="handleDelete(p.id)">删除</button>
          <router-link :to="`/tasks?project_id=${p.id}`" class="btn btn-sm">查看任务</router-link>
        </div>
      </div>
      <div v-if="projectStore.projects.length === 0" class="empty-state">
        <p>暂无项目</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useProjectStore } from '../stores/projectStore'

const projectStore = useProjectStore()
const showForm = ref(false)
const editingId = ref<number | null>(null)
const form = ref({
  name: '',
  display_name: '',
  root_path: '',
  repo_url: '',
  package_manager: '',
  build_command: '',
  test_command: '',
})

onMounted(() => projectStore.fetchProjects())

function resetForm() {
  form.value = { name: '', display_name: '', root_path: '', repo_url: '', package_manager: '', build_command: '', test_command: '' }
  editingId.value = null
}

function editProject(p: any) {
  editingId.value = p.id
  form.value = {
    name: p.name,
    display_name: p.display_name || '',
    root_path: p.root_path,
    repo_url: p.repo_url || '',
    package_manager: p.package_manager || '',
    build_command: p.build_command || '',
    test_command: p.test_command || '',
  }
  showForm.value = true
}

async function handleSubmit() {
  try {
    if (editingId.value) {
      await projectStore.updateProject(editingId.value, form.value)
    } else {
      await projectStore.createProject(form.value)
    }
    showForm.value = false
    resetForm()
  } catch (e: any) {
    alert(e.message)
  }
}

async function handleDelete(id: number) {
  if (!confirm('确定删除此项目？')) return
  try {
    await projectStore.deleteProject(id)
  } catch (e: any) {
    alert(e.message)
  }
}
</script>

<style scoped>
.page { max-width: 1200px; margin: 0 auto; padding: 32px 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.page-header h1 { font-size: 24px; font-weight: 700; }
.back-link { color: var(--color-text-secondary); font-size: 14px; }
.form-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; z-index: 100; }
.form-panel { padding: 32px; width: 500px; max-width: 90vw; }
.form-panel h2 { font-size: 18px; margin-bottom: 20px; }
.form-panel form { display: flex; flex-direction: column; gap: 12px; }
.form-actions { display: flex; gap: 8px; margin-top: 8px; }
.project-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; margin-top: 16px; }
.project-card h3 { margin-bottom: 8px; font-size: 16px; }
.branch { color: var(--color-primary); font-size: 13px; font-family: monospace; }
.meta { color: var(--color-text-secondary); font-size: 13px; margin-top: 4px; }
.card-actions { display: flex; gap: 8px; margin-top: 16px; }
.btn-primary { background: var(--color-primary); color: #fff; border-color: var(--color-primary); }
.btn-danger { color: var(--color-danger); border-color: var(--color-danger); }
.btn-sm { padding: 4px 12px; font-size: 13px; }
</style>

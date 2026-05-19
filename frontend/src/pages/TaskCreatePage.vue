<template>
  <div class="page">
    <header class="page-header">
      <h1>新建任务</h1>
      <router-link :to="backLink" class="back-link">← 返回任务列表</router-link>
    </header>

    <form @submit.prevent="handleCreate" class="create-form card">
      <label>
        所属项目 *
        <select v-model="form.project_id" required :disabled="!!route.query.project_id">
          <option value="">请选择项目</option>
          <option v-for="p in projectStore.activeProjects" :key="p.id" :value="p.id">
            {{ p.display_name || p.name }}
          </option>
        </select>
      </label>
      <label>标题 *<input v-model="form.title" required maxlength="256" /></label>
      <label>描述（Markdown）<textarea v-model="form.description" rows="6"></textarea></label>
      <label>
        优先级
        <select v-model="form.priority">
          <option value="low">低</option>
          <option value="medium">中</option>
          <option value="high">高</option>
        </select>
      </label>
      <label>规划者（Planner）<input v-model="form.planner" /></label>
      <label>执行者（Executor）<input v-model="form.executor" /></label>
      <label>审查者（Reviewer）<input v-model="form.reviewer" /></label>
      <label>最终批准人<input v-model="form.human_approver" /></label>
      <label>目标分支<input v-model="form.target_branch" /></label>
      <button type="submit" class="btn btn-primary" :disabled="submitting">
        {{ submitting ? '创建中...' : '创建任务' }}
      </button>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useProjectStore } from '../stores/projectStore'
import { useTaskStore } from '../stores/taskStore'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const taskStore = useTaskStore()
const submitting = ref(false)

const projectId = computed(() => Number(route.query.project_id) || '')
const backLink = computed(() => {
  const pid = projectId.value
  return pid ? `/tasks?project_id=${pid}` : '/tasks'
})

const form = ref({
  project_id: Number(route.query.project_id) || '',
  title: '',
  description: '',
  priority: 'medium',
  planner: '',
  executor: '',
  reviewer: '',
  human_approver: '',
  target_branch: '',
})

onMounted(() => projectStore.fetchProjects())

async function handleCreate() {
  if (!form.value.project_id) {
    alert('请选择项目')
    return
  }
  submitting.value = true
  try {
    const task = await taskStore.createTask({
      ...form.value,
      project_id: Number(form.value.project_id),
    })
    router.push(`/tasks/${task.id}`)
  } catch (e: any) {
    alert(e.message)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.page { max-width: 700px; margin: 0 auto; padding: 32px 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.page-header h1 { font-size: 24px; font-weight: 700; }
.back-link { color: var(--color-text-secondary); font-size: 14px; }
.create-form { display: flex; flex-direction: column; gap: 16px; padding: 24px; }
.create-form textarea { resize: vertical; }
.btn-primary { background: var(--color-primary); color: #fff; border: none; padding: 10px 20px; border-radius: var(--radius); cursor: pointer; font-size: 14px; align-self: flex-start; }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
</style>

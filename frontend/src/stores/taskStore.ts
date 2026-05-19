import { defineStore } from 'pinia'
import { ref } from 'vue'
import client from '../services/api'

export interface Task {
  id: number
  project_id: number
  title: string
  description: string | null
  status: string
  priority: string
  source: string
  planner: string | null
  executor: string | null
  reviewer: string | null
  human_approver: string | null
  ticket_content: string | null
  result_summary: string | null
  pr_url: string | null
  ci_url: string | null
  deploy_url: string | null
  target_branch: string | null
  created_at: string
  updated_at: string
  project_name: string
}

export const STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  ticket_ready: '任务单就绪',
  dispatched: '已分派',
  result_submitted: '结果已提交',
  reviewing: '审查中',
  changes_requested: '已要求修改',
  approved: '已通过',
  rejected: '已拒绝',
  human_required: '需要人工审批',
  archived: '已归档',
}

export const useTaskStore = defineStore('task', () => {
  const tasks = ref<Task[]>([])
  const currentTask = ref<Task | null>(null)
  const total = ref(0)
  const loading = ref(false)

  async function fetchTasks(params: Record<string, any> = {}) {
    loading.value = true
    try {
      const { data } = await client.get('/tasks', { params })
      tasks.value = data.data || []
      total.value = data.message?.total || 0
    } finally {
      loading.value = false
    }
  }

  async function fetchTask(id: number) {
    const { data } = await client.get(`/tasks/${id}`)
    currentTask.value = data.data
    return data.data
  }

  async function createTask(body: Record<string, any>) {
    const { data } = await client.post('/tasks', body)
    return data.data
  }

  async function deleteTask(id: number) {
    await client.delete(`/tasks/${id}`)
    tasks.value = tasks.value.filter((t) => t.id !== id)
  }

  async function transitionTask(id: number, action: string, body: Record<string, any> = {}) {
    const { data } = await client.post(`/tasks/${id}/${action}`, body)
    if (currentTask.value?.id === id) {
      currentTask.value = { ...currentTask.value, ...data.data }
    }
    return data
  }

  async function fetchEvents(taskId: number) {
    const { data } = await client.get(`/tasks/${taskId}/events`)
    return data.data || []
  }

  async function fetchArtifacts(taskId: number) {
    const { data } = await client.get(`/tasks/${taskId}/artifacts`)
    return data.data || []
  }

  async function uploadArtifact(taskId: number, body: Record<string, any>) {
    const { data } = await client.post(`/tasks/${taskId}/artifacts`, body)
    return data.data
  }

  async function fetchReviews(taskId: number) {
    const { data } = await client.get(`/tasks/${taskId}/reviews`)
    return data.data || []
  }

  async function submitReview(taskId: number, body: Record<string, any>) {
    const { data } = await client.post(`/tasks/${taskId}/reviews`, body)
    return data.data
  }

  return {
    tasks,
    currentTask,
    total,
    loading,
    fetchTasks,
    fetchTask,
    createTask,
    deleteTask,
    transitionTask,
    fetchEvents,
    fetchArtifacts,
    uploadArtifact,
    fetchReviews,
    submitReview,
  }
})

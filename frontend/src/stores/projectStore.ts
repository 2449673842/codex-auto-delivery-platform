import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import client from '../services/api'

export interface Project {
  id: number
  name: string
  display_name: string | null
  root_path: string
  repo_url: string | null
  default_branch: string
  current_branch: string
  package_manager: string | null
  dev_command: string | null
  build_command: string | null
  test_command: string | null
  ci_provider: string | null
  ci_url: string | null
  deploy_provider: string | null
  deploy_url: string | null
  is_active: boolean
  created_at: string
  updated_at: string
  task_count: number
}

export const useProjectStore = defineStore('project', () => {
  const projects = ref<Project[]>([])
  const currentProject = ref<Project | null>(null)
  const loading = ref(false)

  const activeProjects = computed(() =>
    projects.value.filter((p) => p.is_active),
  )

  async function fetchProjects() {
    loading.value = true
    try {
      const { data } = await client.get('/projects')
      projects.value = data.data || []
    } finally {
      loading.value = false
    }
  }

  async function fetchProject(id: number) {
    const { data } = await client.get(`/projects/${id}`)
    currentProject.value = data.data
    return data.data
  }

  async function createProject(body: Record<string, any>) {
    const { data } = await client.post('/projects', body)
    projects.value.unshift(data.data)
    return data.data
  }

  async function updateProject(id: number, body: Record<string, any>) {
    const { data } = await client.patch(`/projects/${id}`, body)
    const idx = projects.value.findIndex((p) => p.id === id)
    if (idx !== -1) projects.value[idx] = data.data
    if (currentProject.value?.id === id) currentProject.value = data.data
    return data.data
  }

  async function deleteProject(id: number) {
    await client.delete(`/projects/${id}`)
    projects.value = projects.value.filter((p) => p.id !== id)
    if (currentProject.value?.id === id) currentProject.value = null
  }

  async function fetchProjectTasks(projectId: number, status?: string) {
    const params: Record<string, any> = { project_id: projectId }
    if (status) params.status = status
    const { data } = await client.get('/tasks', { params })
    return data
  }

  return {
    projects,
    currentProject,
    loading,
    activeProjects,
    fetchProjects,
    fetchProject,
    createProject,
    updateProject,
    deleteProject,
    fetchProjectTasks,
  }
})

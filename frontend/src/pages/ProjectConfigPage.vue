<template>
  <div class="page" v-if="project">
    <header class="page-header">
      <h1>{{ project.display_name || project.name }}</h1>
      <router-link :to="`/tasks?project_id=${project.id}`" class="btn-link">查看任务 →</router-link>
    </header>

    <div class="tabs">
      <button :class="{ active: tab === 'basic' }" @click="tab = 'basic'">基本信息</button>
      <button :class="{ active: tab === 'git' }" @click="tab = 'git'">Git 配置</button>
      <button :class="{ active: tab === 'build' }" @click="tab = 'build'">构建命令</button>
      <button :class="{ active: tab === 'integrate' }" @click="tab = 'integrate'">CI & 部署</button>
    </div>

    <form @submit.prevent="handleSave" class="config-form">
      <div v-show="tab === 'basic'">
        <label>项目名称<input v-model="form.name" /></label>
        <label>展示名<input v-model="form.display_name" /></label>
        <label>根目录路径<input v-model="form.root_path" /></label>
      </div>
      <div v-show="tab === 'git'">
        <label>仓库地址<input v-model="form.repo_url" /></label>
        <label>默认分支<input v-model="form.default_branch" /></label>
        <label>当前分支<input v-model="form.current_branch" /></label>
      </div>
      <div v-show="tab === 'build'">
        <label>包管理器<input v-model="form.package_manager" /></label>
        <label>启动命令<input v-model="form.dev_command" /></label>
        <label>构建命令<input v-model="form.build_command" /></label>
        <label>测试命令<input v-model="form.test_command" /></label>
      </div>
      <div v-show="tab === 'integrate'">
        <label>CI 类型<input v-model="form.ci_provider" /></label>
        <label>CI 地址<input v-model="form.ci_url" /></label>
        <label>部署方式<input v-model="form.deploy_provider" /></label>
        <label>部署地址<input v-model="form.deploy_url" /></label>
      </div>
      <button type="submit" class="btn btn-primary">保存配置</button>
    </form>
  </div>
  <div v-else class="loading">加载中...</div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useProjectStore } from '../stores/projectStore'

const route = useRoute()
const projectStore = useProjectStore()
const tab = ref('basic')
const project = ref<any>(null)
const form = ref<any>({})

onMounted(async () => {
  const id = Number(route.params.id)
  project.value = await projectStore.fetchProject(id)
  form.value = { ...project.value }
})

watch(
  () => route.params.id,
  async (id) => {
    project.value = await projectStore.fetchProject(Number(id))
    form.value = { ...project.value }
  },
)

async function handleSave() {
  try {
    project.value = await projectStore.updateProject(project.value.id, form.value)
    alert('配置已保存')
  } catch (e: any) {
    alert(e.message)
  }
}
</script>

<style scoped>
.page { max-width: 800px; margin: 0 auto; padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.btn-link { color: var(--color-primary); text-decoration: none; }
.tabs { display: flex; gap: 0; border-bottom: 2px solid var(--color-border); margin-bottom: 24px; }
.tabs button { padding: 10px 20px; border: none; background: none; cursor: pointer; font-size: 14px; color: var(--color-text-secondary); border-bottom: 2px solid transparent; margin-bottom: -2px; }
.tabs button.active { color: var(--color-primary); border-bottom-color: var(--color-primary); }
.config-form { display: flex; flex-direction: column; gap: 16px; }
.config-form label { display: flex; flex-direction: column; gap: 4px; font-size: 14px; color: var(--color-text-secondary); }
.config-form input { padding: 8px 12px; border: 1px solid var(--color-border); border-radius: var(--radius); font-size: 14px; }
.btn-primary { background: var(--color-primary); color: #fff; border: none; padding: 10px 20px; border-radius: var(--radius); cursor: pointer; font-size: 14px; align-self: flex-start; }
.loading { text-align: center; padding: 40px; color: var(--color-text-secondary); }
</style>

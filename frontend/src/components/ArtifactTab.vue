<template>
  <div class="artifact-tab">
    <div class="tab-bar">
      <button
        v-for="t in tabs"
        :key="t.key"
        :class="{ active: activeTab === t.key }"
        @click="activeTab = t.key"
      >
        {{ t.label }}
        <span v-if="t.count !== undefined" class="count">({{ t.count }})</span>
      </button>
    </div>

    <div v-if="activeTab === 'diff' || activeTab === 'execution_log'" class="content-area">
      <div v-for="a in filteredArtifacts" :key="a.id" class="artifact-item">
        <div class="artifact-meta">
          <span class="artifact-type">{{ a.artifact_type }}</span>
          <span class="artifact-size">{{ a.size_bytes }} bytes</span>
          <button class="btn-link" @click="showUploadForm = !showUploadForm">+ 上传</button>
        </div>
        <DiffViewer :content="a.content" :is-truncated="a.is_truncated" />
      </div>
    </div>

    <div v-if="showUploadForm" class="upload-form">
      <select v-model="uploadForm.artifact_type">
        <option value="diff">Diff</option>
        <option value="execution_log">Execution Log</option>
      </select>
      <textarea v-model="uploadForm.content" placeholder="粘贴内容..." rows="6"></textarea>
      <button class="btn btn-primary btn-sm" @click="handleUpload">上传</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useTaskStore } from '../stores/taskStore'
import DiffViewer from './DiffViewer.vue'

const props = defineProps<{ taskId: number }>()
const taskStore = useTaskStore()
const artifacts = ref<any[]>([])
const activeTab = ref('diff')
const showUploadForm = ref(false)
const uploadForm = ref({ artifact_type: 'diff', content: '' })

const tabs = computed(() => [
  { key: 'diff', label: 'Diff', count: artifacts.value.filter((a) => a.artifact_type === 'diff').length },
  { key: 'execution_log', label: '执行日志', count: artifacts.value.filter((a) => a.artifact_type === 'execution_log').length },
])

const filteredArtifacts = computed(() =>
  artifacts.value.filter((a) => a.artifact_type === activeTab.value),
)

onMounted(() => load())
watch(() => props.taskId, () => load())

async function load() {
  artifacts.value = await taskStore.fetchArtifacts(props.taskId)
}

async function handleUpload() {
  try {
    await taskStore.uploadArtifact(props.taskId, uploadForm.value)
    uploadForm.value = { artifact_type: 'diff', content: '' }
    showUploadForm.value = false
    await load()
  } catch (e: any) {
    alert(e.message)
  }
}
</script>

<style scoped>
.artifact-tab { font-size: 14px; }
.tab-bar { display: flex; gap: 0; border-bottom: 2px solid var(--color-border); margin-bottom: 16px; }
.tab-bar button { padding: 8px 16px; border: none; background: none; cursor: pointer; font-size: 14px; color: var(--color-text-secondary); border-bottom: 2px solid transparent; margin-bottom: -2px; }
.tab-bar button.active { color: var(--color-primary); border-bottom-color: var(--color-primary); }
.count { font-size: 12px; color: var(--color-text-secondary); }
.content-area { min-height: 100px; }
.artifact-item { margin-bottom: 16px; }
.artifact-meta { display: flex; gap: 12px; align-items: center; margin-bottom: 8px; font-size: 13px; color: var(--color-text-secondary); }
.btn-link { color: var(--color-primary); cursor: pointer; background: none; border: none; font-size: 13px; }
.upload-form { margin-top: 16px; display: flex; flex-direction: column; gap: 8px; }
.upload-form select, .upload-form textarea { padding: 8px; border: 1px solid var(--color-border); border-radius: var(--radius); font-size: 14px; font-family: inherit; }
.btn-primary { background: var(--color-primary); color: #fff; border: none; }
.btn-sm { padding: 8px 16px; border-radius: var(--radius); cursor: pointer; font-size: 14px; align-self: flex-start; }
</style>

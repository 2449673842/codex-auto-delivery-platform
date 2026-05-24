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

    <div v-if="filteredArtifacts.length > 0" class="content-area">
      <div v-for="a in filteredArtifacts" :key="a.id" class="artifact-item">
        <div class="artifact-meta">
          <span class="artifact-type">{{ a.artifact_type }}</span>
          <span v-if="a.filename" class="artifact-file">{{ a.filename }}</span>
          <span class="artifact-size">{{ a.size_bytes }} bytes</span>
        </div>
        <DiffViewer :content="a.content" :is-truncated="a.is_truncated" />
      </div>
    </div>

    <div v-else class="empty-artifacts">
      <p>暂无{{ currentTabLabel }}产物</p>
      <button v-if="!isArchived" class="btn btn-primary btn-sm" @click="showUploadForm = true">+ 上传 {{ currentTabLabel }}</button>
    </div>

    <div v-if="showUploadForm && !isArchived" class="upload-form card" style="margin-top: 16px;">
      <h4>上传产物</h4>
      <select v-model="uploadForm.artifact_type">
        <option value="diff">Diff</option>
        <option value="execution_log">执行日志</option>
        <option value="review_note">审查备注</option>
        <option value="ci_log">CI 日志</option>
        <option value="screenshot">截图文本</option>
      </select>
      <textarea v-model="uploadForm.content" placeholder="粘贴内容..." rows="6"></textarea>
      <div class="upload-actions">
        <button class="btn btn-primary btn-sm" @click="handleUpload">上传</button>
        <button class="btn btn-sm" @click="showUploadForm = false">取消</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useTaskStore } from '../stores/taskStore'
import DiffViewer from './DiffViewer.vue'

const props = defineProps<{ taskId: number; taskStatus?: string }>()
const taskStore = useTaskStore()
const artifacts = ref<any[]>([])
const activeTab = ref('browser_ai_answer')
const showUploadForm = ref(false)
const uploadForm = ref({ artifact_type: 'diff', content: '' })

const isArchived = computed(() => props.taskStatus === 'archived')

const tabs = computed(() => [
  { key: 'browser_ai_answer', label: 'Browser AI', count: artifacts.value.filter((a) => a.artifact_type === 'browser_ai_answer').length },
  { key: 'diff', label: 'Diff', count: artifacts.value.filter((a) => a.artifact_type === 'diff').length },
  { key: 'execution_log', label: '执行日志', count: artifacts.value.filter((a) => a.artifact_type === 'execution_log').length },
  { key: 'review_note', label: '审查备注', count: artifacts.value.filter((a) => a.artifact_type === 'review_note').length },
  { key: 'ci_log', label: 'CI 日志', count: artifacts.value.filter((a) => a.artifact_type === 'ci_log').length },
  { key: 'screenshot', label: '截图', count: artifacts.value.filter((a) => a.artifact_type === 'screenshot').length },
])

const currentTabLabel = computed(() => {
  const t = tabs.value.find((t) => t.key === activeTab.value)
  return t ? t.label : activeTab.value
})

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
.tab-bar { display: flex; gap: 0; border-bottom: 2px solid var(--color-border); margin-bottom: 16px; flex-wrap: wrap; }
.tab-bar button { padding: 8px 16px; border: none; background: none; cursor: pointer; font-size: 14px; color: var(--color-text-secondary); border-bottom: 2px solid transparent; margin-bottom: -2px; transition: color 0.15s; }
.tab-bar button.active { color: var(--color-primary); border-bottom-color: var(--color-primary); }
.tab-bar button:hover { color: var(--color-primary); }
.count { font-size: 12px; color: var(--color-text-secondary); margin-left: 2px; }
.content-area { min-height: 60px; }
.artifact-item { margin-bottom: 16px; padding-bottom: 16px; border-bottom: 1px solid var(--color-border); }
.artifact-item:last-child { border-bottom: none; margin-bottom: 0; padding-bottom: 0; }
.artifact-meta { display: flex; gap: 12px; align-items: center; margin-bottom: 8px; font-size: 13px; color: var(--color-text-secondary); }
.artifact-type { font-weight: 600; text-transform: capitalize; }
.empty-artifacts { text-align: center; padding: 32px 16px; color: var(--color-text-secondary); }
.empty-artifacts p { margin-bottom: 12px; }
.upload-form { display: flex; flex-direction: column; gap: 12px; }
.upload-form h4 { font-size: 15px; font-weight: 600; }
.upload-actions { display: flex; gap: 8px; }
.btn-primary { background: var(--color-primary); color: #fff; border: none; }
.btn-sm { padding: 8px 16px; border-radius: var(--radius); cursor: pointer; font-size: 14px; }
</style>

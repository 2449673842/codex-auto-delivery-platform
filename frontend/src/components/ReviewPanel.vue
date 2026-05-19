<template>
  <div class="review-panel">
    <div v-if="reviews.length === 0 && taskStatus !== 'reviewing'" class="empty">
      暂无审查记录
    </div>

    <div v-for="r in reviews" :key="r.id" class="review-item">
      <div class="review-header">
        <span class="decision" :class="r.decision">{{ r.decision }}</span>
        <span class="reviewer">审查者: {{ r.reviewer || '-' }}</span>
        <span class="review-time">{{ new Date(r.created_at).toLocaleString() }}</span>
      </div>
      <p v-if="r.comments" class="review-comments">{{ r.comments }}</p>
      <p v-if="r.linter_passed !== null" class="review-lint">
        Lint: {{ r.linter_passed ? '✅ 通过' : '❌ 未通过' }}
      </p>
    </div>

    <div v-if="taskStatus === 'reviewing'" class="review-form">
      <h3>提交审查</h3>
      <select v-model="form.decision">
        <option value="approved">通过 (Approved)</option>
        <option value="rejected">拒绝 (Rejected)</option>
        <option value="changes_requested">要求修改 (Changes Requested)</option>
      </select>
      <textarea v-model="form.comments" placeholder="审查意见..." rows="4"></textarea>
      <label class="checkbox-label">
        <input type="checkbox" v-model="form.linter_passed" /> Lint 通过
      </label>
      <button class="btn btn-primary btn-sm" @click="handleSubmit">提交审查</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useTaskStore } from '../stores/taskStore'

const props = defineProps<{ taskId: number; taskStatus: string }>()
const emit = defineEmits<{ 'review-submitted': [] }>()
const taskStore = useTaskStore()
const reviews = ref<any[]>([])
const form = ref({ decision: 'approved', comments: '', linter_passed: false })

onMounted(() => load())
watch(() => props.taskId, () => load())
watch(() => props.taskStatus, () => {
  if (props.taskStatus === 'reviewing') load()
})

async function load() {
  reviews.value = await taskStore.fetchReviews(props.taskId)
}

async function handleSubmit() {
  try {
    await taskStore.submitReview(props.taskId, form.value)
    form.value = { decision: 'approved', comments: '', linter_passed: false }
    await load()
    emit('review-submitted')
  } catch (e: any) {
    alert(e.message)
  }
}
</script>

<style scoped>
.review-panel { font-size: 14px; }
.empty { color: var(--color-text-secondary); }
.review-item { padding: 12px 0; border-bottom: 1px solid var(--color-border); }
.review-item:last-child { border-bottom: none; }
.review-header { display: flex; gap: 12px; align-items: center; margin-bottom: 8px; }
.decision { padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; }
.decision.approved { background: #e8f5e9; color: #2e7d32; }
.decision.rejected { background: #ffebee; color: #c62828; }
.decision.changes_requested { background: #fff3e0; color: #e65100; }
.reviewer { color: var(--color-text-secondary); font-size: 13px; }
.review-time { color: var(--color-text-secondary); font-size: 12px; margin-left: auto; }
.review-comments { color: var(--color-text-secondary); font-size: 13px; }
.review-lint { font-size: 13px; margin-top: 4px; }
.review-form { margin-top: 16px; display: flex; flex-direction: column; gap: 8px; }
.review-form select, .review-form textarea { padding: 8px; border: 1px solid var(--color-border); border-radius: var(--radius); font-size: 14px; font-family: inherit; }
.checkbox-label { display: flex; align-items: center; gap: 8px; font-size: 14px; }
.btn-primary { background: var(--color-primary); color: #fff; border: none; }
.btn-sm { padding: 8px 16px; border-radius: var(--radius); cursor: pointer; font-size: 14px; align-self: flex-start; }
</style>

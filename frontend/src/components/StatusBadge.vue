<template>
  <span class="status-badge" :class="status">{{ label }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ status: string }>()

const LABELS: Record<string, string> = {
  draft: '草稿',
  ticket_ready: '任务单就绪',
  dispatched: '已分派',
  result_submitted: '结果已提交',
  reviewing: '审查中',
  changes_requested: '要求修改',
  approved: '已通过',
  rejected: '已拒绝',
  human_required: '需要人工审批',
  archived: '已归档',
}

const label = computed(() => LABELS[props.status] || props.status)
</script>

<style scoped>
.status-badge { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; white-space: nowrap; }
.status-badge.draft { background: #f5f5f5; color: #616161; }
.status-badge.ticket_ready { background: #e3f2fd; color: #1565c0; }
.status-badge.dispatched { background: #f3e5f5; color: #7b1fa2; }
.status-badge.result_submitted { background: #e0f7fa; color: #00838f; }
.status-badge.reviewing { background: #fff3e0; color: #e65100; }
.status-badge.changes_requested { background: #fff8e1; color: #f57f17; }
.status-badge.approved { background: #e8f5e9; color: #2e7d32; }
.status-badge.rejected { background: #ffebee; color: #c62828; }
.status-badge.human_required { background: #fce4ec; color: #c62828; }
.status-badge.archived { background: #f5f5f5; color: #616161; }
</style>

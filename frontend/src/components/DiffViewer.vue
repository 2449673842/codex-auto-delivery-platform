<template>
  <div class="diff-viewer">
    <pre :class="{ truncated: isTruncated }">{{ content || '（无内容）' }}</pre>
    <p v-if="isTruncated" class="truncated-notice">内容过长，已截断</p>
  </div>
</template>

<script setup lang="ts">
defineProps<{ content: string; isTruncated?: boolean }>()
</script>

<style scoped>
.diff-viewer { background: #f5f5f5; border-radius: var(--radius); padding: 16px; overflow-x: auto; }
.diff-viewer pre { white-space: pre-wrap; font-size: 13px; line-height: 1.5; font-family: 'SFMono-Regular', Consolas, monospace; }
.truncated { max-height: 400px; overflow: hidden; position: relative; }
.truncated-notice { color: var(--color-text-secondary); font-size: 12px; margin-top: 8px; }
</style>

<template>
  <div class="ticket-preview">
    <pre>{{ content }}</pre>
  </div>
</template>

<script setup lang="ts">
defineProps<{ content: string }>()
</script>

<style scoped>
.ticket-preview { background: #f8f9fa; border-radius: var(--radius); padding: 16px; overflow-x: auto; }
.ticket-preview pre { white-space: pre-wrap; font-size: 13px; line-height: 1.6; font-family: 'SFMono-Regular', Consolas, monospace; }
</style>

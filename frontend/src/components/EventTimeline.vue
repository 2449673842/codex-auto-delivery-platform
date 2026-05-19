<template>
  <div class="timeline">
    <div v-for="e in events" :key="e.id" class="event-item">
      <div class="event-dot"></div>
      <div class="event-body">
        <div class="event-header">
          <span class="event-type">{{ e.event_type }}</span>
          <span class="event-time">{{ new Date(e.created_at).toLocaleString() }}</span>
        </div>
        <p class="event-msg">{{ e.message }}</p>
        <p v-if="e.from_status || e.to_status" class="event-transition">
          {{ e.from_status || '(空)' }} → {{ e.to_status || '(空)' }}
        </p>
      </div>
    </div>
    <div v-if="events.length === 0" class="empty">暂无事件记录</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useTaskStore } from '../stores/taskStore'

const props = defineProps<{ taskId: number }>()
const taskStore = useTaskStore()
const events = ref<any[]>([])

onMounted(() => load())
watch(() => props.taskId, () => load())

async function load() {
  events.value = await taskStore.fetchEvents(props.taskId)
}
</script>

<style scoped>
.timeline { position: relative; padding-left: 24px; }
.timeline::before { content: ''; position: absolute; left: 8px; top: 0; bottom: 0; width: 2px; background: var(--color-border); }
.event-item { position: relative; padding-bottom: 16px; }
.event-dot { position: absolute; left: -16px; top: 4px; width: 10px; height: 10px; border-radius: 50%; background: var(--color-primary); border: 2px solid var(--color-surface); }
.event-header { display: flex; justify-content: space-between; margin-bottom: 4px; }
.event-type { font-weight: 600; font-size: 14px; text-transform: capitalize; }
.event-time { color: var(--color-text-secondary); font-size: 12px; }
.event-msg { color: var(--color-text-secondary); font-size: 13px; }
.event-transition { font-size: 12px; font-family: monospace; color: var(--color-primary); margin-top: 4px; }
.empty { color: var(--color-text-secondary); font-size: 14px; padding: 8px 0; }
</style>

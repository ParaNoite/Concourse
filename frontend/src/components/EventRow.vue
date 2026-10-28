<script setup lang="ts">
import type { ScheduleEvent } from '../types'

defineProps<{
  event: ScheduleEvent
  urgency: 'urgent' | 'warn' | 'normal' | 'done'
}>()

const POLICY_LABEL: Record<string, string> = {
  none: '不可补',
  once: '仅一次',
  late: '可补交',
  unlimited: '无限次',
}

function fmt(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso + (iso.endsWith('Z') ? '' : 'Z'))
  return d.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  })
}
</script>

<template>
  <div class="event-row" :class="`row-${urgency}`">
    <span class="col-platform">{{ event.platform }}</span>
    <span class="col-title">{{ event.title }}</span>
    <span class="col-deadline">{{ fmt(event.end_at) }}</span>
    <span class="col-policy">
      <span v-if="event.submission_policy && event.submission_policy !== 'none'"
        class="badge" :class="`policy-${event.submission_policy}`">
        {{ POLICY_LABEL[event.submission_policy] ?? event.submission_policy }}
      </span>
    </span>
  </div>
</template>

<style scoped>
.event-row {
  display: grid;
  grid-template-columns: 96px 1fr 120px 76px;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  transition: background .1s;
  cursor: default;
  position: relative;
}
.event-row:last-child { border-bottom: none; }
.event-row:hover { background: rgba(0,103,192,.04); }

/* urgency left strip */
.row-urgent { border-left: 3px solid var(--urgent); padding-left: 13px; }
.row-warn   { border-left: 3px solid #F59E0B;      padding-left: 13px; }

.col-platform { font-family: var(--mono); font-size: 10px; color: var(--muted); }
.col-title    { font-size: 13px; }
.col-deadline { font-family: var(--mono); font-size: 11px; color: var(--muted); text-align: right; }
.col-policy   { text-align: right; }

.row-urgent .col-deadline { color: var(--urgent); font-weight: 600; }
.row-urgent .col-title    { font-weight: 500; }
.row-warn   .col-deadline { color: var(--warn); }
.row-done   .col-title    { color: var(--done); text-decoration: line-through; }
.row-done   .col-deadline { color: var(--done); }

.badge {
  display: inline-block; padding: 2px 7px; border-radius: 12px;
  font-size: 10px; font-family: var(--mono);
  border: 1px solid var(--border-strong); color: var(--muted);
}
.policy-once { background: #FDE7E9; border-color: #F1BCBF; color: var(--urgent); }
.policy-late { background: #FFF4CE; border-color: #F0D06A; color: var(--warn); }
</style>

<script setup lang="ts">
import { useEventsStore } from '../stores/events'
const store = useEventsStore()

function fmt(iso: string | null): string {
  if (!iso) return '—'
  const ms = Date.parse(iso.endsWith('Z') || /[+-]\d\d:\d\d$/.test(iso) ? iso : iso + 'Z')
  return new Date(ms).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  })
}
</script>

<template>
  <div v-if="store.staged.length" class="staged-panel">
    <div class="staged-header">
      <span>暂存区 — 待确认</span>
      <span class="staged-count">{{ store.staged.length }}</span>
    </div>
    <div v-for="s in store.staged" :key="s.id" class="staged-row">
      <span class="staged-platform">{{ s.platform }}</span>
      <span class="staged-title">{{ s.title }}</span>
      <span class="staged-deadline">{{ fmt(s.end_at) }}</span>
      <div class="staged-actions">
        <button class="btn btn-primary" @click="store.acceptStaged(s.id)">接受</button>
        <button class="btn btn-ghost"   @click="store.dismissStaged(s.id)">驳回</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.staged-panel {
  background: var(--surface);
  backdrop-filter: blur(20px) saturate(1.3);
  -webkit-backdrop-filter: blur(20px) saturate(1.3);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow-sm);
  margin-bottom: 16px;
  overflow: hidden;
}
.staged-header {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  font-size: 12px; font-weight: 600; color: var(--muted);
}
.staged-count {
  background: #FDE7E9; border: 1px solid #F1BCBF;
  color: var(--urgent); border-radius: 12px;
  padding: 1px 7px; font-size: 10px; font-family: var(--mono);
}
.staged-row {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}
.staged-row:last-child { border-bottom: none; }
.staged-platform { font-family: var(--mono); font-size: 10px; color: var(--muted); width: 70px; }
.staged-title { flex: 1; }
.staged-deadline { font-family: var(--mono); font-size: 11px; color: var(--muted); }
.staged-actions { display: flex; gap: 6px; }
.btn { padding: 4px 12px; border-radius: 4px; font-size: 12px; }
.btn-primary { background: var(--accent); color: #fff; border: 1px solid var(--accent-hover); }
.btn-primary:hover { background: var(--accent-hover); }
.btn-ghost { background: transparent; border: 1px solid var(--border-strong); color: var(--muted); }
.btn-ghost:hover { background: var(--bg); }
</style>

<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useEventsStore } from '../stores/events'
import type { ScheduleEvent } from '../types'

const store = useEventsStore()

onMounted(() => { store.fetchTrash() })

const PLATFORM_DISPLAY: Record<string, string> = {
  scholat: '学者网', pigai: '批改网', moodle: 'Moodle',
  itestcloud: 'iTest', welearn: 'WeLearn', codeforces: 'Codeforces', manual: '手动添加',
}
function displayName(p: string): string { return PLATFORM_DISPLAY[p] ?? p }

const items = computed(() => store.trash)

function fmt(iso: string | null): string {
  if (!iso) return '—'
  const ms = Date.parse(iso.endsWith('Z') || /[+-]\d\d:\d\d$/.test(iso) ? iso : iso + 'Z')
  return new Date(ms).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  })
}

function fmtFull(iso: string | null): string {
  if (!iso) return '—'
  const ms = Date.parse(iso.endsWith('Z') || /[+-]\d\d:\d\d$/.test(iso) ? iso : iso + 'Z')
  return new Date(ms).toLocaleString('zh-CN', { hour12: false, timeZone: 'Asia/Shanghai' })
}

async function restore(e: ScheduleEvent) {
  try { await store.restoreEvent(e.id) }
  catch (err: any) { console.error(err.message) }
}

async function permDelete(e: ScheduleEvent) {
  if (!confirm(`永久删除？此操作不可撤销\n${e.title}`)) return
  try { await store.permanentDelete(e.id) }
  catch (err: any) { console.error(err.message) }
}
</script>

<template>
  <div class="trash-view">
    <div class="trash-header">
      <h2 class="trash-title">回收站</h2>
      <span class="trash-count">{{ items.length }} 项</span>
    </div>

    <div v-if="!items.length" class="empty">回收站为空</div>

    <div v-else class="trash-list">
      <div v-for="e in items" :key="e.id" class="trash-row">
        <span class="col-platform">{{ displayName(e.platform) }}</span>
        <span class="col-course">{{ e.course || '—' }}</span>
        <span class="col-title">{{ e.title }}</span>
        <span class="col-deadline">{{ fmt(e.end_at) }}</span>
        <span class="col-deleted">删除于 {{ fmtFull(e.deleted_at) }}</span>
        <span class="col-actions">
          <button class="btn restore-btn" @click="restore(e)">恢复</button>
          <button class="btn perm-btn" @click="permDelete(e)">永久删除</button>
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.trash-view { max-width: 900px; margin: 0 auto; padding: 24px 20px 60px; }
.trash-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 16px; }
.trash-title  { font-size: 18px; font-weight: 600; letter-spacing: -.3px; }
.trash-count  { font-size: 12px; color: var(--muted); font-family: var(--mono); }

.trash-list {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}
.trash-row {
  display: grid;
  grid-template-columns: 80px 96px 1fr 110px 150px 132px;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}
.trash-row:last-child { border-bottom: none; }

.col-platform { font-family: var(--mono); font-size: 10px; color: var(--muted); }
.col-course   { font-family: var(--mono); font-size: 10px; color: var(--muted); }
.col-title    { font-size: 13px; }
.col-deadline { font-family: var(--mono); font-size: 11px; color: var(--muted); text-align: right; }
.col-deleted  { font-family: var(--mono); font-size: 10px; color: var(--muted); text-align: right; }
.col-actions  { display: flex; gap: 6px; justify-content: flex-end; }

.btn {
  padding: 3px 10px; border-radius: 4px; font-size: 11px;
  border: 1px solid var(--border-strong); background: transparent;
  color: var(--muted); cursor: pointer; transition: background .1s, color .1s;
}
.restore-btn:hover { background: #EAF4E9; color: #107C10; border-color: #107C10; }
.perm-btn:hover    { background: #FDE7E9; color: var(--urgent); border-color: var(--urgent); }

.empty { padding: 24px; text-align: center; color: var(--muted); font-size: 13px; }
</style>

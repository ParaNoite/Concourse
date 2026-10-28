<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useEventsStore } from '../stores/events'
import StagedPanel from '../components/StagedPanel.vue'
import EventRow from '../components/EventRow.vue'

const store = useEventsStore()

onMounted(() => {
  store.startPoll()
  store.startTick()
})
onUnmounted(() => {
  store.stopPoll()
  store.stopTick()
})

const addText = ref('')
const adding = ref(false)
const addError = ref('')

import { ref } from 'vue'
const BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

async function addEvent() {
  if (!addText.value.trim()) return
  adding.value = true
  addError.value = ''
  try {
    const token = (import.meta.env.VITE_AGENT_TOKEN as string) || ''
    const resp = await fetch(`${BASE}/agent`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ message: addText.value }),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const data = await resp.json()
    if (data.staged_ids?.length) {
      await store.fetchEvents()
      addText.value = ''
    } else {
      addError.value = data.reply || '未生成暂存事项'
    }
  } catch (e: any) {
    addError.value = e.message
  } finally {
    adding.value = false
  }
}
</script>

<template>
  <div class="dashboard">
    <!-- platform filter tabs -->
    <div class="platform-bar">
      <button
        v-for="p in store.platforms"
        :key="p"
        class="ptab"
        :class="{ active: store.activePlatform === p }"
        @click="store.activePlatform = p"
      >{{ p === 'all' ? '全部' : p }}</button>
    </div>

    <!-- stat tiles -->
    <div class="stat-row">
      <div class="stat-tile hot">
        <div class="stat-num">{{ store.urgentEvents.length }}</div>
        <div class="stat-label">48 小时内截止</div>
      </div>
      <div class="stat-tile">
        <div class="stat-num">{{ store.warnEvents.length }}</div>
        <div class="stat-label">本周内截止</div>
      </div>
      <div class="stat-tile">
        <div class="stat-num">{{ store.staged.length }}</div>
        <div class="stat-label">待确认暂存</div>
      </div>
      <div class="stat-tile">
        <div class="stat-num">{{ store.doneEvents.length }}</div>
        <div class="stat-label">已完成</div>
      </div>
    </div>

    <!-- loading / error -->
    <div v-if="store.loading" class="status-bar">正在加载…</div>
    <div v-else-if="store.error" class="status-bar error">{{ store.error }}</div>

    <!-- staged -->
    <StagedPanel />

    <!-- urgent -->
    <div v-if="store.urgentEvents.length" class="card">
      <div class="card-header">
        <span class="card-title">紧急 — 48 小时内</span>
        <span class="card-count urgent">{{ store.urgentEvents.length }}</span>
      </div>
      <EventRow v-for="e in store.urgentEvents" :key="e.id" :event="e" urgency="urgent" />
    </div>

    <!-- this week -->
    <div v-if="store.warnEvents.length" class="card">
      <div class="card-header">
        <span class="card-title">本周</span>
        <span class="card-count">{{ store.warnEvents.length }}</span>
      </div>
      <EventRow v-for="e in store.warnEvents" :key="e.id" :event="e" urgency="warn" />
    </div>

    <!-- upcoming -->
    <div v-if="store.normalEvents.length" class="card">
      <div class="card-header">
        <span class="card-title">即将到来</span>
        <span class="card-count">{{ store.normalEvents.length }}</span>
      </div>
      <EventRow v-for="e in store.normalEvents" :key="e.id" :event="e" urgency="normal" />
    </div>

    <!-- done -->
    <div v-if="store.doneEvents.length" class="card">
      <div class="card-header">
        <span class="card-title">已完成</span>
        <span class="card-count">{{ store.doneEvents.length }}</span>
      </div>
      <EventRow v-for="e in store.doneEvents" :key="e.id" :event="e" urgency="done" />
    </div>

    <!-- add strip -->
    <div class="add-card">
      <div class="add-strip">
        <input
          v-model="addText"
          type="text"
          placeholder="描述新事项（自然语言），AI 解析后进暂存区"
          @keyup.enter="addEvent"
          :disabled="adding"
        />
        <button @click="addEvent" :disabled="adding">{{ adding ? '…' : '添加' }}</button>
      </div>
      <div v-if="addError" class="add-error">{{ addError }}</div>
      <div class="add-hint">自然语言由 AI 解析 · 需要 VITE_AGENT_TOKEN 环境变量</div>
    </div>
  </div>
</template>

<style scoped>
.dashboard { max-width: 900px; margin: 0 auto; padding: 24px 20px 60px; }

.platform-bar { display: flex; gap: 0; margin-bottom: 20px; flex-wrap: wrap; }
.ptab {
  padding: 5px 14px; font-size: 12px; color: var(--muted);
  border: none; background: none;
  border-bottom: 2px solid transparent;
}
.ptab.active { color: var(--accent); border-bottom-color: var(--accent); }

.stat-row { display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }
.stat-tile {
  flex: 1 1 120px;
  background: var(--surface-solid);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px;
  box-shadow: var(--shadow-sm);
}
.stat-num { font-size: 28px; font-weight: 600; line-height: 1; color: var(--text); }
.stat-tile.hot .stat-num { color: var(--urgent); }
.stat-label { font-size: 11px; color: var(--muted); margin-top: 4px; }

.status-bar { padding: 8px 16px; font-size: 12px; color: var(--muted); }
.status-bar.error { color: var(--urgent); }

.card {
  background: var(--surface);
  backdrop-filter: blur(20px) saturate(1.3);
  -webkit-backdrop-filter: blur(20px) saturate(1.3);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow-sm);
  margin-bottom: 16px;
  overflow: hidden;
  position: relative;
}
.card::before {
  content: '';
  position: absolute; inset: 0;
  background: radial-gradient(circle at var(--mx, 50%) var(--my, 50%), rgba(0,103,192,.10) 0%, transparent 60%);
  pointer-events: none; border-radius: inherit; opacity: 0; transition: opacity .2s;
}
.card:hover::before { opacity: 1; }

.card-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
}
.card-title { font-size: 12px; font-weight: 600; color: var(--muted); }
.card-count {
  font-size: 10px; font-family: var(--mono);
  background: var(--bg); border: 1px solid var(--border);
  border-radius: 12px; padding: 1px 7px; color: var(--muted);
}
.card-count.urgent { background: #FDE7E9; border-color: #F1BCBF; color: var(--urgent); }

.add-card {
  background: var(--surface-solid);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow-sm);
  padding: 16px;
  margin-top: 8px;
}
.add-strip { display: flex; gap: 8px; }
.add-strip input {
  flex: 1; padding: 8px 12px;
  background: var(--bg); border: 1px solid var(--border-strong);
  border-radius: 4px; color: var(--text); font-size: 13px; outline: none;
}
.add-strip input:focus { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(0,103,192,.12); }
.add-strip button {
  padding: 8px 18px;
  background: var(--accent); color: #fff; border: 1px solid var(--accent-hover);
  border-radius: 4px; font-size: 13px;
}
.add-strip button:hover:not(:disabled) { background: var(--accent-hover); }
.add-strip button:disabled { opacity: .6; cursor: default; }
.add-error { font-size: 12px; color: var(--urgent); margin-top: 6px; }
.add-hint { font-size: 11px; color: var(--muted); margin-top: 6px; font-family: var(--mono); }
</style>

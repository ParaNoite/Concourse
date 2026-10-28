<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useEventsStore } from '../stores/events'
import type { ScheduleEvent } from '../types'

const store = useEventsStore()

// ── Timeline window: now-1d to now+30d ─────────────────────────────────────
const now = ref(Date.now())
let timer: ReturnType<typeof setInterval>
onMounted(() => {
  if (!store.events.length) store.fetchEvents()
  timer = setInterval(() => { now.value = Date.now() }, 30_000)
})
onUnmounted(() => clearInterval(timer))

const WINDOW_PAST_H  = 24          // hours before now shown
const WINDOW_FUTURE_D = 30         // days after now shown
const WINDOW_MS = (WINDOW_PAST_H + WINDOW_FUTURE_D * 24) * 3_600_000

const windowStart = computed(() => now.value - WINDOW_PAST_H * 3_600_000)
const windowEnd   = computed(() => now.value + WINDOW_FUTURE_D * 24 * 3_600_000)

// ── Platforms ────────────────────────────────────────────────────────────────
const PLATFORM_COLORS: Record<string, string> = {
  scholat:     '#0067C0',
  pigai:       '#107C10',
  moodle:      '#FF8C00',
  itestcloud:  '#8764B8',
  welearn:     '#00B7C3',
  codeforces:  '#C50F1F',
  manual:      '#767676',
}
function platformColor(p: string): string {
  return PLATFORM_COLORS[p] ?? '#767676'
}

// ── Events in window ─────────────────────────────────────────────────────────
const visibleEvents = computed(() =>
  store.events.filter((e) => {
    if (!e.end_at) return false
    const d = Date.parse(e.end_at + (e.end_at.endsWith('Z') ? '' : 'Z'))
    return d >= windowStart.value && d <= windowEnd.value
  }).sort((a, b) => {
    const da = Date.parse(a.end_at! + 'Z')
    const db = Date.parse(b.end_at! + 'Z')
    return da - db
  })
)

// ── Position helpers (0–100%) ─────────────────────────────────────────────────
function toPercent(ms: number): number {
  return ((ms - windowStart.value) / WINDOW_MS) * 100
}
const nowPercent = computed(() => toPercent(now.value))

// ── Urgency ──────────────────────────────────────────────────────────────────
function urgency(e: ScheduleEvent): 'urgent' | 'warn' | 'done' | 'normal' {
  if (e.status === 'submitted') return 'done'
  if (!e.end_at) return 'normal'
  const d = Date.parse(e.end_at + (e.end_at.endsWith('Z') ? '' : 'Z'))
  const diff = d - now.value
  if (diff <= 0) return 'done'
  if (diff <= 48 * 3_600_000) return 'urgent'
  if (diff <= 7 * 24 * 3_600_000) return 'warn'
  return 'normal'
}

// ── Countdown ─────────────────────────────────────────────────────────────────
function countdown(e: ScheduleEvent): string {
  if (!e.end_at) return '—'
  const d = Date.parse(e.end_at + (e.end_at.endsWith('Z') ? '' : 'Z'))
  const diff = d - now.value
  if (diff <= 0) {
    const over = -diff
    if (over < 3_600_000) return `已过 ${Math.floor(over / 60_000)} 分`
    if (over < 86_400_000) return `已过 ${Math.floor(over / 3_600_000)} 时`
    return `已过 ${Math.floor(over / 86_400_000)} 天`
  }
  if (diff < 3_600_000) return `还剩 ${Math.floor(diff / 60_000)} 分钟`
  if (diff < 86_400_000) return `还剩 ${Math.floor(diff / 3_600_000)} 小时`
  const d2 = Math.floor(diff / 86_400_000)
  const h  = Math.floor((diff % 86_400_000) / 3_600_000)
  return h > 0 ? `还剩 ${d2} 天 ${h} 小时` : `还剩 ${d2} 天`
}

// ── Axis ticks ────────────────────────────────────────────────────────────────
interface Tick { label: string; pct: number; major: boolean }
const ticks = computed<Tick[]>(() => {
  const result: Tick[] = []
  const start = new Date(windowStart.value)
  // Align to next midnight after window start
  const d = new Date(start)
  d.setUTCHours(0, 0, 0, 0)
  d.setUTCDate(d.getUTCDate() + 1)

  while (d.getTime() <= windowEnd.value) {
    const ts = d.getTime()
    result.push({
      label: d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' }),
      pct: toPercent(ts),
      major: true,
    })
    // 12-hour minor tick
    const noon = new Date(d)
    noon.setUTCHours(12)
    if (noon.getTime() < windowEnd.value) {
      result.push({ label: '12:00', pct: toPercent(noon.getTime()), major: false })
    }
    d.setUTCDate(d.getUTCDate() + 1)
  }
  return result
})

// ── Detail popup ──────────────────────────────────────────────────────────────
const selected = ref<ScheduleEvent | null>(null)
function select(e: ScheduleEvent) {
  selected.value = selected.value?.id === e.id ? null : e
}

function fmtFull(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso + (iso.endsWith('Z') ? '' : 'Z'))
    .toLocaleString('zh-CN', { hour12: false, timeZone: 'Asia/Shanghai' })
}
</script>

<template>
  <div class="timeline-view">
    <div class="tl-header">
      <h2 class="tl-title">时间轴</h2>
      <span class="tl-range">未来 {{ WINDOW_FUTURE_D }} 天</span>
    </div>

    <!-- legend -->
    <div class="legend">
      <span v-for="(color, name) in PLATFORM_COLORS" :key="name" class="legend-item">
        <span class="legend-dot" :style="{ background: color }"></span>{{ name }}
      </span>
    </div>

    <div class="tl-wrap">
      <!-- axis -->
      <div class="axis">
        <div class="axis-track">
          <!-- ticks -->
          <div
            v-for="(t, i) in ticks"
            :key="i"
            class="tick"
            :class="{ major: t.major }"
            :style="{ left: t.pct + '%' }"
          >
            <span class="tick-label" v-if="t.major">{{ t.label }}</span>
          </div>
          <!-- now line -->
          <div class="now-line" :style="{ left: nowPercent + '%' }">
            <span class="now-label">现在</span>
          </div>
        </div>
      </div>

      <!-- event lanes -->
      <div class="lanes">
        <div
          v-for="e in visibleEvents"
          :key="e.id"
          class="lane"
        >
          <div class="lane-label">{{ e.platform }}</div>
          <div class="lane-track">
            <!-- time bar from nowPercent to event position (or from left edge) -->
            <div
              class="bar-fill"
              :class="`fill-${urgency(e)}`"
              :style="{
                left: Math.max(0, nowPercent) + '%',
                width: Math.max(0, toPercent(Date.parse(e.end_at! + (e.end_at!.endsWith('Z') ? '' : 'Z'))) - nowPercent) + '%',
              }"
            ></div>
            <!-- event node -->
            <button
              class="event-node"
              :class="`node-${urgency(e)}`"
              :style="{
                left: toPercent(Date.parse(e.end_at! + (e.end_at!.endsWith('Z') ? '' : 'Z'))) + '%',
                borderColor: platformColor(e.platform),
              }"
              @click="select(e)"
              :title="e.title"
            >
              <span class="node-title">{{ e.title }}</span>
              <span class="node-cd">{{ countdown(e) }}</span>
            </button>
          </div>
        </div>

        <div v-if="!visibleEvents.length && !store.loading" class="empty">
          窗口内无事项
        </div>
      </div>

      <!-- now line overlay (full height) -->
      <div class="now-overlay" :style="{ left: nowPercent + '%' }"></div>
    </div>

    <!-- detail panel -->
    <transition name="slide">
      <div v-if="selected" class="detail-panel">
        <div class="detail-header">
          <span class="detail-platform" :style="{ color: platformColor(selected.platform) }">{{ selected.platform }}</span>
          <button class="detail-close" @click="selected = null">✕</button>
        </div>
        <div class="detail-title">{{ selected.title }}</div>
        <div class="detail-row"><span class="detail-k">截止</span><span class="detail-v">{{ fmtFull(selected.end_at) }} (CST)</span></div>
        <div class="detail-row"><span class="detail-k">倒计时</span><span class="detail-v cd" :class="`cd-${urgency(selected)}`">{{ countdown(selected) }}</span></div>
        <div class="detail-row"><span class="detail-k">状态</span><span class="detail-v">{{ selected.status }}</span></div>
        <div class="detail-row"><span class="detail-k">提交</span><span class="detail-v">{{ selected.submission_policy }}</span></div>
        <div v-if="selected.description" class="detail-desc">{{ selected.description.slice(0, 200) }}{{ selected.description.length > 200 ? '…' : '' }}</div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.timeline-view {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px 20px 60px;
}

.tl-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.tl-title  { font-size: 18px; font-weight: 600; letter-spacing: -.3px; }
.tl-range  { font-size: 12px; color: var(--muted); }

/* legend */
.legend { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 20px; }
.legend-item { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--muted); font-family: var(--mono); }
.legend-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }

/* wrap */
.tl-wrap {
  position: relative;
  background: var(--surface);
  backdrop-filter: blur(20px) saturate(1.3);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow-sm);
  overflow-x: auto;
  overflow-y: visible;
  padding-bottom: 8px;
}

/* axis */
.axis { padding: 0 120px; }
.axis-track {
  position: relative;
  height: 28px;
  border-bottom: 1px solid var(--border-strong);
  margin-bottom: 4px;
}
.tick {
  position: absolute;
  top: 0; bottom: 0;
  border-left: 1px solid var(--border);
}
.tick.major { border-left-color: var(--border-strong); }
.tick-label {
  position: absolute;
  top: 6px;
  left: 4px;
  font-size: 10px;
  font-family: var(--mono);
  color: var(--muted);
  white-space: nowrap;
}
.now-line {
  position: absolute;
  top: 0; bottom: -4px;
  border-left: 2px solid var(--accent);
  z-index: 10;
  animation: nowPulse 2s ease-in-out infinite;
}
.now-label {
  position: absolute;
  top: 5px; left: 4px;
  font-size: 10px; font-weight: 600;
  color: var(--accent);
  white-space: nowrap;
  font-family: var(--mono);
}
@keyframes nowPulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: .55; }
}

/* now overlay (full-height ghost line) */
.now-overlay {
  position: absolute;
  top: 28px; bottom: 0;
  border-left: 1px dashed rgba(0,103,192,.3);
  pointer-events: none;
  z-index: 5;
}

/* lanes */
.lanes { padding: 0 0 4px; }
.lane {
  display: flex;
  align-items: center;
  min-height: 52px;
  border-bottom: 1px solid var(--border);
  padding: 0 8px;
}
.lane:last-child { border-bottom: none; }
.lane-label {
  width: 100px;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--muted);
  flex-shrink: 0;
  padding-right: 8px;
}
.lane-track {
  flex: 1;
  position: relative;
  height: 44px;
}

/* bar fill */
.bar-fill {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  height: 3px;
  opacity: .35;
  border-radius: 2px;
  pointer-events: none;
}
.fill-urgent { background: var(--urgent); }
.fill-warn   { background: #F59E0B; }
.fill-normal { background: var(--accent); }
.fill-done   { background: var(--done); }

/* event node */
.event-node {
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  background: var(--surface-solid);
  border: 2px solid var(--accent);
  border-radius: 6px;
  padding: 3px 7px;
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  z-index: 10;
  min-width: 90px;
  max-width: 160px;
  transition: box-shadow .12s, transform .12s;
  white-space: nowrap;
}
.event-node:hover {
  box-shadow: var(--shadow-md);
  transform: translate(-50%, -54%);
}
.node-title {
  font-size: 10px;
  font-weight: 500;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 140px;
}
.node-cd {
  font-size: 9px;
  font-family: var(--mono);
  color: var(--muted);
  margin-top: 1px;
}
.node-urgent .node-cd { color: var(--urgent); }
.node-warn   .node-cd { color: var(--warn); }
.node-urgent { border-color: var(--urgent) !important; }
.node-warn   { border-color: #F59E0B !important; }
.node-done   { opacity: .5; }

.empty { padding: 24px; text-align: center; color: var(--muted); font-size: 13px; }

/* detail panel */
.detail-panel {
  margin-top: 16px;
  background: var(--surface-solid);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow-md);
  padding: 16px 20px;
}
.detail-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.detail-platform { font-family: var(--mono); font-size: 11px; font-weight: 600; }
.detail-close { border: none; background: none; color: var(--muted); font-size: 14px; cursor: pointer; }
.detail-title { font-size: 15px; font-weight: 600; margin-bottom: 12px; line-height: 1.35; }
.detail-row { display: flex; gap: 12px; font-size: 12px; margin-bottom: 6px; }
.detail-k { width: 48px; color: var(--muted); flex-shrink: 0; }
.detail-v { font-family: var(--mono); }
.cd.cd-urgent { color: var(--urgent); font-weight: 600; }
.cd.cd-warn   { color: var(--warn); }
.detail-desc { margin-top: 12px; font-size: 12px; color: var(--muted); line-height: 1.6; border-top: 1px solid var(--border); padding-top: 10px; }

/* slide transition */
.slide-enter-active, .slide-leave-active { transition: opacity .2s, transform .2s; }
.slide-enter-from, .slide-leave-to       { opacity: 0; transform: translateY(-8px); }

@media (prefers-reduced-motion: reduce) {
  .now-line { animation: none; }
}
</style>

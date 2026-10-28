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

// ── Events in window, grouped by platform ────────────────────────────────────
const visibleEvents = computed(() =>
  store.events.filter((e) => {
    if (!e.end_at) return false
    const d = Date.parse(e.end_at + (e.end_at.endsWith('Z') ? '' : 'Z'))
    return d >= windowStart.value && d <= windowEnd.value
  }).sort((a, b) => {
    if (a.platform !== b.platform) return a.platform.localeCompare(b.platform)
    const da = Date.parse(a.end_at! + (a.end_at!.endsWith('Z') ? '' : 'Z'))
    const db = Date.parse(b.end_at! + (b.end_at!.endsWith('Z') ? '' : 'Z'))
    return da - db
  })
)

// Group into platform swimlanes
interface Lane { platform: string; events: typeof visibleEvents.value }
const lanes = computed<Lane[]>(() => {
  const map = new Map<string, Lane>()
  for (const e of visibleEvents.value) {
    if (!map.has(e.platform)) map.set(e.platform, { platform: e.platform, events: [] })
    map.get(e.platform)!.events.push(e)
  }
  return Array.from(map.values())
})

// Within a lane, assign a vertical row (0 or 1) to avoid node overlap
// Two nodes conflict if they are within 14% of each other horizontally
function rowAssignments(events: typeof visibleEvents.value): number[] {
  const rows: number[] = []
  const pcts = events.map(e => eventPct(e))
  for (let i = 0; i < events.length; i++) {
    // try row 0, then 1, then 2
    let assigned = 0
    for (let row = 0; row <= 2; row++) {
      const conflict = rows.slice(0, i).some(
        (r, j) => r === row && Math.abs(pcts[j] - pcts[i]) < 14
      )
      if (!conflict) { assigned = row; break }
    }
    rows.push(assigned)
  }
  return rows
}

// ── Position helpers (0–100%) ─────────────────────────────────────────────────
function toPercent(ms: number): number {
  return ((ms - windowStart.value) / WINDOW_MS) * 100
}
const nowPercent = computed(() => toPercent(now.value))

function eventPct(e: ScheduleEvent): number {
  if (!e.end_at) return 0
  const ms = Date.parse(e.end_at + (e.end_at.endsWith('Z') ? '' : 'Z'))
  return toPercent(ms)
}

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
      <span class="tl-range">未来 {{ WINDOW_FUTURE_D }} 天 · 过去 {{ WINDOW_PAST_H }} 小时</span>
    </div>

    <!-- legend -->
    <div class="legend">
      <span v-for="(color, name) in PLATFORM_COLORS" :key="name" class="legend-item">
        <span class="legend-dot" :style="{ background: color }"></span>{{ name }}
      </span>
    </div>

    <div class="tl-wrap">
      <!-- axis: label cell + track cell share the grid -->
      <div class="axis-row">
        <div class="row-label"></div>
        <div class="track-cell">
          <div class="axis-track">
            <div
              v-for="(t, i) in ticks"
              :key="i"
              class="tick"
              :class="{ major: t.major }"
              :style="{ left: t.pct + '%' }"
            >
              <span class="tick-label" v-if="t.major">{{ t.label }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- lanes + shared now-line overlay -->
      <div class="lanes">
        <div class="now-overlay-row">
          <div class="row-label"></div>
          <div class="track-cell now-track-cell">
            <div class="now-line" :style="{ left: nowPercent + '%' }">
              <span class="now-label">现在</span>
            </div>
          </div>
        </div>

        <div v-for="lane in lanes" :key="lane.platform" class="lane-row">
          <div class="row-label" :style="{ color: platformColor(lane.platform) }">{{ lane.platform }}</div>
          <div class="track-cell">
            <div class="lane-track" :style="{ height: (40 + Math.max(...rowAssignments(lane.events)) * 44) + 'px' }">
              <template v-for="(e, idx) in lane.events" :key="e.id">
                <div
                  class="bar-fill"
                  :class="`fill-${urgency(e)}`"
                  :style="{
                    left: Math.max(0, Math.min(100, nowPercent)) + '%',
                    width: Math.max(0, Math.min(100, eventPct(e) - nowPercent)) + '%',
                    top: (6 + rowAssignments(lane.events)[idx] * 44) + 'px',
                  }"
                ></div>
                <button
                  class="event-node"
                  :class="`node-${urgency(e)}`"
                  :style="{
                    left: eventPct(e) + '%',
                    top: (22 + rowAssignments(lane.events)[idx] * 44) + 'px',
                    borderColor: platformColor(e.platform),
                  }"
                  @click="select(e)"
                  :title="e.title"
                >
                  <span class="node-title">{{ e.title }}</span>
                  <span class="node-cd">{{ countdown(e) }}</span>
                </button>
              </template>
            </div>
          </div>
        </div>

        <div v-if="!lanes.length && !store.loading" class="empty">
          窗口内无事项
        </div>
      </div>
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
        <div class="detail-row" v-if="selected.raw_payload?.proposed_by || selected.raw_payload?.publisher">
          <span class="detail-k">来源</span>
          <span class="detail-v">{{ selected.raw_payload?.proposed_by ?? selected.raw_payload?.publisher ?? '—' }}</span>
        </div>
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

/* ── Outer wrapper ── */
.tl-wrap {
  background: var(--surface);
  backdrop-filter: blur(20px) saturate(1.3);
  -webkit-backdrop-filter: blur(20px) saturate(1.3);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow-sm);
  overflow-x: auto;
  padding-bottom: 8px;
}

/* ── Shared two-column grid: label + track ──
   All rows (axis + lanes) use this so percentages are in the same column. */
.axis-row,
.lane-row {
  display: grid;
  grid-template-columns: 108px 1fr;
}

/* label cell */
.row-label {
  padding: 0 8px 0 12px;
  display: flex;
  align-items: center;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--muted);
  flex-shrink: 0;
}

/* track cell — all percentage positioning is inside this */
.track-cell {
  position: relative;
  min-width: 0;
}

/* ── Axis ── */
.axis-track {
  position: relative;
  height: 28px;
  border-bottom: 1px solid var(--border-strong);
}

.tick {
  position: absolute;
  top: 0; bottom: 0;
  width: 1px;
  background: var(--border);
}
.tick.major {
  width: 2px;
  background: var(--border-strong);
}
.tick-label {
  position: absolute;
  top: 6px; left: 4px;
  font-size: 10px;
  font-family: var(--mono);
  color: var(--muted);
  white-space: nowrap;
}

/* ── Lanes area + now-line overlay ── */
.lanes {
  position: relative;
}

/* now-line overlay row — shares the same two-column grid so the line
   sits inside the track column and nowPercent resolves against track width */
.now-overlay-row {
  display: grid;
  grid-template-columns: 108px 1fr;
  position: absolute;
  top: 0; bottom: 0;
  left: 0; right: 0;
  pointer-events: none;
  z-index: 20;
}
.now-track-cell {
  position: relative;
}

.now-line {
  position: absolute;
  top: 0; bottom: 0;
  border-left: 2px solid var(--accent);
  pointer-events: none;
  animation: nowPulse 2s ease-in-out infinite;
}
.now-label {
  position: absolute;
  top: 4px; left: 4px;
  font-size: 10px; font-weight: 600;
  color: var(--accent);
  white-space: nowrap;
  font-family: var(--mono);
}
@keyframes nowPulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: .5; }
}

/* Lane rows */
.lane-row {
  border-bottom: 1px solid var(--border);
}
.lane-row:last-child { border-bottom: none; }
.lane-row .row-label {
  min-height: 52px;
  font-weight: 500;
  font-size: 11px;
}

.lane-track {
  position: relative;
  min-height: 52px;
}

/* bar fill */
.bar-fill {
  position: absolute;
  height: 3px;
  opacity: .4;
  border-radius: 2px;
  pointer-events: none;
  transform: translateY(-50%);
}
.fill-urgent { background: var(--urgent); }
.fill-warn   { background: #F59E0B; }
.fill-normal { background: var(--accent); }
.fill-done   { background: var(--done); }

/* event node — top is set inline per-row */
.event-node {
  position: absolute;
  transform: translateX(-50%);
  display: flex; flex-direction: column; align-items: center;
  background: var(--surface-solid);
  border: 2px solid var(--accent);
  border-radius: 6px;
  padding: 3px 7px;
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  z-index: 10;
  min-width: 88px; max-width: 160px;
  white-space: nowrap;
  transition: box-shadow .12s, transform .12s;
}
.event-node:hover {
  box-shadow: var(--shadow-md);
  transform: translateX(-50%) translateY(-4px);
}
.node-title {
  font-size: 10px; font-weight: 500; color: var(--text);
  overflow: hidden; text-overflow: ellipsis; max-width: 144px;
}
.node-cd {
  font-size: 9px; font-family: var(--mono); color: var(--muted); margin-top: 1px;
}
.node-urgent .node-cd { color: var(--urgent); }
.node-warn   .node-cd { color: var(--warn); }
.node-urgent { border-color: var(--urgent) !important; }
.node-warn   { border-color: #F59E0B !important; }
.node-done   { opacity: .45; }

.empty { padding: 24px; text-align: center; color: var(--muted); font-size: 13px; }

/* ── Detail panel ── */
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
.detail-k { width: 52px; color: var(--muted); flex-shrink: 0; }
.detail-v { font-family: var(--mono); }
.cd.cd-urgent { color: var(--urgent); font-weight: 600; }
.cd.cd-warn   { color: var(--warn); }
.detail-desc {
  margin-top: 12px; font-size: 12px; color: var(--muted); line-height: 1.6;
  border-top: 1px solid var(--border); padding-top: 10px;
}

/* slide transition */
.slide-enter-active, .slide-leave-active { transition: opacity .2s, transform .2s; }
.slide-enter-from, .slide-leave-to       { opacity: 0; transform: translateY(-8px); }

@media (prefers-reduced-motion: reduce) {
  .now-line { animation: none; }
}
</style>

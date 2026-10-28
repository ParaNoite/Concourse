import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ScheduleEvent, StagedEvent } from '../types'

const BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export const useEventsStore = defineStore('events', () => {
  const events = ref<ScheduleEvent[]>([])
  const staged = ref<StagedEvent[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const activePlatform = ref<string>('all')

  const platforms = computed(() => {
    const ps = new Set(events.value.map(e => e.platform))
    return ['all', ...Array.from(ps).sort()]
  })

  const filteredEvents = computed(() => {
    if (activePlatform.value === 'all') return events.value
    return events.value.filter(e => e.platform === activePlatform.value)
  })

  const now = ref(new Date())

  function urgencyOf(e: ScheduleEvent): 'urgent' | 'warn' | 'normal' | 'done' {
    if (e.status === 'submitted' || e.status === 'done') return 'done'
    if (!e.end_at) return 'normal'
    const ms = new Date(e.end_at + 'Z').getTime() - now.value.getTime()
    if (ms < 0) return 'done'
    if (ms <= 48 * 3600 * 1000) return 'urgent'
    if (ms <= 7 * 24 * 3600 * 1000) return 'warn'
    return 'normal'
  }

  const urgentEvents = computed(() =>
    filteredEvents.value.filter(e => urgencyOf(e) === 'urgent')
  )
  const warnEvents = computed(() =>
    filteredEvents.value.filter(e => urgencyOf(e) === 'warn')
  )
  const normalEvents = computed(() =>
    filteredEvents.value.filter(e => urgencyOf(e) === 'normal')
  )
  const doneEvents = computed(() =>
    filteredEvents.value.filter(e => urgencyOf(e) === 'done')
  )

  async function fetchEvents() {
    loading.value = true
    error.value = null
    try {
      const [evRes, stRes] = await Promise.all([
        fetch(`${BASE}/events?limit=200`),
        fetch(`${BASE}/staged`),
      ])
      if (!evRes.ok) throw new Error(`/events ${evRes.status}`)
      if (!stRes.ok) throw new Error(`/staged ${stRes.status}`)
      events.value = await evRes.json()
      staged.value = await stRes.json()
    } catch (e: any) {
      error.value = e.message ?? 'Fetch failed'
    } finally {
      loading.value = false
    }
  }

  async function acceptStaged(id: number) {
    const res = await fetch(`${BASE}/staged/${id}/accept`, { method: 'POST' })
    if (!res.ok) throw new Error(`Accept failed: ${res.status}`)
    const newEvent: ScheduleEvent = await res.json()
    events.value.push(newEvent)
    staged.value = staged.value.filter(s => s.id !== id)
  }

  async function dismissStaged(id: number) {
    const res = await fetch(`${BASE}/staged/${id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error(`Dismiss failed: ${res.status}`)
    staged.value = staged.value.filter(s => s.id !== id)
  }

  // tick every minute so urgency classes stay fresh
  let tickTimer: ReturnType<typeof setInterval> | null = null
  function startTick() {
    if (tickTimer) return
    tickTimer = setInterval(() => { now.value = new Date() }, 60_000)
  }
  function stopTick() {
    if (tickTimer) { clearInterval(tickTimer); tickTimer = null }
  }

  // poll backend every 5 min
  let pollTimer: ReturnType<typeof setInterval> | null = null
  function startPoll() {
    if (pollTimer) return
    fetchEvents()
    pollTimer = setInterval(fetchEvents, 5 * 60 * 1000)
  }
  function stopPoll() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  }

  return {
    events, staged, loading, error,
    activePlatform, platforms,
    filteredEvents, urgentEvents, warnEvents, normalEvents, doneEvents,
    urgencyOf, now,
    fetchEvents, acceptStaged, dismissStaged,
    startTick, stopTick, startPoll, stopPoll,
  }
})

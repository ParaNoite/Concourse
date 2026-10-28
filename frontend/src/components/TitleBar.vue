<script setup lang="ts">
import { useRouter, useRoute } from 'vue-router'
import { ref, onMounted } from 'vue'

const router = useRouter()
const route = useRoute()
const clock = ref('')

function tick() {
  clock.value = new Date().toLocaleString('zh-CN', { hour12: false })
}
onMounted(() => { tick(); setInterval(tick, 1000) })
</script>

<template>
  <div class="titlebar">
    <span class="logo">Concourse</span>
    <nav class="tabs">
      <button class="tab" :class="{ active: route.path === '/dashboard' }" @click="router.push('/dashboard')">仪表板</button>
      <button class="tab" :class="{ active: route.path === '/timeline' }" @click="router.push('/timeline')">时间轴</button>
    </nav>
    <span class="clock">{{ clock }}</span>
  </div>
</template>

<style scoped>
.titlebar {
  height: 36px;
  background: rgba(255,255,255,0.82);
  backdrop-filter: blur(20px) saturate(1.4);
  -webkit-backdrop-filter: blur(20px) saturate(1.4);
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center;
  padding: 0 20px; gap: 16px;
  position: sticky; top: 0; z-index: 200;
}
.logo { font-size: 14px; font-weight: 600; letter-spacing: -.2px; }
.tabs { display: flex; }
.tab {
  padding: 6px 14px; font-size: 12px; color: var(--muted);
  border: none; background: none;
  border-bottom: 2px solid transparent; margin-bottom: -1px;
}
.tab.active { color: var(--accent); border-bottom-color: var(--accent); }
.clock { margin-left: auto; font-family: var(--mono); font-size: 11px; color: var(--muted); }
</style>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useEventsStore } from './stores/events'
import TitleBar from './components/TitleBar.vue'

const store = useEventsStore()
onMounted(() => { store.startTick(); store.startPoll() })
onUnmounted(() => { store.stopTick(); store.stopPoll() })
</script>

<template>
  <TitleBar />
  <router-view />
</template>

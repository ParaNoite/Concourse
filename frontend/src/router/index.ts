import { createRouter, createWebHashHistory } from 'vue-router'
import DashboardView from '../views/DashboardView.vue'
import TimelineView from '../views/TimelineView.vue'
import TrashView from '../views/TrashView.vue'

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', component: DashboardView },
    { path: '/timeline', component: TimelineView },
    { path: '/trash', component: TrashView },
  ],
})

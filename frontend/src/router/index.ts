import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import DesignView from '@/views/DesignView.vue'
import PlaceholderView from '@/views/PlaceholderView.vue'
import { NAV } from './nav'

export const routes: RouteRecordRaw[] = NAV.map((item) => ({
  path: item.path,
  name: item.name,
  component: PlaceholderView,
  props: { name: item.name, task: item.task },
}))

// Design-system reference page for reviewers; not part of the navigation.
export const designRoute: RouteRecordRaw = {
  path: '/_design',
  name: 'design',
  component: DesignView,
}

export const router = createRouter({
  history: createWebHistory(),
  routes: [...routes, designRoute],
})

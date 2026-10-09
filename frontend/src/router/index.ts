import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import ComponentView from '@/views/ComponentView.vue'
import DesignView from '@/views/DesignView.vue'
import MachineView from '@/views/MachineView.vue'
import OverviewView from '@/views/OverviewView.vue'
import PlaceholderView from '@/views/PlaceholderView.vue'
import { NAV } from './nav'

// Screens delivered so far; the rest show a placeholder naming their task.
const DELIVERED: Record<string, { component: RouteRecordRaw['component']; param?: string }> = {
  overview: { component: OverviewView },
  machine: { component: MachineView, param: ':id?' },
  component: { component: ComponentView, param: ':id?' },
}

export const routes: RouteRecordRaw[] = NAV.map((item) => {
  const delivered = DELIVERED[item.name]
  return delivered
    ? {
        path: delivered.param ? `${item.path}/${delivered.param}` : item.path,
        name: item.name,
        component: delivered.component!,
      }
    : {
        path: item.path,
        name: item.name,
        component: PlaceholderView,
        props: { name: item.name, task: item.task },
      }
})

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

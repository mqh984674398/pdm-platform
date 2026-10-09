import {
  createMemoryHistory,
  createRouter,
  createWebHistory,
  type RouteRecordRaw,
} from 'vue-router'
import AlarmsView from '@/views/AlarmsView.vue'
import AnalysisView from '@/views/AnalysisView.vue'
import BaselinesView from '@/views/BaselinesView.vue'
import ComponentView from '@/views/ComponentView.vue'
import DataSourceStudioView from '@/views/DataSourceStudioView.vue'
import DesignView from '@/views/DesignView.vue'
import MachineView from '@/views/MachineView.vue'
import MaintenanceView from '@/views/MaintenanceView.vue'
import OverviewView from '@/views/OverviewView.vue'
import PlaceholderView from '@/views/PlaceholderView.vue'
import { NAV } from './nav'

// Screens delivered so far; the rest show a placeholder naming their task.
const DELIVERED: Record<string, { component: RouteRecordRaw['component']; param?: string }> = {
  overview: { component: OverviewView },
  machine: { component: MachineView, param: ':id?' },
  component: { component: ComponentView, param: ':id?' },
  datasource: { component: DataSourceStudioView },
  analysis: { component: AnalysisView },
  baselines: { component: BaselinesView },
  maintenance: { component: MaintenanceView },
  alarms: { component: AlarmsView },
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

// VITE_ROUTER=memory builds a self-contained demo that does not depend on server URL rewrites.
export const router = createRouter({
  history: import.meta.env.VITE_ROUTER === 'memory' ? createMemoryHistory() : createWebHistory(),
  routes: [...routes, designRoute],
})

/** Machines and their components from the equipment API, for component pickers (T019/T020). */
import { ref } from 'vue'
import type { ComponentInstance, Machine } from '@/api/contracts'
import type { MonitoringApi } from '@/api/monitoring'

export function useComponents(api: MonitoringApi) {
  const machines = ref<{ machine: Machine; components: ComponentInstance[] }[]>([])
  const error = ref(false)
  const ready = (async () => {
    try {
      const ms = await api.machines()
      machines.value = await Promise.all(
        ms.map(async (m) => ({ machine: m, components: await api.components(m.machine_id) })),
      )
    } catch {
      error.value = true
    }
  })()
  return { machines, error, ready }
}

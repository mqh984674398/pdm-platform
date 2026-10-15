import { computed, ref } from 'vue'
import type { PlantTree } from '@/api/contracts'
import { monitoringApi } from '@/api/monitoring'

export const UNPLACED = '_unplaced'

/** The workshop → process → machine tree, read again every time a screen opens. */
export function usePlantTree() {
  const tree = ref<PlantTree | null>(null)
  const failed = ref(false)
  monitoringApi
    .plantTree()
    .then((t) => (tree.value = t))
    .catch(() => (failed.value = true))
  const workshopOf = computed(() => {
    const out = new Map<string, string>()
    for (const w of tree.value?.workshops ?? [])
      for (const p of w.processes) for (const m of p.machines) out.set(m.machine_id, w.node_id)
    return out
  })
  return { tree, failed, workshopOf }
}

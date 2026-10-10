import { computed, ref } from 'vue'
import { getFleet, refreshFleet, type Fleet, type FleetMachine } from '@/api/fleet'
import { HEALTH_RANK, worstHealth } from '@/theme/health'

const fleet = ref<Fleet | null>(null)
const error = ref<unknown>(null)
let loading: Promise<void> | null = null

export function machineHealth(m: FleetMachine) {
  return worstHealth(m.components.map((c) => c.health))
}

function load(p: Promise<Fleet>): Promise<void> {
  return p
    .then((f) => {
      fleet.value = f
      error.value = null
    })
    .catch((e) => {
      error.value = e
    })
}

export function useFleet() {
  loading ??= load(getFleet())
  const machines = computed(() =>
    [...(fleet.value?.machines ?? [])].sort(
      (a, b) =>
        HEALTH_RANK[machineHealth(a)] - HEALTH_RANK[machineHealth(b)] ||
        a.machine_id.localeCompare(b.machine_id),
    ),
  )
  const findMachine = (id: string | undefined) =>
    fleet.value?.machines.find((m) => m.machine_id === id) ?? fleet.value?.machines[0] ?? null
  const findComponent = (id: string | undefined) => {
    for (const m of fleet.value?.machines ?? []) {
      const c = m.components.find((x) => x.component_id === id)
      if (c) return { machine: m, component: c }
    }
    return null
  }
  /** Fetch the overview again (health is recomputed by the backend). */
  const reload = () => (loading = load(refreshFleet()))
  return { fleet, machines, error, ready: () => loading!, reload, findMachine, findComponent }
}

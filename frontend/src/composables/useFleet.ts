import { computed, ref } from 'vue'
import { refreshFleet, type Fleet, type FleetMachine } from '@/api/fleet'
import { HEALTH_RANK, worstHealth } from '@/theme/health'

const fleet = ref<Fleet | null>(null)
const error = ref<unknown>(null)
let loading: Promise<void> | null = null
let fetchedAt = 0
const MIN_GAP_MS = 3000 // screens opened in quick succession share one fetch

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

function start(force = false): Promise<void> {
  if (!force && loading && Date.now() - fetchedAt < MIN_GAP_MS) return loading
  fetchedAt = Date.now()
  loading = load(refreshFleet())
  return loading
}

/** The next screen that shows the fleet fetches it again (after plant, signal or pipeline changes). */
export function invalidateFleet() {
  fetchedAt = 0
}

export function useFleet() {
  start() // every screen opens on fresh data; the previous overview stays visible until it arrives
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
  const reload = () => start(true)
  return { fleet, machines, error, ready: () => loading!, reload, findMachine, findComponent }
}

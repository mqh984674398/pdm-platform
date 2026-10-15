<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import type { MachineLayout } from '@/api/contracts'
import { monitoringApi } from '@/api/monitoring'
import { devRole, session } from '@/api/session'
import DemoNotice from '@/components/fleet/DemoNotice.vue'
import HealthStrip from '@/components/fleet/HealthStrip.vue'
import MachineTile from '@/components/fleet/MachineTile.vue'
import { machineHealth, useFleet } from '@/composables/useFleet'
import { useLocalized } from '@/composables/useLocalized'
import { useLongPressReorder } from '@/composables/useLongPressReorder'
import { UNPLACED, usePlantTree } from '@/composables/usePlantTree'
import { HEALTH_RANK } from '@/theme/health'
import { fileToBackground } from '@/utils/image'

/**
 * Equipment overview (D-054): one sub-page per workshop. Administrators arrange the machines of a
 * workshop by long-pressing and dragging them, and can give each machine a background picture.
 */
const { t } = useI18n()
const { lt } = useLocalized()
const route = useRoute()
const router = useRouter()
const { fleet, machines, error } = useFleet()
const { tree, failed, workshopOf } = usePlantTree()

const role = computed(() => (session.mode === 'local' ? session.role : devRole()))
const admin = computed(() => role.value === 'admin')

const layout = ref<Record<string, MachineLayout>>({})
monitoringApi
  .machineLayout()
  .then((rows) => (layout.value = Object.fromEntries(rows.map((r) => [r.machine_id, r]))))
  .catch(() => undefined)

const tabs = computed(() => {
  const out = (tree.value?.workshops ?? []).map((w) => ({ id: w.node_id, label: lt(w.name) }))
  const placed = new Set(workshopOf.value.keys())
  if (machines.value.some((m) => !placed.has(m.machine_id)) || !out.length)
    out.push({ id: UNPLACED, label: t('overview.unplaced') })
  return out
})
const active = computed(() => {
  const w = route.query.w as string | undefined
  return tabs.value.find((x) => x.id === w)?.id ?? tabs.value[0]?.id ?? UNPLACED
})
function pickTab(id: string) {
  router.replace({ query: { ...route.query, w: id } })
}

const inTab = computed(() =>
  machines.value
    .filter((m) => (workshopOf.value.get(m.machine_id) ?? UNPLACED) === active.value)
    .sort(
      (a, b) =>
        (layout.value[a.machine_id]?.sort ?? 1e9) - (layout.value[b.machine_id]?.sort ?? 1e9) ||
        HEALTH_RANK[machineHealth(a)] - HEALTH_RANK[machineHealth(b)] ||
        a.machine_id.localeCompare(b.machine_id),
    ),
)
const order = ref<string[]>([])
const shown = computed(() => {
  const by = new Map(inTab.value.map((m) => [m.machine_id, m]))
  return order.value.flatMap((id) => (by.has(id) ? [by.get(id)!] : []))
})
const allStates = computed(() => shown.value.flatMap((m) => m.components.map((c) => c.health)))

const notice = ref('')
async function guarded(action: () => Promise<void>) {
  notice.value = ''
  try {
    await action()
  } catch (e) {
    notice.value = t('overview.saveFailed')
    console.error('overview save failed', e)
  }
}

const gridEl = ref<HTMLElement | null>(null)
const { dragId, onPointerDown, onClickCapture, onContextMenu } = useLongPressReorder({
  enabled: admin,
  ids: order,
  container: gridEl,
  onCommit: (ids) =>
    guarded(async () => {
      await monitoringApi.setMachineOrder(ids)
      ids.forEach((id, i) => {
        layout.value[id] = { ...(layout.value[id] ?? { machine_id: id }), machine_id: id, sort: i }
      })
    }),
})

watch(
  inTab,
  (list) => {
    if (dragId.value) return // a refresh must not undo a drag in progress
    const next = list.map((m) => m.machine_id)
    if (next.join('\u0000') !== order.value.join('\u0000')) order.value = next
  },
  { immediate: true },
)

function setBackground(machineId: string, file: File) {
  return guarded(async () => {
    const image = await fileToBackground(file)
    await monitoringApi.setMachineBackground(machineId, image)
    layout.value[machineId] = {
      ...(layout.value[machineId] ?? {}),
      machine_id: machineId,
      background: image,
    }
  })
}
function clearBackground(machineId: string) {
  return guarded(async () => {
    await monitoringApi.setMachineBackground(machineId, null)
    layout.value[machineId] = {
      ...(layout.value[machineId] ?? {}),
      machine_id: machineId,
      background: null,
    }
  })
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>{{ t('nav.overview') }}</h1>
      <DemoNotice v-if="fleet" :basis="fleet.health_basis" />
    </header>
    <p v-if="error" class="error">{{ t('common.loadFailed') }}</p>
    <template v-else-if="fleet && (tree || failed)">
      <div class="tabs" role="tablist" :aria-label="t('overview.workshops')">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          role="tab"
          class="tab"
          :class="{ active: tab.id === active }"
          :aria-selected="tab.id === active"
          :data-workshop="tab.id"
          data-testid="workshop-tab"
          @click="pickTab(tab.id)"
        >
          {{ tab.label }}
        </button>
      </div>
      <section class="summary" :aria-label="t('overview.summary')">
        <p class="summary-title">
          {{ t('overview.summaryLine', { machines: shown.length, components: allStates.length }) }}
        </p>
        <HealthStrip :states="allStates" />
      </section>
      <p v-if="admin" class="hint" data-testid="overview-admin-hint">
        {{ t('overview.adminHint') }}
      </p>
      <p v-if="notice" class="error" role="alert">{{ notice }}</p>
      <p v-if="!shown.length" class="hint">{{ t('overview.noMachines') }}</p>
      <div ref="gridEl">
        <TransitionGroup tag="section" name="shift" class="grid">
          <MachineTile
            v-for="m in shown"
            :key="m.machine_id"
            :machine="m"
            :background="layout[m.machine_id]?.background"
            :admin="admin"
            :lifted="dragId === m.machine_id"
            @pointerdown="onPointerDown($event, m.machine_id)"
            @click.capture="onClickCapture"
            @contextmenu="onContextMenu"
            @background="setBackground(m.machine_id, $event)"
            @clear-background="clearBackground(m.machine_id)"
          />
        </TransitionGroup>
      </div>
    </template>
  </div>
</template>

<style scoped>
.page {
  display: grid;
  gap: var(--space-5);
  max-width: 1280px;
}
.page-head {
  display: grid;
  gap: var(--space-2);
}
h1 {
  font-size: var(--text-xl);
}
.tabs {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
  border-bottom: 1px solid var(--line);
}
.tab {
  font: inherit;
  padding: 6px 16px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: none;
  color: var(--ink-soft);
  cursor: pointer;
}
.tab.active {
  color: var(--ink);
  border-bottom-color: var(--accent);
  font-weight: 600;
}
.summary {
  padding: var(--space-4) var(--space-5);
  background: var(--surface);
  border-radius: var(--radius-panel);
  box-shadow: var(--shadow-panel);
}
.summary-title {
  color: var(--ink-soft);
  font-size: var(--text-sm);
  margin-bottom: var(--space-3);
}
.hint {
  color: var(--ink-soft);
  font-size: var(--text-sm);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: var(--space-4);
}
.shift-leave-active {
  display: none; /* a tile that leaves (another workshop tab) goes at once */
  transition: none !important;
}
.shift-move {
  transition: transform 200ms ease; /* the other tiles make way smoothly */
}
.error {
  color: var(--health-critical);
}
</style>

<script setup lang="ts">
/** Time-series analysis (UI-06, T019): saved signals at any range, with maintenance and alarm context. */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import type { Alarm, MaintenanceEvent, SignalConfigState } from '@/api/contracts'
import { monitoringApi } from '@/api/monitoring'
import PanelBox from '@/components/base/PanelBox.vue'
import SimBadge from '@/components/base/SimBadge.vue'
import DownsampleNote from '@/charts/DownsampleNote.vue'
import TimeSeriesChart from '@/charts/TimeSeriesChart.vue'
import { alarmPeriods, eventMarkers } from '@/charts/overlays'
import { useSeries } from '@/charts/useSeries'
import { useLocalized } from '@/composables/useLocalized'

const { t } = useI18n()
const { lt } = useLocalized()
const route = useRoute()
const router = useRouter()

const config = ref<SignalConfigState | null>(null)
const loadError = ref(false)
monitoringApi
  .signalConfig()
  .then((c) => (config.value = c))
  .catch(() => (loadError.value = true))

const mapped = computed(() => {
  const c = config.value?.content
  if (!c) return []
  const byId = new Map(c.signals.map((s) => [s.signal_id, s]))
  return c.mappings
    .map((m) => ({ mapping: m, signal: byId.get(m.signal_id)! }))
    .filter((x) => x.signal)
    .sort((a, b) => a.signal.signal_id.localeCompare(b.signal.signal_id))
})
const groups = computed(() => {
  const out = new Map<string, typeof mapped.value>()
  for (const x of mapped.value) {
    const key = x.mapping.component_id ?? x.mapping.device_id
    out.set(key, [...(out.get(key) ?? []), x])
  }
  return [...out.entries()]
})

const signalId = computed<string | null>(
  () => (route.query.signal as string | undefined) ?? mapped.value[0]?.signal.signal_id ?? null,
)
const selected = computed(() => mapped.value.find((x) => x.signal.signal_id === signalId.value))
const { full, points, shown, visible, loading, error, zoom } = useSeries(monitoringApi, signalId)

const events = ref<MaintenanceEvent[]>([])
const alarms = ref<Alarm[]>([])
watch(
  () => selected.value?.mapping.component_id,
  async (cid) => {
    events.value = alarms.value = []
    if (!cid) return
    const [e, a] = await Promise.all([
      monitoringApi.events(cid).catch(() => []),
      monitoringApi.alarms({ component_id: cid }).catch(() => []),
    ])
    events.value = e
    alarms.value = a
  },
  { immediate: true },
)

const lines = computed(() =>
  selected.value ? [{ name: lt(selected.value.signal.name), points: points.value }] : [],
)
const markers = computed(() => eventMarkers(events.value, (k) => t(`maintenanceType.${k}`)))
const periods = computed(() =>
  alarmPeriods(alarms.value, full.value?.end ?? 0, (k) => t(`health.${k}`)),
)

const exporting = ref(false)
async function exportCsv() {
  if (!signalId.value || !visible.value) return
  exporting.value = true
  try {
    const { name, blob } = await monitoringApi.exportCsv(
      signalId.value,
      visible.value.start,
      visible.value.end,
    )
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = name
    a.click()
    URL.revokeObjectURL(a.href)
  } finally {
    exporting.value = false
  }
}
const pick = (id: string) => router.replace({ query: { ...route.query, signal: id } })
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>{{ t('nav.analysis') }}</h1>
      <p class="lede">{{ t('analysis.lede') }}</p>
    </header>
    <p v-if="loadError" class="error">{{ t('common.loadFailed') }}</p>
    <p v-else-if="config && !mapped.length" class="empty">{{ t('analysis.noSignals') }}</p>
    <div v-else class="layout">
      <nav class="list" :aria-label="t('analysis.pick')">
        <div v-for="[group, items] in groups" :key="group" class="group">
          <h2>{{ group }}</h2>
          <button
            v-for="x in items"
            :key="x.signal.signal_id"
            type="button"
            class="item"
            :class="{ active: x.signal.signal_id === signalId }"
            :data-testid="`signal-${x.signal.signal_id}`"
            @click="pick(x.signal.signal_id)"
          >
            {{ lt(x.signal.name) }} <span class="unit">{{ x.signal.unit }}</span>
          </button>
        </div>
      </nav>
      <PanelBox
        :title="selected ? `${lt(selected.signal.name)} · ${selected.signal.signal_id}` : ''"
      >
        <template #actions>
          <SimBadge v-if="shown?.is_simulated" />
          <span v-if="loading" class="loading" data-testid="chart-loading">{{
            t('charts.loading')
          }}</span>
        </template>
        <p v-if="error" class="error">{{ error }}</p>
        <TimeSeriesChart
          :lines="lines"
          :unit="selected?.signal.unit"
          :full="full"
          :markers="markers"
          :periods="periods"
          @zoom="zoom"
        />
        <DownsampleNote :series="shown" :exporting="exporting" @export="exportCsv" />
        <p class="hint">{{ t('analysis.zoomHint') }}</p>
      </PanelBox>
    </div>
  </div>
</template>

<style scoped>
.page {
  display: grid;
  gap: var(--space-5);
  max-width: 1400px;
}
.page-head {
  display: grid;
  gap: var(--space-2);
}
h1 {
  font-size: var(--text-xl);
}
.lede,
.hint {
  color: var(--ink-soft);
  font-size: var(--text-sm);
}
.layout {
  display: grid;
  grid-template-columns: 240px 1fr;
  gap: var(--space-4);
  align-items: start;
}
.list {
  display: grid;
  gap: var(--space-3);
  max-height: 70vh;
  overflow: auto;
}
.group h2 {
  font-size: var(--text-xs);
  color: var(--ink-soft);
  margin-bottom: var(--space-1);
}
.item {
  display: block;
  width: 100%;
  text-align: left;
  border: 0;
  background: none;
  padding: 4px 8px;
  border-radius: var(--radius-control);
  color: var(--ink);
  cursor: pointer;
}
.item.active {
  background: var(--accent-soft, var(--steel-200));
  font-weight: 500;
}
.unit {
  color: var(--ink-soft);
  font-size: var(--text-xs);
}
.loading {
  color: var(--ink-soft);
  font-size: var(--text-xs);
}
.error {
  color: var(--health-critical);
}
.empty {
  color: var(--ink-soft);
}
@media (max-width: 800px) {
  .layout {
    grid-template-columns: 1fr;
  }
}
</style>

<script setup lang="ts">
/** Baseline comparison (UI-07, T019): verified healthy reference vs adaptive baseline, per lifecycle. */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import type { Alarm, Baseline, DegradationHistory } from '@/api/contracts'
import { monitoringApi } from '@/api/monitoring'
import PanelBox from '@/components/base/PanelBox.vue'
import SimBadge from '@/components/base/SimBadge.vue'
import ComponentPicker from '@/components/fleet/ComponentPicker.vue'
import TimeSeriesChart from '@/charts/TimeSeriesChart.vue'
import { alarmPeriods, referenceBands } from '@/charts/overlays'
import { useComponents } from '@/composables/useComponents'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { machines, error: loadError } = useComponents(monitoringApi)

const componentId = computed<string | null>(
  () =>
    (route.query.c as string | undefined) ?? machines.value[0]?.components[0]?.component_id ?? null,
)
const baselines = ref<Baseline[]>([])
const alarms = ref<Alarm[]>([])
const history = ref<DegradationHistory | null>(null)
const verified = computed(() => baselines.value.filter((b) => b.kind === 'VERIFIED_HEALTHY'))
const featureRef = computed(() => verified.value[0]?.feature_ref ?? null)
const features = computed(() => {
  const names = Object.keys(verified.value[0]?.stats ?? {})
  return [
    ...names.filter((n) => n.endsWith('residual')),
    ...names.filter((n) => !n.endsWith('residual')),
  ]
})
const feature = computed<string | null>(() => {
  const q = route.query.f as string | undefined
  return q && features.value.includes(q) ? q : (features.value[0] ?? null)
})

watch(
  componentId,
  async (cid) => {
    baselines.value = alarms.value = []
    history.value = null
    if (!cid) return
    const [b, a] = await Promise.all([
      monitoringApi.baselines(cid).catch(() => []),
      monitoringApi.alarms({ component_id: cid }).catch(() => []),
    ])
    baselines.value = b
    alarms.value = a
  },
  { immediate: true },
)
watch([componentId, feature, featureRef], async ([cid, f, ref_]) => {
  history.value = null
  if (cid && f && ref_)
    history.value = await monitoringApi.degradation(cid, f, ref_).catch(() => null)
})

const ms = (s: string) => Date.parse(s)
const points = computed(() => history.value?.segments.flatMap((s) => s.points) ?? [])
const full = computed(() =>
  points.value.length
    ? { start: ms(points.value[0]!.window.start), end: ms(points.value.at(-1)!.window.end) }
    : null,
)
const lines = computed(() => {
  const segs = history.value?.segments ?? []
  // a null point between lifecycles keeps the adaptive line from joining two installations
  const adaptive = segs.flatMap((s, i) => [
    ...(i ? [[ms(s.points[0]!.window.start), null] as [number, null]] : []),
    ...s.points.map((p) => [ms(p.window.end), p.adaptive_mean] as [number, number]),
  ])
  return [
    {
      name: t('baselines.windows'),
      kind: 'scatter' as const,
      points: points.value.map((p) => [ms(p.window.end), p.value] as [number, number]),
    },
    { name: t('baselines.adaptive'), points: adaptive, color: '--chart-2' },
  ]
})
const bands = computed(() =>
  history.value && feature.value
    ? referenceBands(history.value, baselines.value, feature.value, t('baselines.reference'))
    : [],
)
const markers = computed(() => [
  ...(history.value?.steps ?? []).map((s) => ({
    ts: ms(s.at),
    label: t(`maintenanceType.${s.type}`),
  })),
  ...(history.value?.segments.slice(1) ?? []).map((s) => ({
    ts: ms(s.points[0]!.window.start),
    label: s.lifecycle_id,
  })),
])
const periods = computed(() =>
  alarmPeriods(alarms.value, full.value?.end ?? 0, (k) => t(`health.${k}`)),
)
const fmtTime = (s: string) => s.slice(0, 16).replace('T', ' ')
const pick = (q: Record<string, string>) => router.replace({ query: { ...route.query, ...q } })
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>{{ t('nav.baselines') }}</h1>
      <p class="lede">{{ t('baselines.lede') }}</p>
    </header>
    <p v-if="loadError" class="error">{{ t('common.loadFailed') }}</p>
    <div v-else class="layout">
      <ComponentPicker
        :machines="machines"
        :selected="componentId"
        @pick="(id) => pick({ c: id, f: '' })"
      />
      <PanelBox :title="componentId ?? ''">
        <template #actions>
          <SimBadge v-if="history?.is_simulated" />
          <select
            v-if="features.length"
            :value="feature ?? ''"
            data-testid="feature-select"
            :aria-label="t('baselines.feature')"
            @change="pick({ f: ($event.target as HTMLSelectElement).value })"
          >
            <option v-for="f in features" :key="f" :value="f">{{ f }}</option>
          </select>
        </template>
        <p v-if="!verified.length" class="empty" data-testid="no-reference">
          {{ t('baselines.noReference') }}
        </p>
        <template v-else>
          <TimeSeriesChart
            :lines="lines"
            :full="full"
            :bands="bands"
            :markers="markers"
            :periods="periods"
          />
          <ul class="refs" data-testid="reference-list">
            <li v-for="b in verified" :key="b.baseline_id">
              {{
                t('baselines.verifiedBy', {
                  lifecycle: b.lifecycle_id,
                  user: b.verified_by,
                  start: fmtTime(b.window.start),
                  end: fmtTime(b.window.end),
                })
              }}
              <span class="comment">“{{ b.comment }}”</span>
            </li>
          </ul>
          <p class="hint">{{ t('baselines.legend') }}</p>
        </template>
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
.hint,
.empty {
  color: var(--ink-soft);
  font-size: var(--text-sm);
}
.layout {
  display: grid;
  grid-template-columns: 240px 1fr;
  gap: var(--space-4);
  align-items: start;
}
.refs {
  margin: var(--space-3) 0;
  padding-left: var(--space-4);
  font-size: var(--text-sm);
}
.comment {
  color: var(--ink-soft);
}
.error {
  color: var(--health-critical);
}
@media (max-width: 800px) {
  .layout {
    grid-template-columns: 1fr;
  }
}
</style>

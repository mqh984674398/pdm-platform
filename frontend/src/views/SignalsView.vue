<script setup lang="ts">
/**
 * Signal configuration and preview (UI-05). Lists every saved signal with its mapping, lets engineers
 * correct a signal's definition (name, unit, sampling, valid range), previews the saved mapping over a
 * window with data-quality flags, and shows the configuration's version history. New devices and
 * mappings are set up in the Data Source Studio.
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import type {
  PhysicalQuantity,
  PreviewResponse,
  SignalConfigState,
  SignalConfigVersion,
  SignalDefinition,
  VisualizationSeries,
} from '@/api/contracts'
import { MonitoringApiError, monitoringApi } from '@/api/monitoring'
import { devRole, session } from '@/api/session'
import PanelBox from '@/components/base/PanelBox.vue'
import SimBadge from '@/components/base/SimBadge.vue'
import TimeSeriesChart from '@/charts/TimeSeriesChart.vue'
import { toPoints } from '@/charts/merge'
import '@/components/studio/studio.css'
import { useLocalized } from '@/composables/useLocalized'

const QUANTITIES: PhysicalQuantity[] = [
  'SPEED',
  'TORQUE',
  'DURATION',
  'POSITION',
  'CURRENT',
  'PRESSURE',
  'OTHER',
]
const PREVIEW_HOURS = 24
const PREVIEW_SAMPLES = 5000 // keeps dense signals' full-resolution preview small
const CHART_POINTS = 1500

const { t, te } = useI18n()
const { lt, fmtDate } = useLocalized()
const route = useRoute()
const router = useRouter()

const config = ref<SignalConfigState | null>(null)
const versions = ref<SignalConfigVersion[]>([])
const loadError = ref(false)

async function load() {
  try {
    const [c, v] = await Promise.all([monitoringApi.signalConfig(), monitoringApi.signalVersions()])
    config.value = c
    versions.value = [...v].sort((a, b) => b.version - a.version)
  } catch {
    loadError.value = true
  }
}
load()

const rows = computed(() => {
  const c = config.value?.content
  if (!c) return []
  const mapping = new Map(c.mappings.map((m) => [m.signal_id, m]))
  return c.signals
    .map((s) => ({ signal: s, mapping: mapping.get(s.signal_id) ?? null }))
    .sort((a, b) => a.signal.signal_id.localeCompare(b.signal.signal_id))
})
const groups = computed(() => {
  const out = new Map<string, typeof rows.value>()
  for (const r of rows.value) {
    const key = r.mapping ? `${r.mapping.data_source_id} · ${r.mapping.device_id}` : '—'
    out.set(key, [...(out.get(key) ?? []), r])
  }
  return [...out.entries()]
})
const signalId = computed<string | null>(
  () => (route.query.signal as string | undefined) ?? rows.value[0]?.signal.signal_id ?? null,
)
const selected = computed(() => rows.value.find((r) => r.signal.signal_id === signalId.value))
const pick = (id: string) => router.replace({ query: { ...route.query, signal: id } })

const role = computed(() => (session.mode === 'local' ? session.role : devRole()))
const canEdit = computed(() => role.value === 'engineer' || role.value === 'admin')

// --- editing the definition ---
type Draft = {
  zh: string
  en: string
  quantity: PhysicalQuantity
  unit: string
  sampling: string
  min: string
  max: string
}
const draft = ref<Draft | null>(null)
const comment = ref('')
const saving = ref(false)
const message = ref<{ ok: boolean; text: string } | null>(null)

function resetDraft() {
  const s = selected.value?.signal
  message.value = null
  comment.value = ''
  draft.value = s
    ? {
        zh: s.name.zh,
        en: s.name.en,
        quantity: s.quantity,
        unit: s.unit,
        sampling: s.expected_sampling_s?.toString() ?? '',
        min: s.valid_min?.toString() ?? '',
        max: s.valid_max?.toString() ?? '',
      }
    : null
}
watch(selected, resetDraft, { immediate: true })

const num = (v: string): number | null | undefined => {
  if (v.trim() === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : undefined
}
const edited = computed<SignalDefinition | null>(() => {
  const s = selected.value?.signal
  const dr = draft.value
  if (!s || !dr) return null
  const sampling = num(dr.sampling)
  const min = num(dr.min)
  const max = num(dr.max)
  if (sampling === undefined || min === undefined || max === undefined) return null
  if (sampling !== null && sampling <= 0) return null
  if (min !== null && max !== null && min > max) return null
  if (!dr.zh.trim() || !dr.en.trim() || !dr.unit.trim()) return null
  return {
    signal_id: s.signal_id,
    name: { zh: dr.zh.trim(), en: dr.en.trim() },
    quantity: dr.quantity,
    unit: dr.unit.trim(),
    expected_sampling_s: sampling,
    valid_min: min,
    valid_max: max,
  }
})
const changed = computed(
  () =>
    !!edited.value &&
    !!selected.value &&
    JSON.stringify(edited.value) !==
      JSON.stringify({
        signal_id: selected.value.signal.signal_id,
        name: { zh: selected.value.signal.name.zh, en: selected.value.signal.name.en },
        quantity: selected.value.signal.quantity,
        unit: selected.value.signal.unit,
        expected_sampling_s: selected.value.signal.expected_sampling_s ?? null,
        valid_min: selected.value.signal.valid_min ?? null,
        valid_max: selected.value.signal.valid_max ?? null,
      }),
)
// A unit change must match the mapping's conversion target; that is set in the Studio.
const unitLocked = computed(() => !!selected.value?.mapping?.conversion)

async function save() {
  if (!edited.value || !changed.value) return
  saving.value = true
  message.value = null
  try {
    const v = await monitoringApi.saveSignal(
      edited.value,
      comment.value.trim(),
      config.value?.version?.version ?? 0,
    )
    await load()
    message.value = { ok: true, text: t('signals.saved', { v: v.version }) }
  } catch (e) {
    const body = e instanceof MonitoringApiError ? e.body : null
    message.value = { ok: false, text: body ? lt(body.message) : t('signals.saveFailed') }
  } finally {
    saving.value = false
  }
}

// --- preview of the saved mapping ---
// The chart shows the whole history, downsampled by the server. The quality summary reads the
// full-resolution samples of the most recent stretch of data, bounded so dense signals stay small.
const previewHours = computed(() => {
  const s = selected.value?.signal.expected_sampling_s
  const h = s ? Math.min(PREVIEW_HOURS, (PREVIEW_SAMPLES * s) / 3600) : PREVIEW_HOURS
  return Math.round(h * 10) / 10
})
const series = ref<VisualizationSeries | null>(null)
const preview = ref<PreviewResponse | null>(null)
const previewError = ref<string | null>(null)
const previewLoading = ref(false)
let previewSeq = 0

watch(
  () => selected.value?.mapping ?? null,
  async (mapping) => {
    const seq = ++previewSeq
    series.value = preview.value = null
    previewError.value = null
    if (!mapping) return
    previewLoading.value = true
    try {
      const extent = await monitoringApi.extent(mapping.signal_id)
      if (!extent) throw new Error(t('signals.noData'))
      const s = await monitoringApi.series(
        mapping.signal_id,
        Date.parse(extent.start),
        Date.parse(extent.end) + 1000,
        CHART_POINTS,
      )
      if (seq !== previewSeq) return
      series.value = s
      const last = [...s.points].reverse().find((x) => x.value !== null && x.value !== undefined)
      if (!last) throw new Error(t('signals.noData'))
      const end = Date.parse(last.ts) + 1000
      const start = Math.max(Date.parse(extent.start), end - previewHours.value * 3600_000)
      const p = await monitoringApi.signalPreview(
        mapping.signal_id,
        new Date(start).toISOString(),
        new Date(end).toISOString(),
        10,
      )
      if (seq === previewSeq) preview.value = p
    } catch (e) {
      if (seq !== previewSeq) return
      const body = e instanceof MonitoringApiError ? e.body : null
      previewError.value = body ? lt(body.message) : (e as Error).message
    } finally {
      if (seq === previewSeq) previewLoading.value = false
    }
  },
  { immediate: true },
)

const lines = computed(() =>
  series.value && selected.value
    ? [{ name: lt(selected.value.signal.name), points: toPoints(series.value) }]
    : [],
)
const quality = computed(() => {
  const samples = preview.value?.normalized[0]?.samples ?? []
  const flags = new Map<string, number>()
  for (const x of samples) for (const f of x.quality) flags.set(f, (flags.get(f) ?? 0) + 1)
  return { total: samples.length, flags: [...flags.entries()].sort((a, b) => b[1] - a[1]) }
})
const flagLabel = (f: string) =>
  te(`studio.quality.flags.${f}`) ? t(`studio.quality.flags.${f}`) : f
const fmtNum = (v: number | null | undefined) => (v === null || v === undefined ? '—' : String(v))
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>{{ t('nav.signals') }}</h1>
      <p class="lede">
        {{ t('signals.lede') }}
        <RouterLink to="/datasource">{{ t('nav.datasource') }}</RouterLink>
      </p>
    </header>
    <p v-if="loadError" class="error">{{ t('common.loadFailed') }}</p>
    <p v-else-if="config && !rows.length" class="empty" data-testid="signals-empty">
      {{ t('signals.empty') }}
    </p>
    <div v-else-if="config" class="layout">
      <nav class="list" :aria-label="t('signals.pick')">
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

      <div v-if="selected" class="detail">
        <PanelBox :title="`${lt(selected.signal.name)} · ${selected.signal.signal_id}`">
          <dl class="facts" data-testid="signal-mapping">
            <div>
              <dt>{{ t('signals.source') }}</dt>
              <dd>{{ selected.mapping?.data_source_id ?? '—' }}</dd>
            </div>
            <div>
              <dt>{{ t('signals.device') }}</dt>
              <dd>{{ selected.mapping?.device_id ?? '—' }}</dd>
            </div>
            <div>
              <dt>{{ t('signals.key') }}</dt>
              <dd class="st-mono">{{ selected.mapping?.key_name ?? '—' }}</dd>
            </div>
            <div>
              <dt>{{ t('signals.template') }}</dt>
              <dd class="st-mono">{{ selected.mapping?.template_id ?? '—' }}</dd>
            </div>
            <div>
              <dt>{{ t('signals.conversion') }}</dt>
              <dd v-if="selected.mapping?.conversion">
                {{ selected.mapping.conversion.source_unit }} →
                {{ selected.mapping.conversion.target_unit }} (×
                {{ selected.mapping.conversion.scale }} + {{ selected.mapping.conversion.offset }})
              </dd>
              <dd v-else>{{ t('signals.noConversion') }}</dd>
            </div>
            <div>
              <dt>{{ t('signals.component') }}</dt>
              <dd>{{ selected.mapping?.component_id ?? '—' }}</dd>
            </div>
          </dl>
        </PanelBox>

        <PanelBox :title="t('signals.definition')">
          <form v-if="draft" class="st-stack" @submit.prevent="save">
            <div class="st-form">
              <label class="st-field">
                <span>{{ t('signals.nameZh') }}</span>
                <input v-model="draft.zh" class="st-input" :readonly="!canEdit" />
              </label>
              <label class="st-field">
                <span>{{ t('signals.nameEn') }}</span>
                <input v-model="draft.en" class="st-input" :readonly="!canEdit" />
              </label>
              <label class="st-field">
                <span>{{ t('signals.quantity') }}</span>
                <select v-model="draft.quantity" class="st-select" :disabled="!canEdit">
                  <option v-for="q in QUANTITIES" :key="q" :value="q">
                    {{ t(`signals.quantities.${q}`) }}
                  </option>
                </select>
              </label>
              <label class="st-field">
                <span>{{ t('signals.unit') }}</span>
                <input
                  v-model="draft.unit"
                  class="st-input"
                  :readonly="!canEdit || unitLocked"
                  :title="unitLocked ? t('signals.unitLocked') : undefined"
                />
              </label>
              <label class="st-field">
                <span>{{ t('signals.sampling') }}</span>
                <input
                  v-model="draft.sampling"
                  class="st-input"
                  inputmode="decimal"
                  :readonly="!canEdit"
                  data-testid="signal-sampling"
                />
              </label>
              <label class="st-field">
                <span>{{ t('signals.validMin') }}</span>
                <input
                  v-model="draft.min"
                  class="st-input"
                  inputmode="decimal"
                  :readonly="!canEdit"
                />
              </label>
              <label class="st-field">
                <span>{{ t('signals.validMax') }}</span>
                <input
                  v-model="draft.max"
                  class="st-input"
                  inputmode="decimal"
                  :readonly="!canEdit"
                />
              </label>
            </div>
            <p v-if="unitLocked" class="st-note">{{ t('signals.unitLocked') }}</p>
            <p v-if="!canEdit" class="st-note">{{ t('signals.readOnly') }}</p>
            <div v-else class="save-row">
              <input
                v-model="comment"
                class="st-input grow"
                maxlength="500"
                :placeholder="t('signals.comment')"
                data-testid="signal-comment"
              />
              <button type="button" class="st-button" :disabled="!changed" @click="resetDraft">
                {{ t('signals.reset') }}
              </button>
              <button
                type="submit"
                class="st-button primary"
                :disabled="!changed || !edited || saving"
                data-testid="signal-save"
              >
                {{ t('signals.save') }}
              </button>
            </div>
            <p v-if="draft && !edited" class="error">{{ t('signals.invalid') }}</p>
            <p
              v-if="message"
              :class="message.ok ? 'ok' : 'error'"
              role="status"
              data-testid="signal-message"
            >
              {{ message.text }}
            </p>
          </form>
        </PanelBox>

        <PanelBox :title="t('signals.preview')">
          <template #actions>
            <SimBadge v-if="series?.is_simulated" />
            <span v-if="previewLoading" class="st-note">{{ t('charts.loading') }}</span>
          </template>
          <p v-if="!selected.mapping" class="st-note">{{ t('signals.noMapping') }}</p>
          <p v-else-if="previewError" class="error">{{ previewError }}</p>
          <template v-else-if="series">
            <TimeSeriesChart :lines="lines" :unit="selected.signal.unit" :height="280" />
            <p v-if="preview" class="st-note" data-testid="signal-quality">
              {{ t('signals.samples', { n: quality.total, h: previewHours }) }}
              <template v-if="quality.flags.length">
                ·
                <span v-for="[f, n] in quality.flags" :key="f" class="flag">
                  {{ flagLabel(f) }} {{ n }}
                </span>
              </template>
              <template v-else> · {{ t('signals.noFlags') }}</template>
            </p>
            <p class="st-note">
              {{
                t('signals.range', {
                  min: fmtNum(selected.signal.valid_min),
                  max: fmtNum(selected.signal.valid_max),
                })
              }}
            </p>
          </template>
        </PanelBox>

        <PanelBox :title="t('signals.versions')">
          <table v-if="versions.length" class="st-table" data-testid="signal-versions">
            <thead>
              <tr>
                <th>{{ t('signals.version') }}</th>
                <th>{{ t('signals.when') }}</th>
                <th>{{ t('signals.by') }}</th>
                <th>{{ t('signals.note') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="v in versions.slice(0, 20)" :key="v.version">
                <td class="num">{{ v.version }}</td>
                <td>{{ fmtDate(v.created_at) }} {{ t('studio.utc') }}</td>
                <td>{{ v.created_by }}</td>
                <td>{{ v.comment || '—' }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="st-note">{{ t('signals.noVersions') }}</p>
        </PanelBox>
      </div>
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
.lede {
  color: var(--ink-soft);
  font-size: var(--text-sm);
}
.layout {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: var(--space-4);
  align-items: start;
}
.list {
  display: grid;
  gap: var(--space-3);
  max-height: 75vh;
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
.detail {
  display: grid;
  gap: var(--space-4);
  min-width: 0;
}
.facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--space-3) var(--space-4);
  margin: 0;
  font-size: var(--text-sm);
}
.facts dt {
  color: var(--ink-soft);
  font-size: var(--text-xs);
}
.facts dd {
  margin: 2px 0 0;
  overflow-wrap: anywhere;
}
.save-row {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.grow {
  flex: 1;
  min-width: 200px;
}
.flag + .flag::before {
  content: ' · ';
}
.ok {
  color: var(--health-normal);
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

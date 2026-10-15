<script setup lang="ts">
/**
 * Prediction configuration of one component (D-044..D-046), the seven-step workflow of the
 * Configuration Workbench: component → data → relationships → algorithm pipeline → decision criteria →
 * display → validate, publish and activate. Published versions are immutable; edits happen on drafts.
 */
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type {
  AlgorithmSpec,
  ComponentInstance,
  ConfigContent,
  ComponentLifecycle,
  ConfigRecommendation,
  FeatureCoverage,
  PipelineResult,
  EvidenceType,
  ManagedSource,
  PredictionConfig,
  PreviewResponse,
  RelationType,
  SignalConfigState,
  SignalDefinition,
  SignalMapping,
} from '@/api/contracts'
import { MonitoringApiError, monitoringApi } from '@/api/monitoring'
import PanelBox from '@/components/base/PanelBox.vue'
import ReferenceForm from '@/components/fleet/ReferenceForm.vue'
import SignalMappingEditor from '@/components/studio/SignalMappingEditor.vue'
import PreviewChart, { type ChartSeries } from '@/components/studio/PreviewChart.vue'
import '@/components/studio/studio.css'
import { useLocalized } from '@/composables/useLocalized'

const props = defineProps<{
  component: ComponentInstance
  siblings: ComponentInstance[]
  deviceId?: string | null
  machineId: string
}>()
const { t } = useI18n()
const { lt } = useLocalized()

const RELATIONS: RelationType[] = [
  'INDEPENDENT',
  'SHARED_DRIVETRAIN',
  'MECHANICAL_DEPENDENCY',
  'SHARED_SIGNAL',
]
const EVIDENCE: EvidenceType[] = ['SAFETY', 'STATISTICAL', 'ANOMALY', 'SUPERVISED', 'CONTEXT']
const DISPLAY = [
  'own_status',
  'related_status',
  'trend',
  'evidence',
  'recommendations',
  'alarms',
] as const

const versions = ref<PredictionConfig[]>([])
const catalog = ref<AlgorithmSpec[]>([])
const sources = ref<ManagedSource[]>([])
const rec = ref<ConfigRecommendation | null>(null)
const current = ref<PredictionConfig | null>(null)
const draft = reactive<ConfigContent>({})
const compiled = ref<ConfigRecommendation['compile'] | null>(null)
const busy = ref(false)
const message = ref<{ ok: boolean; text: string } | null>(null)
const comment = ref('')
const copyFrom = ref('')
const addAlgo = ref('')

// --- step 2: mapped signals, editable parameters and a preview of the real data -----------------------
const signalState = ref<SignalConfigState | null>(null)
const mapped = computed<{ signal: SignalDefinition; mapping: SignalMapping }[]>(() => {
  const cfg = signalState.value?.content
  if (!cfg) return []
  return cfg.mappings
    .filter(
      (m) =>
        m.component_id === props.component.component_id ||
        (!!props.deviceId && m.device_id === props.deviceId),
    )
    .flatMap((m) => {
      const sig = cfg.signals.find((x) => x.signal_id === m.signal_id)
      return sig ? [{ signal: sig, mapping: m }] : []
    })
})
const sigEdit = reactive<Record<string, { unit: string; hz: string; min: string; max: string }>>({})
const origin = new Map<string, string>()
watch(
  mapped,
  (rows) => {
    for (const { signal: x } of rows) {
      const key = JSON.stringify(x)
      if (origin.get(x.signal_id) === key) continue // unchanged on the server: keep what is typed
      origin.set(x.signal_id, key)
      sigEdit[x.signal_id] = {
        unit: x.unit,
        hz: x.expected_sampling_s == null ? '' : String(x.expected_sampling_s),
        min: x.valid_min == null ? '' : String(x.valid_min),
        max: x.valid_max == null ? '' : String(x.valid_max),
      }
    }
  },
  { immediate: true },
)
const num = (v: string) => (v.trim() === '' ? null : Number(v))
async function saveSignal(x: SignalDefinition) {
  const e = sigEdit[x.signal_id]!
  const item = {
    ...x,
    unit: e.unit.trim(),
    expected_sampling_s: num(e.hz),
    valid_min: num(e.min),
    valid_max: num(e.max),
  }
  const ok = await run(async () => {
    const latest = await monitoringApi.signalConfig() // the base version must be the current one
    return monitoringApi.saveSignal(item, 'workbench', latest.version?.version ?? 0)
  }, t('workbench.signalSaved'))
  if (ok) {
    signalState.value = await monitoringApi.signalConfig()
    load().catch(() => undefined)
  }
}
async function onMappingSaved() {
  signalState.value = await monitoringApi.signalConfig()
  load().catch(() => undefined)
}
const previewId = ref<string | null>(null)
const previewData = ref<PreviewResponse | null>(null)
const previewNote = ref('')
async function showPreview(id: string) {
  previewId.value = id
  previewData.value = null
  previewNote.value = ''
  try {
    const ext = await monitoringApi.extent(id)
    if (!ext) {
      previewNote.value = t('workbench.noData')
      return
    }
    const end = Date.parse(ext.end) + 1000
    const start = Math.max(Date.parse(ext.start), end - 3600_000)
    previewData.value = await monitoringApi.signalPreview(
      id,
      new Date(start).toISOString(),
      new Date(end).toISOString(),
    )
  } catch {
    previewNote.value = t('workbench.noData')
  }
}
const previewSeries = computed<ChartSeries[]>(() => {
  const n = previewData.value?.normalized[0]
  if (!n) return []
  const pts = n.samples.filter((x) => x.value !== null)
  return [
    {
      name: n.signal_id,
      unit: n.unit,
      points: pts.map((x) => [Date.parse(x.ts), x.value as number]),
      flagged: pts
        .filter((x) => x.quality.length)
        .map((x) => [Date.parse(x.ts), x.value as number]),
    },
  ]
})
const flagged = computed(() => previewSeries.value[0]?.flagged?.length ?? 0)

// --- readiness: installation date, feature windows from the data, verified healthy reference -----------
const lifecycles = ref<ComponentLifecycle[]>([])
const coverage = ref<FeatureCoverage[]>([])
const installAt = ref('')
const pipelineResult = ref<PipelineResult | null>(null)
const mappedHere = computed(() =>
  mapped.value.filter((r) => r.mapping.component_id === props.component.component_id),
)
const windows = computed(() => coverage.value.reduce((n, c) => n + c.windows, 0))
const hasReference = computed(() => coverage.value.some((c) => c.has_reference))
async function loadReadiness() {
  const id = props.component.component_id
  lifecycles.value = await monitoringApi.lifecycles(id).catch(() => [])
  coverage.value = await monitoringApi.featureCoverage(id).catch(() => [])
}
async function install() {
  if (!installAt.value) return
  const ok = await run(
    () =>
      monitoringApi.installComponent(
        props.component.component_id,
        new Date(`${installAt.value}T00:00:00Z`).toISOString(),
        'workbench',
      ),
    t('workbench.installed'),
  )
  if (ok) await loadReadiness()
}
async function runPipeline(provisional = false) {
  // the button always works: a missing prerequisite is named instead of leaving the button dead
  if (!lifecycles.value.length || !mappedHere.value.length) {
    message.value = {
      ok: false,
      text: t(lifecycles.value.length ? 'workbench.needSignals' : 'workbench.needInstall'),
    }
    return
  }
  const r = await run(() => monitoringApi.runPipeline(props.machineId, provisional))
  if (r) {
    pipelineResult.value = r
    await loadReadiness()
  }
}
const pipelineText = computed(() => {
  const r = pipelineResult.value
  if (!r) return ''
  if (r.catalog === 'pending')
    return t('workbench.catalog.pending', {
      date: r.ready_at ? r.ready_at.slice(0, 10) : '—',
    })
  if (r.catalog === 'failed') return t('workbench.catalog.failed', { error: r.error ?? '' })
  const base = t(
    r.provisional ? 'workbench.catalog.provisional' : `workbench.catalog.${r.catalog}`,
    {
      n: r.windows_added,
    },
  )
  return r.error ? `${base} ${t('workbench.catalog.stopped', { error: r.error })}` : base
})
const configIssues = computed(() =>
  (compiled.value?.issues ?? []).filter((i) => !i.code.startsWith('RT_')),
)
const runtimeIssues = computed(() =>
  (compiled.value?.issues ?? []).filter((i) => i.code.startsWith('RT_')),
)
const VALIDATION_STEPS = ['data', 'compile', 'replay', 'simulation'] as const
const checkOf = (name: string) => current.value?.validation.find((c) => c.name === name)
const detailsOf = (name: string) => (checkOf(name)?.details ?? {}) as Record<string, unknown>
const emptyMappings = computed(() => {
  const rows = (detailsOf('data').rows_recent ?? {}) as Record<string, number>
  return Object.entries(rows)
    .filter(([, n]) => n === 0)
    .map(([k]) => k)
})
async function detach(x: SignalDefinition, m: SignalMapping) {
  const cfg = signalState.value?.content
  if (!cfg) return
  const here = (y: SignalMapping) =>
    y.data_source_id === m.data_source_id && y.device_id === m.device_id
  const oldMaps = cfg.mappings.filter(here)
  const ids = new Set(oldMaps.map((y) => y.signal_id))
  const owned = (it: { signal_ids: string[] }) =>
    it.signal_ids.length > 0 && it.signal_ids.every((i) => ids.has(i))
  const ok = await run(
    () =>
      monitoringApi.replaceDevice(m.data_source_id, m.device_id, {
        comment: `workbench: detach ${x.signal_id}`,
        base_version: signalState.value?.version?.version ?? 0,
        signals: cfg.signals.filter((y) => ids.has(y.signal_id)),
        mappings: oldMaps.map((y) =>
          y.signal_id === x.signal_id ? { ...y, component_id: null } : y,
        ),
        groups: cfg.groups.filter(owned),
        visualizations: cfg.visualizations.filter(owned),
      }),
    t('workbench.detached'),
  )
  if (ok) await onMappingSaved()
}

const editable = computed(() => current.value?.status !== 'PUBLISHED')
const active = computed(() => versions.value.find((v) => v.active) ?? null)
const others = computed(() =>
  props.siblings.filter((c) => c.component_id !== props.component.component_id),
)
const spec = (id: string) => catalog.value.find((a) => a.algorithm_id === id)

async function run<T>(action: () => Promise<T>, done?: string): Promise<T | undefined> {
  busy.value = true
  message.value = null
  try {
    const out = await action()
    if (done) message.value = { ok: true, text: done }
    return out
  } catch (e) {
    const body = e instanceof MonitoringApiError ? e.body : null
    message.value = { ok: false, text: body ? lt(body.message) : t('workbench.failed') }
    return undefined
  } finally {
    busy.value = false
  }
}

function open(v: PredictionConfig | null) {
  current.value = v
  compiled.value = null
  const c = v?.content
  Object.assign(draft, {
    template_from: c?.template_from ?? null,
    relationship: c
      ? { ...c.relationship, members: [...c.relationship.members] }
      : {
          type: 'INDEPENDENT',
          members: [],
          affects_status_display: false,
          affects_common_cause: false,
        },
    pipeline: (c?.pipeline ?? []).map((s) => ({ ...s, params: { ...s.params } })),
    criteria: c
      ? { ...c.criteria, allowed_evidence_types: [...c.criteria.allowed_evidence_types] }
      : {},
    display: c ? { ...c.display } : {},
  })
}

async function load() {
  const id = props.component.component_id
  const [v, c, r, s] = await Promise.all([
    monitoringApi.configVersions(id),
    monitoringApi.algorithmCatalog(),
    monitoringApi.recommendedConfig(id),
    monitoringApi.adminDataSources().catch(() => [] as ManagedSource[]),
  ])
  versions.value = v
  catalog.value = c
  rec.value = r
  sources.value = s
  signalState.value = await monitoringApi.signalConfig().catch(() => null)
  await loadReadiness()
  const keep = v.find((x) => x.config_id === current.value?.config_id)
  open(keep ?? v.find((x) => x.active) ?? v[v.length - 1] ?? null)
}
watch(
  () => props.component.component_id,
  () => {
    current.value = null
    message.value = null
    load().catch(() => (message.value = { ok: false, text: t('common.loadFailed') }))
  },
  { immediate: true },
)

const body = (): ConfigContent => JSON.parse(JSON.stringify(draft))

async function startFrom(content: ConfigContent | null, from?: string) {
  const v = await run(
    () => monitoringApi.createDraft(props.component.component_id, content, from),
    t('workbench.draftCreated'),
  )
  if (v) {
    await load()
    open(versions.value.find((x) => x.config_id === v.config_id) ?? v)
  }
}
const startRecommended = () => startFrom(rec.value ? { ...rec.value.content } : null)
const startCopy = () => copyFrom.value && startFrom(null, copyFrom.value.trim())

async function save() {
  if (!current.value) return
  const v = await run(
    () => monitoringApi.updateDraft(current.value!.config_id, body()),
    t('workbench.saved'),
  )
  if (v) {
    current.value = v
    await load()
  }
}
async function compile() {
  compiled.value =
    (await run(() => monitoringApi.compileConfig(props.component.component_id, body()))) ?? null
}
async function validate() {
  if (!current.value) return
  await save()
  const v = await run(() => monitoringApi.validateConfig(current.value!.config_id))
  if (v) {
    await load()
    const failed = v.validation.filter((c) => !c.ok).map((c) => t(`workbench.check.${c.name}`))
    message.value = {
      ok: v.status === 'VALIDATED',
      text:
        v.status === 'VALIDATED'
          ? t('workbench.validated')
          : t('workbench.validationFailedAt', { steps: failed.join('、') || '—' }),
    }
  }
}
async function publish() {
  if (!current.value || !comment.value.trim()) return
  const v = await run(
    () => monitoringApi.publishConfig(current.value!.config_id, comment.value.trim()),
    t('workbench.published'),
  )
  if (v) {
    comment.value = ''
    await load()
  }
}
async function activate(v: PredictionConfig) {
  if (await run(() => monitoringApi.activateConfig(v.config_id), t('workbench.activated')))
    await load()
}
async function deactivate() {
  if (!window.confirm(t('workbench.deactivateConfirm'))) return
  await run(
    () => monitoringApi.deactivateConfig(props.component.component_id),
    t('workbench.deactivated'),
  )
  await load()
}
async function clone(v: PredictionConfig) {
  const c = await run(() => monitoringApi.cloneConfig(v.config_id), t('workbench.draftCreated'))
  if (c) {
    await load()
    open(versions.value.find((x) => x.config_id === c.config_id) ?? c)
  }
}
async function discard() {
  if (!current.value || !window.confirm(t('workbench.discardConfirm'))) return
  const id = current.value.config_id
  current.value = null
  await run(() => monitoringApi.deleteDraft(id), t('workbench.discarded'))
  await load()
}

function addStage() {
  const id = addAlgo.value
  if (!id) return
  let n = 1
  while (draft.pipeline!.some((s) => s.stage_id === `${id}-${n}`)) n++
  draft.pipeline!.push({
    stage_id: n === 1 ? id : `${id}-${n}`,
    algorithm: id,
    enabled: true,
    params: {},
  })
  addAlgo.value = ''
  compiled.value = null
}
function removeStage(i: number) {
  draft.pipeline!.splice(i, 1)
  compiled.value = null
}
function toggleMember(id: string) {
  const m = draft.relationship!.members!
  const i = m.indexOf(id)
  if (i < 0) m.push(id)
  else m.splice(i, 1)
}
function toggleEvidence(e: EvidenceType) {
  if (e === 'SAFETY') return
  const a = draft.criteria!.allowed_evidence_types!
  const i = a.indexOf(e)
  if (i < 0) a.push(e)
  else a.splice(i, 1)
}
const stageState = (id: string) => compiled.value?.stages.find((s) => s.stage_id === id)
const statusLabel = (v: PredictionConfig) =>
  `${t(`workbench.status.${v.status}`)}${v.active ? ' · ' + t('workbench.active') : ''}`
</script>

<template>
  <PanelBox :title="t('workbench.title', { id: component.component_id })">
    <div class="st-stack" data-testid="config-workbench">
      <p v-if="message" :class="message.ok ? 'ok' : 'error'" role="status" data-testid="wb-message">
        {{ message.text }}
      </p>

      <!-- 1 component -->
      <section>
        <h3>1 · {{ t('workbench.s1') }}</h3>
        <p>
          <span class="st-mono">{{ component.component_id }}</span> ·
          {{ t(`types.${component.type}`) }} ·
          {{ lt(component.name) }}
        </p>
        <p v-if="rec" class="st-note">{{ lt(rec.match.rules) }}</p>
        <ul v-if="rec" class="st-note">
          <li v-for="(c, i) in rec.match.constraints" :key="i">{{ lt(c) }}</li>
        </ul>
      </section>

      <!-- 2 data -->
      <section>
        <h3>2 · {{ t('workbench.s2') }}</h3>
        <p class="st-note">{{ t('workbench.s2note') }}</p>
        <p v-if="rec">
          {{ t('workbench.available') }}:
          <span class="st-mono">{{ rec.available_quantities.join(', ') || '—' }}</span>
          <template v-if="rec.missing_quantities.length">
            ·
            <span class="error"
              >{{ t('workbench.missing') }}: {{ rec.missing_quantities.join(', ') }}</span
            >
          </template>
        </p>
        <ul class="st-note" data-testid="wb-sources">
          <li v-for="s in sources" :key="s.data_source_id">
            {{ s.name }} ({{ s.kind }}) ·
            {{
              s.is_simulated
                ? t('workbench.simulated')
                : s.active
                  ? t('workbench.sourceActive')
                  : t('workbench.sourceInactive')
            }}
          </li>
        </ul>
        <div v-if="mapped.length" class="st-scroll">
          <table class="st-table" data-testid="wb-signals">
            <thead>
              <tr>
                <th>{{ t('workbench.signal') }}</th>
                <th>{{ t('workbench.source') }}</th>
                <th>{{ t('workbench.unit') }}</th>
                <th>{{ t('workbench.samplingS') }}</th>
                <th>{{ t('workbench.validRange') }}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in mapped" :key="r.signal.signal_id" :data-signal="r.signal.signal_id">
                <td>
                  {{ lt(r.signal.name) }}
                  <span class="st-note st-mono"
                    >{{ r.signal.signal_id }} · {{ r.signal.quantity }}</span
                  >
                </td>
                <td class="st-mono">{{ r.mapping.data_source_id }}</td>
                <td>
                  <input v-model="sigEdit[r.signal.signal_id]!.unit" class="st-input st-mono num" />
                </td>
                <td>
                  <input
                    v-model="sigEdit[r.signal.signal_id]!.hz"
                    class="st-input st-mono num"
                    type="number"
                    step="any"
                    min="0"
                  />
                </td>
                <td>
                  <input
                    v-model="sigEdit[r.signal.signal_id]!.min"
                    class="st-input st-mono num"
                    type="number"
                    step="any"
                  />
                  <input
                    v-model="sigEdit[r.signal.signal_id]!.max"
                    class="st-input st-mono num"
                    type="number"
                    step="any"
                  />
                </td>
                <td>
                  <button type="button" class="link" :disabled="busy" @click="saveSignal(r.signal)">
                    {{ t('workbench.save') }}
                  </button>
                  <button
                    v-if="r.mapping.component_id === component.component_id"
                    type="button"
                    class="link danger"
                    :disabled="busy"
                    data-testid="wb-detach"
                    @click="detach(r.signal, r.mapping)"
                  >
                    {{ t('workbench.detach') }}
                  </button>
                  <button
                    type="button"
                    class="link"
                    data-testid="wb-preview"
                    @click="showPreview(r.signal.signal_id)"
                  >
                    {{ t('workbench.preview') }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="st-note">{{ t('workbench.noSignals') }}</p>
        <div v-if="previewId" data-testid="wb-preview-box">
          <p class="st-note">
            {{ t('workbench.previewNote', { id: previewId }) }}
            <template v-if="previewSeries[0]">
              ·
              {{
                t('workbench.previewCount', { n: previewSeries[0].points.length, f: flagged })
              }}</template
            >
            <template v-if="previewNote"> · {{ previewNote }}</template>
          </p>
          <PreviewChart
            v-if="previewSeries[0]?.points.length"
            :series="previewSeries"
            :height="200"
            :flagged-label="t('workbench.flagged')"
          />
        </div>
        <SignalMappingEditor
          :component-id="component.component_id"
          :device-id="deviceId"
          :state="signalState"
          @saved="onMappingSaved"
        />
      </section>

      <!-- readiness -->
      <section data-testid="wb-readiness">
        <h3>{{ t('workbench.ready') }}</h3>
        <p class="st-note">{{ t('workbench.readyNote') }}</p>
        <ul class="ready">
          <li :class="lifecycles.length ? 'ok' : 'error'" data-testid="ready-install">
            {{ lifecycles.length ? '✓' : '✗' }} {{ t('workbench.rInstall') }}
            <template v-if="lifecycles.length">
              · {{ lifecycles[0]!.installed_at.slice(0, 10) }}
            </template>
            <span v-else class="row inline">
              <input v-model="installAt" type="date" class="st-input" data-testid="install-date" />
              <button
                type="button"
                class="st-button"
                :disabled="busy || !installAt"
                data-testid="install-save"
                @click="install"
              >
                {{ t('workbench.registerInstall') }}
              </button>
            </span>
          </li>
          <li :class="mappedHere.length ? 'ok' : 'error'" data-testid="ready-signals">
            {{ mappedHere.length ? '✓' : '✗' }}
            {{ t('workbench.rSignals', { n: mappedHere.length }) }}
          </li>
          <li :class="windows ? 'ok' : 'error'" data-testid="ready-features">
            {{ windows ? '✓' : '✗' }} {{ t('workbench.rFeatures', { n: windows }) }}
            <button
              type="button"
              class="st-button"
              :disabled="busy"
              data-testid="run-pipeline"
              @click="runPipeline(false)"
            >
              {{ t('workbench.runPipeline') }}
            </button>
            <span v-if="!lifecycles.length" class="st-note error">{{
              t('workbench.needInstall')
            }}</span>
            <span v-else-if="!mappedHere.length" class="st-note error">{{
              t('workbench.needSignals')
            }}</span>
            <span
              v-if="pipelineResult"
              :class="[
                'st-note',
                ['failed', 'no_data', 'no_signals'].includes(pipelineResult.catalog) ||
                pipelineResult.error
                  ? 'error'
                  : '',
              ]"
              data-testid="pipeline-result"
            >
              {{ pipelineText }}
            </span>
            <button
              v-if="pipelineResult?.catalog === 'pending'"
              type="button"
              class="st-button"
              :disabled="busy"
              data-testid="run-pipeline-provisional"
              @click="runPipeline(true)"
            >
              {{ t('workbench.runProvisional') }}
            </button>
          </li>
          <li :class="hasReference ? 'ok' : 'error'" data-testid="ready-reference">
            {{ hasReference ? '✓' : '✗' }} {{ t('workbench.rReference') }}
          </li>
        </ul>
        <ReferenceForm
          v-if="windows && !hasReference"
          :component-id="component.component_id"
          @verified="loadReadiness"
        />
      </section>

      <!-- Versions -->
      <section>
        <h3>{{ t('workbench.versions') }}</h3>
        <p class="st-note">
          {{ active ? t('workbench.activeIs', { id: active.config_id }) : t('workbench.noActive') }}
        </p>
        <ul v-if="versions.length" class="vers" data-testid="wb-versions">
          <li
            v-for="v in versions"
            :key="v.config_id"
            :aria-current="v.config_id === current?.config_id"
          >
            <button type="button" class="link" @click="open(v)">
              {{ 'v' + v.version }} · {{ statusLabel(v) }}
            </button>
            <span class="st-note st-mono">{{ v.content_hash.slice(0, 8) }}</span>
            <button type="button" class="link" :disabled="busy" @click="clone(v)">
              {{ t('workbench.clone') }}
            </button>
            <button
              v-if="v.status === 'PUBLISHED' && !v.active"
              type="button"
              class="link"
              :disabled="busy"
              @click="activate(v)"
            >
              {{ t('workbench.activate') }}
            </button>
          </li>
        </ul>
        <div class="row">
          <button
            type="button"
            class="st-button"
            :disabled="busy || !rec"
            data-testid="wb-start"
            @click="startRecommended"
          >
            {{ t('workbench.startRecommended') }}
          </button>
          <input
            v-model.trim="copyFrom"
            class="st-input st-mono"
            :placeholder="t('workbench.copyFrom')"
          />
          <button type="button" class="st-button" :disabled="busy || !copyFrom" @click="startCopy">
            {{ t('workbench.copy') }}
          </button>
          <button
            v-if="active"
            type="button"
            class="link danger"
            :disabled="busy"
            @click="deactivate"
          >
            {{ t('workbench.deactivate') }}
          </button>
        </div>
      </section>

      <template v-if="current">
        <p class="st-note">
          {{
            editable
              ? t('workbench.editing', { id: current.config_id })
              : t('workbench.immutable', { id: current.config_id })
          }}
        </p>

        <!-- 3 relationships -->
        <section v-if="draft.relationship">
          <h3>3 · {{ t('workbench.s3') }}</h3>
          <div class="st-form">
            <label class="st-field">
              <span>{{ t('workbench.relType') }}</span>
              <select
                v-model="draft.relationship.type"
                class="st-select"
                :disabled="!editable"
                data-testid="wb-relation"
              >
                <option v-for="r in RELATIONS" :key="r" :value="r">
                  {{ t(`workbench.relation.${r}`) }}
                </option>
              </select>
            </label>
          </div>
          <template v-if="draft.relationship.type !== 'INDEPENDENT'">
            <div class="row">
              <label v-for="c in others" :key="c.component_id" class="chk">
                <input
                  type="checkbox"
                  :checked="draft.relationship.members!.includes(c.component_id)"
                  :disabled="!editable"
                  @change="toggleMember(c.component_id)"
                />
                {{ c.component_id }}
              </label>
              <span v-if="!others.length" class="st-note">{{ t('workbench.noSiblings') }}</span>
            </div>
            <label class="chk"
              ><input
                v-model="draft.relationship.affects_status_display"
                type="checkbox"
                :disabled="!editable"
              />
              {{ t('workbench.affectsDisplay') }}</label
            >
            <label class="chk"
              ><input
                v-model="draft.relationship.affects_common_cause"
                type="checkbox"
                :disabled="!editable"
              />
              {{ t('workbench.affectsCause') }}</label
            >
          </template>
        </section>

        <!-- 4 pipeline -->
        <section>
          <h3>4 · {{ t('workbench.s4') }}</h3>
          <div class="st-scroll">
            <table class="st-table" data-testid="wb-pipeline">
              <thead>
                <tr>
                  <th>{{ t('workbench.stage') }}</th>
                  <th>{{ t('workbench.algorithm') }}</th>
                  <th>{{ t('workbench.enabled') }}</th>
                  <th>{{ t('workbench.effect') }}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(s, i) in draft.pipeline" :key="s.stage_id" :data-stage="s.stage_id">
                  <td class="st-mono">{{ s.stage_id }}</td>
                  <td>
                    {{ spec(s.algorithm) ? lt(spec(s.algorithm)!.name) : s.algorithm }}
                    <span v-if="spec(s.algorithm)?.boundary" class="st-note">{{
                      lt(spec(s.algorithm)!.boundary!)
                    }}</span>
                  </td>
                  <td><input v-model="s.enabled" type="checkbox" :disabled="!editable" /></td>
                  <td>
                    <template v-if="stageState(s.stage_id)">
                      {{
                        stageState(s.stage_id)!.effective
                          ? t('workbench.effective')
                          : t('workbench.notEffective')
                      }}
                      <span v-if="stageState(s.stage_id)!.reason" class="st-note">{{
                        lt(stageState(s.stage_id)!.reason!)
                      }}</span>
                    </template>
                  </td>
                  <td>
                    <button
                      v-if="editable"
                      type="button"
                      class="link danger"
                      @click="removeStage(i)"
                    >
                      {{ t('plant.delete') }}
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="editable" class="row">
            <select v-model="addAlgo" class="st-select" :aria-label="t('workbench.algorithm')">
              <option value="">{{ t('workbench.pickAlgorithm') }}</option>
              <option v-for="a in catalog" :key="a.algorithm_id" :value="a.algorithm_id">
                {{ lt(a.name) }}{{ a.implemented ? '' : ' (' + t('workbench.interfaceOnly') + ')' }}
              </option>
            </select>
            <button type="button" class="st-button" :disabled="!addAlgo" @click="addStage">
              {{ t('plant.add') }}
            </button>
            <button
              type="button"
              class="st-button"
              :disabled="busy"
              data-testid="wb-compile"
              @click="compile"
            >
              {{ t('workbench.compile') }}
            </button>
          </div>
          <p class="st-note">{{ t('workbench.compileNote') }}</p>
          <template v-if="compiled">
            <ul v-if="configIssues.length" class="st-note" data-testid="wb-issues">
              <li class="head">{{ t('workbench.configIssues') }}</li>
              <li v-for="(i, k) in configIssues" :key="k">
                <strong>{{ i.level }}</strong> {{ i.code }}: {{ lt(i.message) }}
              </li>
            </ul>
            <ul class="st-note" data-testid="wb-runtime">
              <li class="head">{{ t('workbench.runtimeIssues') }}</li>
              <li v-if="!runtimeIssues.length">{{ t('workbench.runtimeOk') }}</li>
              <li v-for="(i, k) in runtimeIssues" :key="k">{{ lt(i.message) }}</li>
            </ul>
          </template>
        </section>

        <!-- 5 criteria -->
        <section v-if="draft.criteria">
          <h3>5 · {{ t('workbench.s5') }}</h3>
          <p class="st-note">{{ t('workbench.s5note') }}</p>
          <div class="row">
            <label v-for="e in EVIDENCE" :key="e" class="chk">
              <input
                type="checkbox"
                :checked="draft.criteria.allowed_evidence_types!.includes(e)"
                :disabled="!editable || e === 'SAFETY'"
                @change="toggleEvidence(e)"
              />
              {{ t(`evidence.type.${e}`) }}
            </label>
          </div>
        </section>

        <!-- 6 display -->
        <section v-if="draft.display">
          <h3>6 · {{ t('workbench.s6') }}</h3>
          <div class="row">
            <label v-for="k in DISPLAY" :key="k" class="chk">
              <input v-model="draft.display[k]" type="checkbox" :disabled="!editable" />
              {{ t(`workbench.display.${k}`) }}
            </label>
          </div>
        </section>

        <!-- 7 validate / publish -->
        <section>
          <h3>7 · {{ t('workbench.s7') }}</h3>
          <p class="st-note">{{ t('workbench.checksNote') }}</p>
          <ol class="checks" data-testid="wb-checks">
            <li
              v-for="n in VALIDATION_STEPS"
              :key="n"
              :class="checkOf(n) ? (checkOf(n)!.ok ? 'ok' : 'error') : 'idle'"
              :data-check="n"
            >
              <strong>{{ checkOf(n) ? (checkOf(n)!.ok ? '✓' : '✗') : '○' }}</strong>
              {{ t(`workbench.check.${n}`) }}
              <span class="st-note">{{ t(`workbench.checkWhat.${n}`) }}</span>
              <div v-if="checkOf(n)">
                {{ lt(checkOf(n)!.summary) }}
                <p v-if="!checkOf(n)!.ok" class="fix" :data-fix="n">
                  {{ t(`workbench.fix.${n}`) }}
                </p>
              </div>
              <div v-else class="st-note">{{ t('workbench.notRun') }}</div>
              <ul v-if="n === 'data' && checkOf(n) && emptyMappings.length" class="st-note st-mono">
                <li v-for="k in emptyMappings" :key="k">{{ k }} · {{ t('workbench.noRows') }}</li>
              </ul>
              <div v-if="n === 'replay'" class="st-note" data-testid="replay-prereq">
                {{ t('workbench.replayNeeds') }}
                <span :class="windows ? 'ok' : 'error'">
                  {{ windows ? '✓' : '✗' }} {{ t('workbench.rFeatures', { n: windows }) }}</span
                >
                <span :class="hasReference ? 'ok' : 'error'">
                  {{ hasReference ? '✓' : '✗' }} {{ t('workbench.rReference') }}</span
                >
              </div>
            </li>
          </ol>
          <div v-if="editable" class="row">
            <button type="button" class="st-button" :disabled="busy" @click="save">
              {{ t('workbench.save') }}
            </button>
            <button
              type="button"
              class="st-button primary"
              :disabled="busy"
              data-testid="wb-validate"
              @click="validate"
            >
              {{ t('workbench.validate') }}
            </button>
            <button type="button" class="link danger" :disabled="busy" @click="discard">
              {{ t('workbench.discard') }}
            </button>
          </div>
          <div v-if="current.status === 'VALIDATED'" class="row">
            <input
              v-model="comment"
              class="st-input"
              :placeholder="t('workbench.publishComment')"
              data-testid="wb-comment"
            />
            <button
              type="button"
              class="st-button primary"
              :disabled="busy || !comment.trim()"
              data-testid="wb-publish"
              @click="publish"
            >
              {{ t('workbench.publish') }}
            </button>
          </div>
          <div v-if="current.status === 'PUBLISHED' && !current.active" class="row">
            <button
              type="button"
              class="st-button primary"
              :disabled="busy"
              data-testid="wb-activate"
              @click="activate(current)"
            >
              {{ t('workbench.activate') }}
            </button>
          </div>
        </section>
      </template>
      <p v-else class="st-note">{{ t('workbench.none') }}</p>
    </div>
  </PanelBox>
</template>

<style scoped>
h3 {
  font-size: var(--text-base);
  margin: var(--space-2) 0;
}
section {
  padding-top: var(--space-3);
  border-top: 1px solid var(--line);
}
.row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  flex-wrap: wrap;
  margin-top: var(--space-2);
}
.checks {
  display: grid;
  gap: var(--space-3);
  padding-left: var(--space-5);
}
.checks .idle {
  color: var(--ink-soft);
}
.fix {
  color: var(--health-critical);
  font-size: var(--text-sm);
}
.ready {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: var(--space-2);
}
.inline {
  display: inline-flex;
  margin: 0 0 0 var(--space-3);
}
.num {
  width: 90px;
}
.chk {
  display: inline-flex;
  gap: var(--space-1);
  align-items: center;
  font-size: var(--text-sm);
}
.vers {
  list-style: none;
  padding: 0;
  margin: 0;
}
.vers li {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  padding: var(--space-1) 0;
}
.vers li[aria-current='true'] {
  font-weight: 600;
}
.link {
  border: 0;
  background: none;
  padding: 0;
  font: inherit;
  font-size: var(--text-sm);
  color: var(--accent);
  cursor: pointer;
}
.link.danger:not(:disabled) {
  color: var(--health-critical);
}
.ok {
  color: var(--health-normal);
}
.error {
  color: var(--health-critical);
}
</style>

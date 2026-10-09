/**
 * Draft state of one Data Source Studio session. The draft becomes contract objects
 * (SignalMapping, SignalGroup, VisualizationTemplate) only when a version is saved.
 */
import { defineStore } from 'pinia'
import { computed, ref, shallowRef } from 'vue'
import type {
  ChartKind,
  DataSourceConfig,
  PhysicalQuantity,
  SignalConfigVersion,
  SignalDefinition,
  SignalGroup,
  SignalMapping,
  VisualizationTemplate,
} from '@/api/contracts'
import {
  createMockStudioApi,
  loadStudioFixture,
  type ConnectionCheck,
  type StudioApi,
  type StudioComponent,
  type StudioDevice,
  type StudioPreview,
  type StudioRole,
  type StudioSignal,
  type TemplateView,
} from '@/api/studio'
import { createHttpStudioApi, StudioApiError } from '@/api/studioHttp'
import { summarizeQuality, type QualitySummary } from './quality'
import { suggestedScale } from './units'

export const STEPS = [
  'connection',
  'schema',
  'signals',
  'template',
  'mapping',
  'units',
  'groups',
  'preview',
  'quality',
  'components',
  'viz',
  'version',
] as const
export type StepName = (typeof STEPS)[number]

export interface SignalDraft {
  key_name: string
  signal_id: string
  quantity: PhysicalQuantity
  expected_sampling_s: number | null
  source_unit: string
  target_unit: string
  scale: number | null
  offset: number
  component_id: string | null
}

export interface GroupDraft {
  group_id: string
  name: { zh: string; en: string }
  keys: string[]
  chart: ChartKind
}

export interface FieldMapping {
  device_field: string
  key_field: string
  time_field: string
  value_field: string
}

/** The real backend unless the build asks for the offline mock (VITE_STUDIO_API=mock, G1 demo). */
export async function defaultStudioApi(): Promise<{ api: StudioApi; kind: 'http' | 'mock' }> {
  if (import.meta.env.VITE_STUDIO_API === 'mock') {
    return { api: createMockStudioApi(await loadStudioFixture()), kind: 'mock' }
  }
  return { api: createHttpStudioApi(), kind: 'http' }
}

export const useStudioStore = defineStore('studio', () => {
  const api = shallowRef<StudioApi | null>(null)
  const apiKind = ref<'http' | 'mock'>('mock')
  const role = ref<StudioRole>('operator')
  const step = ref(0)
  const visited = ref(0)

  const source = ref<DataSourceConfig | null>(null)
  const checks = ref<ConnectionCheck[] | null>(null)
  const schema = ref<Awaited<ReturnType<StudioApi['inspectSchema']>> | null>(null)
  const devices = ref<StudioDevice[]>([])
  const templates = ref<TemplateView[]>([])
  const versions = ref<SignalConfigVersion[]>([])

  const deviceId = ref<string | null>(null)
  const selectedKeys = ref<string[]>([])
  const templateId = ref<string | null>(null)
  const fields = ref<FieldMapping>({
    device_field: '',
    key_field: '',
    time_field: '',
    value_field: '',
  })
  const drafts = ref<Record<string, SignalDraft>>({})
  const groups = ref<GroupDraft[]>([])
  const deviceSignals = ref<StudioSignal[]>([])
  const deviceComponents = ref<StudioComponent[]>([])
  const preview = ref<StudioPreview | null>(null)
  const saved = ref<SignalConfigVersion | null>(null)
  const saveError = ref<StudioApiError | Error | null>(null)
  const comment = ref('')

  async function init(given?: StudioApi) {
    if (given) {
      api.value = given
      apiKind.value = 'mock'
    } else {
      const chosen = await defaultStudioApi()
      api.value = chosen.api
      apiKind.value = chosen.kind
    }
    source.value = await api.value.source()
    devices.value = await api.value.devices()
    versions.value = await api.value.versions()
    templates.value = await api.value.templates(role.value)
  }

  async function setRole(r: StudioRole) {
    role.value = r
    if (api.value) templates.value = await api.value.templates(r)
  }

  async function testConnection() {
    checks.value = await api.value!.testConnection()
    schema.value = await api.value!.inspectSchema()
    const col = (r: string) => schema.value!.columns.find((c) => c.role === r)?.name ?? ''
    fields.value = {
      device_field: col('device'),
      key_field: col('key'),
      time_field: col('time'),
      value_field: col('value'),
    }
  }

  async function selectDevice(id: string) {
    if (deviceId.value === id) return
    deviceId.value = id
    const { signals, mappings } = await api.value!.signals(id)
    deviceSignals.value = signals
    deviceComponents.value = await api.value!.components(id)
    preview.value = await api.value!.preview(id)
    const keys = devices.value.find((d) => d.device_id === id)?.keys.map((k) => k.key_name) ?? []
    selectedKeys.value = keys
    const next: Record<string, SignalDraft> = {}
    for (const key of keys) {
      const m: SignalMapping | undefined = mappings.find((x) => x.key_name === key)
      const s = signals.find((x) => x.signal_id === m?.signal_id)
      const source = m?.conversion?.source_unit ?? s?.unit ?? ''
      const target = m?.conversion?.target_unit ?? s?.unit ?? ''
      next[key] = {
        key_name: key,
        signal_id: s?.signal_id ?? key,
        quantity: s?.quantity ?? 'OTHER',
        expected_sampling_s: s?.expected_sampling_s ?? null,
        source_unit: source,
        target_unit: target,
        scale: m?.conversion?.scale ?? suggestedScale(source, target),
        offset: m?.conversion?.offset ?? 0,
        component_id: m?.component_id ?? null,
      }
    }
    drafts.value = next
    groups.value = defaultGroups(keys, next)
  }

  function defaultGroups(keys: string[], d: Record<string, SignalDraft>): GroupDraft[] {
    const byComponent = new Map<string, string[]>()
    for (const k of keys) {
      const comp = d[k]!.signal_id.split('.')[0]!
      byComponent.set(comp, [...(byComponent.get(comp) ?? []), k])
    }
    return [...byComponent.entries()].map(([comp, ks], i) => {
      const c = deviceComponents.value.find((x) => x.component_id === comp)
      const durations = ks.every((k) => d[k]!.quantity === 'DURATION')
      return {
        group_id: `G${i + 1}`,
        name: c ? { ...c.name } : { zh: comp, en: comp },
        keys: ks,
        chart: durations ? 'CYCLE_DURATION' : 'LINE',
      }
    })
  }

  function toggleKey(key: string) {
    if (selectedKeys.value.includes(key)) {
      selectedKeys.value = selectedKeys.value.filter((k) => k !== key)
      for (const g of groups.value) g.keys = g.keys.filter((k) => k !== key)
      groups.value = groups.value.filter((g) => g.keys.length > 0)
    } else {
      selectedKeys.value = [...selectedKeys.value, key]
      groups.value = defaultGroups(selectedKeys.value, drafts.value)
    }
  }

  function addGroup() {
    const n = Math.max(0, ...groups.value.map((g) => Number(g.group_id.slice(1)) || 0)) + 1
    groups.value = [
      ...groups.value,
      {
        group_id: `G${n}`,
        name: { zh: `分组 ${n}`, en: `Group ${n}` },
        keys: [],
        chart: 'LINE',
      },
    ]
  }

  function removeGroup(id: string) {
    groups.value = groups.value.filter((g) => g.group_id !== id)
  }

  function setComponent(key: string, componentId: string) {
    drafts.value[key]!.component_id = componentId
  }

  /** A group belongs to a component when all its signals do. */
  function groupComponent(g: GroupDraft): string | null {
    const comps = new Set(g.keys.map((k) => drafts.value[k]?.component_id ?? null))
    return comps.size === 1 ? ([...comps][0] ?? null) : null
  }

  function signalName(key: string) {
    const d = drafts.value[key]
    return deviceSignals.value.find((s) => s.signal_id === d?.signal_id)?.name
  }

  const activeDrafts = computed(() =>
    selectedKeys.value.map((k) => drafts.value[k]!).filter(Boolean),
  )

  const quality = computed<QualitySummary[]>(() => {
    const p = preview.value
    if (!p) return []
    return activeDrafts.value.map((d) =>
      summarizeQuality(
        d.signal_id,
        p.series[d.key_name] ?? [],
        { start: p.window_start, end: p.window_end },
        d.expected_sampling_s,
      ),
    )
  })

  const stepComplete = computed<Record<StepName, boolean>>(() => ({
    connection: !!checks.value?.every((c) => c.ok),
    schema: !!schema.value,
    signals: !!deviceId.value && selectedKeys.value.length > 0,
    template: !!templateId.value,
    mapping: Object.values(fields.value).every(Boolean),
    units: activeDrafts.value.every((d) => d.target_unit && d.scale !== null && d.scale !== 0),
    groups: groups.value.length > 0 && groups.value.every((g) => g.keys.length > 0),
    preview: !!preview.value,
    quality: quality.value.length > 0,
    components: activeDrafts.value.every((d) => !!d.component_id),
    viz: groups.value.every((g) => !!g.chart),
    version: !!saved.value,
  }))

  const canAdvance = computed(() => stepComplete.value[STEPS[step.value]!])

  function go(i: number) {
    if (i <= visited.value && i >= 0 && i < STEPS.length) step.value = i
  }
  function next() {
    if (!canAdvance.value || step.value >= STEPS.length - 1) return
    step.value++
    visited.value = Math.max(visited.value, step.value)
  }
  function back() {
    if (step.value > 0) step.value--
  }

  /** Contract objects produced by this draft; this is what a version snapshots. */
  const content = computed(() => {
    const mappings: SignalMapping[] = activeDrafts.value.map((d) => ({
      signal_id: d.signal_id,
      data_source_id: schema.value?.metadata.data_source_id ?? '',
      template_id: templateId.value ?? '',
      device_id: deviceId.value ?? '',
      key_name: d.key_name,
      time_field: fields.value.time_field,
      value_field: fields.value.value_field,
      conversion: {
        source_unit: d.source_unit,
        target_unit: d.target_unit,
        scale: d.scale ?? 1,
        offset: d.offset,
      },
      component_id: d.component_id,
    }))
    const signals: SignalDefinition[] = activeDrafts.value.map((d) => {
      const known = deviceSignals.value.find((x) => x.signal_id === d.signal_id)
      return {
        signal_id: d.signal_id,
        name: known ? { ...known.name } : { zh: d.key_name, en: d.key_name },
        quantity: d.quantity,
        unit: d.target_unit,
        expected_sampling_s: d.expected_sampling_s,
        valid_min: known?.valid_min ?? null,
        valid_max: known?.valid_max ?? null,
      }
    })
    const sig = (k: string) => drafts.value[k]!.signal_id
    // Group and chart ids are scoped to the device so several devices can be configured.
    const scoped = (id: string) => `${deviceId.value ?? ''}.${id}`
    const signalGroups: SignalGroup[] = groups.value.map((g) => ({
      group_id: scoped(g.group_id),
      name: g.name,
      signal_ids: g.keys.map(sig),
      component_id: groupComponent(g),
    }))
    const viz: VisualizationTemplate[] = groups.value.map((g) => ({
      template_id: `viz-${scoped(g.group_id)}`,
      name: g.name,
      chart: g.chart,
      signal_ids: g.keys.map(sig),
      y_min: null,
      y_max: null,
    }))
    return { signals, mappings, groups: signalGroups, visualizations: viz }
  })

  async function save() {
    if (!comment.value.trim()) return
    saveError.value = null
    try {
      saved.value = await api.value!.saveVersion(content.value, comment.value.trim(), role.value)
    } catch (e) {
      saveError.value = e instanceof Error ? e : new Error(String(e))
      return
    }
    versions.value = await api.value!.versions()
  }

  return {
    apiKind,
    saveError,
    role,
    step,
    visited,
    source,
    checks,
    schema,
    devices,
    templates,
    versions,
    deviceId,
    selectedKeys,
    templateId,
    fields,
    drafts,
    groups,
    deviceSignals,
    deviceComponents,
    preview,
    saved,
    comment,
    activeDrafts,
    quality,
    stepComplete,
    canAdvance,
    content,
    init,
    setRole,
    testConnection,
    selectDevice,
    toggleKey,
    addGroup,
    removeGroup,
    setComponent,
    groupComponent,
    signalName,
    go,
    next,
    back,
    save,
  }
})

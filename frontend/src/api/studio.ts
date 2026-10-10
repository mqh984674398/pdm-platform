/**
 * Data Source Studio API surface. Two implementations: the real backend (`studioHttp.ts`, T011) and
 * an offline mock over the simulated snapshot Data/fixtures/studio_demo.json (unit tests and the
 * static G1 demo). The mock follows the same rules as the backend: template SQL only for
 * administrators, read-only sources, and immutable configuration versions.
 */
import type {
  ComponentType,
  DataSourceConfig,
  LocalizedText,
  QueryTemplate,
  SignalConfigVersion,
  SignalDefinition,
  SignalMapping,
  SourceMetadata,
} from './contracts'
import { summarizeQuality, type QualitySummary } from '@/studio/quality'

export type StudioRole = 'operator' | 'admin'

export interface TableColumn {
  name: string
  type: string
  role: 'device' | 'key' | 'time' | 'value' | null
}

export interface StudioDevice {
  device_id: string
  scenario_id: string
  scenario_title: LocalizedText
  /** rows is null when the source cannot count cheaply (real SQL sources). */
  keys: { key_name: string; rows: number | null }[]
  /** Machine bound to this device in the plant structure (D-037), when there is one. */
  machine_id?: string | null
  machine_path?: LocalizedText | null
}

export interface StudioPreview {
  window_start: string
  window_end: string
  /** Raw values in source units: [seconds after window_start, value], in source row order. */
  series: Record<string, [number, number][]>
}

export interface StudioSignal extends SignalDefinition {
  device_id: string
}

export interface StudioComponent {
  component_id: string
  device_id: string
  type: ComponentType
  name: LocalizedText
  signal_ids: string[]
}

export interface StudioFixture {
  is_simulated: true
  data_source: DataSourceConfig
  metadata: SourceMetadata
  table: { name: string; row_count: number | null; columns: TableColumn[]; sample_rows: string[][] }
  devices: StudioDevice[]
  templates: QueryTemplate[]
  template_sql: Record<string, string>
  signals: StudioSignal[]
  components: StudioComponent[]
  suggested_mappings: SignalMapping[]
  versions: SignalConfigVersion[]
  previews: Record<string, StudioPreview>
}

export interface ConnectionCheck {
  key: 'reachable' | 'readOnly' | 'timeout' | 'rowLimit'
  ok: boolean
}

export interface TemplateView extends QueryTemplate {
  /** Present only for administrators (UI-05 / L1-05). */
  sql?: string
}

/** What the quality step checks: the draft's mappings and signal definitions over the preview window. */
export interface StudioQualityInput {
  mappings: SignalMapping[]
  signals: SignalDefinition[]
  window: { start: string; end: string }
  /** key name per signal id, for the offline mock which works on preview series by key */
  keys: Record<string, string>
}

export interface StudioApi {
  /** Sources the signed-in user may use; the simulation database is listed for administrators only. */
  sources(): Promise<DataSourceConfig[]>
  /** Development login only: who the ordinary-user calls are made as (operator or administrator). */
  setPersona?(role: StudioRole): void
  /** Selects a source (the first usable one when no id is given) for the calls that follow. */
  source(id?: string): Promise<DataSourceConfig>
  testConnection(): Promise<ConnectionCheck[]>
  inspectSchema(): Promise<StudioFixture['table'] & { metadata: SourceMetadata }>
  devices(): Promise<StudioDevice[]>
  templates(role: StudioRole): Promise<TemplateView[]>
  signals(deviceId: string): Promise<{ signals: StudioSignal[]; mappings: SignalMapping[] }>
  components(deviceId: string): Promise<StudioComponent[]>
  preview(deviceId: string): Promise<StudioPreview>
  quality(input: StudioQualityInput): Promise<QualitySummary[]>
  versions(): Promise<SignalConfigVersion[]>
  saveVersion(content: unknown, comment: string, role: StudioRole): Promise<SignalConfigVersion>
}

export async function loadStudioFixture(): Promise<StudioFixture> {
  const mod = await import('@data/fixtures/studio_demo.json')
  return mod.default as unknown as StudioFixture
}

/** Stable hash of the configuration content; versions are identified by it (L2-05). */
export async function contentHash(content: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(JSON.stringify(content))
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return (
    'sha256:' + [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
  )
}

export function createMockStudioApi(
  fixture: StudioFixture,
  now: () => Date = () => new Date(),
): StudioApi {
  // Saved versions live only for this session: the mock has no persistence.
  const versions = [...fixture.versions]
  return {
    sources: async () => [fixture.data_source],
    source: async () => fixture.data_source,
    testConnection: async () => [
      { key: 'reachable', ok: true },
      { key: 'readOnly', ok: fixture.data_source.read_only },
      { key: 'timeout', ok: (fixture.data_source.statement_timeout_s ?? 0) <= 300 },
      { key: 'rowLimit', ok: (fixture.data_source.max_rows ?? 0) <= 2_000_000 },
    ],
    inspectSchema: async () => ({ ...fixture.table, metadata: fixture.metadata }),
    devices: async () => fixture.devices,
    templates: async (role) =>
      fixture.templates.map((t) =>
        role === 'admin' ? { ...t, sql: fixture.template_sql[t.template_id] } : { ...t },
      ),
    signals: async (deviceId) => ({
      signals: fixture.signals.filter((s) => s.device_id === deviceId),
      mappings: fixture.suggested_mappings.filter((m) => m.device_id === deviceId),
    }),
    components: async (deviceId) => fixture.components.filter((c) => c.device_id === deviceId),
    preview: async (deviceId) => {
      const p = fixture.previews[deviceId]
      if (!p) throw new Error(`no preview for ${deviceId}`)
      return p
    },
    quality: async ({ mappings, signals, window, keys }) =>
      mappings.map((m) => {
        const device = fixture.previews[m.device_id]
        const sig = signals.find((x) => x.signal_id === m.signal_id)
        return summarizeQuality(
          m.signal_id,
          device?.series[keys[m.signal_id] ?? m.key_name] ?? [],
          window,
          sig?.expected_sampling_s,
        )
      }),
    versions: async () => [...versions].reverse(),
    saveVersion: async (content, comment, role) => {
      const v: SignalConfigVersion = {
        version: versions.length + 1,
        created_at: now().toISOString(),
        created_by: role === 'admin' ? 'demo-admin' : 'demo-operator',
        comment,
        content_hash: await contentHash(content),
      }
      versions.push(v)
      return v
    },
  }
}

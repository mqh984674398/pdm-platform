/**
 * Data Source Studio over the real backend (T011). Ordinary users act as `engineer` and never see
 * SQL; administrators additionally get template text. Authentication is the development header
 * provider until T028 (DECISIONS D-010).
 */
import type {
  ApiConnectionCheck,
  ApiError,
  ApiStudioDevice,
  DataSourceConfig,
  DeviceConfigChange,
  DeviceSuggestions,
  LocalizedText,
  PreviewRequest,
  PreviewResponse,
  QualityRequest,
  QualityResponse,
  SignalConfigVersion,
  SignalDefinition,
  SignalMapping,
  SourceLayout,
  SourceMetadata,
} from './contracts'
import type {
  ConnectionCheck,
  StudioApi,
  StudioComponent,
  StudioDevice,
  StudioPreview,
  StudioRole,
  TemplateView,
} from './studio'

const ROLE_HEADER: Record<StudioRole, { user: string; role: string }> = {
  operator: { user: 'studio-operator', role: 'engineer' },
  admin: { user: 'studio-admin', role: 'admin' },
}
const PREVIEW_BATCH = 32 // backend limit of mappings per preview request

/** An API failure with the backend's bilingual message. */
export class StudioApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly localized: LocalizedText | null,
    readonly reason: string | null,
  ) {
    super(localized?.en ?? `request failed (${status})`)
  }
}

export interface StudioContent {
  signals: SignalDefinition[]
  mappings: SignalMapping[]
  groups: DeviceConfigChange['groups']
  visualizations: DeviceConfigChange['visualizations']
}

export function createHttpStudioApi(fetchImpl: typeof fetch = fetch.bind(globalThis)): StudioApi {
  let sourceId: string | null = null
  const deviceCache = new Map<string, StudioDevice>()
  const suggestionCache = new Map<string, Promise<DeviceSuggestions>>()

  async function call<T>(path: string, role: StudioRole, init: RequestInit = {}): Promise<T> {
    const who = ROLE_HEADER[role]
    const resp = await fetchImpl(`/api${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        // Local sign-in uses the session cookie and ignores the development identity headers (T028).
        'X-PDM-CSRF': '1',
        'X-PDM-User': who.user,
        'X-PDM-Role': who.role,
        ...(init.headers ?? {}),
      },
    })
    if (!resp.ok) {
      let body: Partial<ApiError> = {}
      try {
        body = (await resp.json()) as ApiError
      } catch {
        /* not an ApiError body */
      }
      const reason = (body.detail as { reason?: string } | null | undefined)?.reason ?? null
      throw new StudioApiError(resp.status, body.code ?? 'http_error', body.message ?? null, reason)
    }
    return (await resp.json()) as T
  }

  function src(): string {
    if (!sourceId) throw new Error('call source() first')
    return encodeURIComponent(sourceId)
  }

  function suggestions(deviceId: string): Promise<DeviceSuggestions> {
    let p = suggestionCache.get(deviceId)
    if (!p) {
      p = call<DeviceSuggestions>(
        `/datasources/${src()}/devices/${encodeURIComponent(deviceId)}/suggestions`,
        'operator',
      )
      suggestionCache.set(deviceId, p)
      p.catch(() => suggestionCache.delete(deviceId))
    }
    return p
  }

  return {
    async source() {
      const all = await call<DataSourceConfig[]>('/datasources', 'operator')
      const first = all[0]
      if (!first) throw new StudioApiError(404, 'no_sources', null, 'no data source is configured')
      sourceId = first.data_source_id
      return first
    },

    async testConnection() {
      const checks = await call<ApiConnectionCheck[]>(`/datasources/${src()}/check`, 'operator')
      return checks as ConnectionCheck[]
    },

    async inspectSchema() {
      const [layout, metadata] = await Promise.all([
        call<SourceLayout>(`/datasources/${src()}/layout`, 'operator'),
        call<SourceMetadata>(`/datasources/${src()}/metadata`, 'operator'),
      ])
      return {
        name: layout.table,
        row_count: layout.row_count ?? null,
        columns: layout.columns.map((c) => ({ name: c.name, type: c.type, role: c.role ?? null })),
        sample_rows: layout.sample_rows,
        metadata,
      }
    },

    async devices() {
      const list = await call<ApiStudioDevice[]>(`/datasources/${src()}/devices`, 'operator')
      deviceCache.clear()
      return list.map((d) => {
        const device: StudioDevice = {
          device_id: d.device_id,
          scenario_id: d.dataset_id ?? '',
          scenario_title: d.label ?? { zh: d.device_id, en: d.device_id },
          keys: d.keys.map((k) => ({ key_name: k.key_name, rows: k.rows ?? null })),
        }
        deviceCache.set(d.device_id, device)
        return device
      })
    },

    async templates(role) {
      if (role === 'admin') return call<TemplateView[]>('/admin/query-templates', 'admin')
      return call<TemplateView[]>('/query-templates', 'operator')
    },

    async signals(deviceId) {
      const s = await suggestions(deviceId)
      return {
        signals: s.signals.map((x) => ({ ...x, device_id: deviceId })),
        mappings: s.mappings,
      }
    },

    async components(deviceId) {
      const s = await suggestions(deviceId)
      return s.components.map((c): StudioComponent => ({
        component_id: c.component_id,
        device_id: deviceId,
        type: c.type,
        name: c.name,
        signal_ids: c.signal_ids ?? [],
      }))
    },

    /**
     * Full-resolution values of every key of the device in source units, from the backend preview.
     * The Studio applies draft conversions on top, so unsaved unit choices preview immediately.
     */
    async preview(deviceId) {
      const s = await suggestions(deviceId)
      if (!s.preview_window) throw new StudioApiError(404, 'no_data', null, 'device has no data')
      const keys = deviceCache.get(deviceId)?.keys.map((k) => k.key_name) ?? []
      const t0 = Date.parse(s.preview_window.start)
      const series: StudioPreview['series'] = {}
      for (let i = 0; i < keys.length; i += PREVIEW_BATCH) {
        const batch = keys.slice(i, i + PREVIEW_BATCH)
        const body: PreviewRequest = {
          mappings: batch.map((key) => ({
            signal_id: key,
            data_source_id: s.data_source_id,
            template_id: 'preview',
            device_id: deviceId,
            key_name: key,
            time_field: 'ts',
            value_field: 'value',
            conversion: null,
            component_id: null,
          })),
          signals: batch.map((key) => ({
            signal_id: key,
            name: { zh: key, en: key },
            quantity: 'OTHER',
            unit: '',
            expected_sampling_s: null,
            valid_min: null,
            valid_max: null,
          })),
          window: s.preview_window,
          max_points: 10,
          include_normalized: true,
        }
        const resp = await call<PreviewResponse>('/signals/preview', 'operator', {
          method: 'POST',
          body: JSON.stringify(body),
        })
        for (const n of resp.normalized) {
          series[n.signal_id] = n.samples
            .filter((x) => x.value !== null && x.value !== undefined)
            .map((x) => [(Date.parse(x.ts) - t0) / 1000, x.value as number])
        }
      }
      return { window_start: s.preview_window.start, window_end: s.preview_window.end, series }
    },

    /** Backend L4 report; speed/torque findings (MISALIGNED, BIAS_SUSPECT) are shown on the torque row. */
    async quality({ mappings, signals, window }) {
      const body: QualityRequest = {
        signal_ids: [],
        mappings,
        signals,
        window,
        lookback_hours: 168,
        pairs: null,
        tolerance_s: null,
      }
      const resp = await call<QualityResponse>('/quality/report', 'operator', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      return resp.reports.map((r) => {
        const pairFlags = resp.alignment
          .filter((a) => a.torque_signal_id === r.signal_id)
          .flatMap((a) => a.flags)
        return {
          ...r,
          flags: [...new Set([...r.flags, ...pairFlags])],
          observation_windows: r.observation_window_count,
        }
      })
    },

    async versions() {
      return call<SignalConfigVersion[]>('/signal-config/versions', 'operator')
    },

    async saveVersion(content, comment, role) {
      const c = content as StudioContent
      const first = c.mappings[0]
      if (!first) throw new StudioApiError(422, 'empty', null, 'nothing to save')
      const body: DeviceConfigChange = { ...c, comment, base_version: null }
      const path = `/signal-config/sources/${encodeURIComponent(first.data_source_id)}/devices/${encodeURIComponent(first.device_id)}`
      suggestionCache.delete(first.device_id)
      return call<SignalConfigVersion>(path, role, { method: 'PUT', body: JSON.stringify(body) })
    },
  }
}

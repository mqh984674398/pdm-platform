/**
 * Monitoring reads and alarm actions over the real backend (T019/T020). The development header
 * provider stands in for login until T028 (DECISIONS D-010); the UI acts as a maintenance engineer.
 */
import type {
  Alarm,
  ApiError,
  Baseline,
  ComponentInstance,
  DegradationHistory,
  Machine,
  MaintenanceEvent,
  MaintenanceWorkflow,
  SignalConfigState,
  TimeWindow,
  VisualizationSeries,
} from './contracts'

export const UI_USER = { user: 'ui-engineer', role: 'engineer' }

export class MonitoringApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: ApiError | null,
  ) {
    super(body?.message.en ?? `request failed (${status})`)
  }
}

type Query = Record<string, string | number | boolean | undefined>

function url(path: string, query?: Query): string {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(query ?? {})) if (v !== undefined) params.set(k, String(v))
  const qs = params.toString()
  return qs ? `${path}?${qs}` : path
}

export function createMonitoringApi(fetchImpl: typeof fetch = fetch.bind(globalThis)) {
  const headers = { 'X-PDM-User': UI_USER.user, 'X-PDM-Role': UI_USER.role }

  async function call<T>(path: string, init: RequestInit = {}, query?: Query): Promise<T> {
    const resp = await fetchImpl(url(path, query), {
      ...init,
      headers: { ...headers, ...(init.body ? { 'Content-Type': 'application/json' } : {}) },
    })
    if (!resp.ok) {
      const body = (await resp.json().catch(() => null)) as ApiError | null
      throw new MonitoringApiError(resp.status, body)
    }
    return (await resp.json()) as T
  }

  return {
    signalConfig: () => call<SignalConfigState>('/api/signal-config'),
    machines: () => call<Machine[]>('/api/machines'),
    components: (machineId: string) =>
      call<ComponentInstance[]>(`/api/machines/${encodeURIComponent(machineId)}/components`),
    extent: (signalId: string) =>
      call<TimeWindow | null>(`/api/timeseries/${encodeURIComponent(signalId)}/extent`),
    series: (
      signalId: string,
      start: number,
      end: number,
      maxPoints: number,
      signal?: AbortSignal,
    ) =>
      call<VisualizationSeries>(
        `/api/timeseries/${encodeURIComponent(signalId)}`,
        { signal },
        {
          start: new Date(start).toISOString(),
          end: new Date(end).toISOString(),
          max_points: maxPoints,
        },
      ),
    /** Full-resolution CSV of a range; returns the file name and content. */
    async exportCsv(signalId: string, start: number, end: number) {
      const resp = await fetchImpl(
        url(`/api/timeseries/${encodeURIComponent(signalId)}/export`, {
          start: new Date(start).toISOString(),
          end: new Date(end).toISOString(),
        }),
        { headers },
      )
      if (!resp.ok) throw new MonitoringApiError(resp.status, await resp.json().catch(() => null))
      const disposition = resp.headers.get('content-disposition') ?? ''
      const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `${signalId}.csv`
      return { name, blob: await resp.blob() }
    },
    baselines: (componentId: string) =>
      call<Baseline[]>(`/api/components/${encodeURIComponent(componentId)}/baselines`),
    degradation: (componentId: string, feature: string, featureRef: string) =>
      call<DegradationHistory>(
        `/api/components/${encodeURIComponent(componentId)}/degradation`,
        {},
        { feature, feature_ref: featureRef },
      ),
    events: (componentId: string) =>
      call<MaintenanceEvent[]>(
        `/api/components/${encodeURIComponent(componentId)}/maintenance-events`,
      ),
    workflows: (componentId: string) =>
      call<MaintenanceWorkflow[]>('/api/maintenance-workflows', {}, { component_id: componentId }),
    alarms: (query: { component_id?: string; status?: string } = {}) =>
      call<Alarm[]>('/api/alarms', {}, query),
    acknowledge: (alarmId: string, comment: string) =>
      call<Alarm>(`/api/alarms/${encodeURIComponent(alarmId)}/acknowledge`, {
        method: 'POST',
        body: JSON.stringify({ comment }),
      }),
    resolve: (alarmId: string, comment: string) =>
      call<Alarm>(`/api/alarms/${encodeURIComponent(alarmId)}/resolve`, {
        method: 'POST',
        body: JSON.stringify({ comment }),
      }),
  }
}

export type MonitoringApi = ReturnType<typeof createMonitoringApi>
export const monitoringApi = createMonitoringApi()

/**
 * Monitoring reads and alarm actions over the real backend (T019/T020). The development header
 * provider stands in for login until T028 (DECISIONS D-010); the UI acts as a maintenance engineer.
 */
import type {
  Alarm,
  ApiError,
  Baseline,
  BaselineVerification,
  FeatureCoverage,
  ComponentHealthReport,
  ComponentInstance,
  ComponentUsage,
  ComponentLifecycle,
  DegradationHistory,
  FleetOverview,
  Machine,
  MaintenanceEvent,
  MaintenanceWorkflow,
  OptimizationReadiness,
  OptimizationRun,
  LlmConfig,
  LlmConfigState,
  LlmHealth,
  AssistantResponse,
  RagDocument,
  FeedbackItem,
  FeedbackIn,
  DeploymentVersion,
  KindSummary,
  PreviewResponse,
  RoleModules,
  SignalConfigState,
  SignalConfigVersion,
  SignalDefinition,
  TimeWindow,
  UserInfo,
  VisualizationSeries,
  ComponentChange,
  MachineCreate,
  MachinePlacement,
  PlantNodeChange,
  PlantTree,
  MachineLayout,
  AlgorithmModels,
  AlgorithmSpec,
  ApiStudioDevice,
  DataSourceConfig,
  DeviceConfigChange,
  DeviceSuggestions,
  CompileResult,
  ConfigContent,
  ConfigRecommendation,
  ManagedSource,
  PipelineResult,
  RunMode,
  RunModeState,
  ManagedSourceBody,
  SourceStructure,
  SourceTestCheck,
  PredictionConfig,
} from './contracts'
import { authHeaders } from './session'

export { UI_USER, devRole } from './session'

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

export function createMonitoringApi(fetchImpl: typeof fetch = (...a) => fetch(...a)) {
  const headers = authHeaders

  async function call<T>(path: string, init: RequestInit = {}, query?: Query): Promise<T> {
    const resp = await fetchImpl(url(path, query), {
      ...init,
      headers: { ...headers(), ...(init.body ? { 'Content-Type': 'application/json' } : {}) },
    })
    if (!resp.ok) {
      const body = (await resp.json().catch(() => null)) as ApiError | null
      throw new MonitoringApiError(resp.status, body)
    }
    return (await resp.json()) as T
  }

  async function remoteVoid(path: string, body: unknown): Promise<void> {
    const resp = await fetchImpl(url(path), {
      method: 'PUT',
      headers: { ...headers(), 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!resp.ok) throw new MonitoringApiError(resp.status, await resp.json().catch(() => null))
  }

  async function remove(path: string, method = 'DELETE'): Promise<void> {
    const resp = await fetchImpl(url(path), { method, headers: headers() })
    if (!resp.ok) throw new MonitoringApiError(resp.status, await resp.json().catch(() => null))
  }

  return {
    runMode: () => call<RunModeState>('/api/run-mode'),
    setRunMode: (mode: RunMode) =>
      call<RunModeState>('/api/run-mode', { method: 'PUT', body: JSON.stringify({ mode }) }),
    signalConfig: () => call<SignalConfigState>('/api/signal-config'),
    signalVersions: () => call<SignalConfigVersion[]>('/api/signal-config/versions'),
    /** Saved mapping of one signal over a window: normalized samples and the chart series (UI-05). */
    signalPreview: (signalId: string, start: string, end: string, maxPoints = 1000) =>
      call<PreviewResponse>(
        `/api/signals/${encodeURIComponent(signalId)}/preview`,
        {},
        { start, end, max_points: maxPoints },
      ),
    saveSignal: (item: SignalDefinition, comment: string, baseVersion: number) =>
      call<SignalConfigVersion>(
        `/api/signal-config/signals/${encodeURIComponent(item.signal_id)}`,
        {
          method: 'PUT',
          body: JSON.stringify({ item, comment, base_version: baseVersion }),
        },
      ),
    // --- prediction configuration versions (D-044..D-046) ---
    algorithmModels: () => call<AlgorithmModels>('/api/algorithm-models'),
    algorithmCatalog: () => call<AlgorithmSpec[]>('/api/algorithm-catalog'),
    recommendedConfig: (componentId: string) =>
      call<ConfigRecommendation>(
        `/api/components/${encodeURIComponent(componentId)}/recommended-config`,
      ),
    configVersions: (componentId: string) =>
      call<PredictionConfig[]>(
        `/api/components/${encodeURIComponent(componentId)}/prediction-configs`,
      ),
    createDraft: (componentId: string, content: ConfigContent | null, copyFrom?: string) =>
      call<PredictionConfig>(
        `/api/components/${encodeURIComponent(componentId)}/prediction-configs`,
        {
          method: 'POST',
          body: JSON.stringify({ content, copy_from_component: copyFrom ?? null }),
        },
      ),
    updateDraft: (configId: string, content: ConfigContent) =>
      call<PredictionConfig>(`/api/prediction-configs/${encodeURIComponent(configId)}`, {
        method: 'PUT',
        body: JSON.stringify(content),
      }),
    deleteDraft: (configId: string) =>
      remove(`/api/prediction-configs/${encodeURIComponent(configId)}`),
    cloneConfig: (configId: string) =>
      call<PredictionConfig>(`/api/prediction-configs/${encodeURIComponent(configId)}/clone`, {
        method: 'POST',
      }),
    compileConfig: (componentId: string, content: ConfigContent) =>
      call<CompileResult>(
        `/api/components/${encodeURIComponent(componentId)}/prediction-configs/compile`,
        { method: 'POST', body: JSON.stringify(content) },
      ),
    validateConfig: (configId: string) =>
      call<PredictionConfig>(`/api/prediction-configs/${encodeURIComponent(configId)}/validate`, {
        method: 'POST',
      }),
    publishConfig: (configId: string, comment: string) =>
      call<PredictionConfig>(`/api/prediction-configs/${encodeURIComponent(configId)}/publish`, {
        method: 'POST',
        body: JSON.stringify({ comment }),
      }),
    activateConfig: (configId: string) =>
      call<PredictionConfig>(`/api/prediction-configs/${encodeURIComponent(configId)}/activate`, {
        method: 'POST',
      }),
    deactivateConfig: (componentId: string) =>
      remove(
        `/api/components/${encodeURIComponent(componentId)}/prediction-configs/deactivate`,
        'POST',
      ),
    adminDataSources: () => call<ManagedSource[]>('/api/admin/datasources'),
    saveDataSource: (b: ManagedSourceBody) =>
      call<ManagedSource>(`/api/admin/datasources/${encodeURIComponent(b.data_source_id)}`, {
        method: 'PUT',
        body: JSON.stringify(b),
      }),
    testDataSource: (id: string) =>
      call<SourceTestCheck[]>(`/api/admin/datasources/${encodeURIComponent(id)}/test`, {
        method: 'POST',
        body: '{}',
      }),
    dataSourceStructure: (id: string, stable?: string) =>
      call<SourceStructure>(
        `/api/admin/datasources/${encodeURIComponent(id)}/structure${
          stable ? `?stable=${encodeURIComponent(stable)}` : ''
        }`,
      ),
    deleteDataSource: (id: string) => remove(`/api/admin/datasources/${encodeURIComponent(id)}`),
    // --- readiness of a component: installation, feature windows, healthy reference ---
    lifecycles: (componentId: string) =>
      call<ComponentLifecycle[]>(`/api/components/${encodeURIComponent(componentId)}/lifecycles`),
    installComponent: (componentId: string, installedAt: string, comment: string) =>
      call<ComponentLifecycle>(`/api/components/${encodeURIComponent(componentId)}/lifecycles`, {
        method: 'POST',
        body: JSON.stringify({ installed_at: installedAt, comment }),
      }),
    runPipeline: (
      machineId: string,
      provisional = false,
      range: { since?: string; until?: string } = {},
    ) =>
      call<PipelineResult>('/api/pipeline/run', {
        method: 'POST',
        body: JSON.stringify({ machine_id: machineId, provisional, ...range }),
      }),
    optimizationReadiness: () => call<OptimizationReadiness>('/api/optimization/readiness'),
    // --- data sources and signal mappings (step 2 of the configuration workflow) ---
    dataSources: () => call<DataSourceConfig[]>('/api/datasources'),
    sourceDevices: (sourceId: string) =>
      call<ApiStudioDevice[]>(`/api/datasources/${encodeURIComponent(sourceId)}/devices`),
    deviceSuggestions: (sourceId: string, deviceId: string) =>
      call<DeviceSuggestions>(
        `/api/datasources/${encodeURIComponent(sourceId)}/devices/${encodeURIComponent(deviceId)}/suggestions`,
      ),
    replaceDevice: (sourceId: string, deviceId: string, change: DeviceConfigChange) =>
      call<SignalConfigVersion>(
        `/api/signal-config/sources/${encodeURIComponent(sourceId)}/devices/${encodeURIComponent(deviceId)}`,
        { method: 'PUT', body: JSON.stringify(change) },
      ),
    users: () => call<UserInfo[]>('/api/auth/users'),
    createUser: (u: { user_id: string; display_name: string; role: string; password: string }) =>
      call<UserInfo>('/api/auth/users', { method: 'POST', body: JSON.stringify(u) }),
    changeUser: (
      userId: string,
      ch: { display_name?: string; role?: string; active?: boolean; password?: string },
    ) =>
      call<UserInfo>(`/api/auth/users/${encodeURIComponent(userId)}`, {
        method: 'PUT',
        body: JSON.stringify(ch),
      }),
    async deleteUser(userId: string) {
      const resp = await fetchImpl(`/api/auth/users/${encodeURIComponent(userId)}`, {
        method: 'DELETE',
        headers: headers(),
      })
      if (!resp.ok) throw new MonitoringApiError(resp.status, await resp.json().catch(() => null))
    },
    roleModules: () => call<RoleModules[]>('/api/auth/role-modules'),
    setRoleModules: (role: string, modules: string[]) =>
      call<RoleModules>(`/api/auth/role-modules/${encodeURIComponent(role)}`, {
        method: 'PUT',
        body: JSON.stringify({ modules }),
      }),
    plantTree: () => call<PlantTree>('/api/plant-tree'),
    machineLayout: () => call<MachineLayout[]>('/api/machine-layout'),
    setMachineOrder: (machineIds: string[]) =>
      remoteVoid('/api/machine-layout/order', { machine_ids: machineIds }),
    setMachineBackground: (machineId: string, image: string | null) =>
      remoteVoid(`/api/machine-layout/${encodeURIComponent(machineId)}/background`, { image }),
    putPlantNode: (n: PlantNodeChange) =>
      call<PlantTree>(`/api/plant-nodes/${encodeURIComponent(n.node_id)}`, {
        method: 'PUT',
        body: JSON.stringify(n),
      }),
    deletePlantNode: (nodeId: string) => remove(`/api/plant-nodes/${encodeURIComponent(nodeId)}`),
    createMachine: (m: MachineCreate) =>
      call<Machine>('/api/plant-machines', { method: 'POST', body: JSON.stringify(m) }),
    placeMachine: (machineId: string, p: MachinePlacement) =>
      call<Machine>(`/api/plant-machines/${encodeURIComponent(machineId)}`, {
        method: 'PUT',
        body: JSON.stringify(p),
      }),
    deleteMachine: (machineId: string) =>
      remove(`/api/plant-machines/${encodeURIComponent(machineId)}`),
    putComponent: (machineId: string, c: ComponentChange) =>
      call<ComponentInstance>(
        `/api/plant-machines/${encodeURIComponent(machineId)}/components/${encodeURIComponent(c.component_id)}`,
        { method: 'PUT', body: JSON.stringify(c) },
      ),
    componentUsage: (componentId: string) =>
      call<ComponentUsage>(`/api/plant-components/${encodeURIComponent(componentId)}/usage`),
    deleteComponent: (componentId: string, cascade = false) =>
      remove(
        `/api/plant-components/${encodeURIComponent(componentId)}${cascade ? '?cascade=true' : ''}`,
      ),
    fleet: () => call<FleetOverview>('/api/fleet'),
    health: (componentId: string) =>
      call<ComponentHealthReport>(`/api/components/${encodeURIComponent(componentId)}/health`),
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
        { headers: headers() },
      )
      if (!resp.ok) throw new MonitoringApiError(resp.status, await resp.json().catch(() => null))
      const disposition = resp.headers.get('content-disposition') ?? ''
      const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `${signalId}.csv`
      return { name, blob: await resp.blob() }
    },
    featureCoverage: (componentId: string) =>
      call<FeatureCoverage[]>(
        `/api/components/${encodeURIComponent(componentId)}/feature-coverage`,
      ),
    verifyBaseline: (body: BaselineVerification) =>
      call<Baseline>('/api/baselines/verified', { method: 'POST', body: JSON.stringify(body) }),
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
    llmSettings: () => call<LlmConfigState>('/api/llm/settings'),
    saveLlmSettings: (cfg: LlmConfig) =>
      call<LlmConfigState>('/api/llm/settings', { method: 'PUT', body: JSON.stringify(cfg) }),
    llmHealth: () => call<LlmHealth>('/api/llm/health'),
    documents: () => call<RagDocument[]>('/api/llm/documents'),
    addDocument: (doc: { title: string; text: string; min_role: string; source?: string }) =>
      call<RagDocument>('/api/llm/documents', { method: 'POST', body: JSON.stringify(doc) }),
    approveDocument: (docId: string) =>
      call<RagDocument>(`/api/llm/documents/${encodeURIComponent(docId)}/approve`, {
        method: 'POST',
      }),
    feedback: (fb: FeedbackIn) =>
      call<FeedbackItem>('/api/feedback', { method: 'POST', body: JSON.stringify(fb) }),
    cancelAsk: (requestId: string) =>
      fetchImpl(`/api/llm/ask/${encodeURIComponent(requestId)}/cancel`, {
        method: 'POST',
        headers: headers(),
      }),
    /** Stream the assistant's events (NDJSON); calls onEvent for each, resolves when the stream ends. */
    async askStream(
      body: { question: string; component_id?: string; request_id: string },
      onEvent: (ev: AskEvent) => void,
      signal?: AbortSignal,
    ) {
      const resp = await fetchImpl('/api/llm/ask/stream', {
        method: 'POST',
        headers: { ...headers(), 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal,
      })
      if (!resp.ok || !resp.body) {
        throw new MonitoringApiError(resp.status, await resp.json().catch(() => null))
      }
      const reader = resp.body.getReader()
      const dec = new TextDecoder()
      let buf = ''
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        let i
        while ((i = buf.indexOf('\n')) >= 0) {
          const line = buf.slice(0, i).trim()
          buf = buf.slice(i + 1)
          if (line) onEvent(JSON.parse(line) as AskEvent)
        }
      }
    },
    registryKinds: () => call<KindSummary[]>('/api/registry/kinds'),
    registryVersions: (kind: string) =>
      call<DeploymentVersion[]>('/api/registry/versions', {}, { kind }),
    proposeConfig: (candidateId: string, comment: string) =>
      call<DeploymentVersion>('/api/registry/decision-config/candidates', {
        method: 'POST',
        body: JSON.stringify({ candidate_id: candidateId, comment }),
      }),
    promote: (versionId: string, comment: string) =>
      call<DeploymentVersion>(`/api/registry/versions/${encodeURIComponent(versionId)}/promote`, {
        method: 'POST',
        body: JSON.stringify({ comment }),
      }),
    reject: (versionId: string, comment: string) =>
      call<DeploymentVersion>(`/api/registry/versions/${encodeURIComponent(versionId)}/reject`, {
        method: 'POST',
        body: JSON.stringify({ comment }),
      }),
    rollback: (kind: string, comment: string) =>
      call<DeploymentVersion>('/api/registry/rollback', {
        method: 'POST',
        body: JSON.stringify({ kind, comment }),
      }),
    latestOptimization: () => call<OptimizationRun>('/api/optimization/runs/latest'),
    runOptimization: (candidates = 12, seed = 0) =>
      call<OptimizationRun>('/api/optimization/runs', {
        method: 'POST',
        body: JSON.stringify({ candidates, seed }),
      }),
    resolve: (alarmId: string, comment: string) =>
      call<Alarm>(`/api/alarms/${encodeURIComponent(alarmId)}/resolve`, {
        method: 'POST',
        body: JSON.stringify({ comment }),
      }),
  }
}

export type AskEvent =
  | { type: 'context'; citations: unknown[]; health_state: string | null }
  | { type: 'token'; text: string }
  | { type: 'answer'; response: AssistantResponse }
  | { type: 'error'; code: string; message: string }

export type MonitoringApi = ReturnType<typeof createMonitoringApi>
export const monitoringApi = createMonitoringApi()

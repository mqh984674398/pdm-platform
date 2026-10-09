/**
 * Fleet view model for the dashboard demo. Until the backend health APIs exist (T020), data comes
 * from the simulated fixture Data/fixtures/demo_fleet.json. Shapes reuse generated contract types.
 */
import type {
  ComponentLifecycle,
  ComponentType,
  HealthState,
  LocalizedText,
  MaintenanceEvent,
  SignalDefinition,
} from './contracts'

export interface TrendSeries {
  signal_id: string
  unit: string
  points: [string, number][]
}

export interface FleetComponent {
  component_id: string
  source_component_id: string | null
  type: ComponentType
  name: LocalizedText
  drive_chain_id: string | null
  health: HealthState
  reason: LocalizedText
  lifecycle_id: string | null
  lifecycles: ComponentLifecycle[]
  maintenance: MaintenanceEvent[]
  signals: SignalDefinition[]
  trend_regime?: string
  trend: TrendSeries[]
}

export interface FleetMachine {
  machine_id: string
  name: LocalizedText
  scenario_id: string
  scenario_title: LocalizedText
  snapshot_at: string
  components: FleetComponent[]
}

export interface Fleet {
  is_simulated: boolean
  health_basis: LocalizedText
  machines: FleetMachine[]
}

let cache: Promise<Fleet> | null = null

export function getFleet(): Promise<Fleet> {
  cache ??= import('@data/fixtures/demo_fleet.json').then((m) => m.default as unknown as Fleet)
  return cache
}

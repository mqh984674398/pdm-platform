/**
 * Fleet health from the backend (T020): GET /api/fleet computes each component's health from stored
 * features, verified references and the rules. Shapes are the generated contract types.
 */
import type { components } from './generated'
import { monitoringApi } from './monitoring'

type S = components['schemas']
export type Fleet = S['FleetOverview']
export type FleetMachine = S['FleetMachine']
export type FleetComponent = S['FleetComponent']
export type HealthTrend = S['HealthTrend']
export type ComponentHealthReport = S['ComponentHealthReport']

/** The overview is computed by the backend on every request; nothing is kept here, so a deleted or changed
 *  machine or component never lingers on screen. */
export function getFleet(): Promise<Fleet> {
  return monitoringApi.fleet()
}

export function refreshFleet(): Promise<Fleet> {
  return getFleet()
}

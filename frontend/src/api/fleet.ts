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

let cache: Promise<Fleet> | null = null

export function getFleet(): Promise<Fleet> {
  cache ??= monitoringApi.fleet().catch((e) => {
    cache = null // a later visit retries
    throw e
  })
  return cache
}

/** Forget the cached overview, e.g. after an alarm was acknowledged or resolved. */
export function refreshFleet(): Promise<Fleet> {
  cache = null
  return getFleet()
}

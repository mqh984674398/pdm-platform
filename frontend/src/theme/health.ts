import type { HealthState } from '@/api/contracts'

export const HEALTH_STATES: readonly HealthState[] = [
  'NORMAL',
  'WATCH',
  'WARNING',
  'CRITICAL',
  'UNKNOWN',
] as const

/** Severity order for sorting and aggregation. UNKNOWN is not a severity; it sorts last. */
export const HEALTH_RANK: Record<HealthState, number> = {
  CRITICAL: 0,
  WARNING: 1,
  WATCH: 2,
  NORMAL: 3,
  UNKNOWN: 4,
}

export function healthVar(state: HealthState, soft = false): string {
  return `var(--health-${state.toLowerCase()}${soft ? '-soft' : ''})`
}

/** Worst known state; UNKNOWN only when nothing is known. */
export function worstHealth(states: HealthState[]): HealthState {
  const known = states.filter((s) => s !== 'UNKNOWN')
  if (known.length === 0) return 'UNKNOWN'
  return known.reduce((a, b) => (HEALTH_RANK[a] <= HEALTH_RANK[b] ? a : b))
}

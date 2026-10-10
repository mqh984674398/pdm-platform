/** Chart overlays from monitoring records (T019). */
import type { Alarm, Baseline, DegradationHistory, MaintenanceEvent } from '@/api/contracts'
import type { ChartBand, ChartMarker, ChartPeriod } from './TimeSeriesChart.vue'

export function eventMarkers(
  events: MaintenanceEvent[],
  label: (type: string) => string,
): ChartMarker[] {
  return events.map((e) => ({ ts: Date.parse(e.performed_at), label: label(e.type) }))
}

/** An alarm covers raised_at until resolution, else until its last evaluated window or ``now``. */
export function alarmPeriods(
  alarms: Alarm[],
  now: number,
  label: (sev: string) => string,
): ChartPeriod[] {
  return alarms.map((a) => {
    const from = Date.parse(a.raised_at)
    const end = a.resolved_at ?? (a.condition_active ? null : a.last_window_end)
    return {
      from,
      to: end ? Date.parse(end) : Math.max(now, from),
      severity: a.severity,
      label: label(a.severity),
    }
  })
}

/** Verified healthy reference as mean ± 2σ over each lifecycle segment that has one. */
export function referenceBands(
  history: DegradationHistory,
  baselines: Baseline[],
  feature: string,
  label: string,
): ChartBand[] {
  const byId = new Map(baselines.map((b) => [b.baseline_id, b]))
  return history.segments.flatMap((s) => {
    const ref = s.reference_baseline_id ? byId.get(s.reference_baseline_id) : undefined
    const st = ref?.stats[feature]
    if (!st || !s.points.length) return []
    return [
      {
        name: label,
        from: Date.parse(s.points[0]!.window.start),
        to: Date.parse(s.points[s.points.length - 1]!.window.end),
        lower: st.mean - 2 * st.std,
        upper: st.mean + 2 * st.std,
      },
    ]
  })
}

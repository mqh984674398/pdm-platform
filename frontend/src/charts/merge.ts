/** Pure helpers for time-series charts (T019). Times are epoch milliseconds. */
import type { VisualizationSeries } from '@/api/contracts'

export type Point = [number, number | null]
export interface Range {
  start: number
  end: number
}

export function toPoints(s: VisualizationSeries): Point[] {
  return s.points.map((p) => [Date.parse(p.ts), p.value ?? null])
}

/**
 * The overview series outside the zoomed range plus the detail series inside it, so the chart keeps
 * its full context while the visible part is shown at the finer resolution. A null point separates
 * the parts so no line is drawn across a seam.
 */
export function mergeDetail(
  overview: Point[],
  detail: Point[] | null,
  range: Range | null,
): Point[] {
  if (!detail || !range) return overview
  const before = overview.filter((p) => p[0] < range.start)
  const after = overview.filter((p) => p[0] > range.end)
  const seam = (t: number): Point => [t, null]
  return [
    ...before,
    ...(before.length ? [seam(range.start)] : []),
    ...detail,
    ...(after.length ? [seam(range.end)] : []),
    ...after,
  ]
}

/** Whether a zoom changed enough to fetch again (ignores sub-percent jitter of the slider). */
export function rangeChanged(a: Range | null, b: Range, full: Range): boolean {
  if (!a) return true
  const span = full.end - full.start || 1
  return Math.abs(a.start - b.start) / span > 0.005 || Math.abs(a.end - b.end) / span > 0.005
}

export function isFull(r: Range, full: Range): boolean {
  const span = full.end - full.start || 1
  return (r.start - full.start) / span < 0.002 && (full.end - r.end) / span < 0.002
}

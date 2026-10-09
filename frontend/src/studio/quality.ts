/**
 * Demo data-quality summary for the studio preview. It mirrors the DataQualityReport contract so the
 * screen needs no change when the L2 quality service (T010) replaces this function.
 */
import type { DataQualityReport, QualityFlag } from '@/api/contracts'

/** Samples further apart than this belong to different observation windows, not missing data. */
export const WINDOW_BREAK_S = 60

export interface QualitySummary extends DataQualityReport {
  flags: QualityFlag[]
  observation_windows: number
}

function median(xs: number[]): number | null {
  if (!xs.length) return null
  const s = [...xs].sort((a, b) => a - b)
  const m = Math.floor(s.length / 2)
  return s.length % 2 ? s[m]! : (s[m - 1]! + s[m]!) / 2
}

export function summarizeQuality(
  signalId: string,
  points: [number, number][],
  window: { start: string; end: string },
  expectedSamplingS: number | null | undefined,
): QualitySummary {
  const seen = new Set<number>()
  let duplicates = 0
  let outOfOrder = 0
  let maxT = -Infinity
  for (const [t] of points) {
    if (seen.has(t)) duplicates++
    else if (t < maxT) outOfOrder++
    seen.add(t)
    maxT = Math.max(maxT, t)
  }
  const ts = [...seen].sort((a, b) => a - b)
  const inWindow: number[] = []
  const spans: [number, number, number][] = [] // [first, last, unique samples] per window
  for (let i = 0; i < ts.length; i++) {
    const d = i ? ts[i]! - ts[i - 1]! : Infinity
    if (d > WINDOW_BREAK_S) spans.push([ts[i]!, ts[i]!, 1])
    else {
      inWindow.push(d)
      const w = spans[spans.length - 1]!
      w[1] = ts[i]!
      w[2]++
    }
  }
  let missing = 0
  let gaps = 0
  let jitter: number | null = null
  if (expectedSamplingS) {
    // Count against each window's span so timestamp jitter does not read as missing samples.
    for (const [first, last, n] of spans) {
      missing += Math.max(0, Math.round((last - first) / expectedSamplingS) + 1 - n)
    }
    gaps = inWindow.filter((d) => d >= 2.5 * expectedSamplingS).length
    const regular = inWindow.filter((d) => d < 1.5 * expectedSamplingS)
    if (regular.length > 1) {
      const mean = regular.reduce((a, b) => a + b, 0) / regular.length
      jitter = Math.sqrt(regular.reduce((a, d) => a + (d - mean) ** 2, 0) / regular.length)
    }
  }
  // A strictly positive signal whose magnitude jumps 100x has changed unit (e.g. s -> ms).
  const values = points.map(([, v]) => v)
  let unitSuspect = false
  if (values.length > 1 && values.every((v) => v > 0)) {
    for (let i = 1; i < values.length && !unitSuspect; i++) {
      const r = values[i]! / values[i - 1]!
      unitSuspect = r >= 100 || r <= 0.01
    }
  }
  const expected = expectedSamplingS ? ts.length + missing : ts.length
  const flags: QualityFlag[] = []
  if (expected && missing / expected > 0.01) flags.push('MISSING')
  if (duplicates) flags.push('DUPLICATE')
  if (outOfOrder) flags.push('OUT_OF_ORDER')
  if (jitter !== null && expectedSamplingS && jitter > 0.05 * expectedSamplingS)
    flags.push('JITTER')
  if (gaps) flags.push('GAP')
  if (unitSuspect) flags.push('UNIT_SUSPECT')
  return {
    signal_id: signalId,
    window,
    sample_count: points.length,
    missing_count: missing,
    duplicate_count: duplicates,
    out_of_order_count: outOfOrder,
    gap_count: gaps,
    median_interval_s: median(inWindow),
    interval_jitter_s: jitter,
    unit_suspect: unitSuspect,
    is_simulated: true,
    flags,
    observation_windows: spans.length,
  }
}

/** Split a series into observation windows (by time), each sorted and de-duplicated for display. */
export function observationWindows(points: [number, number][]): [number, number][][] {
  const byT = new Map<number, number>()
  for (const [t, v] of points) if (!byT.has(t)) byT.set(t, v)
  const sorted = [...byT.entries()].sort((a, b) => a[0] - b[0])
  const out: [number, number][][] = []
  for (const p of sorted) {
    const cur = out[out.length - 1]
    if (cur && p[0] - cur[cur.length - 1]![0] <= WINDOW_BREAK_S) cur.push(p)
    else out.push([p])
  }
  return out
}

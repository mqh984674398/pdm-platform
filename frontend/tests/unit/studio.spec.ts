import { describe, expect, it } from 'vitest'
import fixtureJson from '@data/fixtures/studio_demo.json'
import { observationWindows, summarizeQuality } from '@/studio/quality'
import { convert, suggestedScale } from '@/studio/units'

const fixture = fixtureJson as unknown as {
  previews: Record<string, { series: Record<string, [number, number][]> }>
}
const W = { start: '2026-02-02T00:00:00Z', end: '2026-02-03T00:00:00Z' }
const regular = (n: number, step = 2, t0 = 0): [number, number][] =>
  Array.from({ length: n }, (_, i) => [t0 + i * step, 1 + (i % 3)])

describe('quality summary', () => {
  it('reports a clean regular series', () => {
    const q = summarizeQuality('x', [...regular(60), ...regular(60, 2, 3600)], W, 2)
    expect(q.flags).toEqual([])
    expect(q.observation_windows).toBe(2)
    expect(q.median_interval_s).toBe(2)
  })
  it('detects missing samples, duplicates, and out-of-order rows', () => {
    const pts = regular(60).filter((_, i) => i % 5 !== 2)
    expect(summarizeQuality('x', pts, W, 2).flags).toContain('MISSING')
    const dup: [number, number][] = [...regular(10), [18, 1]]
    expect(summarizeQuality('x', dup, W, 2).duplicate_count).toBe(1)
    const ooo: [number, number][] = [
      [0, 1],
      [4, 1],
      [2, 1],
      [6, 1],
    ]
    expect(summarizeQuality('x', ooo, W, 2).out_of_order_count).toBe(1)
  })
  it('does not mistake timestamp jitter for missing samples', () => {
    const jittered = regular(60).map(
      ([t, v], i) => [t + (i % 2 ? 0.4 : -0.4), v] as [number, number],
    )
    const q = summarizeQuality('x', jittered, W, 2)
    expect(q.flags).toContain('JITTER')
    expect(q.flags).not.toContain('MISSING')
  })
  it('flags a 1000x unit change in a positive signal', () => {
    const pts: [number, number][] = [
      [0, 0.08],
      [10, 0.09],
      [20, 85],
      [30, 80],
    ]
    expect(summarizeQuality('x', pts, W, null).unit_suspect).toBe(true)
  })
  it('finds the faults built into the simulated scenarios', () => {
    const flags = (device: string, key: string, sampling: number | null) =>
      summarizeQuality(key, fixture.previews[device]!.series[key]!, W, sampling).flags
    expect(flags('SIM-S01', 'M01_BS1_TRQ', 2)).toEqual([])
    expect(flags('SIM-S13', 'M01_BS1_TRQ', 2)).toContain('MISSING')
    expect(flags('SIM-S13', 'M01_CY1_EXT', null)).toContain('DUPLICATE')
    expect(flags('SIM-S14', 'M01_BS1_SPD', 2)).toEqual(['JITTER'])
    expect(flags('SIM-S14', 'M01_LM1_SPD', 2)).toContain('OUT_OF_ORDER')
    expect(flags('SIM-S16', 'M01_VC1_REL', null)).toContain('UNIT_SUSPECT')
  })
  it('splits observation windows and drops duplicate timestamps for display', () => {
    expect(
      observationWindows([
        [0, 1],
        [2, 1],
        [2, 5],
        [500, 1],
      ]),
    ).toEqual([
      [
        [0, 1],
        [2, 1],
      ],
      [[500, 1]],
    ])
  })
})

describe('units', () => {
  it('suggests known scales and leaves equipment-specific ones to the user', () => {
    expect(suggestedScale('mm/s', 'm/s')).toBe(0.001)
    expect(suggestedScale('%rated', 'N*m')).toBeNull()
    expect(convert(400, { scale: 0.001, offset: 0 })).toBeCloseTo(0.4)
  })
})

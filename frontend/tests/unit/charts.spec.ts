import { describe, expect, it } from 'vitest'
import { isFull, mergeDetail, rangeChanged, toPoints, type Point } from '@/charts/merge'
import { alarmPeriods, eventMarkers, referenceBands } from '@/charts/overlays'
import type { Alarm, Baseline, DegradationHistory, MaintenanceEvent } from '@/api/contracts'

const full = { start: 0, end: 1000 }

describe('merge helpers', () => {
  it('converts series points to epoch ms with gaps as null', () => {
    const pts = toPoints({
      points: [
        { ts: '1970-01-01T00:00:01Z', value: 2 },
        { ts: '1970-01-01T00:00:02Z', value: null },
      ],
    } as never)
    expect(pts).toEqual([
      [1000, 2],
      [2000, null],
    ])
  })

  it('splices detail into the overview with null seams', () => {
    const overview: Point[] = [0, 100, 200, 300, 400].map((t) => [t, 1])
    const detail: Point[] = [
      [150, 5],
      [250, 6],
    ]
    const merged = mergeDetail(overview, detail, { start: 150, end: 250 })
    expect(merged).toEqual([
      [0, 1],
      [100, 1],
      [150, null],
      [150, 5],
      [250, 6],
      [250, null],
      [300, 1],
      [400, 1],
    ])
    expect(mergeDetail(overview, null, null)).toBe(overview)
  })

  it('ignores slider jitter and recognizes the full range', () => {
    expect(rangeChanged(null, full, full)).toBe(true)
    expect(rangeChanged({ start: 100, end: 900 }, { start: 101, end: 900 }, full)).toBe(false)
    expect(rangeChanged({ start: 100, end: 900 }, { start: 200, end: 900 }, full)).toBe(true)
    expect(isFull({ start: 1, end: 999 }, full)).toBe(true)
    expect(isFull({ start: 100, end: 999 }, full)).toBe(false)
  })
})

describe('overlays', () => {
  it('labels maintenance events', () => {
    const ev = [{ performed_at: '1970-01-01T00:00:01Z', type: 'LUBRICATION' }] as MaintenanceEvent[]
    expect(eventMarkers(ev, (k) => `x:${k}`)).toEqual([{ ts: 1000, label: 'x:LUBRICATION' }])
  })

  it('ends an alarm period at resolution, clearance, or now', () => {
    const base = { severity: 'WARNING', raised_at: '1970-01-01T00:00:01Z' }
    const alarms = [
      {
        ...base,
        resolved_at: '1970-01-01T00:00:05Z',
        condition_active: true,
        last_window_end: null,
      },
      {
        ...base,
        resolved_at: null,
        condition_active: false,
        last_window_end: '1970-01-01T00:00:03Z',
      },
      {
        ...base,
        resolved_at: null,
        condition_active: true,
        last_window_end: '1970-01-01T00:00:03Z',
      },
    ] as unknown as Alarm[]
    expect(alarmPeriods(alarms, 9000, (s) => s).map((p) => p.to)).toEqual([5000, 3000, 9000])
  })

  it('draws the verified reference as mean ±2σ only where a segment has one', () => {
    const history = {
      segments: [
        {
          reference_baseline_id: 'BL-1',
          points: [
            { window: { start: '1970-01-01T00:00:00Z', end: '1970-01-01T00:00:01Z' } },
            { window: { start: '1970-01-01T00:00:01Z', end: '1970-01-01T00:00:02Z' } },
          ],
        },
        { reference_baseline_id: null, points: [] },
      ],
    } as unknown as DegradationHistory
    const baselines = [
      { baseline_id: 'BL-1', stats: { f: { mean: 10, std: 1 } } },
    ] as unknown as Baseline[]
    expect(referenceBands(history, baselines, 'f', 'ref')).toEqual([
      { name: 'ref', from: 0, to: 2000, lower: 8, upper: 12 },
    ])
    expect(referenceBands(history, baselines, 'other', 'ref')).toEqual([])
  })
})

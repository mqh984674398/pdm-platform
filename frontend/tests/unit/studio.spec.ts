import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import fixtureJson from '@data/fixtures/studio_demo.json'
import { createMockStudioApi, type StudioFixture } from '@/api/studio'
import { i18n, setLocale } from '@/i18n'
import { observationWindows, summarizeQuality } from '@/studio/quality'
import { STEPS, useStudioStore } from '@/studio/store'
import { convert, suggestedScale } from '@/studio/units'
import DataSourceStudioView from '@/views/DataSourceStudioView.vue'

const fixture = fixtureJson as unknown as StudioFixture
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

describe('mock studio API', () => {
  it('returns template SQL only to administrators', async () => {
    const api = createMockStudioApi(fixture)
    expect((await api.templates('operator')).every((t) => t.sql === undefined)).toBe(true)
    expect((await api.templates('admin')).every((t) => t.sql?.startsWith('SELECT'))).toBe(true)
  })
  it('appends immutable versions with a content hash', async () => {
    const api = createMockStudioApi(fixture, () => new Date('2026-10-09T00:00:00Z'))
    const a = await api.saveVersion({ x: 1 }, 'first', 'operator')
    const b = await api.saveVersion({ x: 1 }, 'same content', 'admin')
    expect([a.version, b.version]).toEqual([3, 4])
    expect(a.content_hash).toBe(b.content_hash)
    expect(a.content_hash).toMatch(/^sha256:[0-9a-f]{64}$/)
    expect((await api.versions()).map((v) => v.version)).toEqual([4, 3, 2, 1])
  })
})

describe('studio workflow', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('walks all 12 steps and produces contract-shaped configuration', async () => {
    const s = useStudioStore()
    await s.init(createMockStudioApi(fixture))
    expect(STEPS).toHaveLength(12)
    expect(s.canAdvance).toBe(false)
    await s.testConnection()
    s.next()
    s.next()
    await s.selectDevice('SIM-S13')
    s.next()
    s.templateId = 'telemetry-by-key-range'
    for (let i = 0; i < 8; i++) {
      expect(s.canAdvance, STEPS[s.step]).toBe(true)
      s.next()
    }
    expect(STEPS[s.step]).toBe('version')
    const { mappings, groups, visualizations } = s.content
    expect(mappings.map((m) => m.key_name).sort()).toEqual([
      'M01_BS1_SPD',
      'M01_BS1_TRQ',
      'M01_CY1_EXT',
      'M01_CY1_RET',
    ])
    expect(mappings.every((m) => m.time_field === 'ts' && m.value_field === 'value_double')).toBe(
      true,
    )
    expect(groups.map((g) => g.component_id)).toEqual(['M01-BS1', 'M01-CY1'])
    expect(visualizations.map((v) => v.chart)).toEqual(['LINE', 'CYCLE_DURATION'])
    s.comment = 'demo'
    await s.save()
    expect(s.saved?.version).toBe(3)
    expect(s.stepComplete.version).toBe(true)
  })

  it('blocks the units step until an unknown scale is entered', async () => {
    const s = useStudioStore()
    await s.init(createMockStudioApi(fixture))
    await s.testConnection()
    await s.selectDevice('SIM-S01')
    s.drafts.M01_BS1_TRQ!.scale = null
    expect(s.stepComplete.units).toBe(false)
    s.drafts.M01_BS1_TRQ!.scale = 0.1
    expect(s.stepComplete.units).toBe(true)
  })

  it('renders the first step with the simulated badge', async () => {
    setLocale('en-US')
    const pinia = createPinia()
    setActivePinia(pinia)
    await useStudioStore().init(createMockStudioApi(fixture))
    const w = mount(DataSourceStudioView, { global: { plugins: [i18n, pinia] } })
    await flushPromises()
    await flushPromises()
    expect(w.find('[data-testid="step-title"]').text()).toBe('Connection')
    expect(w.find('[data-simulated="true"]').exists()).toBe(true)
    expect(w.findAll('[data-step]')).toHaveLength(12)
    setLocale('zh-CN')
  })
})

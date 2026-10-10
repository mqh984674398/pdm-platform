import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { i18n, setLocale } from '@/i18n'
import OptimizationView from '@/views/OptimizationView.vue'

const metrics = (within: number, over: number, under: number) => ({
  windows: 100,
  within,
  over,
  under,
  ratio: within / 100,
  cases: [{ case_id: 'GC-S03-01', component_id: 'A03-BS1', windows: 100, within, over, under }],
})
const cand = (id: string, path: string, within: number, under: number) => ({
  candidate_id: id,
  path,
  changes: path === 'A' ? { cusum_h: 16 } : { aging_max_rate: 0.25 },
  rules_version: 'pdm-rules@1.0.0',
  policy_version: 'aging-grading@1.0.0',
  safety_unchanged: true,
  metrics: metrics(within, 100 - within - under, under),
})
const RUN = {
  run_id: 'OPT-1',
  started_by: 'ui-engineer',
  started_at: '2026-10-09T00:00:00Z',
  seed: 0,
  suite: 'golden-cases (SIMULATED demo fleet)',
  champion: { ...cand('champion', 'champion', 80, 5), changes: {} },
  candidates: [cand('A01', 'A', 85, 5), cand('B02', 'B', 70, 3)],
  recommended: 'A01',
  is_simulated: true,
}

afterEach(() => vi.unstubAllGlobals())

describe('optimization comparison', () => {
  it('shows nothing until a run, then champion vs candidates with the recommendation', async () => {
    const calls: string[] = []
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? 'GET'} ${url}`)
      if (init?.method === 'POST') return new Response(JSON.stringify(RUN), { status: 200 })
      return new Response(
        JSON.stringify({
          code: 'no_optimization_run',
          message: { zh: '还没有', en: 'No optimization run yet.' },
        }),
        { status: 404 },
      )
    })
    setLocale('en-US')
    const w = mount(OptimizationView, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(w.find('[data-testid="opt-none"]').exists()).toBe(true)
    expect(w.find('[role="alert"]').exists()).toBe(false)

    await w.find('[data-testid="opt-run"]').trigger('click')
    await flushPromises()
    expect(calls).toEqual(['GET /api/optimization/runs/latest', 'POST /api/optimization/runs'])
    const rows = w.findAll('[data-testid="opt-table"] tbody tr')
    expect(rows.map((r) => r.attributes('data-row'))).toEqual(['champion', 'A01', 'B02'])
    expect(rows[1]!.text()).toContain('Recommended')
    expect(rows[1]!.text()).toContain('+5')
    expect(rows[2]!.text()).toContain('-10')
    expect(w.find('[data-testid="opt-verdict"]').text()).toContain('A01')
    // the recommended candidate's cases are shown against the champion
    expect(w.find('[data-testid="opt-cases"]').text()).toContain('GC-S03-01')
  })
})

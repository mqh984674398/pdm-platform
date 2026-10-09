import { describe, expect, it } from 'vitest'
import { createHttpStudioApi, StudioApiError } from '@/api/studioHttp'

interface Call {
  url: string
  method: string
  headers: Record<string, string>
  body: unknown
}

/** A fake backend: routes by "METHOD path" and records every request. */
function fakeBackend(routes: Record<string, (body: unknown) => [number, unknown]>) {
  const calls: Call[] = []
  const impl = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input)
    const method = init.method ?? 'GET'
    const body = init.body ? JSON.parse(String(init.body)) : undefined
    calls.push({ url, method, headers: init.headers as Record<string, string>, body })
    const route = routes[`${method} ${url}`]
    const [status, payload] = route ? route(body) : [404, { code: 'not_found' }]
    return new Response(JSON.stringify(payload), { status })
  }) as typeof fetch
  return { impl, calls }
}

const SOURCE = { data_source_id: 'sim-iot', name: 'SIM', kind: 'SIMULATED', read_only: true }
const SUGGESTIONS = {
  data_source_id: 'sim-iot',
  device_id: 'SIM-S13',
  signals: [],
  mappings: [],
  components: [
    {
      component_id: 'M01-BS1',
      machine_id: 'M01',
      type: 'BALL_SCREW',
      name: { zh: '丝杠', en: 'Screw' },
    },
  ],
  preview_window: { start: '2026-02-05T00:00:00Z', end: '2026-02-06T00:00:00Z' },
  is_simulated: true,
}
const DEVICES = [
  {
    device_id: 'SIM-S13',
    dataset_id: 'S13',
    label: null,
    keys: [{ key_name: 'K1', rows: null }],
    is_simulated: true,
  },
]

function sample(ts: string, value: number | null) {
  return { signal_id: 'K1', ts, value, unit: '', quality: [], source_ref: 'x', is_simulated: true }
}

describe('studio over the backend', () => {
  it('acts as engineer for ordinary users and admin for administrators', async () => {
    const { impl, calls } = fakeBackend({
      'GET /api/datasources': () => [200, [SOURCE]],
      'GET /api/query-templates': () => [200, []],
      'GET /api/admin/query-templates': () => [200, [{ template_id: 't', sql: 'SELECT 1' }]],
    })
    const api = createHttpStudioApi(impl)
    await api.source()
    await api.templates('operator')
    const admin = await api.templates('admin')
    expect(calls.map((c) => c.headers['X-PDM-Role'])).toEqual(['engineer', 'engineer', 'admin'])
    expect(admin[0]!.sql).toBe('SELECT 1')
  })

  it('maps devices and turns preview samples into seconds from the window start', async () => {
    const { impl, calls } = fakeBackend({
      'GET /api/datasources': () => [200, [SOURCE]],
      'GET /api/datasources/sim-iot/devices': () => [200, DEVICES],
      'GET /api/datasources/sim-iot/devices/SIM-S13/suggestions': () => [200, SUGGESTIONS],
      'POST /api/signals/preview': () => [
        200,
        {
          normalized: [
            {
              signal_id: 'K1',
              unit: '',
              truncated: false,
              samples: [
                sample('2026-02-05T00:00:02Z', 1.5),
                sample('2026-02-05T00:00:04Z', null),
                sample('2026-02-05T00:00:06Z', 2.5),
              ],
            },
          ],
          visualization: [],
          window: SUGGESTIONS.preview_window,
          is_simulated: true,
        },
      ],
    })
    const api = createHttpStudioApi(impl)
    await api.source()
    const [device] = await api.devices()
    expect(device).toMatchObject({ scenario_id: 'S13', scenario_title: { en: 'SIM-S13' } })
    expect(device!.keys[0]!.rows).toBeNull()
    const preview = await api.preview('SIM-S13')
    expect(preview.series.K1).toEqual([
      [2, 1.5],
      [6, 2.5],
    ])
    const req = calls.find((c) => c.method === 'POST')!.body as {
      mappings: { key_name: string; conversion: unknown }[]
    }
    expect(req.mappings).toEqual([expect.objectContaining({ key_name: 'K1', conversion: null })])
    const comps = await api.components('SIM-S13')
    expect(comps[0]).toMatchObject({
      component_id: 'M01-BS1',
      device_id: 'SIM-S13',
      signal_ids: [],
    })
    // suggestions are fetched once per device
    expect(calls.filter((c) => c.url.endsWith('/suggestions'))).toHaveLength(1)
  })

  it('saves a device configuration and surfaces backend conflicts', async () => {
    let status = 200
    const { impl, calls } = fakeBackend({
      'PUT /api/signal-config/sources/sim-iot/devices/SIM-S13': () =>
        status === 200
          ? [
              200,
              {
                version: 1,
                created_at: 'x',
                created_by: 'studio-operator',
                comment: 'c',
                content_hash: 'sha256:1',
              },
            ]
          : [
              409,
              {
                code: 'config_conflict',
                message: { zh: '冲突', en: 'Conflict' },
                detail: { reason: "duplicate signal 'a'" },
              },
            ],
    })
    const api = createHttpStudioApi(impl)
    const content = {
      signals: [],
      mappings: [{ data_source_id: 'sim-iot', device_id: 'SIM-S13', signal_id: 'a' }],
      groups: [],
      visualizations: [],
    }
    const v = await api.saveVersion(content, 'c', 'operator')
    expect(v.version).toBe(1)
    expect(calls[0]!.body).toMatchObject({ comment: 'c', base_version: null })
    status = 409
    const err = await api.saveVersion(content, 'c', 'operator').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(StudioApiError)
    expect(err).toMatchObject({
      status: 409,
      code: 'config_conflict',
      reason: "duplicate signal 'a'",
    })
  })
})

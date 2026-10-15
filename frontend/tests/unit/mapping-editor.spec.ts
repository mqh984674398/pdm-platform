import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SignalMappingEditor from '@/components/studio/SignalMappingEditor.vue'
import { i18n, setLocale } from '@/i18n'

afterEach(() => vi.unstubAllGlobals())

interface Body {
  signals: { signal_id: string }[]
  mappings: Record<string, unknown>[]
}
const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200 })

describe('signal mapping on a real source', () => {
  it('offers the keys the device really has when nothing is proposed, and saves the ticked ones', async () => {
    const puts: Array<{ url: string; body: Body }> = []
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        puts.push({ url, body: JSON.parse(String(init.body)) })
        return json({ version: 2 })
      }
      if (url.endsWith('/api/datasources'))
        return json([
          { data_source_id: 'taosi-01', name: '涛思', kind: 'TDENGINE', is_simulated: false },
        ])
      if (url.endsWith('/devices'))
        return json([
          {
            device_id: 'APAC000Y',
            keys: [
              { key_name: 'E330331100001', rows: null },
              { key_name: 'E330331100002', rows: null },
            ],
            machine_id: null,
            is_simulated: false,
          },
        ])
      if (url.endsWith('/suggestions'))
        return json({
          data_source_id: 'taosi-01',
          device_id: 'APAC000Y',
          signals: [],
          mappings: [],
          components: [],
          preview_window: null,
          is_simulated: false,
        })
      return new Response('{}', { status: 404 })
    })
    setLocale('en-US')
    const state = {
      version: { version: 1 },
      content: { signals: [], mappings: [], groups: [], visualizations: [] },
    }
    const w = mount(SignalMappingEditor, {
      props: { componentId: 'C1', deviceId: 'APAC000Y', state: state as never },
      global: { plugins: [i18n] },
    })
    await flushPromises()
    await w.find('[data-testid="map-suggest"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="map-keys-note"]').text()).toContain('2 signals')
    const rows = w.findAll('[data-testid="map-suggestions"] tbody tr')
    expect(rows.map((r) => r.attributes('data-suggest'))).toEqual([
      'APAC000Y.E330331100001',
      'APAC000Y.E330331100002',
    ])
    await rows[0]!.find('input[type="checkbox"]').setValue(true)
    await w.find('[data-testid="map-save"]').trigger('click')
    await flushPromises()
    const sent = puts[0]!.body
    expect(sent.signals.map((s: { signal_id: string }) => s.signal_id)).toEqual([
      'APAC000Y.E330331100001',
    ])
    expect(sent.mappings[0]).toMatchObject({
      key_name: 'E330331100001',
      device_id: 'APAC000Y',
      data_source_id: 'taosi-01',
      component_id: 'C1',
      template_id: 'taosi-01-telemetry-by-key-range',
    })
  })
})

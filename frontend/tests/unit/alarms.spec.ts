import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { i18n, setLocale } from '@/i18n'
import AlarmsView from '@/views/AlarmsView.vue'

const ALARM = {
  alarm_id: 'AL-1',
  component_id: 'A02-BS1',
  lifecycle_id: 'A02-BS1-LC1',
  severity: 'CRITICAL',
  status: 'RAISED',
  rule_id: 'ST-TORQUE',
  raised_at: '2026-02-20T00:00:00Z',
  acknowledged_at: null,
  acknowledged_by: null,
  resolved_at: null,
  resolved_by: null,
  resolution_comment: '',
  condition_active: true,
  last_window_end: '2026-02-21T00:00:00Z',
  message: {
    zh: '巡航扭矩残差偏离健康基准',
    en: 'Cruise torque residual away from the healthy reference',
  },
  evidence_ids: ['RH:ST-TORQUE:A02-BS1:2026-02-20T00:00:00+00:00'],
  rules_version: 'pdm-rules@1.0.0',
  is_simulated: true,
}

afterEach(() => vi.unstubAllGlobals())

async function mountView(onPost: (url: string, body: { comment: string }) => object) {
  const posts: [string, { comment: string }][] = []
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      const body = JSON.parse(String(init.body))
      posts.push([url, body])
      return new Response(JSON.stringify(onPost(url, body)), { status: 200 })
    }
    if (url.startsWith('/api/alarms')) return new Response(JSON.stringify([ALARM]), { status: 200 })
    return new Response(JSON.stringify({ machines: [] }), { status: 200 })
  })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:p(.*)*', component: AlarmsView }],
  })
  router.push('/alarms')
  await router.isReady()
  setLocale('en-US')
  const w = mount(AlarmsView, { global: { plugins: [i18n, router] } })
  await flushPromises()
  return { w, posts }
}

describe('alarm review', () => {
  it('resolving needs the outcome and records it', async () => {
    const { w, posts } = await mountView((_, body) => ({
      ...ALARM,
      status: 'RESOLVED',
      resolved_at: '2026-02-22T00:00:00Z',
      resolved_by: 'ui-engineer',
      resolution_comment: body.comment,
    }))
    expect(w.find('[data-alarm="AL-1"]').attributes('data-status')).toBe('RAISED')
    await w.find('[data-testid="alarm-resolve"]').trigger('click')
    expect(posts).toEqual([])
    expect(w.find('[role="alert"]').text()).toContain('Enter the outcome')

    await w.find('[data-testid="alarm-comment"]').setValue('lubricated')
    await w.find('[data-testid="alarm-resolve"]').trigger('click')
    await flushPromises()
    expect(posts).toEqual([['/api/alarms/AL-1/resolve', { comment: 'lubricated' }]])
    // resolved alarms leave the default (open) list
    expect(w.find('[data-alarm="AL-1"]').exists()).toBe(false)
    expect(w.find('[data-testid="no-alarms"]').exists()).toBe(true)
  })

  it('acknowledges without a comment', async () => {
    const { w, posts } = await mountView(() => ({ ...ALARM, status: 'ACKNOWLEDGED' }))
    await w.find('[data-testid="alarm-ack"]').trigger('click')
    await flushPromises()
    expect(posts).toEqual([['/api/alarms/AL-1/acknowledge', { comment: '' }]])
    expect(w.find('[data-alarm="AL-1"]').attributes('data-status')).toBe('ACKNOWLEDGED')
    expect(w.find('[data-testid="alarm-ack"]').exists()).toBe(false)
  })
})

import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import App from '@/App.vue'
import { routes } from '@/router'

describe('App shell', () => {
  it('renders the home route and reports backend unreachable', async () => {
    vi.stubGlobal('fetch', async () => {
      throw new TypeError('network')
    })
    const router = createRouter({ history: createMemoryHistory(), routes })
    router.push('/')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('预测性维护')
    expect(wrapper.get('[data-testid="backend-status"]').text()).toBe('Backend unreachable')
    vi.unstubAllGlobals()
  })
})

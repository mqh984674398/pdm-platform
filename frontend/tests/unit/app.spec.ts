import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import App from '@/App.vue'
import { i18n, setLocale } from '@/i18n'
import { routes } from '@/router'
import { NAV } from '@/router/nav'
import PlaceholderView from '@/views/PlaceholderView.vue'

async function mountApp(path = '/') {
  vi.stubGlobal('fetch', async () => {
    throw new TypeError('network')
  })
  const router = createRouter({ history: createMemoryHistory(), routes })
  router.push(path)
  await router.isReady()
  const wrapper = mount(App, { global: { plugins: [router, i18n, createPinia()] } })
  await flushPromises()
  return wrapper
}

describe('App shell', () => {
  it('registers all 12 required interfaces as routes, plus administration', () => {
    expect(NAV.filter((n) => !n.adminOnly)).toHaveLength(11)
    expect(NAV.filter((n) => n.adminOnly).map((n) => n.name)).toEqual([
      'users',
      'datasources',
      'plant',
    ])
    expect(routes.map((r) => r.name)).toEqual(NAV.map((n) => n.name))
  })

  it('delivers every screen; none is left as a placeholder', () => {
    expect(routes.filter((r) => r.component === PlaceholderView).map((r) => r.name)).toEqual([])
  })

  it('switches language at runtime without remounting', async () => {
    setLocale('zh-CN')
    const wrapper = await mountApp('/signals')
    const nav = wrapper.get('[data-nav="signals"]')
    expect(nav.text()).toBe('信号配置')
    expect(wrapper.get('[data-testid="backend-status"]').text()).toBe('无法连接后端服务')
    setLocale('en-US')
    await flushPromises()
    expect(nav.text()).toBe('Signal setup')
    expect(wrapper.get('[data-testid="backend-status"]').text()).toBe('Cannot reach the backend')
    expect(document.documentElement.lang).toBe('en-US')
    setLocale('zh-CN')
    vi.unstubAllGlobals()
  })
})

import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import App from '@/App.vue'
import { i18n, setLocale } from '@/i18n'
import { routes } from '@/router'
import { NAV } from '@/router/nav'

async function mountApp(path = '/') {
  vi.stubGlobal('fetch', async () => {
    throw new TypeError('network')
  })
  const router = createRouter({ history: createMemoryHistory(), routes })
  router.push(path)
  await router.isReady()
  const wrapper = mount(App, { global: { plugins: [router, i18n] } })
  await flushPromises()
  return wrapper
}

describe('App shell', () => {
  it('registers all 12 required interfaces as routes', () => {
    expect(NAV).toHaveLength(12)
    expect(routes.map((r) => r.name)).toEqual(NAV.map((n) => n.name))
  })

  it('switches language at runtime without remounting', async () => {
    setLocale('zh-CN')
    const wrapper = await mountApp('/datasource')
    const nav = wrapper.get('[data-nav="datasource"]')
    expect(nav.text()).toBe('数据源工作室')
    expect(wrapper.get('[data-testid="backend-status"]').text()).toBe('无法连接后端服务')
    setLocale('en-US')
    await flushPromises()
    expect(nav.text()).toBe('Data Source Studio')
    expect(wrapper.get('[data-testid="backend-status"]').text()).toBe('Cannot reach the backend')
    expect(document.documentElement.lang).toBe('en-US')
    setLocale('zh-CN')
    vi.unstubAllGlobals()
  })
})

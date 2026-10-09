import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import fleetJson from '@data/fixtures/demo_fleet.json'
import type { Fleet } from '@/api/fleet'
import MachineMap from '@/components/fleet/MachineMap.vue'
import { fitLines, textWidth } from '@/components/fleet/labelFit'
import { i18n, setLocale } from '@/i18n'
import OverviewView from '@/views/OverviewView.vue'

const fleet = fleetJson as unknown as Fleet
const byId = (id: string) => fleet.machines.find((m) => m.machine_id === id)!

describe('label fitting', () => {
  it('keeps short names on one line', () => {
    expect(fitLines('Clamp cylinder', 200, 16)).toEqual(['Clamp cylinder'])
  })
  it('wraps long Latin names at spaces and never exceeds two lines', () => {
    const lines = fitLines('Transfer linear motor with extra long description', 110, 16)
    expect(lines.length).toBeLessThanOrEqual(2)
    expect(lines.every((l) => textWidth(l, 16) <= 110)).toBe(true)
    expect(lines[1]!.endsWith('…')).toBe(true)
  })
  it('wraps CJK between characters', () => {
    const lines = fitLines('一二三四五六七八九十', 80, 16)
    expect(lines).toEqual(['一二三四五', '六七八九十'])
  })
})

describe('machine map', () => {
  it('renders one selectable station per component with its health', async () => {
    setLocale('en-US')
    const m = byId('A01')
    const w = mount(MachineMap, { props: { machine: m }, global: { plugins: [i18n] } })
    const stations = w.findAll('[data-component]')
    expect(stations.map((s) => s.attributes('data-component'))).toEqual(
      m.components.map((c) => c.component_id),
    )
    expect(stations.map((s) => s.attributes('data-health'))).toEqual(
      m.components.map((c) => c.health),
    )
    await stations[1]!.trigger('click')
    await stations[2]!.trigger('keydown', { key: 'Enter' })
    expect(w.emitted('select')).toEqual([
      [m.components[1]!.component_id],
      [m.components[2]!.component_id],
    ])
    setLocale('zh-CN')
  })

  it('draws the shared drive chain only for machines that have one', () => {
    const shared = mount(MachineMap, {
      props: { machine: byId('A06') },
      global: { plugins: [i18n] },
    })
    const single = mount(MachineMap, {
      props: { machine: byId('A04') },
      global: { plugins: [i18n] },
    })
    expect(shared.findAll('.chain')).toHaveLength(1)
    expect(single.findAll('.chain')).toHaveLength(0)
  })
})

describe('overview', () => {
  it('lists every simulated machine and labels the health basis', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/:p(.*)*', component: { template: '<div />' } }],
    })
    const w = mount(OverviewView, { global: { plugins: [i18n, router] } })
    await flushPromises()
    await flushPromises()
    const tiles = w.findAll('[data-machine]').map((t) => t.attributes('data-machine'))
    expect([...tiles].sort()).toEqual(fleet.machines.map((m) => m.machine_id).sort())
    expect(w.find('[data-testid="demo-notice"]').text()).toContain('Golden Case')
  })
})

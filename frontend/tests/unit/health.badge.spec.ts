import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import HealthBadge from '@/components/base/HealthBadge.vue'
import SimBadge from '@/components/base/SimBadge.vue'
import { i18n, setLocale } from '@/i18n'
import { HEALTH_STATES, worstHealth } from '@/theme/health'

describe('health presentation', () => {
  it('renders a distinct badge for every health state', () => {
    setLocale('en-US')
    const labels = HEALTH_STATES.map((s) => {
      const w = mount(HealthBadge, { props: { state: s }, global: { plugins: [i18n] } })
      expect(w.classes()).toContain(`is-${s.toLowerCase()}`)
      return w.text()
    })
    expect(labels).toEqual(['Normal', 'Watch', 'Warning', 'Critical', 'Unknown'])
    setLocale('zh-CN')
  })

  it('aggregates to the worst known state and keeps UNKNOWN for no evidence', () => {
    expect(worstHealth(['NORMAL', 'WARNING', 'UNKNOWN'])).toBe('WARNING')
    expect(worstHealth(['UNKNOWN', 'UNKNOWN'])).toBe('UNKNOWN')
    expect(worstHealth(['NORMAL', 'WATCH'])).toBe('WATCH')
  })

  it('labels simulated data', () => {
    const w = mount(SimBadge, { global: { plugins: [i18n] } })
    expect(w.attributes('data-simulated')).toBe('true')
    expect(w.text()).toBe('模拟数据')
  })
})

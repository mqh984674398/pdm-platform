import { describe, expect, it } from 'vitest'
import { resolvedTheme, toggleTheme, useTheme } from '@/composables/useTheme'

describe('theme toggle', () => {
  it('flips the shown theme and remembers it as an explicit choice', () => {
    const theme = useTheme()
    theme.value = 'light'
    toggleTheme()
    expect(theme.value).toBe('dark')
    expect(resolvedTheme.value).toBe('dark')
    toggleTheme()
    expect(theme.value).toBe('light')
  })
})

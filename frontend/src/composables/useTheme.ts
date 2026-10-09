import { ref, watch } from 'vue'

export type ThemeChoice = 'system' | 'light' | 'dark'
const KEY = 'pdm.theme'

function load(): ThemeChoice {
  try {
    const v = localStorage.getItem(KEY)
    if (v === 'light' || v === 'dark' || v === 'system') return v
  } catch {
    // storage unavailable
  }
  return 'system'
}

const theme = ref<ThemeChoice>(load())

function apply(choice: ThemeChoice): void {
  const root = document.documentElement
  if (choice === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', choice)
  try {
    localStorage.setItem(KEY, choice)
  } catch {
    // non-critical
  }
}

apply(theme.value)
watch(theme, apply)

export function useTheme() {
  return theme
}

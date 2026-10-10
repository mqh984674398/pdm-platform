import { computed, ref, watch } from 'vue'

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

const systemDark = ref(prefersDark())

function prefersDark(): boolean {
  return (
    typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-color-scheme: dark)').matches
  )
}

if (typeof window !== 'undefined' && window.matchMedia) {
  window
    .matchMedia('(prefers-color-scheme: dark)')
    .addEventListener?.('change', () => (systemDark.value = prefersDark()))
}

/** The theme actually shown: an explicit choice, or the operating system's setting. */
export const resolvedTheme = computed<'light' | 'dark'>(() =>
  theme.value === 'system' ? (systemDark.value ? 'dark' : 'light') : theme.value,
)

/** One-button switch: always flips what is shown and remembers it as an explicit choice. */
export function toggleTheme(): void {
  theme.value = resolvedTheme.value === 'dark' ? 'light' : 'dark'
}

export function useTheme() {
  return theme
}

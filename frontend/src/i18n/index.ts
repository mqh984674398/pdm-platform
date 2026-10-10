import { createI18n } from 'vue-i18n'
import zhCN from './locales/zh-CN'
import enUS from './locales/en-US'

export const LOCALES = ['zh-CN', 'en-US'] as const
export type Locale = (typeof LOCALES)[number]
const STORAGE_KEY = 'pdm.locale'

function initialLocale(): Locale {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved && (LOCALES as readonly string[]).includes(saved)) return saved as Locale
  } catch {
    // storage unavailable: fall through to browser language
  }
  return typeof navigator !== 'undefined' && navigator.language.toLowerCase().startsWith('en')
    ? 'en-US'
    : 'zh-CN'
}

export const i18n = createI18n({
  legacy: false,
  locale: initialLocale(),
  fallbackLocale: 'zh-CN',
  messages: { 'zh-CN': zhCN, 'en-US': enUS },
})

/** Switch language at runtime without reloading (GEN-05). */
export function setLocale(locale: Locale): void {
  i18n.global.locale.value = locale
  document.documentElement.lang = locale
  try {
    localStorage.setItem(STORAGE_KEY, locale)
  } catch {
    // non-critical
  }
}

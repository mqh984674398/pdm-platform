import { useI18n } from 'vue-i18n'
import type { LocalizedText } from '@/api/contracts'

/** Pick the active language from bilingual contract text, and format dates for the locale. */
export function useLocalized() {
  const { locale } = useI18n()
  const lt = (text: LocalizedText | null | undefined): string =>
    text ? (locale.value === 'en-US' ? text.en : text.zh) : ''
  const fmtDate = (iso: string, withTime = true): string =>
    new Intl.DateTimeFormat(locale.value, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      ...(withTime ? { hour: '2-digit', minute: '2-digit', hour12: false } : {}),
      timeZone: 'UTC',
    }).format(new Date(iso))
  return { lt, fmtDate }
}

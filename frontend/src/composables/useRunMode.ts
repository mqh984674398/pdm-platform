/**
 * Run mode (D-053): the platform shows either the simulation database or the production TDengine
 * sources. The mode is stored on the server; changing it reloads the page so that every list is read
 * again for the new mode.
 */
import { readonly, ref } from 'vue'
import { monitoringApi } from '@/api/monitoring'
import type { RunMode } from '@/api/contracts'

const mode = ref<RunMode | null>(null)

export async function loadRunMode(): Promise<void> {
  try {
    mode.value = (await monitoringApi.runMode()).mode
  } catch {
    mode.value = null
  }
}

export async function changeRunMode(next: RunMode): Promise<void> {
  mode.value = (await monitoringApi.setRunMode(next)).mode
  if (typeof window !== 'undefined') window.location.reload()
}

export function useRunMode() {
  return { mode: readonly(mode) }
}

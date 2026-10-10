/** Overview plus zoom-detail loading for one signal (T019). The server downsamples; nothing here does. */
import { computed, ref, shallowRef, watch, type Ref } from 'vue'
import type { VisualizationSeries } from '@/api/contracts'
import type { MonitoringApi } from '@/api/monitoring'
import { isFull, mergeDetail, rangeChanged, toPoints, type Range } from './merge'

export const MAX_POINTS = 2000

export function useSeries(api: MonitoringApi, signalId: Ref<string | null>) {
  const full = ref<Range | null>(null)
  const overview = shallowRef<VisualizationSeries | null>(null)
  const detail = shallowRef<VisualizationSeries | null>(null)
  const view = ref<Range | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  let controller: AbortController | null = null

  async function fetchRange(range: Range) {
    controller?.abort()
    controller = new AbortController()
    loading.value = true
    try {
      return await api.series(
        signalId.value!,
        range.start,
        range.end,
        MAX_POINTS,
        controller.signal,
      )
    } finally {
      loading.value = false
    }
  }

  watch(
    signalId,
    async (id) => {
      overview.value = detail.value = null
      view.value = full.value = null
      error.value = null
      if (!id) return
      try {
        const extent = await api.extent(id)
        if (!extent || signalId.value !== id) return
        full.value = { start: Date.parse(extent.start), end: Date.parse(extent.end) }
        overview.value = await fetchRange(full.value)
      } catch (e) {
        if ((e as Error).name !== 'AbortError') error.value = (e as Error).message
      }
    },
    { immediate: true },
  )

  async function zoom(range: Range) {
    if (!full.value || !rangeChanged(view.value, range, full.value)) return
    view.value = range
    if (isFull(range, full.value)) {
      detail.value = null
      return
    }
    try {
      detail.value = await fetchRange(range)
    } catch (e) {
      if ((e as Error).name !== 'AbortError') error.value = (e as Error).message
    }
  }

  const points = computed(() =>
    overview.value
      ? mergeDetail(
          toPoints(overview.value),
          detail.value && toPoints(detail.value),
          detail.value && view.value,
        )
      : [],
  )
  /** What is on screen: the detail series when zoomed, else the overview. */
  const shown = computed(() => detail.value ?? overview.value)
  const visible = computed<Range | null>(() => view.value ?? full.value)

  return { full, overview, detail, points, shown, visible, loading, error, zoom }
}

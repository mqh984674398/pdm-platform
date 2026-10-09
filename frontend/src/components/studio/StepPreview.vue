<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useLocalized } from '@/composables/useLocalized'
import { observationWindows } from '@/studio/quality'
import { useStudioStore } from '@/studio/store'
import { convert } from '@/studio/units'
import PreviewChart, { type ChartSeries } from './PreviewChart.vue'

const s = useStudioStore()
const { t } = useI18n()
const { lt } = useLocalized()
const windowIndex = ref(0)
const chosen = ref<string[]>([])

const t0 = computed(() => (s.preview ? Date.parse(s.preview.window_start) : 0))
const shown = computed(() =>
  chosen.value.length
    ? chosen.value.filter((k) => s.selectedKeys.includes(k))
    : s.selectedKeys.slice(0, 2),
)
/** Observation-window boundaries from the densest selected signal. */
const windows = computed(() => {
  const all = s.activeDrafts.map((d) => observationWindows(s.preview?.series[d.key_name] ?? []))
  const ref_ = all.reduce((a, b) => (b.length > a.length ? b : a), [] as [number, number][][])
  return ref_.map((w) => [w[0]![0], w[w.length - 1]![0]] as [number, number])
})
const range = computed(() => {
  const w = windows.value[windowIndex.value]
  return w ? [w[0] - 5, w[1] + 5] : [-Infinity, Infinity]
})

const series = computed<ChartSeries[]>(() =>
  shown.value.map((key) => {
    const d = s.drafts[key]!
    const raw = s.preview?.series[key] ?? []
    const conv = { scale: d.scale ?? 1, offset: d.offset }
    const inRange = raw.filter(([x]) => x >= range.value[0]! && x <= range.value[1]!)
    const q = s.quality.find((r) => r.signal_id === d.signal_id)
    const flagged: [number, number][] = []
    if (q && (q.duplicate_count || q.out_of_order_count || q.unit_suspect)) {
      const seen = new Set<number>()
      let maxT = -Infinity
      let prev: number | null = null
      for (const [x, v] of raw) {
        const ratio = prev ? v / prev : 1
        const bad = seen.has(x) || x < maxT || (q.unit_suspect && (ratio >= 100 || ratio <= 0.01))
        if (bad && x >= range.value[0]! && x <= range.value[1]!)
          flagged.push([t0.value + x * 1000, convert(v, conv)])
        seen.add(x)
        maxT = Math.max(maxT, x)
        prev = v
      }
    }
    return {
      name: lt(s.signalName(key)) || key,
      unit: d.target_unit,
      points: observationWindows(inRange)
        .flat()
        .map(([x, v]) => [t0.value + x * 1000, convert(v, conv)]),
      flagged,
    }
  }),
)
const utc = (sec: number) => new Date(t0.value + sec * 1000).toISOString().slice(11, 16)
function toggle(key: string) {
  const cur = shown.value
  chosen.value = cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key]
}
</script>

<template>
  <div class="st-stack">
    <div class="controls">
      <div class="signals" role="group" :aria-label="t('studio.groups.signals')">
        <button
          v-for="d in s.activeDrafts"
          :key="d.key_name"
          type="button"
          class="chip"
          :aria-pressed="shown.includes(d.key_name)"
          :data-preview-key="d.key_name"
          @click="toggle(d.key_name)"
        >
          {{ lt(s.signalName(d.key_name)) || d.key_name }}
        </button>
      </div>
      <label class="st-field">
        <span>{{ t('studio.preview.window') }}</span>
        <select v-model.number="windowIndex" class="st-select" data-testid="preview-window">
          <option v-for="(w, i) in windows" :key="i" :value="i">
            {{ i + 1 }}. {{ utc(w[0]) }} {{ t('studio.utc') }}
          </option>
        </select>
      </label>
    </div>
    <PreviewChart :series="series" :flagged-label="t('studio.preview.flagged')" />
    <p class="st-note">{{ t('studio.preview.note') }}</p>
  </div>
</template>

<style scoped>
.controls {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  justify-content: space-between;
  align-items: flex-end;
}
.signals {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.chip {
  padding: 4px 12px;
  border-radius: 999px;
  border: 1px solid var(--line-strong);
  background: var(--surface);
  font-size: var(--text-sm);
  cursor: pointer;
}
.chip[aria-pressed='true'] {
  background: var(--accent-soft);
  border-color: var(--accent);
}
</style>

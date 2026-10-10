<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ChartKind } from '@/api/contracts'
import { useLocalized } from '@/composables/useLocalized'
import { observationWindows } from '@/studio/quality'
import { useStudioStore } from '@/studio/store'
import { convert } from '@/studio/units'
import PreviewChart, { type ChartSeries } from './PreviewChart.vue'

const s = useStudioStore()
const { t } = useI18n()
const { lt } = useLocalized()
const KINDS: ChartKind[] = ['LINE', 'SCATTER', 'HISTOGRAM', 'CYCLE_DURATION']
const ICONS: Record<ChartKind, string> = {
  LINE: 'M2 12l3-4 3 2 3-6 3 3',
  SCATTER: 'M3 11h.01M6 7h.01M8 10h.01M10 5h.01M13 6h.01M11 9h.01',
  HISTOGRAM: 'M2 14V9h3v5M6 14V4h3v10M10 14V7h3v7',
  CYCLE_DURATION: 'M2 10h2M5 9h2M8 9h2M11 7h2M14 6h1',
}
const active = ref(0)
const group = computed(() => s.groups[active.value] ?? s.groups[0])

const series = computed<ChartSeries[]>(() => {
  const g = group.value
  if (!g || !s.preview) return []
  const t0 = Date.parse(s.preview.window_start)
  return g.keys.map((key) => {
    const d = s.drafts[key]!
    // Time-based charts show one observation window; distributions and cycles use them all.
    const windows = observationWindows(s.preview!.series[key] ?? [])
    const pts = g.chart === 'LINE' || g.chart === 'SCATTER' ? (windows[0] ?? []) : windows.flat()
    return {
      name: lt(s.signalName(key)) || key,
      unit: d.target_unit,
      points: pts.map(([x, v]) => [
        t0 + x * 1000,
        convert(v, { scale: d.scale ?? 1, offset: d.offset }),
      ]),
    }
  })
})
</script>

<template>
  <div class="st-stack">
    <div class="layout">
      <ul class="groups">
        <li v-for="(g, i) in s.groups" :key="g.group_id">
          <button type="button" class="st-choice" :aria-pressed="i === active" @click="active = i">
            <strong>{{ lt(g.name) }}</strong>
            <span class="muted">{{ t(`studio.viz.charts.${g.chart}`) }}</span>
          </button>
        </li>
      </ul>
      <div v-if="group" class="st-stack">
        <div class="kinds" role="radiogroup" :aria-label="t('studio.steps.viz')">
          <button
            v-for="k in KINDS"
            :key="k"
            type="button"
            role="radio"
            class="kind"
            :aria-checked="group.chart === k"
            :data-chart="k"
            @click="group.chart = k"
          >
            <svg viewBox="0 0 16 16" width="28" height="28" aria-hidden="true">
              <path
                :d="ICONS[k]"
                fill="none"
                stroke="currentColor"
                stroke-width="1.6"
                stroke-linecap="round"
              />
            </svg>
            <strong>{{ t(`studio.viz.charts.${k}`) }}</strong>
            <span class="st-note">{{ t(`studio.viz.help.${k}`) }}</span>
          </button>
        </div>
        <PreviewChart :series="series" :kind="group.chart" :height="240" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: var(--space-4);
}
@media (max-width: 760px) {
  .layout {
    grid-template-columns: 1fr;
  }
}
.groups {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: var(--space-2);
  align-content: start;
}
.groups .st-choice {
  width: 100%;
}
.kinds {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--space-2);
}
.kind {
  display: grid;
  justify-items: start;
  gap: 2px;
  padding: var(--space-3);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-panel);
  background: var(--surface);
  text-align: left;
  cursor: pointer;
  color: var(--ink);
}
.kind svg {
  color: var(--accent);
}
.kind[aria-checked='true'] {
  border-color: var(--accent);
  box-shadow: inset 0 0 0 1px var(--accent);
  background: var(--accent-soft);
}
</style>

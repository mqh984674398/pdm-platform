<script setup lang="ts">
/** States whether the chart shows every point or a server-side downsample (L2-06, T019 AC3). */
import { useI18n } from 'vue-i18n'
import type { VisualizationSeries } from '@/api/contracts'

defineProps<{ series: VisualizationSeries | null; exporting?: boolean }>()
defineEmits<{ export: [] }>()
const { t } = useI18n()
const n = (x: number) => x.toLocaleString()
</script>

<template>
  <div
    v-if="series"
    class="note"
    data-testid="downsample-note"
    :data-downsampled="series.downsampled"
  >
    <span v-if="series.downsampled" class="tag down">{{ t('charts.downsampled') }}</span>
    <span v-else class="tag fullres">{{ t('charts.fullResolution') }}</span>
    <span class="count">
      {{
        series.downsampled
          ? t('charts.shownOf', {
              shown: n(series.points.length),
              total: n(series.source_point_count),
            })
          : t('charts.allPoints', { total: n(series.source_point_count) })
      }}
    </span>
    <button
      type="button"
      class="export"
      data-testid="export-csv"
      :disabled="exporting"
      @click="$emit('export')"
    >
      {{ t('charts.export') }}
    </button>
  </div>
</template>

<style scoped>
.note {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  font-size: var(--text-sm);
  color: var(--ink-soft);
  flex-wrap: wrap;
}
.tag {
  padding: 1px 8px;
  border-radius: var(--radius-control);
  font-size: var(--text-xs);
  font-weight: 500;
}
.down {
  background: var(--health-watch-soft);
  color: var(--ink);
}
.fullres {
  background: var(--health-normal-soft);
  color: var(--ink);
}
.export {
  margin-left: auto;
}
</style>

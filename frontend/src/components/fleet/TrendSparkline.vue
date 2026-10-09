<script setup lang="ts">
import { computed } from 'vue'

/**
 * History sparkline. With ``thresholds`` (T020: deviation from the verified reference) it draws them
 * as dashed lines; without, the early-period band (first 20% of points) as before.
 */
const props = defineProps<{ points: [string, number][]; label: string; thresholds?: number[] }>()
const W = 320
const H = 72
const geo = computed(() => {
  const ys = props.points.map((p) => p[1])
  if (ys.length < 2) return null
  const marks = props.thresholds ?? []
  const min = Math.min(...ys, ...(marks.length ? [0] : []))
  const max = Math.max(...ys, ...marks)
  const pad = (max - min) * 0.12 || Math.abs(max) * 0.05 || 1
  const lo = min - pad
  const hi = max + pad
  const x = (i: number) => (i / (ys.length - 1)) * W
  const y = (v: number) => H - ((v - lo) / (hi - lo)) * H
  const ref = ys.slice(0, Math.max(2, Math.floor(ys.length / 5)))
  const mean = ref.reduce((a, b) => a + b, 0) / ref.length
  const sd = Math.sqrt(ref.reduce((a, b) => a + (b - mean) ** 2, 0) / ref.length)
  return {
    line: ys.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' '),
    band: marks.length
      ? null
      : { y: y(mean + 2 * sd), h: Math.max(1, y(mean - 2 * sd) - y(mean + 2 * sd)) },
    marks: marks.map((m) => y(m)),
    last: { x: x(ys.length - 1), y: y(ys[ys.length - 1]) },
  }
})
</script>

<template>
  <svg
    v-if="geo"
    :viewBox="`0 0 ${W} ${H}`"
    class="spark"
    role="img"
    :aria-label="label"
    preserveAspectRatio="none"
  >
    <rect v-if="geo.band" x="0" :y="geo.band.y" :width="W" :height="geo.band.h" class="band" />
    <line
      v-for="(my, i) in geo.marks"
      :key="i"
      x1="0"
      :x2="W"
      :y1="my"
      :y2="my"
      class="mark"
      vector-effect="non-scaling-stroke"
    />
    <polyline :points="geo.line" class="line" vector-effect="non-scaling-stroke" />
    <circle :cx="geo.last.x" :cy="geo.last.y" r="3" class="dot" />
  </svg>
</template>

<style scoped>
.spark {
  width: 100%;
  height: 72px;
  display: block;
  overflow: visible;
}
.band {
  fill: var(--accent-soft);
}
.line {
  fill: none;
  stroke: var(--accent);
  stroke-width: 1.6;
}
.mark {
  stroke: var(--ink-faint);
  stroke-dasharray: 4 3;
  stroke-width: 1;
}
.dot {
  fill: var(--accent);
}
</style>

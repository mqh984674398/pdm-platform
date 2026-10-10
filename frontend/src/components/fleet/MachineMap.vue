<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { FleetComponent, FleetMachine } from '@/api/fleet'
import { useLocalized } from '@/composables/useLocalized'
import { healthVar } from '@/theme/health'
import ComponentGlyph from './ComponentGlyph.vue'
import { fitLines } from './labelFit'

const props = defineProps<{ machine: FleetMachine; selected?: string | null }>()
const emit = defineEmits<{ select: [componentId: string] }>()
const { t } = useI18n()
const { lt } = useLocalized()

const W = 960
const H = 430
const stations = computed(() => {
  const n = props.machine.components.length
  const gap = W / n
  return props.machine.components.map((c, i) => ({ c, x: gap * i + gap / 2 }))
})
// Plate width shrinks when many components share the bed; glyph scales with it.
const plate = computed(() => {
  const w = Math.min(180, W / props.machine.components.length - 14)
  const s = Math.min(1.3, (w - 30) / 100)
  return { w, s, gx: (w - 100 * s) / 2, font: w < 150 ? 16 : 19 }
})
// Names wrap to two lines on narrow plates; the full name stays in <title> and aria-label.
function nameLines(c: FleetComponent): string[] {
  return fitLines(lt(c.name), plate.value.w - 14, plate.value.font)
}
const chains = computed(() => {
  const groups = new Map<string, number[]>()
  for (const s of stations.value) {
    if (!s.c.drive_chain_id) continue
    groups.set(s.c.drive_chain_id, [...(groups.get(s.c.drive_chain_id) ?? []), s.x])
  }
  return [...groups.values()].filter((xs) => xs.length > 1)
})

function stroke(c: FleetComponent) {
  return c.health === 'UNKNOWN' ? 'var(--health-unknown)' : healthVar(c.health)
}
function onKey(e: KeyboardEvent, id: string) {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    emit('select', id)
  }
}
</script>

<template>
  <svg :viewBox="`0 0 ${W} ${H}`" class="machine-map" role="group" :aria-label="lt(machine.name)">
    <defs>
      <pattern
        id="hatch-unknown"
        width="6"
        height="6"
        patternUnits="userSpaceOnUse"
        patternTransform="rotate(45)"
      >
        <rect width="6" height="6" fill="var(--health-unknown-soft)" />
        <line x1="0" y1="0" x2="0" y2="6" stroke="var(--health-unknown)" stroke-width="2.4" />
      </pattern>
    </defs>

    <rect x="16" y="360" :width="W - 32" height="34" rx="8" class="bed" />
    <line
      v-for="s in stations"
      :key="`p-${s.c.component_id}`"
      :x1="s.x"
      y1="296"
      :x2="s.x"
      y2="360"
      class="post"
    />

    <g v-for="(xs, i) in chains" :key="`chain-${i}`" class="chain">
      <path :d="`M${xs[0]} 70 H${xs[xs.length - 1]}`" />
      <circle v-for="x in xs" :key="x" :cx="x" cy="70" r="5" />
      <line v-for="x in xs" :key="`l${x}`" :x1="x" y1="75" :x2="x" y2="96" />
      <text :x="(xs[0] + xs[xs.length - 1]) / 2" y="58" text-anchor="middle" class="chain-label">
        {{ t('machine.sharedChain') }}
      </text>
    </g>

    <g
      v-for="s in stations"
      :key="s.c.component_id"
      class="station"
      :class="{ selected: selected === s.c.component_id }"
      :transform="`translate(${s.x - plate.w / 2}, 96)`"
      tabindex="0"
      role="button"
      :aria-label="`${lt(s.c.name)}: ${t(`health.${s.c.health}`)}`"
      :aria-pressed="selected === s.c.component_id"
      :data-component="s.c.component_id"
      :data-health="s.c.health"
      @click="emit('select', s.c.component_id)"
      @keydown="onKey($event, s.c.component_id)"
    >
      <rect
        x="0"
        y="0"
        :width="plate.w"
        height="200"
        rx="14"
        class="plate"
        :style="{ stroke: stroke(s.c) }"
        :stroke-dasharray="s.c.health === 'UNKNOWN' ? '6 5' : undefined"
      />
      <g :transform="`translate(${plate.gx}, 8) scale(${plate.s})`" class="glyph-wrap">
        <ComponentGlyph :type="s.c.type" :health="s.c.health" />
      </g>
      <title>{{ lt(s.c.name) }}</title>
      <text
        :x="plate.w / 2"
        :y="nameLines(s.c).length > 1 ? 146 : 160"
        text-anchor="middle"
        class="name"
        :style="{ fontSize: `${plate.font}px` }"
      >
        <tspan
          v-for="(line, i) in nameLines(s.c)"
          :key="i"
          :x="plate.w / 2"
          :dy="i === 0 ? 0 : plate.font + 3"
        >
          {{ line }}
        </tspan>
      </text>
      <text
        :x="plate.w / 2"
        :y="nameLines(s.c).length > 1 ? 189 : 186"
        text-anchor="middle"
        class="state"
        :style="{ fill: stroke(s.c) }"
      >
        {{ t(`health.${s.c.health}`) }}
      </text>
    </g>
  </svg>
</template>

<style scoped>
.machine-map {
  width: 100%;
  height: auto;
  display: block;
  color: var(--ink-soft);
}
.bed {
  fill: var(--surface-inset);
  stroke: var(--line-strong);
}
.post {
  stroke: var(--line-strong);
  stroke-width: 6;
}
.chain path,
.chain line {
  stroke: var(--ink-faint);
  stroke-width: 3;
  fill: none;
  stroke-dasharray: 2 6;
  stroke-linecap: round;
}
.chain circle {
  fill: var(--surface);
  stroke: var(--ink-faint);
  stroke-width: 2;
}
.chain-label {
  font-size: 17px;
  fill: var(--ink-soft);
}
.station {
  cursor: pointer;
  outline: none;
}
.plate {
  fill: var(--surface);
  stroke-width: 2;
  transition: stroke-width var(--dur-fast) var(--ease);
}
.station:hover .plate {
  stroke-width: 3;
}
.station.selected .plate {
  stroke-width: 4;
  filter: drop-shadow(0 4px 10px rgb(29 35 42 / 14%));
}
.station:focus-visible .plate {
  stroke-width: 4;
  outline: 3px solid var(--accent);
}
.name {
  font-weight: 500;
  fill: var(--ink);
}
.state {
  font-size: 17px;
  font-weight: 600;
}
</style>

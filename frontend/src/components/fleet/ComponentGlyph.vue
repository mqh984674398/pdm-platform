<script setup lang="ts">
import { computed } from 'vue'
import type { ComponentType, HealthState } from '@/api/contracts'
import { healthVar } from '@/theme/health'

/** Schematic symbol for a component type, drawn in a 100x100 box. Health colors the working part. */
const props = defineProps<{ type: ComponentType; health: HealthState }>()
const fill = computed(() =>
  props.health === 'UNKNOWN' ? 'url(#hatch-unknown)' : healthVar(props.health),
)

function gearPath(cx: number, cy: number, r: number, teeth: number): string {
  const pts: string[] = []
  for (let i = 0; i < teeth * 4; i++) {
    const a = (Math.PI * 2 * i) / (teeth * 4)
    const rr = i % 4 < 2 ? r : r - 7
    pts.push(`${(cx + rr * Math.cos(a)).toFixed(1)},${(cy + rr * Math.sin(a)).toFixed(1)}`)
  }
  return `M${pts.join('L')}Z`
}
const threads = Array.from({ length: 13 }, (_, i) => 12 + i * 6.3)
</script>

<template>
  <g class="glyph" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" fill="none">
    <template v-if="type === 'BALL_SCREW'">
      <rect x="4" y="42" width="8" height="16" rx="1.5" />
      <rect x="88" y="42" width="8" height="16" rx="1.5" />
      <line x1="12" y1="50" x2="88" y2="50" stroke-width="5" />
      <line v-for="x in threads" :key="x" :x1="x" y1="45" :x2="x + 4" y2="55" stroke-width="1.4" />
      <rect x="38" y="33" width="26" height="34" rx="4" :fill="fill" />
    </template>
    <template v-else-if="type === 'LINEAR_MOTOR'">
      <rect x="6" y="60" width="88" height="12" rx="2" />
      <rect
        v-for="i in 7"
        :key="i"
        :x="9 + (i - 1) * 12.5"
        y="63"
        width="7"
        height="6"
        fill="currentColor"
        stroke="none"
        opacity="0.35"
      />
      <rect x="30" y="36" width="40" height="22" rx="4" :fill="fill" />
      <path d="M18 28h-10M8 28l5-4M8 28l5 4M82 28h10M92 28l-5-4M92 28l-5 4" stroke-width="1.6" />
    </template>
    <template v-else-if="type === 'VACUUM_CUP'">
      <line x1="50" y1="8" x2="50" y2="44" stroke-width="5" />
      <rect x="40" y="38" width="20" height="10" rx="2" />
      <path d="M28 74 L72 74 L62 48 L38 48 Z" :fill="fill" />
      <path d="M36 84h28M42 92h16" stroke-width="1.6" stroke-dasharray="3 3" />
    </template>
    <template v-else-if="type === 'PNEUMATIC_CYLINDER'">
      <rect x="8" y="36" width="56" height="28" rx="4" />
      <rect x="40" y="38" width="8" height="24" rx="1" :fill="fill" />
      <line x1="48" y1="50" x2="88" y2="50" stroke-width="5" />
      <rect x="86" y="42" width="8" height="16" rx="2" />
      <circle cx="16" cy="32" r="3" />
      <circle cx="56" cy="32" r="3" />
    </template>
    <template v-else-if="type === 'CAM'">
      <line x1="46" y1="6" x2="46" y2="26" stroke-width="4" />
      <circle cx="46" cy="30" r="5" />
      <path d="M46 36 C72 36 78 62 64 78 C52 92 26 88 22 68 C18 50 30 36 46 36 Z" :fill="fill" />
      <circle cx="44" cy="62" r="4" fill="currentColor" stroke="none" />
    </template>
    <template v-else>
      <path :d="gearPath(50, 52, 36, 10)" :fill="fill" />
      <circle cx="50" cy="52" r="10" fill="var(--surface)" />
    </template>
  </g>
</template>

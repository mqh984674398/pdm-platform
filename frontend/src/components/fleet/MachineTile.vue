<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import type { FleetMachine } from '@/api/fleet'
import HealthBadge from '@/components/base/HealthBadge.vue'
import { machineHealth } from '@/composables/useFleet'
import { useLocalized } from '@/composables/useLocalized'
import { healthVar } from '@/theme/health'

const props = defineProps<{
  machine: FleetMachine
  background?: string | null
  admin?: boolean
  lifted?: boolean // the tile is being dragged: its place in the grid is held open
}>()
const emit = defineEmits<{ background: [file: File]; clearBackground: [] }>()
const { t } = useI18n()
const { lt, fmtDate } = useLocalized()
const worst = computed(() => machineHealth(props.machine))
const attention = computed(() =>
  props.machine.components.filter((c) => c.health !== 'NORMAL' && c.health !== 'UNKNOWN'),
)
const file = ref<HTMLInputElement | null>(null)
function picked(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  input.value = ''
  if (f) emit('background', f)
}
</script>

<template>
  <RouterLink
    :to="`/machine/${machine.machine_id}`"
    class="tile"
    :class="{ withBg: !!background, lifted, admin }"
    :style="background ? { '--bg': `url(${background})` } : {}"
    :data-machine="machine.machine_id"
    :data-health="worst"
    draggable="false"
  >
    <span class="bg" aria-hidden="true"></span>
    <span
      class="edge"
      :class="{ unknown: worst === 'UNKNOWN' }"
      :style="worst === 'UNKNOWN' ? {} : { background: healthVar(worst) }"
    ></span>
    <div class="head">
      <div>
        <h3>{{ lt(machine.name) }}</h3>
        <p class="sub">{{ machine.path ? lt(machine.path) : machine.line }}</p>
      </div>
      <HealthBadge :state="worst" />
    </div>
    <ul class="components" data-testid="tile-components">
      <li
        v-for="c in machine.components"
        :key="c.component_id"
        :title="`${lt(c.name)}: ${t(`health.${c.health}`)}`"
      >
        <span
          class="dot"
          :class="{ unknown: c.health === 'UNKNOWN' }"
          :style="c.health === 'UNKNOWN' ? {} : { background: healthVar(c.health) }"
        ></span>
        {{ lt(c.name) }}
      </li>
    </ul>
    <p class="foot">
      <template v-if="attention.length">{{
        t('overview.attention', { n: attention.length })
      }}</template>
      <template v-else>{{ t('overview.noAttention') }}</template>
      <span v-if="machine.as_of" class="time">{{ fmtDate(machine.as_of) }}</span>
    </p>
    <span v-if="admin" class="tools" @pointerdown.stop @click.stop>
      <button
        type="button"
        class="tool"
        data-testid="tile-background"
        @click.prevent="file?.click()"
      >
        {{ t('overview.setBackground') }}
      </button>
      <button
        v-if="background"
        type="button"
        class="tool"
        data-testid="tile-background-clear"
        @click.prevent="emit('clearBackground')"
      >
        {{ t('overview.clearBackground') }}
      </button>
      <input
        ref="file"
        type="file"
        accept="image/png,image/jpeg,image/webp"
        hidden
        data-testid="tile-background-file"
        @change="picked"
      />
    </span>
  </RouterLink>
</template>

<style scoped>
.tile {
  position: relative;
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-4) var(--space-3) calc(var(--space-4) + 4px);
  background: var(--surface);
  border-radius: var(--radius-panel);
  box-shadow: var(--shadow-panel);
  color: var(--ink);
  overflow: hidden;
  min-height: 190px;
  grid-template-rows: auto 1fr auto;
  transition: box-shadow var(--dur) var(--ease);
}
.tile.admin {
  user-select: none;
  -webkit-touch-callout: none;
}
.tile.lifted {
  opacity: 0.25; /* the floating copy is the picture; this is the slot it will drop into */
}
.bg {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
}
.tile.withBg .bg {
  background:
    linear-gradient(
      color-mix(in srgb, var(--surface) 45%, transparent),
      color-mix(in srgb, var(--surface) 60%, transparent)
    ),
    var(--bg) center / cover no-repeat;
}
.tile > :not(.bg):not(.edge) {
  position: relative;
  z-index: 1;
}
.tile:hover {
  box-shadow: var(--shadow-raised);
}
.edge {
  position: absolute;
  inset: 0 auto 0 0;
  width: 5px;
}
.edge.unknown,
.dot.unknown {
  background: var(--hatch), var(--health-unknown-soft);
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-2);
}
h3 {
  font-size: var(--text-lg);
}
.sub {
  color: var(--ink-soft);
  font-size: var(--text-sm);
}
.components {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  align-content: center;
  justify-content: center;
  gap: 6px 8px;
  font-size: var(--text-sm);
  color: var(--ink);
  z-index: 2; /* statuses sit on top of the background picture */
}
.components li {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--surface) 82%, transparent);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
}
.tools {
  position: absolute;
  right: var(--space-3);
  bottom: 34px;
  display: flex;
  gap: 6px;
  opacity: 0;
  transition: opacity var(--dur) var(--ease);
}
.tile:hover .tools,
.tile:focus-within .tools {
  opacity: 1;
}
.tool {
  font: inherit;
  font-size: var(--text-xs);
  padding: 2px 8px;
  border-radius: var(--radius-control);
  border: 1px solid var(--line-strong);
  background: var(--surface);
  color: var(--ink);
  cursor: pointer;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.foot {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-xs);
  color: var(--ink-faint);
  border-top: 1px solid var(--line);
  padding-top: var(--space-2);
}
</style>

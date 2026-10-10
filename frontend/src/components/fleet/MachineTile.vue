<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import type { FleetMachine } from '@/api/fleet'
import HealthBadge from '@/components/base/HealthBadge.vue'
import { machineHealth } from '@/composables/useFleet'
import { useLocalized } from '@/composables/useLocalized'
import { healthVar } from '@/theme/health'

const props = defineProps<{ machine: FleetMachine }>()
const { t } = useI18n()
const { lt, fmtDate } = useLocalized()
const worst = computed(() => machineHealth(props.machine))
const attention = computed(() =>
  props.machine.components.filter((c) => c.health !== 'NORMAL' && c.health !== 'UNKNOWN'),
)
</script>

<template>
  <RouterLink
    :to="`/machine/${machine.machine_id}`"
    class="tile"
    :data-machine="machine.machine_id"
    :data-health="worst"
  >
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
    <ul class="components">
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
  transition: box-shadow var(--dur) var(--ease);
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
  gap: 4px 14px;
  font-size: var(--text-sm);
  color: var(--ink-soft);
}
.components li {
  display: flex;
  align-items: center;
  gap: 6px;
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

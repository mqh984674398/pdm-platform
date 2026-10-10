<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { HealthState } from '@/api/contracts'
import { HEALTH_RANK, HEALTH_STATES, healthVar } from '@/theme/health'

const props = defineProps<{ states: HealthState[] }>()
const { t } = useI18n()
const counts = computed(() =>
  [...HEALTH_STATES]
    .sort((a, b) => HEALTH_RANK[a] - HEALTH_RANK[b])
    .map((s) => ({ s, n: props.states.filter((x) => x === s).length })),
)
</script>

<template>
  <div class="strip-wrap">
    <div
      class="strip"
      role="img"
      :aria-label="counts.map((c) => `${t(`health.${c.s}`)} ${c.n}`).join(', ')"
    >
      <span
        v-for="c in counts.filter((x) => x.n > 0)"
        :key="c.s"
        :class="{ unknown: c.s === 'UNKNOWN' }"
        :style="{ flexGrow: c.n, background: c.s === 'UNKNOWN' ? undefined : healthVar(c.s) }"
      ></span>
    </div>
    <ul class="legend">
      <li v-for="c in counts" :key="c.s" :data-count-for="c.s">
        <span class="n">{{ c.n }}</span>
        <span
          class="mark"
          :class="{ unknown: c.s === 'UNKNOWN' }"
          :style="{ background: c.s === 'UNKNOWN' ? undefined : healthVar(c.s) }"
        ></span>
        {{ t(`health.${c.s}`) }}
      </li>
    </ul>
  </div>
</template>

<style scoped>
.strip {
  display: flex;
  gap: 3px;
  height: 14px;
}
.strip span {
  border-radius: 3px;
  min-width: 6px;
}
.unknown {
  background: var(--hatch), var(--health-unknown-soft);
}
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-5);
  list-style: none;
  padding: 0;
  margin: var(--space-3) 0 0;
  color: var(--ink-soft);
  font-size: var(--text-sm);
}
.legend li {
  display: flex;
  align-items: center;
  gap: 6px;
}
.n {
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--ink);
  line-height: 1;
}
.mark {
  width: 9px;
  height: 9px;
  border-radius: 2px;
}
</style>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { HealthState } from '@/api/contracts'

const props = withDefaults(defineProps<{ state: HealthState; size?: 'sm' | 'md' }>(), {
  size: 'md',
})
const { t } = useI18n()
const label = computed(() => t(`health.${props.state}`))
const title = computed(() => (props.state === 'UNKNOWN' ? t('health.unknownHint') : label.value))
</script>

<template>
  <span
    class="health-badge"
    :class="[`is-${state.toLowerCase()}`, `size-${size}`]"
    :title="title"
    :data-health="state"
  >
    <span class="mark" aria-hidden="true"></span>
    <span class="label">{{ label }}</span>
  </span>
</template>

<style scoped>
.health-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 9px 2px 7px;
  border-radius: 999px;
  font-weight: 500;
  white-space: nowrap;
  color: var(--ink);
}
.size-md {
  font-size: var(--text-sm);
}
.size-sm {
  font-size: var(--text-xs);
  padding: 1px 7px 1px 5px;
}
.mark {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex: none;
}
.is-normal {
  background: var(--health-normal-soft);
}
.is-normal .mark {
  background: var(--health-normal);
}
.is-watch {
  background: var(--health-watch-soft);
}
.is-watch .mark {
  background: var(--health-watch);
}
.is-warning {
  background: var(--health-warning-soft);
}
.is-warning .mark {
  background: var(--health-warning);
  border-radius: 2px;
  transform: rotate(45deg) scale(0.85);
}
.is-critical {
  background: var(--health-critical-soft);
}
.is-critical .mark {
  background: var(--health-critical);
  border-radius: 1px;
}
/* UNKNOWN means "no evidence": hatched and outlined, never a filled severity color */
.is-unknown {
  background: var(--health-unknown-soft);
  color: var(--ink-soft);
}
.is-unknown .mark {
  background: var(--hatch);
  box-shadow: inset 0 0 0 1px var(--health-unknown);
}
</style>

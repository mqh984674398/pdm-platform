<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <span class="sim-badge" :title="t('sim.hint')" data-simulated="true">
    <svg viewBox="0 0 12 12" aria-hidden="true">
      <path d="M2 10 L6 2 L10 10 Z" fill="none" stroke="currentColor" stroke-width="1.4" />
      <path d="M6 5.5 V7.6 M6 8.8 V9" stroke="currentColor" stroke-width="1.3" />
    </svg>
    {{ t('sim.badge') }}
  </span>
</template>

<style scoped>
.sim-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px;
  border-radius: var(--radius-control);
  border: 1px dashed var(--sim-ink);
  background: var(--sim-soft);
  color: var(--sim-ink);
  font-size: var(--text-xs);
  font-weight: 500;
  white-space: nowrap;
}
svg {
  width: 12px;
  height: 12px;
}
</style>

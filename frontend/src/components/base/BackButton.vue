<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { RouterLink, type RouteLocationRaw } from 'vue-router'

defineProps<{ to: RouteLocationRaw; target: string }>()
const { t } = useI18n()
</script>

<template>
  <RouterLink :to="to" class="back" data-testid="back-button">
    <svg viewBox="0 0 16 16" aria-hidden="true">
      <path d="M10 3 5 8l5 5" fill="none" stroke="currentColor" stroke-width="1.6" />
    </svg>
    {{ t('common.backTo', { target }) }}
  </RouterLink>
</template>

<style scoped>
.back {
  justify-self: start;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px 4px 6px;
  border-radius: var(--radius-control);
  border: 1px solid var(--line-strong);
  background: var(--surface);
  color: var(--ink);
  font-size: var(--text-sm);
}
.back:hover {
  background: var(--accent-soft);
}
svg {
  width: 14px;
  height: 14px;
}
</style>

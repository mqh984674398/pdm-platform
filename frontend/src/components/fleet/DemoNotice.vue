<script setup lang="ts">
import SimBadge from '@/components/base/SimBadge.vue'
import { useLocalized } from '@/composables/useLocalized'
import type { LocalizedText } from '@/api/contracts'

defineProps<{ basis: LocalizedText }>()
const { lt } = useLocalized()
</script>

<template>
  <p class="notice" data-testid="demo-notice">
    <SimBadge />
    <span>{{ lt(basis) }}</span>
  </p>
</template>

<style scoped>
.notice {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
  color: var(--ink-soft);
  font-size: var(--text-sm);
}
</style>

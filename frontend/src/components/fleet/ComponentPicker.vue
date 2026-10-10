<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { ComponentInstance, Machine } from '@/api/contracts'
import { useLocalized } from '@/composables/useLocalized'

defineProps<{
  machines: { machine: Machine; components: ComponentInstance[] }[]
  selected: string | null
}>()
defineEmits<{ pick: [id: string] }>()
const { t } = useI18n()
const { lt } = useLocalized()
</script>

<template>
  <nav class="list" :aria-label="t('component.pick')">
    <div v-for="m in machines" :key="m.machine.machine_id" class="group">
      <h2>{{ lt(m.machine.name) }}</h2>
      <button
        v-for="c in m.components"
        :key="c.component_id"
        type="button"
        class="item"
        :class="{ active: c.component_id === selected }"
        :data-testid="`pick-${c.component_id}`"
        @click="$emit('pick', c.component_id)"
      >
        {{ lt(c.name) }}
      </button>
    </div>
  </nav>
</template>

<style scoped>
.list {
  display: grid;
  gap: var(--space-3);
  max-height: 70vh;
  overflow: auto;
}
h2 {
  font-size: var(--text-xs);
  color: var(--ink-soft);
  margin-bottom: var(--space-1);
}
.item {
  display: block;
  width: 100%;
  text-align: left;
  border: 0;
  background: none;
  padding: 4px 8px;
  border-radius: var(--radius-control);
  color: var(--ink);
  cursor: pointer;
}
.item.active {
  background: var(--accent-soft, var(--steel-200));
  font-weight: 500;
}
</style>

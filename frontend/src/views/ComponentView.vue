<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute } from 'vue-router'
import PanelBox from '@/components/base/PanelBox.vue'
import ComponentDetail from '@/components/fleet/ComponentDetail.vue'
import DemoNotice from '@/components/fleet/DemoNotice.vue'
import EvidenceTrail from '@/components/fleet/EvidenceTrail.vue'
import { useFleet } from '@/composables/useFleet'
import { useLocalized } from '@/composables/useLocalized'
import { healthVar } from '@/theme/health'

const { t } = useI18n()
const { lt } = useLocalized()
const route = useRoute()
const { fleet, machines, findComponent } = useFleet()
const found = computed(() => {
  const id = route.params.id as string | undefined
  return (
    findComponent(id) ??
    (machines.value[0]
      ? { machine: machines.value[0], component: machines.value[0].components[0] }
      : null)
  )
})
</script>

<template>
  <div v-if="fleet && found" class="page">
    <header class="page-head">
      <h1>{{ t('nav.component') }}</h1>
      <DemoNotice :basis="fleet.health_basis" />
    </header>
    <div class="layout">
      <nav class="list" :aria-label="t('component.pick')">
        <div v-for="m in machines" :key="m.machine_id" class="group">
          <h2>{{ lt(m.name) }}</h2>
          <RouterLink
            v-for="c in m.components"
            :key="c.component_id"
            :to="`/component/${c.component_id}`"
            class="item"
            :class="{ active: c.component_id === found.component.component_id }"
          >
            <span
              class="dot"
              :class="{ unknown: c.health === 'UNKNOWN' }"
              :style="c.health === 'UNKNOWN' ? {} : { background: healthVar(c.health) }"
            ></span>
            {{ lt(c.name) }}
          </RouterLink>
        </div>
      </nav>
      <PanelBox>
        <p class="crumb" data-testid="component-crumb">
          <span v-if="found.machine.path">{{ lt(found.machine.path) }} / </span>
          <RouterLink
            :to="`/machine/${found.machine.machine_id}?c=${found.component.component_id}`"
            >{{ lt(found.machine.name) }}</RouterLink
          >
        </p>
        <ComponentDetail :component="found.component" />
        <EvidenceTrail class="evidence" :component-id="found.component.component_id" />
      </PanelBox>
    </div>
  </div>
</template>

<style scoped>
.page {
  display: grid;
  gap: var(--space-4);
  max-width: 1200px;
}
.page-head {
  display: grid;
  gap: var(--space-2);
}
h1 {
  font-size: var(--text-xl);
}
.layout {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: var(--space-4);
  align-items: start;
}
.group {
  margin-bottom: var(--space-3);
}
.group h2 {
  font-size: var(--text-xs);
  color: var(--ink-faint);
  font-weight: 500;
  margin-bottom: 2px;
}
.item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 4px var(--space-2);
  border-radius: var(--radius-control);
  color: var(--ink);
  font-size: var(--text-sm);
}
.item.active {
  background: var(--accent-soft);
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.dot.unknown {
  background: var(--hatch), var(--health-unknown-soft);
}
.evidence {
  margin-top: var(--space-4);
}
.crumb {
  font-size: var(--text-sm);
  margin-bottom: var(--space-3);
}
@media (max-width: 860px) {
  .layout {
    grid-template-columns: 1fr;
  }
}
</style>

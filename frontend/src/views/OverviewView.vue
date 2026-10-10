<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import DemoNotice from '@/components/fleet/DemoNotice.vue'
import HealthStrip from '@/components/fleet/HealthStrip.vue'
import MachineTile from '@/components/fleet/MachineTile.vue'
import { useFleet } from '@/composables/useFleet'

const { t } = useI18n()
const { fleet, machines, error } = useFleet()
const allStates = computed(() => machines.value.flatMap((m) => m.components.map((c) => c.health)))
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>{{ t('nav.overview') }}</h1>
      <DemoNotice v-if="fleet" :basis="fleet.health_basis" />
    </header>
    <p v-if="error" class="error">{{ t('common.loadFailed') }}</p>
    <template v-else-if="fleet">
      <section class="summary" :aria-label="t('overview.summary')">
        <p class="summary-title">
          {{
            t('overview.summaryLine', { machines: machines.length, components: allStates.length })
          }}
        </p>
        <HealthStrip :states="allStates" />
      </section>
      <section class="grid">
        <MachineTile v-for="m in machines" :key="m.machine_id" :machine="m" />
      </section>
    </template>
  </div>
</template>

<style scoped>
.page {
  display: grid;
  gap: var(--space-5);
  max-width: 1280px;
}
.page-head {
  display: grid;
  gap: var(--space-2);
}
h1 {
  font-size: var(--text-xl);
}
.summary {
  padding: var(--space-4) var(--space-5);
  background: var(--surface);
  border-radius: var(--radius-panel);
  box-shadow: var(--shadow-panel);
}
.summary-title {
  color: var(--ink-soft);
  font-size: var(--text-sm);
  margin-bottom: var(--space-3);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: var(--space-4);
}
.error {
  color: var(--health-critical);
}
</style>

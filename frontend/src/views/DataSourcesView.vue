<script setup lang="ts">
/**
 * Data sources (administrators only, D-049): where the platform reads telemetry from. The production
 * TDengine sources are added, tested and removed here; the Configuration workbench only picks one of
 * them for a component. The simulation database is defined by the datasources file and listed for
 * reference.
 */
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import DataSourcePanel from '@/components/studio/DataSourcePanel.vue'
import RunModeCard from '@/components/studio/RunModeCard.vue'

const { t } = useI18n()
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>{{ t('nav.datasources') }}</h1>
      <p class="lede">{{ t('datasources.lede') }}</p>
    </header>
    <RunModeCard />
    <DataSourcePanel />
    <p class="st-note">
      {{ t('datasources.next') }}
      <RouterLink to="/plant">{{ t('nav.plant') }}</RouterLink>
    </p>
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
.lede {
  color: var(--ink-soft);
  font-size: var(--text-sm);
}
</style>

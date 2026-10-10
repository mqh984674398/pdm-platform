<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import type { FleetComponent, HealthTrend } from '@/api/fleet'
import HealthBadge from '@/components/base/HealthBadge.vue'
import { useLocalized } from '@/composables/useLocalized'
import TrendSparkline from './TrendSparkline.vue'

defineProps<{ component: FleetComponent; compact?: boolean }>()
const { t } = useI18n()
const { lt, fmtDate } = useLocalized()

function last(tr: HealthTrend) {
  return tr.points[tr.points.length - 1]?.value
}
</script>

<template>
  <article class="detail" :data-detail="component.component_id">
    <header>
      <div>
        <p class="type">{{ t(`types.${component.type}`) }}</p>
        <h2>{{ lt(component.name) }}</h2>
      </div>
      <HealthBadge :state="component.health" />
    </header>
    <p class="reason" data-testid="health-reason">{{ lt(component.reason) }}</p>
    <p v-if="component.common_cause" class="common" data-testid="common-cause">
      <strong>{{ t('component.commonCause') }}</strong>
      {{ lt(component.common_cause.note) }}
    </p>
    <RouterLink
      v-if="component.open_alarms"
      :to="`/alarms?c=${component.component_id}`"
      class="alarms"
      data-testid="open-alarms"
      >{{ t('component.openAlarms', { n: component.open_alarms }) }}</RouterLink
    >

    <section v-if="component.trend.length">
      <h3>{{ t('component.trend') }}</h3>
      <div v-for="tr in component.trend" :key="tr.rule_id" class="trend" :data-trend="tr.rule_id">
        <div class="trend-head">
          <span>{{ lt(tr.name) }}</span>
          <span class="value">{{ last(tr)?.toFixed(1) }}</span>
        </div>
        <TrendSparkline
          :points="tr.points.map((p) => [p.ts, p.value] as [string, number])"
          :label="lt(tr.name)"
          :thresholds="[tr.watch, tr.warning].filter((x): x is number => x !== null)"
        />
      </div>
      <p class="note">{{ t('component.bandNote') }}</p>
    </section>
    <p v-else class="empty">{{ t('component.noTelemetry') }}</p>

    <section v-if="!compact">
      <h3>{{ t('component.lifecycles') }}</h3>
      <ol class="list">
        <li v-for="lc in component.lifecycles" :key="lc.lifecycle_id">
          <span class="mono">{{ lc.lifecycle_id }}</span>
          <span>{{ t(`lifecycle.${lc.status}`) }}</span>
          <span class="muted">{{ fmtDate(lc.installed_at, false) }}</span>
        </li>
      </ol>
      <p v-if="!component.lifecycles.length" class="empty">{{ t('component.noLifecycle') }}</p>
    </section>

    <section>
      <h3>{{ t('component.maintenance') }}</h3>
      <ol class="list">
        <li v-for="e in component.maintenance" :key="e.event_id">
          <span>{{ t(`maintenanceType.${e.type}`) }}</span>
          <span class="muted">{{ fmtDate(e.performed_at) }}</span>
        </li>
      </ol>
      <p v-if="!component.maintenance.length" class="empty">{{ t('component.noMaintenance') }}</p>
    </section>

    <RouterLink v-if="compact" :to="`/component/${component.component_id}`" class="more">
      {{ t('component.openHistory') }}
    </RouterLink>
  </article>
</template>

<style scoped>
.detail {
  display: grid;
  gap: var(--space-4);
}
header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-2);
}
.type {
  font-size: var(--text-xs);
  color: var(--ink-faint);
}
h2 {
  font-size: var(--text-lg);
}
h3 {
  font-size: var(--text-sm);
  color: var(--ink-soft);
  margin-bottom: var(--space-2);
}
.alarms {
  font-size: var(--text-sm);
}
.common {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-left: 3px solid var(--health-warning);
  background: var(--surface-inset);
  font-size: var(--text-sm);
}
.common strong {
  display: block;
}
.reason {
  padding: var(--space-3);
  background: var(--surface-inset);
  border-radius: var(--radius-control);
}
.trend {
  margin-bottom: var(--space-3);
}
.trend-head {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-sm);
}
.value {
  font-weight: 600;
}
.note,
.muted,
.empty {
  color: var(--ink-faint);
  font-size: var(--text-xs);
}
.list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 6px;
  font-size: var(--text-sm);
}
.list li {
  display: flex;
  gap: var(--space-3);
  align-items: baseline;
}
.mono {
  font-variant-numeric: tabular-nums;
}
.more {
  font-size: var(--text-sm);
}
</style>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import type { FleetComponent } from '@/api/fleet'
import HealthBadge from '@/components/base/HealthBadge.vue'
import { useLocalized } from '@/composables/useLocalized'
import TrendSparkline from './TrendSparkline.vue'

defineProps<{ component: FleetComponent; compact?: boolean }>()
const { t } = useI18n()
const { lt, fmtDate } = useLocalized()

function signalName(c: FleetComponent, id: string) {
  return lt(c.signals.find((s) => s.signal_id === id)?.name)
}
function last(points: [string, number][]) {
  return points[points.length - 1]?.[1]
}
function fmt(v: number | undefined, unit: string) {
  if (v === undefined) return ''
  return unit === 's'
    ? `${(v * 1000).toFixed(0)} ms`
    : `${v.toFixed(2)} ${unit === '%' ? '%' : unit}`
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
    <p class="reason">{{ lt(component.reason) }}</p>

    <section v-if="component.trend.length">
      <h3>{{ t('component.trend') }}</h3>
      <div v-for="tr in component.trend" :key="tr.signal_id" class="trend">
        <div class="trend-head">
          <span>{{ signalName(component, tr.signal_id) }}</span>
          <span class="value">{{ fmt(last(tr.points), tr.unit) }}</span>
        </div>
        <TrendSparkline :points="tr.points" :label="signalName(component, tr.signal_id)" />
      </div>
      <p class="note">{{ t('component.bandNote', { regime: component.trend_regime ?? '' }) }}</p>
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

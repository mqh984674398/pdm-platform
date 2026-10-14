<script setup lang="ts">
/** The evidence behind a component's current health (T020, L6-04): rule hits, reference, alarms, impact. */
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import type { ComponentHealthReport } from '@/api/fleet'
import { monitoringApi } from '@/api/monitoring'
import { useLocalized } from '@/composables/useLocalized'

const props = defineProps<{ componentId: string }>()
const { t } = useI18n()
const { lt, fmtDate } = useLocalized()
const report = ref<ComponentHealthReport | null>(null)
const failed = ref(false)

watch(
  () => props.componentId,
  async (id) => {
    report.value = null
    failed.value = false
    try {
      report.value = await monitoringApi.health(id)
    } catch {
      failed.value = true
    }
  },
  { immediate: true },
)
</script>

<template>
  <section class="trail" data-testid="evidence-trail">
    <h3>{{ t('evidence.title') }}</h3>
    <p v-if="failed" class="empty">{{ t('common.loadFailed') }}</p>
    <template v-else-if="report">
      <p class="meta">
        {{
          t('evidence.meta', {
            rules: report.decision.meta.model_version,
            features: report.decision.meta.feature_version,
            time: fmtDate(report.decision.meta.data_window.end),
          })
        }}
      </p>
      <p class="safety" :data-status="report.decision.safety_status" data-testid="safety-status">
        {{ t(`evidence.safety.${report.decision.safety_status}`) }}
        <template v-if="report.decision.safety_unevaluated.length">
          · {{ report.decision.safety_unevaluated.join(', ') }}
        </template>
      </p>
      <ol v-if="report.evidence.length" class="list">
        <li v-for="e in report.evidence" :key="e.evidence_id" :data-source="e.source">
          <span class="src">{{ t(`evidence.type.${e.evidence_type}`) }}</span>
          <span v-if="e.quality_status !== 'OK'" class="src">{{
            t(`evidence.quality.${e.quality_status}`)
          }}</span>
          <span class="text">{{ lt(e.summary) }}</span>
          <span class="ref">{{ e.result_ref }}</span>
        </li>
      </ol>
      <p v-else class="empty">{{ t('evidence.none') }}</p>
      <p class="links">
        <RouterLink :to="`/baselines?c=${componentId}`">{{ t('nav.baselines') }}</RouterLink>
        <RouterLink :to="`/alarms?c=${componentId}`">{{ t('nav.alarms') }}</RouterLink>
        <RouterLink :to="`/maintenance?c=${componentId}`">{{ t('nav.maintenance') }}</RouterLink>
      </p>
    </template>
  </section>
</template>

<style scoped>
.trail {
  display: grid;
  gap: var(--space-2);
}
h3 {
  font-size: var(--text-sm);
  color: var(--ink-soft);
}
.safety[data-status='NOT_EVALUATED'],
.safety[data-status='VIOLATED'] {
  font-weight: 600;
  color: var(--danger, #c0392b);
}
.meta,
.empty {
  font-size: var(--text-xs);
  color: var(--ink-faint);
}
.list {
  list-style: none;
  display: grid;
  gap: var(--space-2);
}
.list li {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  gap: 2px var(--space-2);
  font-size: var(--text-sm);
}
.src {
  color: var(--ink-soft);
  font-size: var(--text-xs);
  padding-top: 2px;
}
.ref {
  grid-column: 2;
  font-size: var(--text-xs);
  color: var(--ink-faint);
  overflow-wrap: anywhere;
}
.links {
  display: flex;
  gap: var(--space-3);
  font-size: var(--text-sm);
}
</style>

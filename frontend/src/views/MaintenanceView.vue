<script setup lang="ts">
/** Maintenance timeline (UI-08, T019): events, post-maintenance workflows and their steps. */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import type { MaintenanceEvent, MaintenanceWorkflow } from '@/api/contracts'
import { monitoringApi } from '@/api/monitoring'
import PanelBox from '@/components/base/PanelBox.vue'
import SimBadge from '@/components/base/SimBadge.vue'
import ComponentPicker from '@/components/fleet/ComponentPicker.vue'
import { useComponents } from '@/composables/useComponents'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { machines, error: loadError } = useComponents(monitoringApi)
const componentId = computed<string | null>(
  () =>
    (route.query.c as string | undefined) ?? machines.value[0]?.components[0]?.component_id ?? null,
)
const events = ref<MaintenanceEvent[]>([])
const workflows = ref<MaintenanceWorkflow[]>([])
watch(
  componentId,
  async (cid) => {
    events.value = workflows.value = []
    if (!cid) return
    ;[events.value, workflows.value] = await Promise.all([
      monitoringApi.events(cid).catch(() => []),
      monitoringApi.workflows(cid).catch(() => []),
    ])
  },
  { immediate: true },
)
const items = computed(() =>
  [...events.value]
    .sort((a, b) => b.performed_at.localeCompare(a.performed_at))
    .map((e) => ({
      event: e,
      workflow: workflows.value.find((w) => w.event_id === e.event_id) ?? null,
    })),
)
const fmt = (s: string) => s.slice(0, 16).replace('T', ' ')
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>{{ t('nav.maintenance') }}</h1>
      <p class="lede">{{ t('maintenance.lede') }}</p>
    </header>
    <p v-if="loadError" class="error">{{ t('common.loadFailed') }}</p>
    <div v-else class="layout">
      <ComponentPicker
        :machines="machines"
        :selected="componentId"
        @pick="(id) => router.replace({ query: { c: id } })"
      />
      <PanelBox :title="componentId ?? ''">
        <template #actions><SimBadge v-if="events.some((e) => e.is_simulated)" /></template>
        <p v-if="!items.length" class="empty">{{ t('maintenance.none') }}</p>
        <ol class="timeline" data-testid="maintenance-timeline">
          <li v-for="{ event, workflow } in items" :key="event.event_id" class="entry">
            <div class="when">{{ fmt(event.performed_at) }} {{ t('common.utc') }}</div>
            <div class="what">
              <strong>{{ t(`maintenanceType.${event.type}`) }}</strong>
              <span class="meta"
                >{{ event.lifecycle_id
                }}{{ event.new_lifecycle_id ? ` → ${event.new_lifecycle_id}` : '' }}</span
              >
              <p v-if="event.notes" class="notes">{{ event.notes }}</p>
              <ol v-if="workflow" class="steps" :data-testid="`workflow-${event.event_id}`">
                <li
                  v-for="(s, i) in workflow.transitions"
                  :key="i"
                  :class="['step', s.to_state.toLowerCase()]"
                >
                  <span class="state">{{ t(`maintenance.states.${s.to_state}`) }}</span>
                  <span class="meta">{{ fmt(s.at) }} · {{ s.by }}</span>
                  <span v-if="s.comment" class="comment">{{ s.comment }}</span>
                </li>
              </ol>
              <p v-else class="meta">{{ t('maintenance.noWorkflow') }}</p>
            </div>
          </li>
        </ol>
      </PanelBox>
    </div>
  </div>
</template>

<style scoped>
.page {
  display: grid;
  gap: var(--space-5);
  max-width: 1400px;
}
.page-head {
  display: grid;
  gap: var(--space-2);
}
h1 {
  font-size: var(--text-xl);
}
.lede,
.empty,
.meta,
.comment {
  color: var(--ink-soft);
  font-size: var(--text-sm);
}
.layout {
  display: grid;
  grid-template-columns: 240px 1fr;
  gap: var(--space-4);
  align-items: start;
}
.timeline {
  list-style: none;
  padding: 0;
  display: grid;
  gap: var(--space-4);
}
.entry {
  display: grid;
  grid-template-columns: 150px 1fr;
  gap: var(--space-3);
  border-left: 2px solid var(--chart-grid);
  padding-left: var(--space-3);
}
.when {
  font-variant-numeric: tabular-nums;
  font-size: var(--text-sm);
}
.steps {
  list-style: none;
  padding: 0;
  margin-top: var(--space-2);
  display: grid;
  gap: var(--space-1);
}
.step {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
  align-items: baseline;
}
.state {
  font-size: var(--text-sm);
  font-weight: 500;
}
.step.review_required .state {
  color: var(--health-warning);
}
.step.normal_monitoring .state {
  color: var(--health-normal);
}
.notes {
  font-size: var(--text-sm);
}
.error {
  color: var(--health-critical);
}
@media (max-width: 800px) {
  .layout,
  .entry {
    grid-template-columns: 1fr;
  }
}
</style>

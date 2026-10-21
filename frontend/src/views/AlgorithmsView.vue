<script setup lang="ts">
/**
 * Algorithm models (administrators, D-050): the algorithm library the decision engine can run, the
 * deep-model adapters (LSTM, D-RCNN) with their availability, registered plugins, and where each
 * algorithm is used. Read-only: an algorithm is selected for a component in its configuration draft.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import type { AlgorithmModels } from '@/api/contracts'
import { monitoringApi } from '@/api/monitoring'
import PanelBox from '@/components/base/PanelBox.vue'
import { useLocalized } from '@/composables/useLocalized'

const { t } = useI18n()
const { lt } = useLocalized()

const data = ref<AlgorithmModels | null>(null)
const failed = ref(false)
const category = ref('ALL')
const open = ref<string | null>(null)

onMounted(async () => {
  try {
    data.value = await monitoringApi.algorithmModels()
  } catch {
    failed.value = true
  }
})

const categories = computed(() => [
  'ALL',
  ...new Set((data.value?.algorithms ?? []).map((a) => a.spec.category)),
])
const shown = computed(() =>
  (data.value?.algorithms ?? []).filter(
    (a) => category.value === 'ALL' || a.spec.category === category.value,
  ),
)
function state(a: AlgorithmModels['algorithms'][number]): 'ready' | 'planned' | 'unavailable' {
  if (!a.spec.implemented) return 'planned'
  if (a.adapter_available === false) return 'unavailable'
  return 'ready'
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>{{ t('nav.algorithms') }}</h1>
      <p class="lede">{{ t('algorithms.lede') }}</p>
    </header>
    <p v-if="failed" class="error">{{ t('common.loadFailed') }}</p>

    <PanelBox v-if="data" :title="t('algorithms.library')">
      <div class="row filter" role="group" :aria-label="t('algorithms.category')">
        <button
          v-for="c in categories"
          :key="c"
          type="button"
          class="st-button"
          :aria-pressed="category === c"
          :data-testid="`alg-cat-${c}`"
          @click="category = c"
        >
          {{ t(`algorithms.cat.${c}`) }}
        </button>
      </div>
      <table class="st-table" data-testid="alg-table">
        <thead>
          <tr>
            <th>{{ t('algorithms.name') }}</th>
            <th>{{ t('algorithms.category') }}</th>
            <th>{{ t('algorithms.evidence') }}</th>
            <th>{{ t('algorithms.status') }}</th>
            <th>{{ t('algorithms.usedBy') }}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <template v-for="a in shown" :key="a.spec.algorithm_id">
            <tr :data-alg="a.spec.algorithm_id">
              <td>
                {{ lt(a.spec.name) }}
                <span class="st-note st-mono">{{ a.spec.algorithm_id }}</span>
              </td>
              <td>{{ t(`algorithms.cat.${a.spec.category}`) }}</td>
              <td>{{ t(`algorithms.ev.${a.spec.evidence_type}`) }}</td>
              <td>
                <span :class="`st-badge ${state(a)}`" :data-state="state(a)">
                  {{ t(`algorithms.state.${state(a)}`) }}
                </span>
              </td>
              <td>
                {{ t('algorithms.uses', { n: a.active_uses.length, d: a.draft_uses }) }}
              </td>
              <td>
                <button
                  type="button"
                  class="link"
                  :aria-expanded="open === a.spec.algorithm_id"
                  @click="open = open === a.spec.algorithm_id ? null : a.spec.algorithm_id"
                >
                  {{ t('algorithms.details') }}
                </button>
              </td>
            </tr>
            <tr v-if="open === a.spec.algorithm_id" class="detail">
              <td colspan="6">
                <p v-if="a.spec.boundary">{{ lt(a.spec.boundary) }}</p>
                <ul class="st-note">
                  <li v-if="a.spec.component_types">
                    {{ t('algorithms.types') }}:
                    {{ a.spec.component_types.map((x) => t(`types.${x}`)).join(' / ') }}
                  </li>
                  <li v-else>{{ t('algorithms.allTypes') }}</li>
                  <li v-if="a.spec.required_quantities.length">
                    {{ t('algorithms.needs') }}: {{ a.spec.required_quantities.join(', ') }}
                  </li>
                  <li v-if="a.spec.min_sampling_hz">
                    {{ t('algorithms.minHz', { hz: a.spec.min_sampling_hz }) }}
                  </li>
                  <li v-if="a.spec.needs_labels">{{ t('algorithms.needsLabels') }}</li>
                  <li v-if="a.spec.needs_validated_model">{{ t('algorithms.needsModel') }}</li>
                  <li v-if="a.adapter_available === false">
                    {{ t('algorithms.adapterOff')
                    }}{{ a.adapter_reason ? `: ${a.adapter_reason}` : '' }}
                  </li>
                </ul>
                <ul v-if="a.active_uses.length" class="st-note" data-testid="alg-uses">
                  <li v-for="u in a.active_uses" :key="u.config_id + u.stage_id">
                    <span class="st-mono">{{
                      `${u.component_id} · v${u.version} · ${u.stage_id}`
                    }}</span>
                    {{ u.enabled ? '' : `(${t('algorithms.off')})` }}
                  </li>
                </ul>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </PanelBox>

    <PanelBox v-if="data" :title="t('algorithms.deep')">
      <p class="st-note">{{ t('algorithms.deepNote') }}</p>
      <ul class="st-stack" data-testid="alg-deep">
        <li v-for="d in data.deep_adapters" :key="d.family">
          <strong>{{ d.family.toUpperCase() }}</strong> ·
          <span :class="d.available ? 'ok' : 'error'">
            {{ d.available ? t('algorithms.state.ready') : t('algorithms.state.unavailable') }}
          </span>
          <span v-if="d.unavailable_reason" class="st-note"> · {{ d.unavailable_reason }}</span>
          <div class="st-note">
            {{ t(`algorithms.input.${d.contract.kind}`) }} ·
            {{
              d.contract.kind === 'WINDOW_SEQUENCE'
                ? t('algorithms.seq', { n: d.contract.sequence_length })
                : t('algorithms.wave', { hz: d.contract.min_sampling_hz ?? '—' })
            }}
            ·
            {{
              t('algorithms.minSamples', {
                n: d.contract.min_training_samples,
                f: d.contract.min_fault_samples,
              })
            }}
          </div>
        </li>
      </ul>
    </PanelBox>

    <PanelBox v-if="data" :title="t('algorithms.plugins')">
      <p v-if="!data.plugins.length" class="st-note" data-testid="alg-no-plugins">
        {{ t('algorithms.noPlugins') }}
      </p>
      <ul v-else class="st-stack">
        <li v-for="p in data.plugins" :key="p.plugin_id + p.version">
          {{ lt(p.name) }} <span class="st-mono st-note">{{ p.plugin_id }}@{{ p.version }}</span>
          <div class="st-note">{{ lt(p.description) }}</div>
        </li>
      </ul>
    </PanelBox>

    <p class="st-note">
      {{ t('algorithms.next') }}
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
.filter {
  margin-bottom: var(--space-3);
  flex-wrap: wrap;
}
.detail td {
  background: var(--surface-2, transparent);
}
</style>

<script setup lang="ts">
/** Parameter optimization comparison (UI-10, T025): champion vs candidates scored on replay. */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import type { CandidateResult, OptimizationReadiness, OptimizationRun } from '@/api/contracts'
import { MonitoringApiError, monitoringApi } from '@/api/monitoring'
import PanelBox from '@/components/base/PanelBox.vue'
import SimBadge from '@/components/base/SimBadge.vue'
import { useLocalized } from '@/composables/useLocalized'

const { t } = useI18n()
const { fmtDate, lt } = useLocalized()

const run = ref<OptimizationRun | null>(null)
const ready = ref<OptimizationReadiness | null>(null)
const candidates = ref(12)
const busy = ref(false)
const failed = ref(false)
const failReason = ref('')
const selected = ref<string | null>(null)
const proposed = ref<string | null>(null)
const proposeFailed = ref<string | null>(null)

async function propose(id: string) {
  proposeFailed.value = null
  try {
    proposed.value = (
      await monitoringApi.proposeConfig(id, `Recommended by ${run.value?.run_id}`)
    ).version_id
  } catch (e) {
    proposeFailed.value =
      e instanceof MonitoringApiError && e.body ? e.body.message.en : t('optimization.failed')
  }
}

onMounted(async () => {
  ready.value = await monitoringApi.optimizationReadiness().catch(() => null)
  try {
    run.value = await monitoringApi.latestOptimization()
  } catch (e) {
    if (!(e instanceof MonitoringApiError && e.status === 404)) failed.value = true
  }
})

async function start() {
  busy.value = true
  failed.value = false
  try {
    run.value = await monitoringApi.runOptimization(candidates.value, 0)
    selected.value = run.value.recommended
  } catch (e) {
    failed.value = true
    failReason.value = e instanceof MonitoringApiError && e.body ? lt(e.body.message) : ''
  } finally {
    busy.value = false
  }
}

const pct = (c: CandidateResult) => (100 * c.metrics.ratio).toFixed(1)
const delta = (c: CandidateResult) =>
  run.value ? c.metrics.within - run.value.champion.metrics.within : 0
const signed = (n: number) => (n > 0 ? `+${n}` : String(n))
const changes = (c: CandidateResult) =>
  Object.entries(c.changes)
    .map(([k, v]) => `${k} ${v}`)
    .join(', ')

const ranked = computed(() =>
  [...(run.value?.candidates ?? [])].sort(
    (a, b) => b.metrics.within - a.metrics.within || a.metrics.over - b.metrics.over,
  ),
)
const pick = computed(() => run.value?.candidates.find((c) => c.candidate_id === selected.value))
const caseRows = computed(() => {
  if (!run.value) return []
  const other = new Map(pick.value?.metrics.cases.map((c) => [c.case_id, c]))
  return run.value.champion.metrics.cases.map((c) => ({
    champion: c,
    candidate: other.get(c.case_id),
  }))
})
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>{{ t('nav.optimization') }}</h1>
      <p class="lede">{{ t('optimization.lede') }}</p>
    </header>
    <PanelBox v-if="ready" :title="t('optimization.readiness.title')">
      <div data-testid="opt-readiness" class="readiness">
        <p>{{ t('optimization.readiness.how') }}</p>
        <p v-if="ready.suite">
          {{ t('optimization.readiness.suite', { suite: ready.suite }) }} ·
          {{
            t('optimization.readiness.counts', {
              cases: ready.cases,
              components: ready.components,
              windows: ready.stored_windows,
            })
          }}
        </p>
        <p class="note">{{ t('optimization.readiness.scope') }}</p>
        <p v-if="ready.reason" class="error" data-testid="opt-blocked">
          {{ t('optimization.readiness.blocked') }}{{ lt(ready.reason) }}
        </p>
      </div>
    </PanelBox>
    <div class="bar">
      <label class="cand"
        >{{ t('optimization.candidates') }}
        <input v-model.number="candidates" type="number" min="1" max="40" data-testid="opt-count"
      /></label>
      <button
        type="button"
        class="primary"
        :disabled="busy || (ready !== null && !ready.can_run)"
        data-testid="opt-run"
        @click="start"
      >
        {{ busy ? t('optimization.running') : t('optimization.run') }}
      </button>
      <p v-if="run" class="meta">
        {{
          t('optimization.meta', {
            id: run.run_id,
            time: fmtDate(run.started_at),
            suite: run.suite,
          })
        }}
      </p>
    </div>
    <p v-if="failed" class="error" role="alert">{{ t('optimization.failed') }} {{ failReason }}</p>
    <p v-else-if="!run && !busy" class="empty" data-testid="opt-none">
      {{ t('optimization.none') }}
    </p>

    <template v-if="run">
      <PanelBox>
        <template #actions><SimBadge v-if="run.is_simulated" /></template>
        <p class="verdict" data-testid="opt-verdict">
          {{
            run.recommended
              ? t('optimization.recommendedNote', { id: run.recommended })
              : t('optimization.noRecommendation')
          }}
        </p>
        <p v-if="run.recommended" class="propose">
          <button
            v-if="!proposed"
            type="button"
            data-testid="opt-propose"
            @click="propose(run.recommended)"
          >
            {{ t('optimization.propose', { id: run.recommended }) }}
          </button>
          <RouterLink v-else to="/models" data-testid="opt-proposed">{{
            t('optimization.proposed', { id: proposed })
          }}</RouterLink>
          <span v-if="proposeFailed" class="error" role="alert">{{ proposeFailed }}</span>
        </p>
        <div class="scroll">
          <table data-testid="opt-table">
            <thead>
              <tr>
                <th>{{ t('optimization.candidate') }}</th>
                <th>{{ t('optimization.path') }}</th>
                <th>{{ t('optimization.changes') }}</th>
                <th class="num">{{ t('optimization.within') }}</th>
                <th class="num">{{ t('optimization.delta') }}</th>
                <th class="num">{{ t('optimization.over') }}</th>
                <th class="num">{{ t('optimization.under') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr class="champion" data-row="champion">
                <th scope="row">{{ t('optimization.champion') }}</th>
                <td>—</td>
                <td class="small">
                  {{ run.champion.rules_version }} · {{ run.champion.policy_version }}
                </td>
                <td class="num">
                  {{ run.champion.metrics.within }}/{{ run.champion.metrics.windows }} ({{
                    pct(run.champion)
                  }}%)
                </td>
                <td class="num">—</td>
                <td class="num">{{ run.champion.metrics.over }}</td>
                <td class="num">{{ run.champion.metrics.under }}</td>
              </tr>
              <tr
                v-for="c in ranked"
                :key="c.candidate_id"
                :data-row="c.candidate_id"
                :class="{
                  best: c.candidate_id === run.recommended,
                  picked: c.candidate_id === selected,
                }"
              >
                <th scope="row">
                  <button
                    type="button"
                    class="link"
                    :aria-label="t('optimization.select', { id: c.candidate_id })"
                    @click="selected = c.candidate_id"
                  >
                    {{ c.candidate_id }}
                  </button>
                  <span v-if="c.candidate_id === run.recommended" class="tag">{{
                    t('optimization.recommended')
                  }}</span>
                </th>
                <td>{{ c.path === 'A' ? t('optimization.pathA') : t('optimization.pathB') }}</td>
                <td class="small">{{ changes(c) }}</td>
                <td class="num">{{ c.metrics.within }}/{{ c.metrics.windows }} ({{ pct(c) }}%)</td>
                <td class="num" :class="{ up: delta(c) > 0, down: delta(c) < 0 }">
                  {{ signed(delta(c)) }}
                </td>
                <td class="num">{{ c.metrics.over }}</td>
                <td class="num">{{ c.metrics.under }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </PanelBox>

      <PanelBox v-if="pick" :title="`${t('optimization.cases')} · ${pick.candidate_id}`">
        <div class="scroll">
          <table data-testid="opt-cases">
            <thead>
              <tr>
                <th>{{ t('optimization.case') }}</th>
                <th>{{ t('optimization.component') }}</th>
                <th class="num">{{ t('optimization.windows') }}</th>
                <th class="num">{{ t('optimization.champion') }}</th>
                <th class="num">{{ pick.candidate_id }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in caseRows" :key="r.champion.case_id">
                <th scope="row">{{ r.champion.case_id }}</th>
                <td>{{ r.champion.component_id }}</td>
                <td class="num">{{ r.champion.windows }}</td>
                <td class="num">{{ r.champion.within }}</td>
                <td
                  class="num"
                  :class="{
                    up: (r.candidate?.within ?? 0) > r.champion.within,
                    down: (r.candidate?.within ?? 0) < r.champion.within,
                  }"
                >
                  {{ r.candidate?.within ?? '—' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </PanelBox>
    </template>
  </div>
</template>

<style scoped>
.readiness {
  display: grid;
  gap: var(--space-2);
  font-size: var(--text-sm);
}
.cand {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  font-size: var(--text-sm);
}
.cand input {
  width: 5rem;
}
.note {
  color: var(--ink-soft);
}
.page {
  display: grid;
  gap: var(--space-4);
  max-width: 1100px;
}
.page-head {
  display: grid;
  gap: var(--space-2);
}
h1 {
  font-size: var(--text-xl);
}
.lede,
.meta,
.empty {
  color: var(--ink-soft);
  font-size: var(--text-sm);
}
.bar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  align-items: center;
}
.verdict {
  font-size: var(--text-sm);
  margin-bottom: var(--space-3);
}
.propose {
  margin-bottom: var(--space-3);
}
.scroll {
  overflow-x: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}
th,
td {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
}
thead th {
  color: var(--ink-faint);
  font-weight: 500;
}
.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.small {
  font-size: var(--text-xs);
  color: var(--ink-soft);
  white-space: normal;
}
tr.champion {
  background: var(--surface-inset);
}
tr.best th {
  font-weight: 600;
}
tr.picked {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}
.tag {
  margin-left: var(--space-2);
  font-size: var(--text-xs);
  padding: 1px 6px;
  border-radius: var(--radius-control);
  background: var(--accent);
  color: var(--surface);
}
.up {
  color: var(--health-normal);
}
.down {
  color: var(--health-critical);
}
button {
  font: inherit;
  font-size: var(--text-sm);
  padding: 6px 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius-control);
  background: var(--surface);
  color: var(--ink);
  cursor: pointer;
}
button.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--surface);
}
button.link {
  border: none;
  padding: 0;
  background: none;
  color: var(--accent);
  text-decoration: underline;
}
button:disabled {
  opacity: 0.6;
  cursor: default;
}
.error {
  color: var(--health-critical);
  font-size: var(--text-sm);
}
</style>

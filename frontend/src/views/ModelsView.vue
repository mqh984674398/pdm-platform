<script setup lang="ts">
/** Model and configuration versions (UI-11, T026): champion, gated candidates, promotion, rollback. */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DeploymentVersion, KindSummary } from '@/api/contracts'
import { MonitoringApiError, devRole, monitoringApi } from '@/api/monitoring'
import { session } from '@/api/session'
import PanelBox from '@/components/base/PanelBox.vue'
import SimBadge from '@/components/base/SimBadge.vue'
import { useLocalized } from '@/composables/useLocalized'

const { t } = useI18n()
const { fmtDate, lt } = useLocalized()

const kinds = ref<KindSummary[]>([])
const history = ref<Record<string, DeploymentVersion[]>>({})
const failed = ref(false)
const busy = ref<string | null>(null)
const message = ref<{ key: string; text: string; ok: boolean } | null>(null)
const comments = ref<Record<string, string>>({})
const role = ref(devRole())

function setRole(r: string) {
  try {
    localStorage.setItem('pdm-dev-role', r)
  } catch {
    /* storage unavailable: keep the default role */
  }
  role.value = devRole()
}

async function load() {
  failed.value = false
  try {
    kinds.value = await monitoringApi.registryKinds()
    const all = await Promise.all(kinds.value.map((k) => monitoringApi.registryVersions(k.kind)))
    history.value = Object.fromEntries(kinds.value.map((k, i) => [k.kind, all[i]!]))
    kinds.value = await monitoringApi.registryKinds()
  } catch {
    failed.value = true
  }
}
onMounted(load)

async function act(key: string, fn: () => Promise<unknown>, needComment = true) {
  const comment = (comments.value[key] ?? '').trim()
  message.value = null
  if (needComment && !comment) {
    message.value = { key, text: t('models.needComment'), ok: false }
    return
  }
  busy.value = key
  try {
    await fn()
    comments.value[key] = ''
    message.value = { key, text: t('models.done'), ok: true }
    await load()
  } catch (e) {
    const body = e instanceof MonitoringApiError ? e.body : null
    message.value = {
      key,
      text: body ? `${lt(body.message)} ${body.detail?.reason ?? ''}` : t('models.failed'),
      ok: false,
    }
  } finally {
    busy.value = null
  }
}

const promote = (v: DeploymentVersion) =>
  act(v.version_id, () => monitoringApi.promote(v.version_id, comments.value[v.version_id]!.trim()))
const reject = (v: DeploymentVersion) =>
  act(v.version_id, () => monitoringApi.reject(v.version_id, comments.value[v.version_id]!.trim()))
const rollback = (kind: string) =>
  act(`rb:${kind}`, () => monitoringApi.rollback(kind, comments.value[`rb:${kind}`]!.trim()))

type Ev = Record<string, unknown> & {
  gate_passed?: boolean
  reasons?: string[]
  champion?: { within: number; windows: number; over: number; under: number }
  candidate?: { within: number; windows: number; over: number; under: number }
  grouped_cv?: { roc_auc?: number; f1?: number }
}
const ev = (v: DeploymentVersion) => (v.evaluation ?? {}) as Ev
function label(v: DeploymentVersion): string {
  const p = v.payload as {
    rules?: { name: string; version: string }
    policy?: { version: string }
    model_id?: string
  }
  if (p.model_id) return p.model_id
  if (p.rules) return `${p.rules.name}@${p.rules.version} · ${p.policy?.version ?? ''}`
  return v.version_id
}
const candidates = (kind: string) =>
  (history.value[kind] ?? []).filter((v) => v.status === 'CANDIDATE')
const past = (kind: string) =>
  [...(history.value[kind] ?? [])].reverse().filter((v) => v.status !== 'CANDIDATE')
const canRollback = (k: KindSummary) => !!k.champion?.previous_version_id
const anySimulated = computed(() =>
  Object.values(history.value)
    .flat()
    .some((v) => v.is_simulated),
)
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>{{ t('nav.models') }}</h1>
      <p class="lede">{{ t('models.lede') }}</p>
    </header>
    <div class="bar">
      <label v-if="session.mode !== 'local'" class="role">
        <span>{{ t('models.actAs') }}</span>
        <select
          :value="role"
          data-testid="dev-role"
          @change="setRole(($event.target as HTMLSelectElement).value)"
        >
          <option v-for="r in ['viewer', 'maintenance', 'engineer', 'admin']" :key="r" :value="r">
            {{ t(`models.roles.${r}`) }}
          </option>
        </select>
      </label>
      <SimBadge v-if="anySimulated" />
    </div>
    <p v-if="failed" class="error" role="alert">{{ t('common.loadFailed') }}</p>

    <PanelBox
      v-for="k in kinds"
      :key="k.kind"
      :title="t(`models.kinds.${k.kind.split(':')[0]}`, { type: k.kind.split(':')[1] ?? '' })"
    >
      <section :data-kind="k.kind">
        <div class="champion" data-testid="champion">
          <h3>{{ t('models.champion') }}</h3>
          <template v-if="k.champion">
            <p class="name">{{ label(k.champion) }}</p>
            <p class="small">
              {{ k.champion.version_id }} ·
              {{
                t('models.decided', {
                  who: k.champion.decided_by ?? '—',
                  time: k.champion.decided_at ? fmtDate(k.champion.decided_at) : '—',
                })
              }}
            </p>
            <form v-if="canRollback(k)" class="actions" @submit.prevent>
              <input
                v-model="comments[`rb:${k.kind}`]"
                type="text"
                maxlength="2000"
                :placeholder="t('models.commentHint')"
                :aria-label="t('models.comment')"
                data-testid="rollback-comment"
              />
              <button
                type="button"
                :disabled="busy === `rb:${k.kind}`"
                data-testid="rollback"
                @click="rollback(k.kind)"
              >
                {{ t('models.rollback', { id: k.champion.previous_version_id }) }}
              </button>
            </form>
            <p
              v-if="message?.key === `rb:${k.kind}`"
              :class="message.ok ? 'ok' : 'error'"
              role="status"
            >
              {{ message.text }}
            </p>
          </template>
          <p v-else class="small">{{ t('models.noChampion') }}</p>
        </div>

        <h3>{{ t('models.candidates') }}</h3>
        <p v-if="!candidates(k.kind).length" class="small">{{ t('models.noCandidates') }}</p>
        <ol class="cands">
          <li v-for="v in candidates(k.kind)" :key="v.version_id" :data-version="v.version_id">
            <div class="head">
              <span class="name">{{ label(v) }}</span>
              <span class="gate" :class="ev(v).gate_passed ? 'pass' : 'fail'" data-testid="gate">
                {{ ev(v).gate_passed ? t('models.gatePassed') : t('models.gateFailed') }}
              </span>
            </div>
            <p class="small">
              {{ v.version_id }} · {{ v.created_by }} · {{ fmtDate(v.created_at) }} ·
              {{ v.comment }}
            </p>
            <table v-if="ev(v).champion && ev(v).candidate" class="cmp">
              <thead>
                <tr>
                  <th></th>
                  <th class="num">{{ t('optimization.within') }}</th>
                  <th class="num">{{ t('optimization.over') }}</th>
                  <th class="num">{{ t('optimization.under') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in ['champion', 'candidate'] as const" :key="row">
                  <th scope="row">{{ t(`models.${row}`) }}</th>
                  <td class="num">{{ ev(v)[row]!.within }}/{{ ev(v)[row]!.windows }}</td>
                  <td class="num">{{ ev(v)[row]!.over }}</td>
                  <td class="num">{{ ev(v)[row]!.under }}</td>
                </tr>
              </tbody>
            </table>
            <p v-else-if="ev(v).grouped_cv" class="small">
              {{
                t('models.cv', {
                  auc: ev(v).grouped_cv!.roc_auc?.toFixed(3) ?? '—',
                  f1: ev(v).grouped_cv!.f1?.toFixed(3) ?? '—',
                })
              }}
            </p>
            <ul v-if="ev(v).reasons?.length" class="reasons">
              <li v-for="r in ev(v).reasons" :key="r">{{ r }}</li>
            </ul>
            <form class="actions" @submit.prevent>
              <input
                v-model="comments[v.version_id]"
                type="text"
                maxlength="2000"
                :placeholder="t('models.commentHint')"
                :aria-label="t('models.comment')"
                data-testid="decision-comment"
              />
              <button
                type="button"
                class="primary"
                :disabled="busy === v.version_id || !ev(v).gate_passed"
                data-testid="promote"
                @click="promote(v)"
              >
                {{ t('models.promote') }}
              </button>
              <button
                type="button"
                :disabled="busy === v.version_id"
                data-testid="reject"
                @click="reject(v)"
              >
                {{ t('models.reject') }}
              </button>
            </form>
            <p
              v-if="message?.key === v.version_id"
              :class="message.ok ? 'ok' : 'error'"
              role="status"
            >
              {{ message.text }}
            </p>
          </li>
        </ol>

        <details v-if="past(k.kind).length">
          <summary>{{ t('models.history', { n: past(k.kind).length }) }}</summary>
          <ol class="hist" data-testid="history">
            <li v-for="v in past(k.kind)" :key="v.version_id" :data-status="v.status">
              <span class="status">{{ t(`models.status.${v.status}`) }}</span>
              {{ v.version_id }} · {{ label(v) }} · {{ v.decided_by ?? v.created_by }}
            </li>
          </ol>
        </details>
      </section>
    </PanelBox>
    <p class="note">{{ t('models.note') }}</p>
  </div>
</template>

<style scoped>
.page {
  display: grid;
  gap: var(--space-4);
  max-width: 1000px;
}
.page-head {
  display: grid;
  gap: var(--space-2);
}
h1 {
  font-size: var(--text-xl);
}
h3 {
  font-size: var(--text-sm);
  color: var(--ink-faint);
  font-weight: 500;
  margin: var(--space-3) 0 var(--space-2);
}
.lede,
.note,
.small {
  color: var(--ink-soft);
  font-size: var(--text-sm);
}
.small {
  font-size: var(--text-xs);
}
.bar {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  flex-wrap: wrap;
}
.role {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  font-size: var(--text-sm);
  color: var(--ink-soft);
}
.name {
  font-weight: 600;
  overflow-wrap: anywhere;
}
.cands,
.hist {
  list-style: none;
  display: grid;
  gap: var(--space-3);
}
.cands > li {
  border: 1px solid var(--line);
  border-radius: var(--radius-control);
  padding: var(--space-3);
}
.head {
  display: flex;
  justify-content: space-between;
  gap: var(--space-2);
  align-items: baseline;
}
.gate {
  font-size: var(--text-xs);
  padding: 2px 8px;
  border-radius: var(--radius-control);
  white-space: nowrap;
}
.gate.pass {
  color: var(--health-normal);
  border: 1px solid var(--health-normal);
}
.gate.fail {
  color: var(--health-critical);
  border: 1px solid var(--health-critical);
}
.cmp {
  margin-top: var(--space-2);
  border-collapse: collapse;
  font-size: var(--text-sm);
}
.cmp th,
.cmp td {
  padding: 4px 10px;
  border-bottom: 1px solid var(--line);
  text-align: left;
}
.num {
  text-align: right !important;
  font-variant-numeric: tabular-nums;
}
.reasons {
  margin: var(--space-2) 0 0 var(--space-4);
  font-size: var(--text-xs);
  color: var(--health-critical);
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-2);
}
.actions input {
  flex: 1 1 220px;
  font: inherit;
  font-size: var(--text-sm);
  padding: 6px 8px;
  border: 1px solid var(--line);
  border-radius: var(--radius-control);
  background: var(--surface);
  color: var(--ink);
}
button,
select {
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
button:disabled {
  opacity: 0.6;
  cursor: default;
}
.hist {
  gap: 2px;
  margin-top: var(--space-2);
  font-size: var(--text-xs);
}
.status {
  display: inline-block;
  min-width: 72px;
  color: var(--ink-faint);
}
.error {
  color: var(--health-critical);
  font-size: var(--text-sm);
}
.ok {
  color: var(--health-normal);
  font-size: var(--text-sm);
}
</style>

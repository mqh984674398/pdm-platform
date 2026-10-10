<script setup lang="ts">
/** Alarm review (UI-09, T020): open alarms first; acknowledge, or resolve with the outcome. */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import type { Alarm } from '@/api/contracts'
import { monitoringApi } from '@/api/monitoring'
import HealthBadge from '@/components/base/HealthBadge.vue'
import PanelBox from '@/components/base/PanelBox.vue'
import SegmentedControl from '@/components/base/SegmentedControl.vue'
import SimBadge from '@/components/base/SimBadge.vue'
import { useFleet } from '@/composables/useFleet'
import { useLocalized } from '@/composables/useLocalized'

const { t } = useI18n()
const { lt, fmtDate } = useLocalized()
const route = useRoute()
const router = useRouter()
const { findComponent, reload } = useFleet()

type Filter = 'open' | 'all'
const filter = computed<Filter>(() => (route.query.status === 'all' ? 'all' : 'open'))
const componentId = computed(() => (route.query.c as string | undefined) || undefined)
const alarms = ref<Alarm[]>([])
const failed = ref(false)
const busy = ref<string | null>(null)
const actionError = ref<string | null>(null)
const comments = ref<Record<string, string>>({})
const feedbackSent = ref<Record<string, boolean>>({})

async function sendFeedback(a: Alarm, verdict: 'CONFIRMED' | 'FALSE_ALARM') {
  try {
    await monitoringApi.feedback({
      alarm_id: a.alarm_id,
      verdict,
      comment: comments.value[a.alarm_id] ?? '',
    })
    feedbackSent.value[a.alarm_id] = true
  } catch {
    actionError.value = a.alarm_id
  }
}

async function load() {
  failed.value = false
  try {
    alarms.value = await monitoringApi.alarms({ component_id: componentId.value })
  } catch {
    failed.value = true
  }
}
watch(componentId, load, { immediate: true })

const SEV = { CRITICAL: 0, WARNING: 1, WATCH: 2 } as const
const shown = computed(() =>
  alarms.value
    .filter((a) => filter.value === 'all' || a.status !== 'RESOLVED')
    .sort(
      (a, b) =>
        Number(a.status === 'RESOLVED') - Number(b.status === 'RESOLVED') ||
        SEV[a.severity] - SEV[b.severity] ||
        b.raised_at.localeCompare(a.raised_at),
    ),
)

function setFilter(v: Filter) {
  router.replace({ query: { ...route.query, status: v === 'all' ? 'all' : undefined } })
}
function componentName(id: string) {
  const f = findComponent(id)
  return f ? `${lt(f.machine.name)} · ${lt(f.component.name)}` : id
}

async function act(a: Alarm, action: 'acknowledge' | 'resolve') {
  const comment = (comments.value[a.alarm_id] ?? '').trim()
  actionError.value = null
  if (action === 'resolve' && !comment) {
    actionError.value = a.alarm_id
    return
  }
  busy.value = a.alarm_id
  try {
    const updated = await monitoringApi[action](a.alarm_id, comment)
    alarms.value = alarms.value.map((x) => (x.alarm_id === updated.alarm_id ? updated : x))
    comments.value[a.alarm_id] = ''
    reload()
  } catch {
    actionError.value = a.alarm_id
  } finally {
    busy.value = null
  }
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>{{ t('nav.alarms') }}</h1>
      <p class="lede">{{ t('alarms.lede') }}</p>
    </header>
    <div class="bar">
      <SegmentedControl
        :model-value="filter"
        :options="[
          { value: 'open', label: t('alarms.open') },
          { value: 'all', label: t('alarms.all') },
        ]"
        :label="t('alarms.filter')"
        @update:model-value="(v: string) => setFilter(v as Filter)"
      />
      <span v-if="componentId" class="scope">
        {{ componentName(componentId) }}
        <RouterLink :to="{ query: { ...route.query, c: undefined } }">{{
          t('alarms.allComponents')
        }}</RouterLink>
      </span>
    </div>
    <p v-if="failed" class="error">{{ t('common.loadFailed') }}</p>
    <p v-else-if="!shown.length" class="empty" data-testid="no-alarms">{{ t('alarms.none') }}</p>
    <ol class="cards">
      <li v-for="a in shown" :key="a.alarm_id" :data-alarm="a.alarm_id" :data-status="a.status">
        <PanelBox>
          <template #actions>
            <SimBadge v-if="a.is_simulated" />
          </template>
          <div class="head">
            <HealthBadge :state="a.severity" />
            <div>
              <h2>
                <RouterLink :to="`/component/${a.component_id}`">{{
                  componentName(a.component_id)
                }}</RouterLink>
              </h2>
              <p class="msg">{{ a.rule_id }} · {{ lt(a.message) }}</p>
            </div>
            <span class="status" :class="a.status.toLowerCase()">{{
              t(`alarms.status.${a.status}`)
            }}</span>
          </div>
          <dl class="facts">
            <dt>{{ t('alarms.raised') }}</dt>
            <dd>{{ fmtDate(a.raised_at) }}</dd>
            <dt>{{ t('alarms.condition') }}</dt>
            <dd>{{ a.condition_active ? t('alarms.active') : t('alarms.cleared') }}</dd>
            <template v-if="a.acknowledged_at">
              <dt>{{ t('alarms.acknowledged') }}</dt>
              <dd>{{ fmtDate(a.acknowledged_at) }} · {{ a.acknowledged_by }}</dd>
            </template>
            <template v-if="a.resolved_at">
              <dt>{{ t('alarms.resolved') }}</dt>
              <dd>{{ fmtDate(a.resolved_at) }} · {{ a.resolved_by }}</dd>
              <dt>{{ t('alarms.outcome') }}</dt>
              <dd data-testid="resolution">{{ a.resolution_comment }}</dd>
            </template>
            <dt>{{ t('alarms.evidence') }}</dt>
            <dd class="ids">{{ a.evidence_ids.join(', ') }}</dd>
          </dl>
          <p class="fb">
            <span>{{ t('alarms.feedback') }}</span>
            <template v-if="!feedbackSent[a.alarm_id]">
              <button
                type="button"
                data-testid="fb-confirmed"
                @click="sendFeedback(a, 'CONFIRMED')"
              >
                {{ t('alarms.confirmed') }}
              </button>
              <button type="button" data-testid="fb-false" @click="sendFeedback(a, 'FALSE_ALARM')">
                {{ t('alarms.falseAlarm') }}
              </button>
            </template>
            <span v-else data-testid="fb-sent">{{ t('alarms.feedbackSent') }}</span>
          </p>
          <form v-if="a.status !== 'RESOLVED'" class="actions" @submit.prevent>
            <label class="comment">
              <span>{{ t('alarms.comment') }}</span>
              <input
                v-model="comments[a.alarm_id]"
                type="text"
                maxlength="2000"
                :placeholder="t('alarms.commentHint')"
                data-testid="alarm-comment"
              />
            </label>
            <button
              v-if="a.status === 'RAISED'"
              type="button"
              :disabled="busy === a.alarm_id"
              data-testid="alarm-ack"
              @click="act(a, 'acknowledge')"
            >
              {{ t('alarms.acknowledge') }}
            </button>
            <button
              type="button"
              class="primary"
              :disabled="busy === a.alarm_id"
              data-testid="alarm-resolve"
              @click="act(a, 'resolve')"
            >
              {{ t('alarms.resolve') }}
            </button>
            <p v-if="actionError === a.alarm_id" class="error" role="alert">
              {{ t('alarms.needComment') }}
            </p>
          </form>
        </PanelBox>
      </li>
    </ol>
    <p class="note">{{ t('alarms.noNotify') }}</p>
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
.lede,
.note,
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
.scope {
  display: flex;
  gap: var(--space-2);
  font-size: var(--text-sm);
}
.cards {
  list-style: none;
  display: grid;
  gap: var(--space-3);
}
.head {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: var(--space-3);
  align-items: start;
}
h2 {
  font-size: var(--text-md);
}
.msg {
  color: var(--ink-soft);
  font-size: var(--text-sm);
}
.status {
  font-size: var(--text-xs);
  padding: 2px 8px;
  border-radius: var(--radius-control);
  background: var(--surface-inset);
}
.status.raised {
  color: var(--ink);
  font-weight: 600;
}
.facts {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr);
  gap: 2px var(--space-3);
  margin-top: var(--space-3);
  font-size: var(--text-sm);
}
dt {
  color: var(--ink-faint);
}
.ids {
  font-size: var(--text-xs);
  color: var(--ink-faint);
  overflow-wrap: anywhere;
}
.fb {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
  margin-top: var(--space-2);
  font-size: var(--text-xs);
  color: var(--ink-soft);
}
.fb button {
  padding: 2px 8px;
  font-size: var(--text-xs);
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: end;
  margin-top: var(--space-3);
}
.comment {
  display: grid;
  gap: 2px;
  flex: 1 1 240px;
  font-size: var(--text-xs);
  color: var(--ink-soft);
}
.comment input {
  font: inherit;
  font-size: var(--text-sm);
  padding: 6px 8px;
  border: 1px solid var(--line);
  border-radius: var(--radius-control);
  background: var(--surface);
  color: var(--ink);
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
button:disabled {
  opacity: 0.6;
  cursor: default;
}
.error {
  color: var(--health-critical);
  font-size: var(--text-sm);
  flex-basis: 100%;
}
</style>

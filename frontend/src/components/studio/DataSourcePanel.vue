<script setup lang="ts">
/**
 * Data sources (administrators): add, edit, test and delete the production TDengine sources. The
 * account is write-only and never shown again; reading production needs no approval but the
 * connection is read-only and bounded (D-035). Sources from the datasources file are listed but
 * cannot be edited here.
 */
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type {
  ManagedSource,
  ManagedSourceBody,
  SourceStructure,
  SourceTestCheck,
} from '@/api/contracts'
import { MonitoringApiError, monitoringApi } from '@/api/monitoring'
import PanelBox from '@/components/base/PanelBox.vue'
import '@/components/studio/studio.css'
import { useLocalized } from '@/composables/useLocalized'

const { t } = useI18n()
const { lt } = useLocalized()
const SCHEMES = ['http', 'https']
const ID = /^[a-z0-9][a-z0-9-]{0,40}$/

const sources = ref<ManagedSource[]>([])
const busy = ref(false)
const open = ref(false)
const editing = ref<string | null>(null)
const message = ref<{ ok: boolean; text: string } | null>(null)
const checks = ref<{ id: string; list: SourceTestCheck[] } | null>(null)
const structure = ref<SourceStructure | null>(null)
const HOST_INPUT = /^(?:(https?):\/\/)?([^/:\s]+)(?::(\d{1,5}))?(?:\/.*)?$/i
const form = reactive({
  id: '',
  name: '',
  host: '',
  port: 6041,
  database: '',
  scheme: 'http',
  user: '',
  password: '',
  stable: '',
  deviceTag: '',
  timeColumn: 'ts',
  keyColumn: '',
  valueColumns: '',
  zone: 'UTC',
})

async function load() {
  sources.value = await monitoringApi.adminDataSources().catch(() => [])
}
load()

async function run<T>(action: () => Promise<T>, done?: string): Promise<T | undefined> {
  busy.value = true
  message.value = null
  try {
    const out = await action()
    if (done) message.value = { ok: true, text: done }
    return out
  } catch (e) {
    const body = e instanceof MonitoringApiError ? e.body : null
    message.value = { ok: false, text: body ? lt(body.message) : t('datasources.failed') }
    return undefined
  } finally {
    busy.value = false
  }
}

function edit(s: ManagedSource | null) {
  editing.value = s?.data_source_id ?? null
  structure.value = null
  Object.assign(form, {
    id: s?.data_source_id ?? '',
    name: s?.name ?? '',
    host: s?.host ?? '',
    port: s?.port ?? 6041,
    database: s?.database ?? '',
    scheme: s?.scheme ?? 'http',
    user: '',
    password: '',
    stable: s?.layout?.stable ?? '',
    deviceTag: s?.layout?.device_tag ?? '',
    timeColumn: s?.layout?.time_column ?? 'ts',
    keyColumn: s?.layout?.key_column ?? '',
    valueColumns: (s?.layout?.value_columns ?? []).join(', '),
    zone: s?.layout?.naive_time_zone ?? 'UTC',
  })
  open.value = true
}

/** A pasted address (http://host:port/...) is split into host, protocol and port. */
function splitHost() {
  const m = HOST_INPUT.exec(form.host.trim())
  if (!m) return
  form.host = m[2]!
  if (m[1]) form.scheme = m[1].toLowerCase()
  if (m[3]) form.port = Number(m[3])
}
const portWarning = computed(() => Number(form.port) === 6060)
const tagColumns = computed(() => structure.value?.columns ?? [])
const tagMissing = computed(
  () =>
    !!structure.value?.columns.length &&
    !!form.deviceTag &&
    !structure.value.columns.some((c) => c.name === form.deviceTag),
)
/** Guess the layout from the real columns: key name column + value columns mean a narrow table. */
const recommended = computed(() => {
  const cols = structure.value?.columns ?? []
  if (!cols.length) return null
  const time = cols.find((c) => c.type === 'TIMESTAMP')?.name
  const key = cols.find((c) => !c.is_tag && /^key(_?name)?$/i.test(c.name))?.name
  const tag =
    cols.find((c) => c.is_tag && /dev/i.test(c.name))?.name ?? cols.find((c) => c.is_tag)?.name
  const NUM = ['DOUBLE', 'FLOAT', 'BIGINT', 'INT', 'SMALLINT']
  const values = cols
    .filter((c) => !c.is_tag && c.name !== key && /^value/i.test(c.name) && NUM.includes(c.type))
    .map((c) => c.name)
  return { time, key, tag, values }
})
function applyRecommended() {
  const r = recommended.value
  if (!r) return
  if (r.time) form.timeColumn = r.time
  if (r.tag) form.deviceTag = r.tag
  form.keyColumn = r.key ?? ''
  if (r.key) form.valueColumns = r.values.join(', ')
}
async function readStructure() {
  if (!editing.value) return
  const out = await run(() =>
    monitoringApi.dataSourceStructure(editing.value!, form.stable.trim() || undefined),
  )
  if (out) structure.value = out
}

const valid = computed(
  () =>
    ID.test(form.id) &&
    !!form.name.trim() &&
    !!form.host.trim() &&
    !!form.database.trim() &&
    !!form.stable.trim() &&
    !!form.deviceTag.trim() &&
    (editing.value !== null || (!!form.user && !!form.password)) &&
    !!form.user === !!form.password,
)

async function save() {
  if (!valid.value) return
  const body: ManagedSourceBody = {
    data_source_id: form.id,
    name: form.name.trim(),
    host: form.host.trim(),
    port: Number(form.port),
    database: form.database.trim(),
    scheme: form.scheme,
    user: form.user || null,
    password: form.password || null,
    stable: form.stable.trim(),
    device_tag: form.deviceTag.trim(),
    time_column: form.timeColumn.trim() || 'ts',
    key_column: form.keyColumn.trim() || null,
    value_columns: form.valueColumns
      .split(',')
      .map((x) => x.trim())
      .filter(Boolean),
    naive_time_zone: form.zone.trim() || 'UTC',
    statement_timeout_s: 30,
    max_rows: 200000,
  }
  const out = await run(() => monitoringApi.saveDataSource(body), t('datasources.saved'))
  form.password = ''
  if (out) {
    open.value = false
    await load()
  }
}
async function test(id: string) {
  const list = await run(() => monitoringApi.testDataSource(id))
  if (list) {
    checks.value = { id, list }
    await load()
  }
}
async function remove(id: string) {
  if (!window.confirm(t('datasources.deleteConfirm', { id }))) return
  if (await run(() => monitoringApi.deleteDataSource(id), t('datasources.deleted'))) await load()
}
const kindLabel = (s: ManagedSource) =>
  s.kind === 'TDENGINE' ? 'TDengine' : s.is_simulated ? t('datasources.simulated') : s.kind
</script>

<template>
  <PanelBox :title="t('datasources.title')">
    <div class="st-stack" data-testid="datasource-panel">
      <p class="st-note">{{ t('datasources.note') }}</p>
      <p v-if="message" :class="message.ok ? 'ok' : 'error'" role="status" data-testid="ds-message">
        {{ message.text }}
      </p>
      <div class="st-scroll">
        <table class="st-table" data-testid="ds-list">
          <thead>
            <tr>
              <th>{{ t('datasources.id') }}</th>
              <th>{{ t('datasources.name') }}</th>
              <th>{{ t('datasources.kind') }}</th>
              <th>{{ t('datasources.state') }}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in sources" :key="s.data_source_id" :data-source="s.data_source_id">
              <td class="st-mono">{{ s.data_source_id }}</td>
              <td>
                {{ s.name
                }}<span v-if="s.host" class="st-note st-mono">
                  {{ s.host }}:{{ s.port }}/{{ s.database }}</span
                >
              </td>
              <td>{{ kindLabel(s) }}</td>
              <td>
                {{
                  s.active
                    ? t('datasources.active')
                    : s.credential_set
                      ? t('datasources.inactive')
                      : t('datasources.noAccount')
                }}
                <span v-if="s.layout && !s.layout.verified" class="st-note"
                  >· {{ t('datasources.untested') }}</span
                >
              </td>
              <td>
                <template v-if="s.managed">
                  <button
                    type="button"
                    class="link"
                    :disabled="busy"
                    @click="test(s.data_source_id)"
                  >
                    {{ t('datasources.test') }}
                  </button>
                  <button type="button" class="link" :disabled="busy" @click="edit(s)">
                    {{ t('plant.editNode') }}
                  </button>
                  <button
                    type="button"
                    class="link danger"
                    :disabled="busy"
                    @click="remove(s.data_source_id)"
                  >
                    {{ t('plant.delete') }}
                  </button>
                </template>
                <span v-else class="st-note">{{ t('datasources.fixed') }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <ul v-if="checks" class="st-note" data-testid="ds-checks">
        <li v-for="c in checks.list" :key="c.key" :class="c.ok ? 'ok' : 'error'">
          {{ c.ok ? '✓' : '✗' }} {{ t(`datasources.check.${c.key}`) }}
          <template v-if="!c.ok && c.hint">
            <br /><strong>{{ t(`datasources.hint.${c.hint}`) }}</strong>
          </template>
          <template v-if="!c.ok && c.detail">
            <br /><span class="st-mono">{{ c.detail }}</span>
          </template>
        </li>
      </ul>
      <button v-if="!open" type="button" class="st-button" data-testid="ds-add" @click="edit(null)">
        + {{ t('datasources.add') }}
      </button>
      <form v-else class="st-form" data-testid="ds-form" @submit.prevent="save">
        <label class="st-field"
          ><span>{{ t('datasources.id') }}</span>
          <input
            v-model.trim="form.id"
            class="st-input st-mono"
            :disabled="editing !== null"
            data-testid="ds-id"
          />
          <span v-if="form.id && !ID.test(form.id)" class="st-note error">{{
            t('datasources.badId')
          }}</span>
        </label>
        <label class="st-field"
          ><span>{{ t('datasources.name') }}</span
          ><input v-model="form.name" class="st-input"
        /></label>
        <label class="st-field"
          ><span>{{ t('datasources.host') }}</span
          ><input
            v-model.trim="form.host"
            class="st-input st-mono"
            data-testid="ds-host"
            @blur="splitHost"
          /><span class="st-note">{{ t('datasources.hostNote') }}</span></label
        >
        <label class="st-field"
          ><span>{{ t('datasources.port') }}</span
          ><input
            v-model.number="form.port"
            type="number"
            class="st-input st-mono"
            data-testid="ds-port"
          /><span v-if="portWarning" class="st-note error" data-testid="ds-port-warning">{{
            t('datasources.port6060')
          }}</span
          ><span v-else class="st-note">{{ t('datasources.portNote') }}</span></label
        >
        <label class="st-field"
          ><span>{{ t('datasources.scheme') }}</span>
          <select v-model="form.scheme" class="st-select">
            <option v-for="x in SCHEMES" :key="x" :value="x">{{ x }}</option>
          </select>
        </label>
        <label class="st-field"
          ><span>{{ t('datasources.database') }}</span
          ><input v-model.trim="form.database" class="st-input st-mono"
        /></label>
        <label class="st-field"
          ><span>{{ t('datasources.stable') }}</span
          ><input
            v-model.trim="form.stable"
            class="st-input st-mono"
            list="ds-stables"
            data-testid="ds-stable"
          />
          <datalist id="ds-stables">
            <option v-for="x in structure?.stables ?? []" :key="x" :value="x" />
          </datalist>
        </label>
        <label class="st-field"
          ><span>{{ t('datasources.deviceTag') }}</span
          ><input
            v-model.trim="form.deviceTag"
            class="st-input st-mono"
            list="ds-columns"
            data-testid="ds-tag"
          /><span v-if="tagMissing" class="st-note error" data-testid="ds-tag-warning">{{
            t('datasources.tagMissing', { name: form.deviceTag })
          }}</span
          ><span v-else class="st-note">{{ t('datasources.tagNote') }}</span></label
        >
        <label class="st-field"
          ><span>{{ t('datasources.timeColumn') }}</span
          ><input
            v-model.trim="form.timeColumn"
            class="st-input st-mono"
            list="ds-columns"
          /><datalist id="ds-columns">
            <option v-for="c in tagColumns" :key="c.name" :value="c.name">
              {{ c.type }}{{ c.is_tag ? ' · tag' : '' }}
            </option>
          </datalist></label
        >
        <div v-if="editing" class="st-field">
          <button
            type="button"
            class="st-button"
            :disabled="busy"
            data-testid="ds-structure"
            @click="readStructure"
          >
            {{ t('datasources.readStructure') }}
          </button>
          <span class="st-note">{{ t('datasources.structureNote') }}</span>
          <div v-if="recommended" class="st-note" data-testid="ds-recommended">
            {{
              recommended.key
                ? t('datasources.narrow', {
                    key: recommended.key,
                    values: recommended.values.join(', ') || '—',
                  })
                : t('datasources.wide')
            }}
            <button type="button" class="link" data-testid="ds-apply" @click="applyRecommended">
              {{ t('datasources.apply') }}
            </button>
          </div>
          <ul v-if="structure" class="st-note st-mono" data-testid="ds-columns">
            <li v-for="c in structure.columns" :key="c.name">
              {{ c.name }} · {{ c.type }}{{ c.is_tag ? ' · tag' : '' }}
            </li>
            <li v-if="!structure.columns.length">{{ t('datasources.noColumns') }}</li>
          </ul>
        </div>
        <label class="st-field"
          ><span>{{ t('datasources.keyColumn') }}</span
          ><input v-model.trim="form.keyColumn" class="st-input st-mono" /><span class="st-note">{{
            t('datasources.keyNote')
          }}</span></label
        >
        <label class="st-field"
          ><span>{{ t('datasources.valueColumns') }}</span
          ><input v-model="form.valueColumns" class="st-input st-mono"
        /></label>
        <label class="st-field"
          ><span>{{ t('datasources.zone') }}</span
          ><input v-model.trim="form.zone" class="st-input st-mono"
        /></label>
        <label class="st-field"
          ><span>{{ t('datasources.user') }}</span
          ><input v-model.trim="form.user" class="st-input st-mono" autocomplete="off"
        /></label>
        <label class="st-field"
          ><span>{{ t('datasources.password') }}</span
          ><input
            v-model="form.password"
            type="password"
            class="st-input"
            autocomplete="new-password"
          /><span class="st-note">{{ t('datasources.accountNote') }}</span></label
        >
        <div class="row">
          <button
            type="submit"
            class="st-button primary"
            :disabled="busy || !valid"
            data-testid="ds-save"
          >
            {{ t('plant.save') }}
          </button>
          <button type="button" class="link" @click="open = false">{{ t('common.close') }}</button>
        </div>
      </form>
    </div>
  </PanelBox>
</template>

<style scoped>
.row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
}
.link {
  border: 0;
  background: none;
  padding: 0 var(--space-1);
  font: inherit;
  font-size: var(--text-sm);
  color: var(--accent);
  cursor: pointer;
}
.link.danger:not(:disabled) {
  color: var(--health-critical);
}
.ok {
  color: var(--health-normal);
}
.error {
  color: var(--health-critical);
}
</style>

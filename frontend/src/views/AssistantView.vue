<script setup lang="ts">
/** Local Ollama settings, diagnostic assistant with citations, and RAG documents (UI-12, T027). */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { AssistantResponse, LlmConfig, LlmHealth, RagDocument } from '@/api/contracts'
import { MonitoringApiError, monitoringApi } from '@/api/monitoring'
import HealthBadge from '@/components/base/HealthBadge.vue'
import PanelBox from '@/components/base/PanelBox.vue'
import { useFleet } from '@/composables/useFleet'
import { useLocalized } from '@/composables/useLocalized'

const { t } = useI18n()
const { lt } = useLocalized()
const { fleet } = useFleet()

// --- settings
const cfg = ref<LlmConfig | null>(null)
const hosts = ref('')
const health = ref<LlmHealth | null>(null)
const settingsMsg = ref<{ ok: boolean; text: string } | null>(null)

function apiText(e: unknown): string {
  return e instanceof MonitoringApiError && e.body ? lt(e.body.message) : t('assistant.failed')
}

async function loadSettings() {
  try {
    cfg.value = { ...(await monitoringApi.llmSettings()).config }
    hosts.value = (cfg.value.allowed_hosts ?? []).join(', ')
    health.value = await monitoringApi.llmHealth()
  } catch {
    settingsMsg.value = { ok: false, text: t('common.loadFailed') }
  }
}

async function saveSettings() {
  if (!cfg.value) return
  settingsMsg.value = null
  try {
    const body = {
      ...cfg.value,
      allowed_hosts: hosts.value
        .split(',')
        .map((h) => h.trim())
        .filter(Boolean),
    }
    cfg.value = { ...(await monitoringApi.saveLlmSettings(body)).config }
    settingsMsg.value = { ok: true, text: t('assistant.saved') }
    health.value = await monitoringApi.llmHealth()
  } catch (e) {
    settingsMsg.value = { ok: false, text: apiText(e) }
  }
}

async function checkHealth() {
  health.value = await monitoringApi.llmHealth()
}

// --- ask
const components = computed(() =>
  (fleet.value?.machines ?? []).flatMap((m) =>
    m.components.map((c) => ({ id: c.component_id, label: `${lt(m.name)} · ${lt(c.name)}` })),
  ),
)
const componentId = ref('')
const question = ref('')
const asking = ref(false)
const streamed = ref('')
const answer = ref<AssistantResponse | null>(null)
const askError = ref<string | null>(null)
const requestId = ref<string | null>(null)
const fbDone = ref<string | null>(null)
let abort: AbortController | null = null

const partial = computed(() => {
  const m = /"answer"\s*:\s*"((?:[^"\\]|\\.)*)/.exec(streamed.value)
  return m ? m[1]!.replace(/\\n/g, '\n').replace(/\\"/g, '"') : ''
})

async function ask() {
  if (!question.value.trim()) return
  asking.value = true
  answer.value = null
  askError.value = null
  streamed.value = ''
  fbDone.value = null
  requestId.value = `ask-${Date.now()}`
  abort = new AbortController()
  try {
    await monitoringApi.askStream(
      {
        question: question.value.trim(),
        component_id: componentId.value || undefined,
        request_id: requestId.value,
      },
      (ev) => {
        if (ev.type === 'token') streamed.value += ev.text
        else if (ev.type === 'answer') answer.value = ev.response
        else if (ev.type === 'error')
          askError.value = ev.code === 'LlmCancelled' ? t('assistant.cancelled') : ev.message
      },
      abort.signal,
    )
  } catch (e) {
    askError.value = (e as Error).name === 'AbortError' ? t('assistant.cancelled') : apiText(e)
  } finally {
    asking.value = false
    abort = null
  }
}

async function cancel() {
  if (requestId.value) await monitoringApi.cancelAsk(requestId.value).catch(() => undefined)
  abort?.abort()
}

async function rate(verdict: 'CONFIRMED' | 'FALSE_ALARM') {
  if (!answer.value) return
  try {
    await monitoringApi.feedback({
      assistant_ref: `${requestId.value} ${answer.value.decision_id ?? ''}`.trim(),
      decision_id: answer.value.decision_id,
      verdict,
      comment: question.value.slice(0, 500),
    })
    fbDone.value = t('assistant.thanks')
  } catch (e) {
    fbDone.value = apiText(e)
  }
}

// --- documents
const docs = ref<RagDocument[]>([])
const newDoc = ref({ title: '', text: '', min_role: 'viewer' })
const docMsg = ref<{ ok: boolean; text: string } | null>(null)

async function loadDocs() {
  docs.value = await monitoringApi.documents().catch(() => [])
}
async function addDoc() {
  docMsg.value = null
  try {
    await monitoringApi.addDocument(newDoc.value)
    newDoc.value = { title: '', text: '', min_role: 'viewer' }
    docMsg.value = { ok: true, text: t('assistant.docAdded') }
    await loadDocs()
  } catch (e) {
    docMsg.value = { ok: false, text: apiText(e) }
  }
}
async function approve(d: RagDocument) {
  docMsg.value = null
  try {
    await monitoringApi.approveDocument(d.doc_id)
    await loadDocs()
  } catch (e) {
    docMsg.value = { ok: false, text: apiText(e) }
  }
}

onMounted(() => {
  loadSettings()
  loadDocs()
})
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>{{ t('nav.assistant') }}</h1>
      <p class="lede">{{ t('assistant.lede') }}</p>
    </header>

    <PanelBox :title="t('assistant.ask')">
      <form class="ask" @submit.prevent="ask">
        <label>
          <span>{{ t('assistant.component') }}</span>
          <select v-model="componentId" data-testid="ask-component">
            <option value="">{{ t('assistant.noComponent') }}</option>
            <option v-for="c in components" :key="c.id" :value="c.id">{{ c.label }}</option>
          </select>
        </label>
        <label class="wide">
          <span>{{ t('assistant.question') }}</span>
          <textarea v-model="question" rows="3" maxlength="2000" data-testid="ask-question" />
        </label>
        <div class="row">
          <button
            type="submit"
            class="primary"
            :disabled="asking || !question.trim()"
            data-testid="ask-go"
          >
            {{ asking ? t('assistant.thinking') : t('assistant.send') }}
          </button>
          <button v-if="asking" type="button" data-testid="ask-cancel" @click="cancel">
            {{ t('assistant.cancel') }}
          </button>
        </div>
      </form>
      <p v-if="askError" class="error" role="alert" data-testid="ask-error">{{ askError }}</p>
      <p v-if="asking && partial" class="partial">{{ partial }}</p>

      <div v-if="answer" class="answer" data-testid="answer">
        <p v-if="answer.health_state" class="health">
          {{ t('assistant.ruleHealth') }} <HealthBadge :state="answer.health_state" />
        </p>
        <p class="text" data-testid="answer-text">{{ answer.answer }}</p>
        <ul v-if="answer.checks.length" class="checks">
          <li v-for="c in answer.checks" :key="c">{{ c }}</li>
        </ul>
        <h3 v-if="answer.citations.length">{{ t('assistant.sources') }}</h3>
        <ol class="cites" data-testid="citations">
          <li v-for="c in answer.citations" :key="c.chunk_id" :data-chunk="c.chunk_id">
            <strong>{{ c.title }}</strong> <span class="small">{{ c.chunk_id }}</span>
            <blockquote>{{ c.excerpt }}</blockquote>
          </li>
        </ol>
        <ul v-if="answer.guard_notes.length" class="notes" data-testid="guard-notes">
          <li v-for="n in answer.guard_notes" :key="n">{{ n }}</li>
        </ul>
        <p class="small">{{ t('assistant.advisory', { model: answer.model }) }}</p>
        <div class="row">
          <span class="small">{{ t('assistant.rate') }}</span>
          <button type="button" data-testid="rate-good" @click="rate('CONFIRMED')">
            {{ t('assistant.good') }}
          </button>
          <button type="button" data-testid="rate-bad" @click="rate('FALSE_ALARM')">
            {{ t('assistant.bad') }}
          </button>
          <span v-if="fbDone" class="small" data-testid="rated">{{ fbDone }}</span>
        </div>
      </div>
    </PanelBox>

    <PanelBox :title="t('assistant.documents')">
      <p class="small">{{ t('assistant.docsLede') }}</p>
      <table class="docs" data-testid="documents">
        <thead>
          <tr>
            <th>{{ t('assistant.docTitle') }}</th>
            <th>{{ t('assistant.minRole') }}</th>
            <th>{{ t('assistant.state') }}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in docs" :key="d.doc_id" :data-doc="d.doc_id">
            <td>
              {{ d.title }} <span class="small">{{ d.doc_id }}</span>
            </td>
            <td>{{ t(`models.roles.${d.min_role}`) }}</td>
            <td>
              {{ d.approved ? t('assistant.approved', { n: d.chunks }) : t('assistant.pending') }}
            </td>
            <td>
              <button
                v-if="!d.approved"
                type="button"
                data-testid="doc-approve"
                @click="approve(d)"
              >
                {{ t('assistant.approve') }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <form class="newdoc" @submit.prevent="addDoc">
        <input
          v-model="newDoc.title"
          :placeholder="t('assistant.docTitle')"
          data-testid="doc-title"
        />
        <select v-model="newDoc.min_role" :aria-label="t('assistant.minRole')">
          <option v-for="r in ['viewer', 'maintenance', 'engineer', 'admin']" :key="r" :value="r">
            {{ t(`models.roles.${r}`) }}
          </option>
        </select>
        <textarea
          v-model="newDoc.text"
          rows="4"
          :placeholder="t('assistant.docText')"
          data-testid="doc-text"
        />
        <button type="submit" :disabled="!newDoc.title || !newDoc.text" data-testid="doc-add">
          {{ t('assistant.addDoc') }}
        </button>
      </form>
      <p v-if="docMsg" :class="docMsg.ok ? 'ok' : 'error'" role="status" data-testid="doc-msg">
        {{ docMsg.text }}
      </p>
    </PanelBox>

    <PanelBox v-if="cfg" :title="t('assistant.settings')">
      <form class="settings" @submit.prevent="saveSettings">
        <label class="check">
          <input v-model="cfg.enabled" type="checkbox" data-testid="llm-enabled" />
          {{ t('assistant.enabled') }}
        </label>
        <label>
          <span>{{ t('assistant.endpoint') }}</span>
          <input v-model="cfg.endpoint" type="text" data-testid="llm-endpoint" />
        </label>
        <label>
          <span>{{ t('assistant.hosts') }}</span>
          <input v-model="hosts" type="text" placeholder="ollama.plant.lan" />
        </label>
        <label>
          <span>{{ t('assistant.chatModel') }}</span>
          <select v-model="cfg.chat_model" data-testid="llm-chat-model">
            <option value="">—</option>
            <option v-for="m in health?.models ?? []" :key="m" :value="m">{{ m }}</option>
          </select>
        </label>
        <label>
          <span>{{ t('assistant.embedModel') }}</span>
          <select v-model="cfg.embed_model" data-testid="llm-embed-model">
            <option value="">—</option>
            <option v-for="m in health?.models ?? []" :key="m" :value="m">{{ m }}</option>
          </select>
        </label>
        <div class="row">
          <button type="submit" class="primary" data-testid="llm-save">
            {{ t('assistant.save') }}
          </button>
          <button type="button" data-testid="llm-check" @click="checkHealth">
            {{ t('assistant.check') }}
          </button>
        </div>
      </form>
      <p
        v-if="settingsMsg"
        :class="settingsMsg.ok ? 'ok' : 'error'"
        role="status"
        data-testid="llm-msg"
      >
        {{ settingsMsg.text }}
      </p>
      <p v-if="health" class="small" data-testid="llm-health">
        {{
          health.reachable
            ? t('assistant.reachable', {
                endpoint: health.endpoint,
                version: health.version,
                n: health.models.length,
              })
            : t('assistant.unreachable', { endpoint: health.endpoint })
        }}
      </p>
      <p class="small">{{ t('assistant.localOnly') }}</p>
    </PanelBox>
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
  margin-top: var(--space-3);
}
.lede,
.small {
  color: var(--ink-soft);
  font-size: var(--text-sm);
}
.small {
  font-size: var(--text-xs);
}
form {
  display: grid;
  gap: var(--space-3);
}
label {
  display: grid;
  gap: 2px;
  font-size: var(--text-xs);
  color: var(--ink-soft);
}
label.check {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  font-size: var(--text-sm);
  color: var(--ink);
}
input[type='text'],
input:not([type]),
textarea,
select {
  font: inherit;
  font-size: var(--text-sm);
  padding: 6px 8px;
  border: 1px solid var(--line);
  border-radius: var(--radius-control);
  background: var(--surface);
  color: var(--ink);
}
.row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
}
.partial {
  white-space: pre-wrap;
  color: var(--ink-soft);
  font-size: var(--text-sm);
}
.answer {
  display: grid;
  gap: var(--space-2);
  margin-top: var(--space-3);
}
.health {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  font-size: var(--text-sm);
}
.text {
  white-space: pre-wrap;
  line-height: 1.6;
}
.checks,
.notes {
  margin-left: var(--space-4);
  font-size: var(--text-sm);
}
.notes {
  color: var(--health-warning);
  font-size: var(--text-xs);
}
.cites {
  display: grid;
  gap: var(--space-2);
  margin-left: var(--space-4);
  font-size: var(--text-sm);
}
blockquote {
  margin: 2px 0 0;
  padding-left: var(--space-2);
  border-left: 2px solid var(--line);
  color: var(--ink-soft);
  font-size: var(--text-xs);
  white-space: pre-wrap;
}
.docs {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
  margin: var(--space-2) 0 var(--space-3);
}
.docs th,
.docs td {
  text-align: left;
  padding: 4px 8px;
  border-bottom: 1px solid var(--line);
}
.docs th {
  color: var(--ink-faint);
  font-weight: 500;
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
}
.ok {
  color: var(--health-normal);
  font-size: var(--text-sm);
}
</style>

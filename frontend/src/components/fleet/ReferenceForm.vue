<script setup lang="ts">
/** Freeze a period of stored feature windows as the verified healthy reference (L4-06, D-040). */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Baseline, FeatureCoverage } from '@/api/contracts'
import { monitoringApi } from '@/api/monitoring'
import { useLocalized } from '@/composables/useLocalized'

const props = defineProps<{ componentId: string }>()
const emit = defineEmits<{ verified: [Baseline] }>()
const { t } = useI18n()
const { lt } = useLocalized()

const coverage = ref<FeatureCoverage[]>([])
const pick = ref(0)
const start = ref('')
const end = ref('')
const comment = ref('')
const busy = ref(false)
const error = ref<string | null>(null)
const result = ref<Baseline | null>(null)
const cur = computed(() => coverage.value[pick.value] ?? null)
const local = (iso: string) => iso.slice(0, 16)
const DAY = 86_400_000

function reset() {
  const c = cur.value
  if (!c) return
  start.value = local(c.start)
  end.value = local(
    new Date(Math.min(Date.parse(c.start) + 3 * DAY, Date.parse(c.end))).toISOString(),
  )
}
watch(
  () => props.componentId,
  async (id) => {
    coverage.value = []
    result.value = error.value = null
    pick.value = 0
    coverage.value = await monitoringApi.featureCoverage(id).catch(() => [])
    reset()
  },
  { immediate: true },
)
watch(pick, reset)

async function submit() {
  const c = cur.value
  if (!c || busy.value) return
  busy.value = true
  error.value = null
  try {
    result.value = await monitoringApi.verifyBaseline({
      component_id: props.componentId,
      lifecycle_id: c.lifecycle_id,
      feature_ref: c.feature_ref,
      regime_id: null,
      window: {
        start: new Date(`${start.value}:00Z`).toISOString(),
        end: new Date(`${end.value}:00Z`).toISOString(),
      },
      comment: comment.value,
    })
    emit('verified', result.value)
    comment.value = ''
    coverage.value = await monitoringApi
      .featureCoverage(props.componentId)
      .catch(() => coverage.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section v-if="coverage.length" class="verify" data-testid="reference-form">
    <h3>{{ t('baselines.verify.title') }}</h3>
    <p class="hint">{{ t('baselines.verify.hint') }}</p>
    <form @submit.prevent="submit">
      <label>
        {{ t('baselines.verify.lifecycle') }}
        <select v-model.number="pick" data-testid="verify-lifecycle">
          <option v-for="(c, i) in coverage" :key="c.lifecycle_id + c.feature_ref" :value="i">
            {{ c.lifecycle_id }} · {{ c.feature_ref }} · {{ c.windows }}
            {{ c.has_reference ? '✓' : '' }}
          </option>
        </select>
      </label>
      <label>
        {{ t('baselines.verify.start') }}
        <input v-model="start" type="datetime-local" required />
      </label>
      <label>
        {{ t('baselines.verify.end') }}
        <input v-model="end" type="datetime-local" required />
      </label>
      <label class="wide">
        {{ t('baselines.verify.comment') }}
        <input v-model.trim="comment" required maxlength="2000" data-testid="verify-comment" />
      </label>
      <button type="submit" :disabled="busy || !comment" data-testid="verify-submit">
        {{ t('baselines.verify.submit') }}
      </button>
    </form>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div v-if="result" data-testid="verify-result">
      <p>{{ t('baselines.verify.done', { id: result.baseline_id }) }}</p>
      <ul v-if="result.warnings.length" class="warn" data-testid="verify-warnings">
        <li v-for="(w, i) in result.warnings" :key="i">{{ lt(w) }}</li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.verify {
  display: grid;
  gap: var(--space-2);
  margin-top: var(--space-4);
  font-size: var(--text-sm);
}
form {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  align-items: end;
}
label {
  display: grid;
  gap: var(--space-1);
}
.wide {
  flex: 1 1 260px;
}
.hint {
  color: var(--ink-soft);
}
.warn {
  color: var(--health-warning);
  padding-left: var(--space-4);
}
.error {
  color: var(--health-critical);
}
</style>

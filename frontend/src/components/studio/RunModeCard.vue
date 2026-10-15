<script setup lang="ts">
/** Run mode switch (administrators only, D-053): simulation demo or production TDengine, never both. */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { changeRunMode, useRunMode } from '@/composables/useRunMode'
import type { RunMode } from '@/api/contracts'

const { t } = useI18n()
const { mode } = useRunMode()
const error = ref('')
const busy = ref(false)

async function switchTo(next: RunMode) {
  const key = next === 'production' ? 'runMode.confirmProduction' : 'runMode.confirmSimulation'
  if (typeof window !== 'undefined' && !window.confirm(t(key))) return
  busy.value = true
  error.value = ''
  try {
    await changeRunMode(next)
  } catch (e) {
    error.value = `${t('runMode.failed')}: ${e instanceof Error ? e.message : String(e)}`
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section v-if="mode" class="card" data-testid="run-mode-card">
    <h2>{{ t('runMode.title') }}</h2>
    <p class="st-note">{{ t('runMode.lede') }}</p>
    <p class="row">
      <strong data-testid="run-mode-current">{{
        t('runMode.current', { mode: t(`runMode.${mode}`) })
      }}</strong>
      <button
        v-if="mode === 'simulation'"
        type="button"
        data-testid="run-mode-production"
        :disabled="busy"
        @click="switchTo('production')"
      >
        {{ t('runMode.toProduction') }}
      </button>
      <button
        v-else
        type="button"
        data-testid="run-mode-simulation"
        :disabled="busy"
        @click="switchTo('simulation')"
      >
        {{ t('runMode.toSimulation') }}
      </button>
    </p>
    <p v-if="error" class="st-note error" role="alert">{{ error }}</p>
  </section>
</template>

<style scoped>
.card {
  display: grid;
  gap: var(--space-2);
  padding: var(--space-4);
  border: 1px solid var(--line);
  border-radius: var(--radius-md, 8px);
  background: var(--surface);
}
h2 {
  font-size: var(--text-md, 1rem);
}
.row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  flex-wrap: wrap;
}
.error {
  color: var(--danger, #b3261e);
}
</style>

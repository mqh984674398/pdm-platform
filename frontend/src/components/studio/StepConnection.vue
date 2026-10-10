<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useStudioStore } from '@/studio/store'

const s = useStudioStore()
const source = computed(() => s.source!)
const { t, n } = useI18n()
const testing = ref(false)
const hasTdengine = computed(() => s.sources.some((c) => c.kind === 'TDENGINE'))

async function test() {
  testing.value = true
  try {
    await s.testConnection()
  } finally {
    testing.value = false
  }
}
</script>

<template>
  <div class="st-stack">
    <div class="st-choices" role="radiogroup" :aria-label="t('studio.connection.source')">
      <button
        v-for="c in s.sources"
        :key="c.data_source_id"
        type="button"
        class="st-choice"
        role="radio"
        :aria-checked="c.data_source_id === source.data_source_id"
        :data-testid="`source-${c.data_source_id}`"
        @click="s.selectSource(c.data_source_id)"
      >
        <strong>{{ c.kind === 'SIMULATED' ? t('studio.connection.demoSource') : c.name }}</strong>
        <span class="muted">{{
          c.kind === 'SIMULATED'
            ? t('studio.connection.demoSourceNote')
            : c.kind === 'TDENGINE'
              ? t('studio.connection.tdengineNote')
              : t('studio.connection.production')
        }}</span>
      </button>
    </div>
    <p v-if="!hasTdengine" class="st-note" data-testid="no-tdengine">
      {{ t('studio.connection.noTdengine') }}
    </p>

    <div class="st-form">
      <label class="st-field">
        <span>{{ t('studio.connection.engine') }}</span>
        <input
          class="st-input"
          readonly
          :value="source.engine ?? t('studio.connection.engineUnverified')"
        />
      </label>
      <label class="st-field">
        <span>{{ t('studio.connection.host') }}</span>
        <input class="st-input st-mono" readonly :value="source.host" />
      </label>
      <label class="st-field">
        <span>{{ t('studio.connection.port') }}</span>
        <input class="st-input st-mono" readonly :value="source.port" />
      </label>
      <label class="st-field">
        <span>{{ t('studio.connection.database') }}</span>
        <input class="st-input st-mono" readonly :value="source.database" />
      </label>
      <label class="st-field">
        <span>{{ t('studio.connection.credential') }}</span>
        <input class="st-input st-mono" readonly :value="source.credential_ref" />
        <span class="st-note">{{ t('studio.connection.credentialNote') }}</span>
      </label>
      <label class="st-field">
        <span>{{ t('studio.connection.readOnly') }}</span>
        <span class="lock"
          ><input type="checkbox" checked disabled />
          {{ t('studio.connection.readOnlyNote') }}</span
        >
      </label>
      <label class="st-field">
        <span>{{ t('studio.connection.timeout') }}</span>
        <input
          class="st-input"
          readonly
          :value="t('studio.connection.seconds', { n: source.statement_timeout_s })"
        />
      </label>
      <label class="st-field">
        <span>{{ t('studio.connection.maxRows') }}</span>
        <input class="st-input" readonly :value="n(source.max_rows ?? 0)" />
      </label>
    </div>

    <div class="test">
      <button
        type="button"
        class="st-button primary"
        data-testid="test-connection"
        :disabled="testing"
        @click="test"
      >
        {{ testing ? t('studio.connection.testing') : t('studio.connection.test') }}
      </button>
      <ul v-if="s.checks" class="checks" data-testid="connection-checks">
        <li v-for="c in s.checks" :key="c.key" :class="c.ok ? 'st-ok' : 'bad'">
          <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
            <path
              v-if="c.ok"
              d="M3 8.5l3 3 7-7"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            />
            <path
              v-else
              d="M4 4l8 8M12 4l-8 8"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            />
          </svg>
          {{ t(`studio.connection.checks.${c.key}`) }}
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.lock {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  min-height: 34px;
  color: var(--ink-soft);
}
.test {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  align-items: flex-start;
}
.checks {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 2px;
  font-size: var(--text-sm);
}
.checks li {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}
.bad {
  color: var(--health-critical);
}
</style>

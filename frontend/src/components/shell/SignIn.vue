<script setup lang="ts">
/** Local account sign-in for LAN deployment (SEC-01, T028). */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { signIn } from '@/api/session'

const { t } = useI18n()
const user = ref('')
const password = ref('')
const busy = ref(false)
const failed = ref(false)

async function submit() {
  busy.value = true
  failed.value = false
  try {
    failed.value = !(await signIn(user.value.trim(), password.value))
  } catch {
    failed.value = true
  } finally {
    password.value = ''
    busy.value = false
  }
}
</script>

<template>
  <form class="sign-in" data-testid="sign-in" @submit.prevent="submit">
    <h1>{{ t('auth.title') }}</h1>
    <p class="hint">{{ t('auth.hint') }}</p>
    <label>
      <span>{{ t('auth.user') }}</span>
      <input v-model="user" autocomplete="username" required data-testid="sign-in-user" />
    </label>
    <label>
      <span>{{ t('auth.password') }}</span>
      <input
        v-model="password"
        type="password"
        autocomplete="current-password"
        required
        data-testid="sign-in-password"
      />
    </label>
    <p v-if="failed" class="error" role="alert">{{ t('auth.failed') }}</p>
    <button type="submit" class="primary" :disabled="busy">{{ t('auth.submit') }}</button>
  </form>
</template>

<style scoped>
.sign-in {
  display: grid;
  gap: var(--space-3);
  max-width: 340px;
  margin: 10vh auto 0;
  padding: var(--space-5);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-panel, 10px);
}
h1 {
  font-size: var(--text-xl);
}
.hint {
  color: var(--ink-soft);
  font-size: var(--text-sm);
}
label {
  display: grid;
  gap: var(--space-1);
  font-size: var(--text-sm);
}
input {
  font: inherit;
  padding: 6px 8px;
  border: 1px solid var(--line);
  border-radius: var(--radius-control);
  background: var(--surface);
  color: var(--ink);
}
button.primary {
  font: inherit;
  padding: 7px 12px;
  border: 1px solid var(--accent);
  border-radius: var(--radius-control);
  background: var(--accent);
  color: var(--surface);
  cursor: pointer;
}
button:disabled {
  opacity: 0.6;
}
.error {
  color: var(--health-critical);
  font-size: var(--text-sm);
}
</style>

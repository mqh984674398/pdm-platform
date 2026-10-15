<script setup lang="ts">
/** Non-modal side sheet for editing one node; the page behind it stays usable. Esc closes it. */
import { useI18n } from 'vue-i18n'

defineProps<{ open: boolean; title: string }>()
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()
</script>

<template>
  <aside
    v-if="open"
    class="drawer"
    role="dialog"
    :aria-label="title"
    data-testid="side-drawer"
    @keydown.esc="emit('close')"
  >
    <header>
      <h2>{{ title }}</h2>
      <button type="button" class="close" :aria-label="t('common.close')" @click="emit('close')">
        ×
      </button>
    </header>
    <div class="body"><slot /></div>
  </aside>
</template>

<style scoped>
.drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: min(520px, 100vw);
  z-index: 30;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border-left: 1px solid var(--line);
  box-shadow: -8px 0 24px rgb(0 0 0 / 0.18);
}
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--line);
}
h2 {
  font-size: var(--text-base);
  margin: 0;
}
.close {
  border: 0;
  background: none;
  font-size: 1.5rem;
  line-height: 1;
  color: var(--ink-soft);
  cursor: pointer;
}
.body {
  overflow: auto;
  padding: var(--space-4);
}
</style>

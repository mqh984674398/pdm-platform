<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import PanelBox from '@/components/base/PanelBox.vue'

defineProps<{ name: string; task: string }>()
const { t } = useI18n()
</script>

<template>
  <div class="page">
    <h1>{{ t(`nav.${name}`) }}</h1>
    <p class="purpose">{{ t(`placeholder.purpose.${name}`) }}</p>
    <PanelBox>
      <p class="pending" data-testid="placeholder">{{ t('placeholder.deliveredIn', { task }) }}</p>
    </PanelBox>
  </div>
</template>

<style scoped>
.page {
  display: grid;
  gap: var(--space-4);
  max-width: 960px;
}
h1 {
  font-size: var(--text-xl);
}
.purpose {
  color: var(--ink-soft);
}
.pending {
  color: var(--ink-faint);
}
</style>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useLocalized } from '@/composables/useLocalized'
import { useStudioStore } from '@/studio/store'

const s = useStudioStore()
const { t, n } = useI18n()
const { lt } = useLocalized()
const chosen = computed(() => s.templates.find((x) => x.template_id === s.templateId))
</script>

<template>
  <div class="st-stack">
    <div class="st-choices" role="radiogroup" :aria-label="t('studio.steps.template')">
      <button
        v-for="tp in s.templates"
        :key="tp.template_id"
        type="button"
        class="st-choice"
        role="radio"
        :aria-checked="s.templateId === tp.template_id"
        :data-template="tp.template_id"
        @click="s.templateId = tp.template_id"
      >
        <strong>{{ lt(tp.name) }}</strong>
        <span class="muted">{{ lt(tp.description) }}</span>
        <span class="st-note">
          {{ t('studio.template.version', { v: tp.version }) }} ·
          {{ t('studio.template.limits', { rows: n(tp.max_rows), hours: tp.max_range_hours }) }}
        </span>
      </button>
    </div>

    <div v-if="chosen" class="detail">
      <div>
        <h3>{{ t('studio.template.params') }}</h3>
        <ul class="params">
          <li v-for="p in chosen.parameters" :key="p.name">
            <span>{{ lt(p.label) }}</span>
            <span class="st-note">{{ t(`studio.template.paramTypes.${p.type}`) }}</span>
          </li>
        </ul>
      </div>
      <div>
        <h3>{{ t('studio.template.sql') }}</h3>
        <pre v-if="chosen.sql" class="sql st-mono" data-testid="template-sql">{{ chosen.sql }}</pre>
        <p v-else class="locked" data-testid="template-sql-locked">
          <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
            <rect
              x="3"
              y="7"
              width="10"
              height="7"
              rx="1.5"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
            />
            <path
              d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
            />
          </svg>
          {{ t('studio.template.sqlLocked') }}
        </p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.detail {
  display: grid;
  grid-template-columns: minmax(200px, 1fr) 2fr;
  gap: var(--space-5);
}
@media (max-width: 760px) {
  .detail {
    grid-template-columns: 1fr;
  }
}
h3 {
  font-size: var(--text-sm);
  margin-bottom: var(--space-2);
}
.params {
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: var(--text-sm);
}
.params li {
  display: flex;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-1) 0;
  border-bottom: 1px solid var(--line);
}
.sql {
  margin: 0;
  padding: var(--space-3);
  border-radius: var(--radius-control);
  background: var(--surface-inset);
  box-shadow: inset 0 0 0 1px var(--line);
  white-space: pre-wrap;
}
.locked {
  display: flex;
  gap: var(--space-2);
  align-items: flex-start;
  padding: var(--space-3);
  border-radius: var(--radius-control);
  background: var(--surface-inset);
  color: var(--ink-soft);
  font-size: var(--text-sm);
}
.locked svg {
  flex: none;
  margin-top: 3px;
}
</style>

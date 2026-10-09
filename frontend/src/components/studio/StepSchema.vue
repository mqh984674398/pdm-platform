<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useLocalized } from '@/composables/useLocalized'
import { useStudioStore } from '@/studio/store'

const s = useStudioStore()
const { t, n } = useI18n()
const { fmtDate } = useLocalized()
</script>

<template>
  <div v-if="s.schema" class="st-stack">
    <div class="facts">
      <p>
        <span class="label">{{ t('studio.schema.table') }}</span>
        <strong class="st-mono">{{ s.schema.name }}</strong>
      </p>
      <p>{{ t('studio.schema.rows', { n: n(s.schema.row_count) }) }}</p>
      <p>{{ t('studio.schema.devices', { n: s.schema.metadata.devices.length }) }}</p>
      <p v-if="s.schema.metadata.earliest_ts && s.schema.metadata.latest_ts">
        {{
          t('studio.schema.range', {
            start: fmtDate(s.schema.metadata.earliest_ts, false),
            end: fmtDate(s.schema.metadata.latest_ts, false),
          })
        }}
      </p>
    </div>
    <div class="st-scroll">
      <table class="st-table" data-testid="schema-columns">
        <thead>
          <tr>
            <th>{{ t('studio.schema.column') }}</th>
            <th>{{ t('studio.schema.type') }}</th>
            <th>{{ t('studio.schema.role') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in s.schema.columns" :key="c.name">
            <td class="st-mono">{{ c.name }}</td>
            <td class="st-mono muted">{{ c.type }}</td>
            <td>
              <span :class="{ role: c.role }">{{
                t(`studio.schema.roles.${c.role ?? 'none'}`)
              }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div>
      <h3>{{ t('studio.schema.sample') }}</h3>
      <div class="st-scroll">
        <table class="st-table st-mono">
          <thead>
            <tr>
              <th v-for="c in s.schema.columns" :key="c.name">{{ c.name }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in s.schema.sample_rows" :key="i">
              <td v-for="(v, j) in r" :key="j">{{ v }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<style scoped>
.facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-5);
  font-size: var(--text-sm);
  color: var(--ink-soft);
}
.label {
  margin-right: var(--space-2);
}
.facts strong {
  color: var(--ink);
}
.muted {
  color: var(--ink-soft);
}
.role {
  font-weight: 500;
  color: var(--accent);
}
h3 {
  font-size: var(--text-sm);
  margin-bottom: var(--space-2);
}
</style>

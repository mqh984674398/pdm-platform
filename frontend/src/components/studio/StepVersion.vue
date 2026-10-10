<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useLocalized } from '@/composables/useLocalized'
import { useStudioStore } from '@/studio/store'

const s = useStudioStore()
const { t } = useI18n()
const { lt, fmtDate } = useLocalized()
const template = computed(() => s.templates.find((x) => x.template_id === s.templateId))
/** Backend messages are bilingual; show the one for the current language plus the reason. */
const errorText = computed(() => {
  const e = s.saveError
  if (!e) return ''
  const loc = 'localized' in e && e.localized ? lt(e.localized) : ''
  const reason = 'reason' in e && e.reason ? e.reason : ''
  return [loc || t('studio.version.saveFailed'), reason].filter(Boolean).join(' ')
})
</script>

<template>
  <div class="st-stack">
    <section>
      <h3>{{ t('studio.version.summary') }}</h3>
      <dl class="summary" data-testid="version-summary">
        <dt>{{ t('studio.version.device') }}</dt>
        <dd class="st-mono">{{ s.deviceId }}</dd>
        <dt>{{ t('studio.version.template') }}</dt>
        <dd>{{ lt(template?.name) }}</dd>
        <dt>{{ t('studio.version.signals') }}</dt>
        <dd>
          <span v-for="m in s.content.mappings" :key="m.signal_id" class="item">
            {{ lt(s.signalName(m.key_name)) || m.key_name }}
            <span class="st-note">{{ m.conversion?.target_unit }}</span>
          </span>
        </dd>
        <dt>{{ t('studio.version.groups') }}</dt>
        <dd>
          <span v-for="g in s.groups" :key="g.group_id" class="item">
            {{ lt(g.name) }}
            <span class="st-note">{{ t(`studio.viz.charts.${g.chart}`) }}</span>
          </span>
        </dd>
      </dl>
    </section>

    <form class="save" @submit.prevent="s.save()">
      <label class="st-field">
        <span>{{ t('studio.version.comment') }}</span>
        <input
          v-model="s.comment"
          class="st-input"
          data-testid="version-comment"
          :placeholder="t('studio.version.commentPlaceholder')"
          :disabled="!!s.saved"
        />
      </label>
      <button
        type="submit"
        class="st-button primary"
        data-testid="save-version"
        :disabled="!s.comment.trim() || !!s.saved"
      >
        {{ t('studio.version.save') }}
      </button>
    </form>
    <p v-if="s.saved" class="saved" role="status" data-testid="saved-status">
      {{ t('studio.version.saved', { v: s.saved.version }) }}
    </p>
    <p v-if="s.saveError" class="save-error" role="alert" data-testid="save-error">
      {{ errorText }}
    </p>
    <p class="st-note">{{ t('studio.version.immutable') }}</p>

    <section>
      <h3>{{ t('studio.version.history') }}</h3>
      <div class="st-scroll">
        <table class="st-table" data-testid="version-history">
          <thead>
            <tr>
              <th></th>
              <th>{{ t('studio.version.at') }}</th>
              <th>{{ t('studio.version.by') }}</th>
              <th>{{ t('studio.version.note') }}</th>
              <th>{{ t('studio.version.hash') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="v in s.versions"
              :key="v.version"
              :class="{ fresh: s.saved?.version === v.version }"
            >
              <td>
                <strong>{{ t('studio.version.versionN', { v: v.version }) }}</strong>
                <span v-if="s.saved?.version === v.version" class="new">{{
                  t('studio.version.current')
                }}</span>
              </td>
              <td>{{ fmtDate(v.created_at) }} {{ t('studio.utc') }}</td>
              <td class="st-mono">{{ v.created_by }}</td>
              <td>{{ v.comment }}</td>
              <td class="st-mono hash" :title="v.content_hash">
                {{ v.content_hash.slice(0, 19) }}…
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="s.apiKind === 'mock'" class="st-note">{{ t('studio.version.simHistory') }}</p>
    </section>
  </div>
</template>

<style scoped>
h3 {
  font-size: var(--text-sm);
  margin-bottom: var(--space-2);
}
.summary {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: var(--space-2) var(--space-5);
  margin: 0;
  font-size: var(--text-sm);
}
dt {
  color: var(--ink-soft);
}
dd {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1) var(--space-4);
}
.item {
  display: inline-flex;
  gap: var(--space-1);
  align-items: baseline;
}
.save {
  display: flex;
  gap: var(--space-3);
  align-items: flex-end;
}
.save .st-field {
  flex: 1;
}
.saved {
  color: var(--health-normal);
  font-weight: 600;
}
.save-error {
  color: var(--health-critical);
  font-weight: 600;
}
.fresh td {
  background: var(--health-normal-soft);
}
.new {
  margin-left: var(--space-2);
  padding: 0 6px;
  border-radius: 4px;
  font-size: var(--text-xs);
  background: var(--health-normal);
  color: #fff;
}
.hash {
  color: var(--ink-soft);
}
</style>

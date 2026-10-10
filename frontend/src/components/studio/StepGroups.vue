<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useLocalized } from '@/composables/useLocalized'
import { useStudioStore, type GroupDraft } from '@/studio/store'

const s = useStudioStore()
const { t } = useI18n()
const { lt } = useLocalized()

function toggle(g: GroupDraft, key: string) {
  g.keys = g.keys.includes(key) ? g.keys.filter((k) => k !== key) : [...g.keys, key]
}
</script>

<template>
  <div class="st-stack">
    <article v-for="g in s.groups" :key="g.group_id" class="group" :data-group="g.group_id">
      <div class="st-form">
        <label class="st-field">
          <span>{{ t('studio.groups.nameZh') }}</span>
          <input v-model="g.name.zh" class="st-input" />
        </label>
        <label class="st-field">
          <span>{{ t('studio.groups.nameEn') }}</span>
          <input v-model="g.name.en" class="st-input" />
        </label>
      </div>
      <div class="members" role="group" :aria-label="t('studio.groups.signals')">
        <button
          v-for="d in s.activeDrafts"
          :key="d.key_name"
          type="button"
          class="member"
          :aria-pressed="g.keys.includes(d.key_name)"
          @click="toggle(g, d.key_name)"
        >
          {{ lt(s.signalName(d.key_name)) || d.key_name }}
          <span class="st-mono st-note">{{ d.key_name }}</span>
        </button>
      </div>
      <div class="foot">
        <span v-if="!g.keys.length" class="warn">{{ t('studio.groups.empty') }}</span>
        <button type="button" class="link" @click="s.removeGroup(g.group_id)">
          {{ t('studio.groups.remove') }}
        </button>
      </div>
    </article>
    <div>
      <button type="button" class="st-button" data-testid="add-group" @click="s.addGroup()">
        {{ t('studio.groups.add') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.group {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
  border: 1px solid var(--line);
  border-radius: var(--radius-panel);
}
.members {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.member {
  display: inline-flex;
  gap: var(--space-2);
  align-items: baseline;
  padding: 4px 12px;
  border-radius: 999px;
  border: 1px solid var(--line-strong);
  background: var(--surface);
  font-size: var(--text-sm);
  cursor: pointer;
}
.member[aria-pressed='true'] {
  background: var(--accent-soft);
  border-color: var(--accent);
}
.foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: var(--text-sm);
}
.warn {
  color: var(--health-warning);
}
.link {
  margin-left: auto;
  border: 0;
  background: none;
  color: var(--accent);
  cursor: pointer;
  font-size: var(--text-sm);
}
</style>

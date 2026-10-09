<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useLocalized } from '@/composables/useLocalized'
import { useStudioStore } from '@/studio/store'

const s = useStudioStore()
const { t } = useI18n()
const { lt } = useLocalized()
const comp = (id: string | null) => s.deviceComponents.find((c) => c.component_id === id)
</script>

<template>
  <div class="st-stack">
    <div class="st-scroll">
      <table class="st-table">
        <thead>
          <tr>
            <th>{{ t('studio.units.signal') }}</th>
            <th>{{ t('studio.components.component') }}</th>
            <th>{{ t('studio.components.type') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in s.activeDrafts" :key="d.key_name">
            <td>
              <div>{{ lt(s.signalName(d.key_name)) || d.key_name }}</div>
              <div class="st-note st-mono">{{ d.key_name }}</div>
            </td>
            <td>
              <select
                class="st-select"
                :value="d.component_id ?? ''"
                :data-component-for="d.key_name"
                @change="s.setComponent(d.key_name, ($event.target as HTMLSelectElement).value)"
              >
                <option value="" disabled>{{ t('studio.components.choose') }}</option>
                <option
                  v-for="c in s.deviceComponents"
                  :key="c.component_id"
                  :value="c.component_id"
                >
                  {{ lt(c.name) }}
                </option>
              </select>
            </td>
            <td class="type">
              {{ comp(d.component_id) ? t(`types.${comp(d.component_id)!.type}`) : '' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <ul class="groups">
      <li v-for="g in s.groups" :key="g.group_id">
        <strong>{{ lt(g.name) }}</strong>
        <span class="st-note">
          {{
            s.groupComponent(g)
              ? t('studio.components.groupComponent', { name: lt(comp(s.groupComponent(g))?.name) })
              : t('studio.components.mixed')
          }}
        </span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.type {
  color: var(--ink-soft);
}
.groups {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: var(--space-1);
  font-size: var(--text-sm);
}
.groups li {
  display: flex;
  gap: var(--space-3);
  align-items: baseline;
}
</style>

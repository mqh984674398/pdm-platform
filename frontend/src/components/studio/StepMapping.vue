<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useStudioStore, type FieldMapping } from '@/studio/store'

const s = useStudioStore()
const { t } = useI18n()
const FIELDS: { key: keyof FieldMapping; label: string }[] = [
  { key: 'device_field', label: 'device' },
  { key: 'key_field', label: 'key' },
  { key: 'time_field', label: 'time' },
  { key: 'value_field', label: 'value' },
]
</script>

<template>
  <div class="st-stack">
    <p class="st-note">{{ t('studio.mapping.detected') }}</p>
    <div class="st-form">
      <label v-for="f in FIELDS" :key="f.key" class="st-field">
        <span>{{ t(`studio.mapping.${f.label}`) }}</span>
        <select v-model="s.fields[f.key]" class="st-select st-mono" :data-field="f.key">
          <option value="">{{ t('studio.mapping.choose') }}</option>
          <option v-for="c in s.schema?.columns ?? []" :key="c.name" :value="c.name">
            {{ c.name }}
          </option>
        </select>
      </label>
    </div>
  </div>
</template>

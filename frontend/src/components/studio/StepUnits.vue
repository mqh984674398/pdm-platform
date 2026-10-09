<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useLocalized } from '@/composables/useLocalized'
import { useStudioStore, type SignalDraft } from '@/studio/store'
import { convert, suggestedScale, UNITS } from '@/studio/units'

const s = useStudioStore()
const { t } = useI18n()
const { lt } = useLocalized()

function units(d: SignalDraft) {
  const list = UNITS[d.quantity]
  return [...new Set([...list, d.source_unit, d.target_unit])].filter(Boolean)
}
function onUnit(d: SignalDraft) {
  d.scale = suggestedScale(d.source_unit, d.target_unit) ?? d.scale
}
function example(d: SignalDraft) {
  const raw = s.preview?.series[d.key_name]?.find(([, v]) => v !== 0)?.[1]
  if (raw === undefined || d.scale === null) return ''
  return `${raw} ${d.source_unit} → ${+convert(raw, { scale: d.scale, offset: d.offset }).toPrecision(5)} ${d.target_unit}`
}
function onScale(d: SignalDraft, e: Event) {
  const v = (e.target as HTMLInputElement).value
  d.scale = v === '' ? null : Number(v)
}
</script>

<template>
  <div class="st-stack">
    <p class="st-note">{{ t('studio.units.formula') }}</p>
    <div class="st-scroll">
      <table class="st-table" data-testid="units-table">
        <thead>
          <tr>
            <th>{{ t('studio.units.signal') }}</th>
            <th>{{ t('studio.units.quantity') }}</th>
            <th>{{ t('studio.units.source') }}</th>
            <th>{{ t('studio.units.target') }}</th>
            <th>{{ t('studio.units.scale') }}</th>
            <th>{{ t('studio.units.offset') }}</th>
            <th>{{ t('studio.units.example') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in s.activeDrafts" :key="d.key_name" :data-unit-row="d.key_name">
            <td>
              <div>{{ lt(s.signalName(d.key_name)) }}</div>
              <div class="st-note st-mono">{{ d.key_name }}</div>
            </td>
            <td>{{ t(`studio.quantities.${d.quantity}`) }}</td>
            <td>
              <select v-model="d.source_unit" class="st-select" @change="onUnit(d)">
                <option v-for="u in units(d)" :key="u" :value="u">{{ u }}</option>
              </select>
            </td>
            <td>
              <select v-model="d.target_unit" class="st-select" @change="onUnit(d)">
                <option v-for="u in units(d)" :key="u" :value="u">{{ u }}</option>
              </select>
            </td>
            <td>
              <input
                class="st-input small"
                type="number"
                step="any"
                :value="d.scale ?? ''"
                :aria-label="t('studio.units.scale')"
                :aria-invalid="d.scale === null || d.scale === 0"
                @input="onScale(d, $event)"
              />
              <div v-if="d.scale === null" class="st-note">{{ t('studio.units.needsScale') }}</div>
            </td>
            <td>
              <input
                v-model.number="d.offset"
                class="st-input small"
                type="number"
                step="any"
                :aria-label="t('studio.units.offset')"
              />
            </td>
            <td class="st-mono example">{{ example(d) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.example {
  white-space: nowrap;
  color: var(--ink-soft);
}
</style>

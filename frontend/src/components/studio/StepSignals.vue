<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useLocalized } from '@/composables/useLocalized'
import { useStudioStore } from '@/studio/store'

const s = useStudioStore()
const { t, n } = useI18n()
const { lt } = useLocalized()
const device = computed(() => s.devices.find((d) => d.device_id === s.deviceId))
</script>

<template>
  <div class="st-stack">
    <div class="st-choices" role="radiogroup" :aria-label="t('studio.signals.device')">
      <button
        v-for="d in s.devices"
        :key="d.device_id"
        type="button"
        class="st-choice"
        role="radio"
        :aria-checked="s.deviceId === d.device_id"
        :data-device="d.device_id"
        @click="s.selectDevice(d.device_id)"
      >
        <strong class="st-mono">{{ d.device_id }}</strong>
        <span class="muted">{{ d.scenario_id }} {{ lt(d.scenario_title) }}</span>
      </button>
    </div>

    <fieldset v-if="device" class="keys">
      <legend>
        {{ t('studio.signals.keys') }}
        <span class="st-note">{{
          t('studio.signals.selected', { n: s.selectedKeys.length, total: device.keys.length })
        }}</span>
      </legend>
      <label v-for="k in device.keys" :key="k.key_name" class="key">
        <input
          type="checkbox"
          :checked="s.selectedKeys.includes(k.key_name)"
          :data-key="k.key_name"
          @change="s.toggleKey(k.key_name)"
        />
        <span class="st-mono">{{ k.key_name }}</span>
        <span class="name">{{ lt(s.signalName(k.key_name)) || t('studio.signals.unnamed') }}</span>
        <span v-if="k.rows !== null" class="st-note">{{
          t('studio.signals.rows', { n: n(k.rows) })
        }}</span>
      </label>
    </fieldset>
  </div>
</template>

<style scoped>
.keys {
  border: 1px solid var(--line);
  border-radius: var(--radius-panel);
  padding: var(--space-2) var(--space-4) var(--space-3);
  margin: 0;
  display: grid;
}
legend {
  padding: 0 var(--space-2);
  font-weight: 600;
  font-size: var(--text-sm);
  display: flex;
  gap: var(--space-3);
  align-items: baseline;
}
.key {
  display: grid;
  grid-template-columns: auto 160px 1fr auto;
  gap: var(--space-3);
  align-items: center;
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--line);
  font-size: var(--text-sm);
}
.key:last-child {
  border-bottom: 0;
}
.name {
  color: var(--ink-soft);
}
@media (max-width: 640px) {
  .key {
    grid-template-columns: auto 1fr;
  }
}
</style>

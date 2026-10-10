<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PlantTree } from '@/api/contracts'
import { monitoringApi } from '@/api/monitoring'
import { session } from '@/api/session'
import { useLocalized } from '@/composables/useLocalized'
import { useStudioStore } from '@/studio/store'

const s = useStudioStore()
const { t, n } = useI18n()
const { lt } = useLocalized()
const device = computed(() => s.devices.find((d) => d.device_id === s.deviceId))

// A device comes from the database list, or from the plant structure: workshop → process → machine
// (D-037). The machine's bound device id is what the data is read with.
const mode = ref<'db' | 'tree'>('db')
const tree = ref<PlantTree | null>(null)
monitoringApi
  .plantTree()
  .then((x) => (tree.value = x))
  .catch(() => (tree.value = null))
const ws = ref('')
const proc = ref('')
const mach = ref('')
const workshop = computed(() => tree.value?.workshops.find((w) => w.node_id === ws.value))
const process = computed(() => workshop.value?.processes.find((p) => p.node_id === proc.value))
const machine = computed(() => process.value?.machines.find((m) => m.machine_id === mach.value))
const machineDevice = computed(() =>
  machine.value ? (machine.value.device_id ?? machine.value.machine_id) : null,
)
const unbound = computed(
  () => !!machineDevice.value && !s.devices.some((d) => d.device_id === machineDevice.value),
)
function pickMachine(id: string) {
  mach.value = id
  const dev = machineDevice.value
  if (dev && s.devices.some((d) => d.device_id === dev)) void s.selectDevice(dev)
}
</script>

<template>
  <div class="st-stack">
    <div v-if="tree" class="mode" role="radiogroup" :aria-label="t('studio.signals.pickBy')">
      <label
        ><input v-model="mode" type="radio" value="db" data-testid="pick-db" />
        {{ t('studio.signals.fromDb') }}</label
      >
      <label
        ><input v-model="mode" type="radio" value="tree" data-testid="pick-tree" />
        {{ t('studio.signals.fromTree') }}</label
      >
    </div>

    <div v-if="mode === 'tree' && tree" class="cascade" data-testid="device-tree">
      <label class="st-field">
        <span>{{ t('plant.workshop') }}</span>
        <select
          v-model="ws"
          class="st-select"
          data-testid="tree-workshop"
          @change="((proc = ''), (mach = ''))"
        >
          <option value="" disabled>{{ t('studio.signals.choose') }}</option>
          <option v-for="w in tree.workshops" :key="w.node_id" :value="w.node_id">
            {{ lt(w.name) }}
          </option>
        </select>
      </label>
      <label class="st-field">
        <span>{{ t('plant.process') }}</span>
        <select
          v-model="proc"
          class="st-select"
          :disabled="!workshop"
          data-testid="tree-process"
          @change="mach = ''"
        >
          <option value="" disabled>{{ t('studio.signals.choose') }}</option>
          <option v-for="p in workshop?.processes ?? []" :key="p.node_id" :value="p.node_id">
            {{ lt(p.name) }}
          </option>
        </select>
      </label>
      <label class="st-field">
        <span>{{ t('studio.signals.machine') }}</span>
        <select
          :value="mach"
          class="st-select"
          :disabled="!process"
          data-testid="tree-machine"
          @change="pickMachine(($event.target as HTMLSelectElement).value)"
        >
          <option value="" disabled>{{ t('studio.signals.choose') }}</option>
          <option v-for="m in process?.machines ?? []" :key="m.machine_id" :value="m.machine_id">
            {{ lt(m.name) }} ({{ m.device_id ?? m.machine_id }})
          </option>
        </select>
      </label>
      <p v-if="!tree.workshops.length" class="st-note">
        {{ t('studio.signals.emptyTree') }}
        <RouterLink v-if="session.role === 'admin'" to="/plant">{{ t('nav.plant') }}</RouterLink>
      </p>
      <p v-if="unbound" class="st-note bad" data-testid="tree-unbound">
        {{ t('studio.signals.unbound', { id: machineDevice }) }}
      </p>
    </div>

    <div
      v-if="mode === 'db'"
      class="st-choices"
      role="radiogroup"
      :aria-label="t('studio.signals.device')"
    >
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
        <span v-if="d.machine_path" class="muted">{{ lt(d.machine_path) }}</span>
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
.mode {
  display: flex;
  gap: var(--space-4);
  font-size: var(--text-sm);
}
.cascade {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--space-3);
  align-items: end;
}
.cascade .st-note {
  grid-column: 1 / -1;
}
.bad {
  color: var(--health-critical);
}
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

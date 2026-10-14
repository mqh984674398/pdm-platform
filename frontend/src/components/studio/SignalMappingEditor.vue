<script setup lang="ts">
/**
 * Step 2 of the configuration workflow: bind a component to a data source and map signals to it.
 * Pick a source (simulated database or TDengine) and a device, read the proposed signals for that
 * device, choose the ones this component uses and save. Saving replaces the device's signal
 * configuration with the existing signals plus the chosen ones (a new signal configuration version).
 */
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type {
  ApiStudioDevice,
  DataSourceConfig,
  DeviceSuggestions,
  PhysicalQuantity,
  SignalConfigState,
} from '@/api/contracts'
import { MonitoringApiError, monitoringApi } from '@/api/monitoring'
import '@/components/studio/studio.css'
import { useLocalized } from '@/composables/useLocalized'

const props = defineProps<{
  componentId: string
  deviceId?: string | null
  state: SignalConfigState | null
}>()
const emit = defineEmits<{ saved: [] }>()
const { t } = useI18n()
const { lt } = useLocalized()

const QUANTITIES: PhysicalQuantity[] = [
  'SPEED',
  'TORQUE',
  'DURATION',
  'POSITION',
  'CURRENT',
  'PRESSURE',
  'VIBRATION',
  'OTHER',
]

const sources = ref<DataSourceConfig[]>([])
const devices = ref<ApiStudioDevice[]>([])
const source = ref('')
const device = ref(props.deviceId ?? '')
const suggestion = ref<DeviceSuggestions | null>(null)
const pick = reactive<Record<string, { on: boolean; quantity: PhysicalQuantity; unit: string }>>({})
const busy = ref(false)
const message = ref<{ ok: boolean; text: string } | null>(null)

const fail = (e: unknown) => {
  const body = e instanceof MonitoringApiError ? e.body : null
  message.value = { ok: false, text: body ? lt(body.message) : t('workbench.failed') }
}

monitoringApi
  .dataSources()
  .then((list) => (sources.value = list))
  .catch(fail)

// Start on the source that already holds this component's (or its device's) signals; the user may change it.
let chosenInitially = false
watch(
  [sources, () => props.state],
  () => {
    if (chosenInitially || !sources.value.length || !props.state) return
    chosenInitially = true
    const maps = props.state.content.mappings
    const bound =
      maps.find((m) => m.component_id === props.componentId) ??
      maps.find((m) => !!props.deviceId && m.device_id === props.deviceId)
    source.value = bound?.data_source_id ?? sources.value[0]!.data_source_id
  },
  { immediate: true },
)

watch(
  source,
  async (id) => {
    devices.value = []
    suggestion.value = null
    if (!id) return
    try {
      devices.value = await monitoringApi.sourceDevices(id)
      if (!devices.value.some((d) => d.device_id === device.value))
        device.value = devices.value[0]?.device_id ?? device.value
    } catch (e) {
      fail(e)
    }
  },
  { immediate: true },
)

const kind = computed(() => sources.value.find((s) => s.data_source_id === source.value)?.kind)
const mappedIds = computed(
  () =>
    new Set(
      (props.state?.content.mappings ?? [])
        .filter((m) => m.data_source_id === source.value && m.device_id === device.value)
        .map((m) => m.signal_id),
    ),
)

async function suggest() {
  message.value = null
  suggestion.value = null
  busy.value = true
  try {
    const s = await monitoringApi.deviceSuggestions(source.value, device.value)
    suggestion.value = s
    for (const x of s.signals) {
      const on = mappedIds.value.has(x.signal_id)
      pick[x.signal_id] = { on, quantity: x.quantity, unit: x.unit }
    }
  } catch (e) {
    fail(e)
  } finally {
    busy.value = false
  }
}

const chosen = computed(() =>
  (suggestion.value?.signals ?? []).filter((x) => pick[x.signal_id]?.on),
)

async function save() {
  const cfg = props.state?.content
  const sug = suggestion.value
  if (!cfg || !sug || !chosen.value.length) return
  const here = (m: { data_source_id: string; device_id: string }) =>
    m.data_source_id === source.value && m.device_id === device.value
  const oldMaps = cfg.mappings.filter(here)
  const oldIds = new Set(oldMaps.map((m) => m.signal_id))
  const picked = new Set(chosen.value.map((x) => x.signal_id))
  const keep = [...oldIds].filter((id) => !picked.has(id))
  const owned = (it: { signal_ids: string[] }) =>
    it.signal_ids.length > 0 && it.signal_ids.every((id) => oldIds.has(id))
  const signals = [
    ...cfg.signals.filter((x) => keep.includes(x.signal_id)),
    ...chosen.value.map((x) => ({
      ...x,
      quantity: pick[x.signal_id]!.quantity,
      unit: pick[x.signal_id]!.unit,
    })),
  ]
  const mappings = [
    ...oldMaps.filter((m) => keep.includes(m.signal_id)),
    ...sug.mappings
      .filter((m) => picked.has(m.signal_id))
      .map((m) => ({ ...m, component_id: props.componentId })),
  ]
  busy.value = true
  message.value = null
  try {
    await monitoringApi.replaceDevice(source.value, device.value, {
      comment: `workbench: ${props.componentId}`,
      base_version: props.state?.version?.version ?? 0,
      signals,
      mappings,
      groups: cfg.groups.filter(owned),
      visualizations: cfg.visualizations.filter(owned),
    })
    message.value = { ok: true, text: t('workbench.mappingSaved') }
    emit('saved')
  } catch (e) {
    fail(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="st-stack" data-testid="mapping-editor">
    <h4>{{ t('workbench.bind') }}</h4>
    <div class="st-form">
      <label class="st-field">
        <span>{{ t('workbench.source') }}</span>
        <select v-model="source" class="st-select" data-testid="map-source">
          <option v-for="s in sources" :key="s.data_source_id" :value="s.data_source_id">
            {{ s.name }} ({{
              s.kind === 'TDENGINE'
                ? 'TDengine'
                : s.is_simulated
                  ? t('workbench.simulated')
                  : s.kind
            }})
          </option>
        </select>
      </label>
      <label class="st-field">
        <span>{{ t('plant.deviceId') }}</span>
        <select v-model="device" class="st-select st-mono" data-testid="map-device">
          <option v-for="d in devices" :key="d.device_id" :value="d.device_id">
            {{ d.device_id }}{{ d.machine_id ? ' · ' + d.machine_id : '' }}
          </option>
          <option v-if="device && !devices.some((d) => d.device_id === device)" :value="device">
            {{ device }}
          </option>
        </select>
      </label>
    </div>
    <p v-if="kind === 'TDENGINE'" class="st-note">{{ t('workbench.productionNote') }}</p>
    <button
      type="button"
      class="st-button"
      :disabled="busy || !source || !device"
      data-testid="map-suggest"
      @click="suggest"
    >
      {{ t('workbench.readSignals') }}
    </button>
    <p v-if="message" :class="message.ok ? 'ok' : 'error'" role="status" data-testid="map-message">
      {{ message.text }}
    </p>
    <template v-if="suggestion">
      <p v-if="!suggestion.signals.length" class="st-note">{{ t('workbench.noSuggestions') }}</p>
      <div v-else class="st-scroll">
        <table class="st-table" data-testid="map-suggestions">
          <thead>
            <tr>
              <th>{{ t('workbench.use') }}</th>
              <th>{{ t('workbench.signal') }}</th>
              <th>{{ t('workbench.quantity') }}</th>
              <th>{{ t('workbench.unit') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="x in suggestion.signals" :key="x.signal_id" :data-suggest="x.signal_id">
              <td><input v-model="pick[x.signal_id]!.on" type="checkbox" /></td>
              <td>
                {{ lt(x.name) }}
                <span class="st-note st-mono">{{ x.signal_id }}</span>
              </td>
              <td>
                <select v-model="pick[x.signal_id]!.quantity" class="st-select">
                  <option v-for="q in QUANTITIES" :key="q" :value="q">{{ q }}</option>
                </select>
              </td>
              <td>
                <input
                  v-model="pick[x.signal_id]!.unit"
                  class="st-input st-mono"
                  style="width: 90px"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <button
        type="button"
        class="st-button primary"
        :disabled="busy || !chosen.length"
        data-testid="map-save"
        @click="save"
      >
        {{ t('workbench.saveMapping') }}
      </button>
    </template>
  </div>
</template>

<style scoped>
h4 {
  margin: var(--space-2) 0;
  font-size: var(--text-sm);
}
.ok {
  color: var(--health-normal);
}
.error {
  color: var(--health-critical);
}
</style>

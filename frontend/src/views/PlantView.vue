<script setup lang="ts">
/**
 * Plant structure (D-037/D-038), administrators only: workshop (车间) → process (工序) → machine (机台).
 * Each machine carries its device id in the data source and its components, including which components
 * share a drive chain. Machine paths show on the overview, machine map and component history; the
 * Algorithm configuration screen offers this tree to pick a device.
 */
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ComponentInstance, PlantMachine, PlantTree } from '@/api/contracts'
import { MonitoringApiError, monitoringApi } from '@/api/monitoring'
import PanelBox from '@/components/base/PanelBox.vue'
import SideDrawer from '@/components/base/SideDrawer.vue'
import ConfigWorkbench from '@/components/studio/ConfigWorkbench.vue'
import '@/components/studio/studio.css'
import { useLocalized } from '@/composables/useLocalized'

const TYPES = [
  'BALL_SCREW',
  'LINEAR_MOTOR',
  'VACUUM_CUP',
  'PNEUMATIC_CYLINDER',
  'CAM',
  'GEAR',
] as const
const ID = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/

const { t } = useI18n()
const { lt } = useLocalized()

const tree = ref<PlantTree | null>(null)
const loadError = ref(false)
const busy = ref(false)
const message = ref<{ ok: boolean; text: string } | null>(null)
type Sel = { kind: 'workshop' | 'process' | 'machine'; id: string } | null
const selected = ref<Sel>(null)
type Drawer = {
  kind: 'workshop' | 'process' | 'machine' | 'new'
  mode: 'all' | 'add' | 'edit'
} | null
const drawer = ref<Drawer>(null)
const configuring = ref<string | null>(null)
const configComponent = computed(() =>
  machine.value?.components.find((c) => c.component_id === configuring.value),
)

async function load() {
  try {
    tree.value = await monitoringApi.plantTree()
  } catch {
    loadError.value = true
  }
}
load()

async function run(action: () => Promise<unknown>, done: string) {
  busy.value = true
  message.value = null
  try {
    await action()
    await load()
    message.value = { ok: true, text: done }
  } catch (e) {
    const body = e instanceof MonitoringApiError ? e.body : null
    message.value = { ok: false, text: body ? lt(body.message) : t('plant.failed') }
  } finally {
    busy.value = false
  }
}

const processes = computed(() =>
  (tree.value?.workshops ?? []).flatMap((w) =>
    w.processes.map((p) => ({ ...p, workshop: w, label: `${lt(w.name)} / ${lt(p.name)}` })),
  ),
)
const machines = computed<(PlantMachine & { process_id: string | null })[]>(() => [
  ...processes.value.flatMap((p) => p.machines.map((m) => ({ ...m, process_id: p.node_id }))),
  ...(tree.value?.unplaced ?? []).map((m) => ({ ...m, process_id: null })),
])
const workshop = computed(() =>
  selected.value?.kind === 'workshop'
    ? tree.value?.workshops.find((w) => w.node_id === selected.value!.id)
    : undefined,
)
const process = computed(() =>
  selected.value?.kind === 'process'
    ? processes.value.find((p) => p.node_id === selected.value!.id)
    : undefined,
)
const machine = computed(() =>
  selected.value?.kind === 'machine'
    ? machines.value.find((m) => m.machine_id === selected.value!.id)
    : undefined,
)

// --- editing forms ---
const node = reactive({ zh: '', en: '', sort: 0 })
const child = reactive({ id: '', zh: '', en: '', device: '' })
const wsForm = reactive({ id: '', zh: '', en: '' })
const mform = reactive({ zh: '', en: '', device: '', process: '' as string | null })
const comp = reactive({ id: '', type: 'BALL_SCREW', zh: '', en: '', chain: '' })

function select(
  kind: 'workshop' | 'process' | 'machine',
  id: string,
  mode: 'all' | 'add' | 'edit' | null = 'all',
) {
  selected.value = { kind, id }
  drawer.value = mode ? { kind, mode } : null
  configuring.value = null
  message.value = null
  Object.assign(child, { id: '', zh: '', en: '', device: '' })
  Object.assign(comp, { id: '', type: 'BALL_SCREW', zh: '', en: '', chain: '' })
  if (kind === 'machine') {
    const m = machines.value.find((x) => x.machine_id === id)!
    Object.assign(mform, {
      zh: m.name.zh,
      en: m.name.en,
      device: m.device_id ?? '',
      process: m.process_id,
    })
  } else {
    const n =
      kind === 'workshop'
        ? tree.value!.workshops.find((w) => w.node_id === id)!
        : processes.value.find((p) => p.node_id === id)!
    Object.assign(node, { zh: n.name.zh, en: n.name.en, sort: n.sort })
  }
}

const name = (zh: string, en: string) => ({ zh: zh.trim(), en: (en || zh).trim() })
const idError = (id: string) => (ID.test(id) ? null : t('plant.badId'))

function addWorkshop() {
  if (idError(wsForm.id) || !wsForm.zh.trim()) return
  const id = wsForm.id
  run(
    () =>
      monitoringApi.putPlantNode({
        node_id: id,
        parent_id: null,
        level: 'WORKSHOP',
        name: name(wsForm.zh, wsForm.en),
        sort: (tree.value?.workshops.length ?? 0) * 10,
      }),
    t('plant.saved', { id }),
  ).then(() => {
    Object.assign(wsForm, { id: '', zh: '', en: '' })
    drawer.value = null
  })
}
function saveNode() {
  const n = workshop.value ?? process.value
  if (!n || !node.zh.trim()) return
  run(
    () =>
      monitoringApi.putPlantNode({
        node_id: n.node_id,
        parent_id: process.value ? process.value.workshop.node_id : null,
        level: process.value ? 'PROCESS' : 'WORKSHOP',
        name: name(node.zh, node.en),
        sort: Number(node.sort) || 0,
      }),
    t('plant.saved', { id: n.node_id }),
  )
}
function deleteNode() {
  const n = workshop.value ?? process.value
  if (!n || !window.confirm(t('plant.deleteConfirm', { id: n.node_id }))) return
  run(() => monitoringApi.deletePlantNode(n.node_id), t('plant.deleted', { id: n.node_id })).then(
    () => (selected.value = null),
  )
}
function addProcess() {
  const w = workshop.value
  if (!w || idError(child.id) || !child.zh.trim()) return
  const id = child.id
  run(
    () =>
      monitoringApi.putPlantNode({
        node_id: id,
        parent_id: w.node_id,
        level: 'PROCESS',
        name: name(child.zh, child.en),
        sort: w.processes.length * 10,
      }),
    t('plant.saved', { id }),
  ).then(() => Object.assign(child, { id: '', zh: '', en: '', device: '' }))
}
function addMachine() {
  const p = process.value
  if (!p || idError(child.id) || !child.zh.trim()) return
  const id = child.id
  run(
    () =>
      monitoringApi.createMachine({
        machine_id: id,
        name: name(child.zh, child.en),
        process_id: p.node_id,
        device_id: child.device.trim() || null,
      }),
    t('plant.saved', { id }),
  ).then(() => Object.assign(child, { id: '', zh: '', en: '', device: '' }))
}
function saveMachine() {
  const m = machine.value
  if (!m || !mform.zh.trim()) return
  run(
    () =>
      monitoringApi.placeMachine(m.machine_id, {
        process_id: mform.process || null,
        device_id: mform.device.trim() || null,
        name: name(mform.zh, mform.en),
      }),
    t('plant.saved', { id: m.machine_id }),
  )
}
function deleteMachine() {
  const m = machine.value
  if (!m || !window.confirm(t('plant.deleteConfirm', { id: m.machine_id }))) return
  run(
    () => monitoringApi.deleteMachine(m.machine_id),
    t('plant.deleted', { id: m.machine_id }),
  ).then(() => (selected.value = null))
}
function saveComponent(c?: ComponentInstance, chain?: string) {
  const m = machine.value
  if (!m) return
  const body = c
    ? {
        component_id: c.component_id,
        type: c.type,
        name: c.name,
        drive_chain_id: (chain ?? '').trim() || null,
        torque_limit: c.torque_limit ?? null,
      }
    : {
        component_id: comp.id,
        type: comp.type as (typeof TYPES)[number],
        name: name(comp.zh, comp.en),
        drive_chain_id: comp.chain.trim() || null,
        torque_limit: null,
      }
  if (idError(body.component_id) || !body.name.zh) return
  if (body.drive_chain_id && idError(body.drive_chain_id)) return
  run(
    () => monitoringApi.putComponent(m.machine_id, body),
    t('plant.saved', { id: body.component_id }),
  )
}
function saveTorqueLimit(c: ComponentInstance, raw: string) {
  const m = machine.value
  const limit = raw.trim() === '' ? null : Number(raw)
  if (!m || (limit !== null && !(limit > 0))) return
  run(
    () =>
      monitoringApi.putComponent(m.machine_id, {
        component_id: c.component_id,
        type: c.type,
        name: c.name,
        drive_chain_id: c.drive_chain_id ?? null,
        torque_limit: limit,
      }),
    t('plant.saved', { id: c.component_id }),
  )
}
function deleteComponent(c: ComponentInstance) {
  if (!window.confirm(t('plant.deleteConfirm', { id: c.component_id }))) return
  run(
    () => monitoringApi.deleteComponent(c.component_id),
    t('plant.deleted', { id: c.component_id }),
  )
}
function removeNode(kind: 'workshop' | 'process' | 'machine', id: string) {
  select(kind, id, null)
  if (kind === 'machine') deleteMachine()
  else deleteNode()
}
function openConfig(machineId: string, componentId: string) {
  select('machine', machineId, null)
  configuring.value = componentId
}
function removeComponent(machineId: string, c: ComponentInstance) {
  select('machine', machineId, null)
  deleteComponent(c)
}
/** Components sharing a drive chain with at least one other component of the same machine. */
const chains = computed(() => {
  const counts = new Map<string, number>()
  for (const c of machine.value?.components ?? [])
    if (c.drive_chain_id) counts.set(c.drive_chain_id, (counts.get(c.drive_chain_id) ?? 0) + 1)
  return counts
})
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>{{ t('nav.plant') }}</h1>
      <p class="lede">{{ t('plant.lede') }}</p>
    </header>
    <p v-if="loadError" class="error">{{ t('common.loadFailed') }}</p>
    <p
      v-if="message"
      :class="message.ok ? 'ok' : 'error'"
      role="status"
      data-testid="plant-message"
    >
      {{ message.text }}
    </p>
    <div v-if="tree" class="layout">
      <PanelBox :title="t('plant.tree')">
        <div class="row tree-head">
          <button
            type="button"
            class="st-button"
            data-testid="add-workshop-open"
            @click="drawer = { kind: 'new', mode: 'add' }"
          >
            + {{ t('plant.addTop') }}
          </button>
        </div>
        <ul class="tree" data-testid="plant-tree">
          <li v-for="w in tree.workshops" :key="w.node_id">
            <div class="line">
              <button
                type="button"
                class="node ws"
                :aria-current="selected?.kind === 'workshop' && selected.id === w.node_id"
                :data-node="w.node_id"
                @click="select('workshop', w.node_id)"
              >
                {{ lt(w.name) }}
              </button>
              <span class="acts">
                <button
                  type="button"
                  :aria-label="t('plant.addChildOf')"
                  @click="select('workshop', w.node_id, 'add')"
                >
                  +
                </button>
                <button
                  type="button"
                  :aria-label="t('plant.editNode')"
                  @click="select('workshop', w.node_id, 'edit')"
                >
                  ✎
                </button>
                <button
                  type="button"
                  class="danger"
                  :aria-label="t('plant.delete')"
                  @click="removeNode('workshop', w.node_id)"
                >
                  ✕
                </button>
              </span>
            </div>
            <ul>
              <li v-for="p in w.processes" :key="p.node_id">
                <div class="line">
                  <button
                    type="button"
                    class="node"
                    :aria-current="selected?.kind === 'process' && selected.id === p.node_id"
                    :data-node="p.node_id"
                    @click="select('process', p.node_id)"
                  >
                    {{ lt(p.name) }}
                  </button>
                  <span class="acts">
                    <button
                      type="button"
                      :aria-label="t('plant.addChildOf')"
                      @click="select('process', p.node_id, 'add')"
                    >
                      +
                    </button>
                    <button
                      type="button"
                      :aria-label="t('plant.editNode')"
                      @click="select('process', p.node_id, 'edit')"
                    >
                      ✎
                    </button>
                    <button
                      type="button"
                      class="danger"
                      :aria-label="t('plant.delete')"
                      @click="removeNode('process', p.node_id)"
                    >
                      ✕
                    </button>
                  </span>
                </div>
                <ul>
                  <li v-for="m in p.machines" :key="m.machine_id">
                    <div class="line">
                      <button
                        type="button"
                        class="node mc"
                        :aria-current="selected?.kind === 'machine' && selected.id === m.machine_id"
                        :data-machine="m.machine_id"
                        @click="select('machine', m.machine_id)"
                      >
                        {{ lt(m.name) }} <span class="st-mono st-note">{{ m.machine_id }}</span>
                      </button>
                      <span class="acts">
                        <button
                          type="button"
                          :aria-label="t('plant.addComponent')"
                          @click="select('machine', m.machine_id, 'add')"
                        >
                          +
                        </button>
                        <button
                          type="button"
                          :aria-label="t('plant.editNode')"
                          @click="select('machine', m.machine_id, 'edit')"
                        >
                          ✎
                        </button>
                        <button
                          type="button"
                          class="danger"
                          :aria-label="t('plant.delete')"
                          @click="removeNode('machine', m.machine_id)"
                        >
                          ✕
                        </button>
                      </span>
                    </div>
                    <ul>
                      <li v-for="c in m.components" :key="c.component_id">
                        <div class="line">
                          <button
                            type="button"
                            class="node cp"
                            :data-comp-node="c.component_id"
                            @click="openConfig(m.machine_id, c.component_id)"
                          >
                            {{ lt(c.name) }}
                            <span class="st-mono st-note">{{ c.component_id }}</span>
                          </button>
                          <span class="acts">
                            <button
                              type="button"
                              :aria-label="t('plant.editNode')"
                              @click="select('machine', m.machine_id, 'edit')"
                            >
                              ✎
                            </button>
                            <button
                              type="button"
                              class="danger"
                              :aria-label="t('plant.delete')"
                              @click="removeComponent(m.machine_id, c)"
                            >
                              ✕
                            </button>
                          </span>
                        </div>
                      </li>
                    </ul>
                  </li>
                </ul>
              </li>
            </ul>
          </li>
          <li v-if="tree.unplaced.length">
            <span class="node ws muted">{{ t('plant.unplaced') }}</span>
            <ul>
              <li v-for="m in tree.unplaced" :key="m.machine_id">
                <div class="line">
                  <button
                    type="button"
                    class="node mc"
                    :aria-current="selected?.kind === 'machine' && selected.id === m.machine_id"
                    :data-machine="m.machine_id"
                    @click="select('machine', m.machine_id)"
                  >
                    {{ lt(m.name) }} <span class="st-mono st-note">{{ m.machine_id }}</span>
                  </button>
                  <span class="acts">
                    <button
                      type="button"
                      :aria-label="t('plant.addComponent')"
                      @click="select('machine', m.machine_id, 'add')"
                    >
                      +
                    </button>
                    <button
                      type="button"
                      :aria-label="t('plant.editNode')"
                      @click="select('machine', m.machine_id, 'edit')"
                    >
                      ✎
                    </button>
                    <button
                      type="button"
                      class="danger"
                      :aria-label="t('plant.delete')"
                      @click="removeNode('machine', m.machine_id)"
                    >
                      ✕
                    </button>
                  </span>
                </div>
                <ul>
                  <li v-for="c in m.components" :key="c.component_id">
                    <div class="line">
                      <button
                        type="button"
                        class="node cp"
                        :data-comp-node="c.component_id"
                        @click="openConfig(m.machine_id, c.component_id)"
                      >
                        {{ lt(c.name) }} <span class="st-mono st-note">{{ c.component_id }}</span>
                      </button>
                      <span class="acts">
                        <button
                          type="button"
                          :aria-label="t('plant.editNode')"
                          @click="select('machine', m.machine_id, 'edit')"
                        >
                          ✎
                        </button>
                        <button
                          type="button"
                          class="danger"
                          :aria-label="t('plant.delete')"
                          @click="removeComponent(m.machine_id, c)"
                        >
                          ✕
                        </button>
                      </span>
                    </div>
                  </li>
                </ul>
              </li>
            </ul>
          </li>
        </ul>
      </PanelBox>

      <SideDrawer
        :open="drawer?.kind === 'new'"
        :title="t('plant.drawerNew')"
        @close="drawer = null"
      >
        <form class="add first" data-testid="add-workshop" @submit.prevent="addWorkshop">
          <input v-model.trim="wsForm.id" class="st-input" :placeholder="t('plant.id')" />
          <input v-model="wsForm.zh" class="st-input" :placeholder="t('plant.nameZh')" />
          <input v-model="wsForm.en" class="st-input" :placeholder="t('plant.nameEn')" />
          <button type="submit" class="st-button" :disabled="busy">{{ t('plant.add') }}</button>
        </form>
      </SideDrawer>

      <SideDrawer
        :open="
          (drawer?.kind === 'workshop' || drawer?.kind === 'process') && !!(workshop || process)
        "
        :title="
          workshop
            ? t('plant.drawerWorkshop', { id: workshop.node_id })
            : t('plant.drawerProcess', { id: process?.node_id ?? '' })
        "
        @close="drawer = null"
      >
        <div class="st-stack">
          <div v-if="drawer?.mode !== 'add'" class="st-form">
            <label class="st-field"
              ><span>{{ t('plant.nameZh') }}</span
              ><input v-model="node.zh" class="st-input"
            /></label>
            <label class="st-field"
              ><span>{{ t('plant.nameEn') }}</span
              ><input v-model="node.en" class="st-input"
            /></label>
            <label class="st-field"
              ><span>{{ t('plant.sort') }}</span
              ><input v-model.number="node.sort" type="number" class="st-input"
            /></label>
          </div>
          <div v-if="drawer?.mode !== 'add'" class="row">
            <button type="button" class="st-button primary" :disabled="busy" @click="saveNode">
              {{ t('plant.save') }}
            </button>
            <button type="button" class="link danger" :disabled="busy" @click="deleteNode">
              {{ t('plant.delete') }}
            </button>
          </div>
          <form
            v-if="drawer?.mode !== 'edit'"
            class="add"
            :data-testid="workshop ? 'add-process' : 'add-machine'"
            @submit.prevent="workshop ? addProcess() : addMachine()"
          >
            <strong>{{ workshop ? t('plant.addProcess') : t('plant.addMachine') }}</strong>
            <input v-model.trim="child.id" class="st-input" :placeholder="t('plant.id')" />
            <input v-model="child.zh" class="st-input" :placeholder="t('plant.nameZh')" />
            <input v-model="child.en" class="st-input" :placeholder="t('plant.nameEn')" />
            <input
              v-if="process"
              v-model="child.device"
              class="st-input st-mono"
              :placeholder="t('plant.deviceId')"
            />
            <button type="submit" class="st-button" :disabled="busy">{{ t('plant.add') }}</button>
          </form>
        </div>
      </SideDrawer>

      <SideDrawer
        :open="drawer?.kind === 'machine' && !!machine"
        :title="t('plant.drawerMachine', { id: machine?.machine_id ?? '' })"
        @close="drawer = null"
      >
        <div v-if="machine" class="st-stack">
          <div v-if="drawer?.mode !== 'add'" class="st-form">
            <label class="st-field"
              ><span>{{ t('plant.nameZh') }}</span
              ><input v-model="mform.zh" class="st-input"
            /></label>
            <label class="st-field"
              ><span>{{ t('plant.nameEn') }}</span
              ><input v-model="mform.en" class="st-input"
            /></label>
            <label class="st-field">
              <span>{{ t('plant.process') }}</span>
              <select v-model="mform.process" class="st-select" data-testid="machine-process">
                <option :value="null">{{ t('plant.unplaced') }}</option>
                <option v-for="p in processes" :key="p.node_id" :value="p.node_id">
                  {{ p.label }}
                </option>
              </select>
            </label>
            <label class="st-field">
              <span>{{ t('plant.deviceId') }}</span>
              <input v-model="mform.device" class="st-input st-mono" data-testid="machine-device" />
              <span class="st-note">{{ t('plant.deviceNote') }}</span>
            </label>
          </div>
          <div v-if="drawer?.mode !== 'add'" class="row">
            <button type="button" class="st-button primary" :disabled="busy" @click="saveMachine">
              {{ t('plant.save') }}
            </button>
            <button type="button" class="link danger" :disabled="busy" @click="deleteMachine">
              {{ t('plant.delete') }}
            </button>
          </div>

          <h3 v-if="drawer?.mode !== 'add'">{{ t('plant.components') }}</h3>
          <p v-if="drawer?.mode !== 'add'" class="st-note">{{ t('plant.chainNote') }}</p>
          <div v-if="drawer?.mode !== 'add'" class="st-scroll">
            <table class="st-table" data-testid="plant-components">
              <thead>
                <tr>
                  <th>{{ t('plant.id') }}</th>
                  <th>{{ t('plant.type') }}</th>
                  <th>{{ t('plant.name') }}</th>
                  <th>{{ t('plant.driveChain') }}</th>
                  <th>{{ t('plant.torqueLimit') }}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="c in machine.components"
                  :key="c.component_id"
                  :data-component="c.component_id"
                >
                  <td class="st-mono">{{ c.component_id }}</td>
                  <td>{{ t(`types.${c.type}`) }}</td>
                  <td>{{ lt(c.name) }}</td>
                  <td>
                    <input
                      class="st-input st-mono chain"
                      :value="c.drive_chain_id ?? ''"
                      :aria-label="t('plant.driveChain')"
                      data-testid="component-chain"
                      @change="saveComponent(c, ($event.target as HTMLInputElement).value)"
                    />
                    <span
                      v-if="c.drive_chain_id && (chains.get(c.drive_chain_id) ?? 0) > 1"
                      class="st-note"
                      >{{ t('plant.shared', { n: chains.get(c.drive_chain_id) }) }}</span
                    >
                  </td>
                  <td>
                    <input
                      class="st-input st-mono chain"
                      type="number"
                      min="0"
                      step="any"
                      :value="c.torque_limit ?? ''"
                      :placeholder="t('plant.torqueLimitOff')"
                      :aria-label="t('plant.torqueLimit')"
                      data-testid="component-torque-limit"
                      @change="saveTorqueLimit(c, ($event.target as HTMLInputElement).value)"
                    />
                  </td>
                  <td>
                    <button
                      type="button"
                      class="link"
                      data-testid="component-configure"
                      @click="openConfig(machine.machine_id, c.component_id)"
                    >
                      {{ t('workbench.configure') }}
                    </button>
                    <button
                      type="button"
                      class="link danger"
                      :disabled="busy"
                      @click="deleteComponent(c)"
                    >
                      {{ t('plant.delete') }}
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <form
            v-if="drawer?.mode !== 'edit'"
            class="add"
            data-testid="add-component"
            @submit.prevent="saveComponent()"
          >
            <strong>{{ t('plant.addComponent') }}</strong>
            <input v-model.trim="comp.id" class="st-input st-mono" :placeholder="t('plant.id')" />
            <select v-model="comp.type" class="st-select" :aria-label="t('plant.type')">
              <option v-for="ty in TYPES" :key="ty" :value="ty">{{ t(`types.${ty}`) }}</option>
            </select>
            <input v-model="comp.zh" class="st-input" :placeholder="t('plant.nameZh')" />
            <input v-model="comp.en" class="st-input" :placeholder="t('plant.nameEn')" />
            <input
              v-model.trim="comp.chain"
              class="st-input st-mono"
              :placeholder="t('plant.driveChain')"
            />
            <button type="submit" class="st-button" :disabled="busy">{{ t('plant.add') }}</button>
          </form>
        </div>
      </SideDrawer>
      <ConfigWorkbench
        v-if="machine && configComponent"
        :key="configComponent.component_id"
        class="wide"
        :component="configComponent"
        :siblings="machine.components"
        :device-id="machine.device_id"
      />
      <PanelBox v-if="!selected" :title="t('plant.hintTitle')">
        <p class="st-note">{{ t('plant.hint') }}</p>
      </PanelBox>
    </div>
  </div>
</template>

<style scoped>
.page {
  display: grid;
  gap: var(--space-4);
  max-width: 1200px;
}
.page-head {
  display: grid;
  gap: var(--space-2);
}
h1 {
  font-size: var(--text-xl);
}
h3 {
  font-size: var(--text-base);
  margin: var(--space-2) 0 0;
}
.lede {
  color: var(--ink-soft);
  font-size: var(--text-sm);
}
.layout {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) 2fr;
  gap: var(--space-4);
  align-items: start;
}
@media (max-width: 860px) {
  .layout {
    grid-template-columns: 1fr;
  }
}
.tree,
.tree ul {
  list-style: none;
  margin: 0;
  padding: 0;
}
.tree ul {
  padding-left: var(--space-4);
  border-left: 1px solid var(--line);
  margin-left: var(--space-2);
}
.node {
  display: block;
  width: 100%;
  text-align: left;
  border: 0;
  background: none;
  padding: var(--space-1) var(--space-2);
  border-radius: 6px;
  font: inherit;
  font-size: var(--text-sm);
  color: var(--ink);
  cursor: pointer;
}
.node.ws {
  font-weight: 600;
}
.node[aria-current='true'] {
  background: var(--surface-inset);
  outline: 1px solid var(--accent);
}
.add {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
  margin-top: var(--space-3);
  padding-top: var(--space-3);
  border-top: 1px solid var(--line);
}
.add strong {
  width: 100%;
  font-size: var(--text-sm);
}
.add .st-input,
.add .st-select {
  flex: 1 1 120px;
  min-width: 0;
}
.line {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}
.line .node {
  flex: 1;
  width: auto;
}
.acts {
  display: inline-flex;
  gap: 2px;
  opacity: 0.35;
}
.line:hover .acts,
.line:focus-within .acts {
  opacity: 1;
}
.acts button {
  border: 0;
  background: none;
  cursor: pointer;
  padding: 0 var(--space-1);
  font-size: var(--text-sm);
  color: var(--ink-soft);
}
.acts button.danger:hover {
  color: var(--health-critical);
}
.tree-head {
  margin-bottom: var(--space-2);
}
.add.first {
  margin-top: 0;
  padding-top: 0;
  border-top: 0;
}
.wide {
  grid-column: 1 / -1;
}
.chain {
  width: 140px;
}
.row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  flex-wrap: wrap;
}
.link {
  border: 0;
  background: none;
  padding: 0;
  font: inherit;
  font-size: var(--text-sm);
  color: var(--accent);
  cursor: pointer;
}
.link.danger:not(:disabled) {
  color: var(--health-critical);
}
.ok {
  color: var(--health-normal);
}
.muted {
  color: var(--ink-faint);
}
.error {
  color: var(--health-critical);
}
</style>

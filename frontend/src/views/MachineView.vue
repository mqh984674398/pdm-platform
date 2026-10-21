<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import HealthBadge from '@/components/base/HealthBadge.vue'
import PanelBox from '@/components/base/PanelBox.vue'
import DemoNotice from '@/components/fleet/DemoNotice.vue'
import MachineMap from '@/components/fleet/MachineMap.vue'
import BackButton from '@/components/base/BackButton.vue'
import { machineHealth, useFleet } from '@/composables/useFleet'
import { usePlantTree } from '@/composables/usePlantTree'
import { useLocalized } from '@/composables/useLocalized'

const { t } = useI18n()
const { lt, fmtDate } = useLocalized()
const route = useRoute()
const router = useRouter()
const { fleet, machines, findMachine } = useFleet()

const machine = computed(() => findMachine(route.params.id as string | undefined))
const { workshopOf } = usePlantTree()
const backTo = computed(() => {
  const w = machine.value ? workshopOf.value.get(machine.value.machine_id) : undefined
  return w ? { path: '/', query: { w } } : { path: '/' }
})

function selectMachine(id: string) {
  router.push(`/machine/${id}`)
}
function openComponent(id: string) {
  router.push(`/component/${id}`) // the component's history
}
</script>

<template>
  <div v-if="fleet && machine" class="page">
    <header class="page-head">
      <BackButton :to="backTo" :target="t('nav.overview')" />
      <div class="title-row">
        <h1>{{ lt(machine.name) }}</h1>
        <HealthBadge :state="machineHealth(machine)" />
        <label class="picker">
          <span class="visually-hidden">{{ t('machine.choose') }}</span>
          <select
            :value="machine.machine_id"
            data-testid="machine-picker"
            @change="selectMachine(($event.target as HTMLSelectElement).value)"
          >
            <option v-for="m in machines" :key="m.machine_id" :value="m.machine_id">
              {{ lt(m.name) }}
            </option>
          </select>
        </label>
      </div>
      <p class="sub">
        {{
          t('machine.snapshot', {
            source: machine.path ? lt(machine.path) : (machine.line ?? ''),
            time: machine.as_of ? fmtDate(machine.as_of) : '',
          })
        }}
      </p>
      <DemoNotice :basis="fleet.health_basis" />
    </header>
    <div class="layout">
      <PanelBox :title="t('machine.mapTitle')">
        <MachineMap :machine="machine" :selected="null" @select="openComponent" />
        <p class="hint">{{ t('machine.hint') }}</p>
      </PanelBox>
    </div>
  </div>
</template>

<style scoped>
.page {
  display: grid;
  gap: var(--space-4);
  max-width: 1400px;
}
.page-head {
  display: grid;
  gap: var(--space-2);
}
.title-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}
h1 {
  font-size: var(--text-xl);
}
.picker {
  margin-left: auto;
}
select {
  padding: 5px 28px 5px 10px;
  border-radius: var(--radius-control);
  border: 1px solid var(--line-strong);
  background: var(--surface);
}
.sub,
.hint {
  color: var(--ink-soft);
  font-size: var(--text-sm);
}
.hint {
  margin-top: var(--space-2);
}
.layout {
  display: grid;
  gap: var(--space-4);
}
.layout.withDetail {
  grid-template-columns: minmax(0, 1fr) 360px;
  align-items: start;
}
@media (max-width: 1100px) {
  .layout.withDetail {
    grid-template-columns: 1fr;
  }
}
</style>

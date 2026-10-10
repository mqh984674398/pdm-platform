<script setup lang="ts">
import { computed, onMounted, ref, type Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { session } from '@/api/session'
import type { StudioRole } from '@/api/studio'
import PanelBox from '@/components/base/PanelBox.vue'
import SegmentedControl from '@/components/base/SegmentedControl.vue'
import SimBadge from '@/components/base/SimBadge.vue'
import StepComponents from '@/components/studio/StepComponents.vue'
import StepConnection from '@/components/studio/StepConnection.vue'
import StepGroups from '@/components/studio/StepGroups.vue'
import StepMapping from '@/components/studio/StepMapping.vue'
import StepPreview from '@/components/studio/StepPreview.vue'
import StepQuality from '@/components/studio/StepQuality.vue'
import StepRail from '@/components/studio/StepRail.vue'
import StepSchema from '@/components/studio/StepSchema.vue'
import StepSignals from '@/components/studio/StepSignals.vue'
import StepTemplate from '@/components/studio/StepTemplate.vue'
import StepUnits from '@/components/studio/StepUnits.vue'
import StepVersion from '@/components/studio/StepVersion.vue'
import StepViz from '@/components/studio/StepViz.vue'
import '@/components/studio/studio.css'
import { STEPS, useStudioStore, type StepName } from '@/studio/store'

const s = useStudioStore()
const { t } = useI18n()
const error = ref(false)

const VIEWS: Record<StepName, Component> = {
  connection: StepConnection,
  schema: StepSchema,
  signals: StepSignals,
  template: StepTemplate,
  mapping: StepMapping,
  units: StepUnits,
  groups: StepGroups,
  preview: StepPreview,
  quality: StepQuality,
  components: StepComponents,
  viz: StepViz,
  version: StepVersion,
}
const name = computed(() => STEPS[s.step]!)
const nextName = computed(() => STEPS[s.step + 1])
const role = computed({
  get: () => s.role,
  set: (r: StudioRole) => void s.setRole(r),
})

// With local sign-in the server decides the role; the switch is only for development login (D-010).
const signedIn = computed(() => session.mode === 'local')

onMounted(async () => {
  try {
    if (signedIn.value) {
      const r: StudioRole = session.role === 'admin' ? 'admin' : 'operator'
      if (s.source) await s.setRole(r)
      else s.role = r
    }
    if (!s.source) await s.init()
  } catch {
    error.value = true
  }
})
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div class="title">
        <h1>{{ t('nav.datasource') }}</h1>
        <SimBadge />
      </div>
      <label v-if="!signedIn" class="role">
        <span>{{ t('studio.role') }}</span>
        <SegmentedControl
          v-model="role"
          data-testid="role-switch"
          :label="t('studio.role')"
          :options="[
            { value: 'operator', label: t('studio.roles.operator') },
            { value: 'admin', label: t('studio.roles.admin') },
          ]"
        />
      </label>
      <p class="intro">{{ t('studio.intro') }}</p>
    </header>
    <p v-if="error" class="error">{{ t('common.loadFailed') }}</p>
    <div v-else-if="s.source" class="layout">
      <StepRail />
      <PanelBox>
        <div class="step-head">
          <p class="count">{{ t('studio.stepOf', { n: s.step + 1, total: STEPS.length }) }}</p>
          <h2 data-testid="step-title">{{ t(`studio.steps.${name}`) }}</h2>
          <p class="desc">{{ t(`studio.desc.${name}`) }}</p>
        </div>
        <component :is="VIEWS[name]" />
        <footer class="step-foot">
          <button
            type="button"
            class="st-button"
            :disabled="s.step === 0"
            data-testid="step-back"
            @click="s.back()"
          >
            {{ t('studio.back') }}
          </button>
          <span v-if="!s.canAdvance && t(`studio.hint.${name}`)" class="hint">{{
            t(`studio.hint.${name}`)
          }}</span>
          <button
            v-if="nextName"
            type="button"
            class="st-button primary"
            :disabled="!s.canAdvance"
            data-testid="step-next"
            @click="s.next()"
          >
            {{ t('studio.next', { step: t(`studio.steps.${nextName}`) }) }}
          </button>
        </footer>
      </PanelBox>
    </div>
  </div>
</template>

<style scoped>
.page {
  display: grid;
  gap: var(--space-4);
  max-width: 1280px;
}
.page-head {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: var(--space-2) var(--space-4);
  align-items: center;
}
.title {
  display: flex;
  gap: var(--space-3);
  align-items: center;
}
h1 {
  font-size: var(--text-xl);
}
.role {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  font-size: var(--text-sm);
  color: var(--ink-soft);
}
.intro {
  grid-column: 1 / -1;
  color: var(--ink-soft);
}
.layout {
  display: grid;
  grid-template-columns: 210px minmax(0, 1fr);
  gap: var(--space-5);
  align-items: start;
}
@media (max-width: 900px) {
  .layout {
    grid-template-columns: 1fr;
  }
}
.step-head {
  margin-bottom: var(--space-4);
}
.count {
  font-size: var(--text-xs);
  color: var(--ink-faint);
}
h2 {
  font-size: var(--text-lg);
}
.desc {
  color: var(--ink-soft);
  font-size: var(--text-sm);
}
.step-foot {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: space-between;
  margin-top: var(--space-5);
  padding-top: var(--space-4);
  border-top: 1px solid var(--line);
}
.hint {
  margin-left: auto;
  font-size: var(--text-sm);
  color: var(--ink-faint);
}
.error {
  color: var(--health-critical);
}
</style>

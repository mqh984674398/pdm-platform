<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import HealthBadge from '@/components/base/HealthBadge.vue'
import PanelBox from '@/components/base/PanelBox.vue'
import SimBadge from '@/components/base/SimBadge.vue'
import { HEALTH_STATES, healthVar } from '@/theme/health'

const { t } = useI18n()
const surfaces = ['--bg', '--surface', '--surface-inset', '--line', '--ink', '--accent']
</script>

<template>
  <div class="page">
    <h1>{{ t('design.title') }}</h1>
    <p class="lead">{{ t('design.lead') }}</p>
    <PanelBox :title="t('design.health')">
      <div class="row">
        <HealthBadge v-for="s in HEALTH_STATES" :key="s" :state="s" />
      </div>
      <div class="row">
        <HealthBadge v-for="s in HEALTH_STATES" :key="s" :state="s" size="sm" />
      </div>
      <div class="strip" :aria-label="t('design.health')">
        <span
          v-for="s in HEALTH_STATES"
          :key="s"
          :class="{ hatch: s === 'UNKNOWN' }"
          :style="s === 'UNKNOWN' ? {} : { background: healthVar(s) }"
        ></span>
      </div>
    </PanelBox>
    <PanelBox :title="t('design.markers')">
      <div class="row">
        <SimBadge />
        <span class="muted">{{ t('sim.hint') }}</span>
      </div>
    </PanelBox>
    <PanelBox :title="t('design.surfaces')">
      <div class="swatches">
        <div v-for="v in surfaces" :key="v" class="swatch">
          <span :style="{ background: `var(${v})` }"></span>
          <code>{{ v }}</code>
        </div>
      </div>
    </PanelBox>
  </div>
</template>

<style scoped>
.page {
  display: grid;
  gap: var(--space-4);
  max-width: 960px;
}
h1 {
  font-size: var(--text-xl);
}
.lead,
.muted {
  color: var(--ink-soft);
}
.row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}
.strip {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  height: 10px;
  border-radius: 5px;
  overflow: hidden;
}
.strip .hatch {
  background: var(--hatch), var(--health-unknown-soft);
}
.swatches {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: var(--space-3);
}
.swatch {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.swatch span {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  box-shadow: inset 0 0 0 1px var(--line-strong);
}
code {
  font-size: var(--text-xs);
  color: var(--ink-soft);
}
</style>

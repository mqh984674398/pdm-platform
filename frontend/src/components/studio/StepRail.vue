<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { STEPS, useStudioStore, type StepName } from '@/studio/store'

const s = useStudioStore()
const { t } = useI18n()
// Phases group the contract's 12 steps; order is fixed by the workflow (T008 AC1).
const PHASES: { key: string; steps: StepName[] }[] = [
  { key: 'connect', steps: ['connection', 'schema'] },
  { key: 'choose', steps: ['signals', 'template'] },
  { key: 'define', steps: ['mapping', 'units', 'groups'] },
  { key: 'verify', steps: ['preview', 'quality'] },
  { key: 'publish', steps: ['components', 'viz', 'version'] },
]
const index = (name: StepName) => STEPS.indexOf(name)
const done = (name: StepName) =>
  s.stepComplete[name] && index(name) <= s.visited && s.step !== index(name)
</script>

<template>
  <nav class="rail" :aria-label="t('nav.datasource')">
    <div v-for="p in PHASES" :key="p.key" class="phase">
      <p class="phase-name">{{ t(`studio.phases.${p.key}`) }}</p>
      <ol>
        <li v-for="name in p.steps" :key="name">
          <button
            type="button"
            class="step"
            :class="{
              current: s.step === index(name),
              done: done(name),
            }"
            :disabled="index(name) > s.visited"
            :aria-current="s.step === index(name) ? 'step' : undefined"
            :data-step="name"
            @click="s.go(index(name))"
          >
            <span class="node">
              <svg v-if="done(name)" viewBox="0 0 16 16" aria-hidden="true">
                <path
                  d="M4 8.5l2.5 2.5L12 5.5"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                />
              </svg>
              <template v-else>{{ index(name) + 1 }}</template>
            </span>
            <span class="label">{{ t(`studio.steps.${name}`) }}</span>
          </button>
        </li>
      </ol>
    </div>
  </nav>
</template>

<style scoped>
.rail {
  display: grid;
  gap: var(--space-3);
  align-content: start;
}
.phase-name {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--ink-faint);
  margin: 0 0 var(--space-1) 2px;
}
ol {
  margin: 0;
  padding: 0;
  list-style: none;
  position: relative;
}
li {
  position: relative;
}
/* the process line linking step nodes */
li + li::before {
  content: '';
  position: absolute;
  left: 13px;
  top: -6px;
  height: 12px;
  border-left: 2px solid var(--line-strong);
}
.step {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  width: 100%;
  padding: 4px 8px 4px 2px;
  border: 0;
  border-radius: var(--radius-control);
  background: transparent;
  text-align: left;
  font-size: var(--text-sm);
  color: var(--ink-soft);
  cursor: pointer;
}
.step:disabled {
  cursor: default;
  color: var(--ink-faint);
}
.step:not(:disabled):hover {
  background: var(--surface-inset);
}
.node {
  flex: none;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 2px solid var(--line-strong);
  background: var(--surface);
  font-size: var(--text-xs);
  font-weight: 600;
}
.node svg {
  width: 14px;
  height: 14px;
}
.step.done .node {
  border-color: var(--accent);
  background: var(--accent);
  color: #fff;
}
.step.current {
  color: var(--ink);
  font-weight: 600;
  background: var(--accent-soft);
}
.step.current .node {
  border-color: var(--accent);
  color: var(--accent);
}
</style>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useLocalized } from '@/composables/useLocalized'
import { useStudioStore } from '@/studio/store'

const s = useStudioStore()
const { t, n } = useI18n()
const { lt } = useLocalized()

function keyOf(signalId: string) {
  return s.activeDrafts.find((d) => d.signal_id === signalId)!.key_name
}
function sec(v: number | null | undefined, digits = 2) {
  return v === null || v === undefined ? '' : `${n(v, { maximumFractionDigits: digits })} s`
}
</script>

<template>
  <div class="st-stack">
    <p class="st-note">{{ t('studio.quality.intro') }}</p>
    <div class="st-scroll">
      <table class="st-table" data-testid="quality-table">
        <thead>
          <tr>
            <th>{{ t('studio.quality.signal') }}</th>
            <th class="num">{{ t('studio.quality.samples') }}</th>
            <th class="num">{{ t('studio.quality.windows') }}</th>
            <th class="num">{{ t('studio.quality.interval') }}</th>
            <th class="num">{{ t('studio.quality.jitter') }}</th>
            <th class="num">{{ t('studio.quality.missing') }}</th>
            <th class="num">{{ t('studio.quality.duplicates') }}</th>
            <th class="num">{{ t('studio.quality.outOfOrder') }}</th>
            <th>{{ t('studio.quality.issues') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="q in s.quality" :key="q.signal_id" :data-quality="keyOf(q.signal_id)">
            <td>
              <div>{{ lt(s.signalName(keyOf(q.signal_id))) }}</div>
              <div class="st-note st-mono">{{ keyOf(q.signal_id) }}</div>
            </td>
            <td class="num">{{ n(q.sample_count) }}</td>
            <td class="num">{{ q.observation_windows }}</td>
            <td class="num">
              {{
                s.drafts[keyOf(q.signal_id)]?.expected_sampling_s
                  ? sec(q.median_interval_s)
                  : t('studio.quality.eventBased')
              }}
            </td>
            <td class="num">{{ sec(q.interval_jitter_s, 3) }}</td>
            <td class="num">{{ q.missing_count }}</td>
            <td class="num">{{ q.duplicate_count }}</td>
            <td class="num">{{ q.out_of_order_count }}</td>
            <td>
              <span v-if="!q.flags.length" class="st-ok">{{ t('studio.quality.clean') }}</span>
              <span
                v-for="f in q.flags"
                :key="f"
                class="st-flag"
                :title="t(`studio.quality.help.${f}`)"
                :data-flag="f"
                >{{ t(`studio.quality.flags.${f}`) }}</span
              >
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <dl class="legend">
      <template v-for="f in [...new Set(s.quality.flatMap((q) => q.flags))]" :key="f">
        <dt>{{ t(`studio.quality.flags.${f}`) }}</dt>
        <dd>{{ t(`studio.quality.help.${f}`) }}</dd>
      </template>
    </dl>
  </div>
</template>

<style scoped>
.legend {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: var(--space-1) var(--space-4);
  margin: 0;
  font-size: var(--text-sm);
}
dt {
  font-weight: 500;
}
dd {
  margin: 0;
  color: var(--ink-soft);
}
</style>

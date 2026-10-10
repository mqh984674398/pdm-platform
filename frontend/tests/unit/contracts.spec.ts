import { describe, expect, it } from 'vitest'
import type { PredictionResult } from '@/api/contracts'

function describeResult(r: PredictionResult): string {
  // Exhaustive switch: adding a result kind without handling it fails type checking.
  switch (r.kind) {
    case 'anomaly_score':
      return `score ${r.score}`
    case 'class_probability':
      return `classes ${Object.keys(r.probabilities).length}`
    case 'degradation_indicator':
      return `degradation ${r.value} ${r.unit}`
    case 'failure_probability':
      return `p=${r.probability}`
    case 'unsupported':
      return `unsupported ${r.reason}`
    default: {
      const never: never = r
      return never
    }
  }
}

describe('generated contract types', () => {
  it('narrow the prediction union by kind', () => {
    const meta = {
      model_version: 'm@1',
      feature_version: 'f@1',
      config_version: 'c@1',
      computed_at: '2026-01-01T00:00:00Z',
      data_window: { start: '2026-01-01T00:00:00Z', end: '2026-01-02T00:00:00Z' },
      is_simulated: true,
    }
    const r: PredictionResult = {
      kind: 'unsupported',
      operator_id: 'op',
      component_id: 'c1',
      lifecycle_id: 'l1',
      regime_id: null,
      meta,
      requested_kind: 'failure_probability',
      reason: 'NO_FAILURE_EVIDENCE',
      detail: { zh: '缺少失效证据', en: 'No failure evidence' },
    }
    expect(describeResult(r)).toBe('unsupported NO_FAILURE_EVIDENCE')
  })
})

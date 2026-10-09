import { describe, expect, it } from 'vitest'
import { fetchHealth } from '@/api/health'

describe('fetchHealth', () => {
  it('returns parsed body on success', async () => {
    const body = { status: 'ok', version: '0.1.0', llm_enabled: false, llm_required: false }
    const fake = (async () => new Response(JSON.stringify(body), { status: 200 })) as typeof fetch
    expect(await fetchHealth(fake)).toEqual(body)
  })

  it('returns null when backend is unreachable', async () => {
    const failing = (async () => {
      throw new TypeError('network')
    }) as typeof fetch
    expect(await fetchHealth(failing)).toBeNull()
  })
})

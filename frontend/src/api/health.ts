export interface HealthResponse {
  status: string
  version: string
  llm_enabled: boolean
  llm_required: boolean
}

export async function fetchHealth(fetchImpl: typeof fetch = fetch): Promise<HealthResponse | null> {
  try {
    const resp = await fetchImpl('/api/health')
    return resp.ok ? ((await resp.json()) as HealthResponse) : null
  } catch {
    return null
  }
}

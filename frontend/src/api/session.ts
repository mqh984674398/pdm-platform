/**
 * Who is signed in (SEC-01, T028).
 *
 * Deployment runs with local accounts: the server sets an HttpOnly session cookie and every state-changing
 * request carries `X-PDM-CSRF: 1`. In development mode (D-010) the browser states a user and role in
 * headers instead; the role picker on the Models screen only appears in that mode.
 */
import { reactive } from 'vue'

export type AuthMode = 'unknown' | 'dev' | 'local'
export const UI_USER = { user: 'ui-engineer', role: 'engineer' }
const DEV_ROLES = ['viewer', 'maintenance', 'engineer', 'admin']

export const session = reactive<{ mode: AuthMode; user: string | null; role: string | null }>({
  mode: 'unknown',
  user: null,
  role: null,
})

/** Development header auth only (D-010): a reviewer may act as another role. */
export function devRole(): string {
  try {
    const r = localStorage.getItem('pdm-dev-role')
    return r && DEV_ROLES.includes(r) ? r : UI_USER.role
  } catch {
    return UI_USER.role
  }
}

/** Headers for every API call: CSRF marker always, development identity unless signed in locally. */
export function authHeaders(): Record<string, string> {
  if (session.mode === 'local') return { 'X-PDM-CSRF': '1' }
  const role = devRole()
  return {
    'X-PDM-CSRF': '1',
    'X-PDM-User': role === UI_USER.role ? UI_USER.user : `ui-${role}`,
    'X-PDM-Role': role,
  }
}

type Me = { user_id: string; role: string; mode: string }

function apply(me: Me | null, mode?: AuthMode) {
  session.mode = mode ?? (me?.mode === 'local' ? 'local' : 'dev')
  session.user = me?.user_id ?? null
  session.role = me?.role ?? null
}

/** Ask the server who we are. A 401 without dev headers working means local sign-in is needed. */
export async function loadSession(fetchImpl: typeof fetch = (...a) => fetch(...a)): Promise<void> {
  try {
    const resp = await fetchImpl('/api/auth/me', { headers: authHeaders() })
    if (resp.ok) return apply((await resp.json()) as Me)
    apply(null, resp.status === 401 ? 'local' : 'dev')
  } catch {
    apply(null, 'dev')
  }
}

export async function signIn(
  userId: string,
  password: string,
  fetchImpl: typeof fetch = (...a) => fetch(...a),
): Promise<boolean> {
  const resp = await fetchImpl('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, password }),
  })
  if (!resp.ok) return false
  apply((await resp.json()) as Me, 'local')
  return true
}

export async function signOut(fetchImpl: typeof fetch = (...a) => fetch(...a)): Promise<void> {
  await fetchImpl('/api/auth/logout', { method: 'POST', headers: { 'X-PDM-CSRF': '1' } })
  apply(null, 'local')
}

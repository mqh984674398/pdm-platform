import { beforeEach, describe, expect, it } from 'vitest'
import { authHeaders, loadSession, session, signIn } from '@/api/session'
import { canOpen, MODULES, NAV } from '@/router/nav'

const reply = (status: number, body: unknown = null) =>
  (async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch

describe('session (T028)', () => {
  beforeEach(() =>
    Object.assign(session, { mode: 'unknown', user: null, role: null, modules: null }),
  )

  it('sends CSRF and dev identity in development mode', async () => {
    await loadSession(reply(200, { user_id: 'ui-engineer', role: 'engineer', mode: 'dev' }))
    expect(session.mode).toBe('dev')
    expect(authHeaders()).toMatchObject({ 'X-PDM-CSRF': '1', 'X-PDM-Role': 'engineer' })
  })

  it('asks for sign-in on 401 and drops identity headers once local', async () => {
    await loadSession(reply(401))
    expect(session).toMatchObject({ mode: 'local', user: null })
    expect(authHeaders()).toEqual({ 'X-PDM-CSRF': '1' })
    expect(await signIn('adm', 'bad', reply(401))).toBe(false)
    expect(
      await signIn('adm', 'pw', reply(200, { user_id: 'adm', role: 'admin', mode: 'local' })),
    ).toBe(true)
    expect(session).toMatchObject({ mode: 'local', user: 'adm', role: 'admin' })
  })

  it('keeps the modules the server allows for the role (D-033)', async () => {
    await loadSession(
      reply(200, { user_id: 'tech', role: 'maintenance', mode: 'local', modules: ['alarms'] }),
    )
    expect(session.modules).toEqual(['alarms'])
    expect(canOpen('alarms', session.role, session.modules)).toBe(true)
    expect(canOpen('datasource', session.role, session.modules)).toBe(false)
    expect(canOpen('users', session.role, session.modules)).toBe(false)
    expect(canOpen('users', 'admin', MODULES)).toBe(true)
  })

  it('hides nothing until the server has answered, except administration', () => {
    for (const n of MODULES) expect(canOpen(n, 'viewer', null)).toBe(true)
    expect(canOpen('users', 'viewer', null)).toBe(false)
    expect(NAV.find((n) => n.name === 'users')?.adminOnly).toBe(true)
    expect(MODULES).not.toContain('users')
  })
})

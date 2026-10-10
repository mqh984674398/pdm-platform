<script setup lang="ts">
/**
 * User and role administration (D-033), administrators only. Accounts: register, rename, change role,
 * reset password, deactivate, delete. Roles: which screens each role may use; the server enforces the
 * same setting on the screens' own endpoints. The administrator role always keeps every screen.
 */
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { RoleModules, UserInfo } from '@/api/contracts'
import { MonitoringApiError, monitoringApi } from '@/api/monitoring'
import { loadSession, session } from '@/api/session'
import PanelBox from '@/components/base/PanelBox.vue'
import '@/components/studio/studio.css'
import { useLocalized } from '@/composables/useLocalized'
import { MODULES } from '@/router/nav'

const ROLES = ['viewer', 'maintenance', 'engineer', 'admin'] as const
const MIN_PASSWORD = 10

const { t } = useI18n()
const { lt, fmtDate } = useLocalized()

const users = ref<UserInfo[]>([])
const roles = ref<RoleModules[]>([])
const loadError = ref(false)
const message = ref<{ ok: boolean; text: string } | null>(null)
const busy = ref(false)

function fail(e: unknown) {
  const body = e instanceof MonitoringApiError ? e.body : null
  const reason = (body?.detail as { reason?: string } | null | undefined)?.reason
  message.value = {
    ok: false,
    text: body ? `${lt(body.message)}${reason ? ` (${reason})` : ''}` : t('users.failed'),
  }
}
async function run(action: () => Promise<unknown>, done: string) {
  busy.value = true
  message.value = null
  try {
    await action()
    await load()
    message.value = { ok: true, text: done }
  } catch (e) {
    fail(e)
  } finally {
    busy.value = false
  }
}

async function load() {
  try {
    const [u, r] = await Promise.all([monitoringApi.users(), monitoringApi.roleModules()])
    users.value = u
    roles.value = r
    for (const x of r) matrix[x.role] = [...x.modules]
  } catch {
    loadError.value = true
  }
}
load()

// --- accounts ---
const form = reactive({ user_id: '', display_name: '', role: 'viewer', password: '', confirm: '' })
const formError = computed(() => {
  if (!/^[a-zA-Z0-9._-]{2,64}$/.test(form.user_id)) return t('users.badUserId')
  if (!form.display_name.trim()) return t('users.needName')
  if (form.password.length < MIN_PASSWORD) return t('users.shortPassword', { n: MIN_PASSWORD })
  if (form.password !== form.confirm) return t('users.mismatch')
  return null
})
const formTouched = ref(false)
function register() {
  formTouched.value = true
  if (formError.value) return
  const u = { ...form, display_name: form.display_name.trim() }
  run(
    async () => {
      await monitoringApi.createUser({
        user_id: u.user_id,
        display_name: u.display_name,
        role: u.role,
        password: u.password,
      })
      Object.assign(form, {
        user_id: '',
        display_name: '',
        role: 'viewer',
        password: '',
        confirm: '',
      })
      formTouched.value = false
    },
    t('users.registered', { id: u.user_id }),
  )
}

const isSelf = (u: UserInfo) => u.user_id === session.user
function changeRole(u: UserInfo, role: string) {
  if (role === u.role) return
  run(() => monitoringApi.changeUser(u.user_id, { role }), t('users.changed', { id: u.user_id }))
}
function toggleActive(u: UserInfo) {
  run(
    () => monitoringApi.changeUser(u.user_id, { active: !u.active }),
    t('users.changed', { id: u.user_id }),
  )
}
function rename(u: UserInfo) {
  const name = window.prompt(t('users.renamePrompt', { id: u.user_id }), u.display_name)?.trim()
  if (!name || name === u.display_name) return
  run(
    () => monitoringApi.changeUser(u.user_id, { display_name: name }),
    t('users.changed', { id: u.user_id }),
  )
}
function resetPassword(u: UserInfo) {
  const pw = window.prompt(t('users.passwordPrompt', { id: u.user_id, n: MIN_PASSWORD }))
  if (pw === null) return
  if (pw.length < MIN_PASSWORD) {
    message.value = { ok: false, text: t('users.shortPassword', { n: MIN_PASSWORD }) }
    return
  }
  run(
    () => monitoringApi.changeUser(u.user_id, { password: pw }),
    t('users.passwordReset', { id: u.user_id }),
  )
}
function remove(u: UserInfo) {
  if (!window.confirm(t('users.deleteConfirm', { id: u.user_id }))) return
  run(() => monitoringApi.deleteUser(u.user_id), t('users.deleted', { id: u.user_id }))
}

// --- role modules ---
const matrix = reactive<Record<string, string[]>>({})
const editableRoles = computed(() => roles.value.filter((r) => r.editable))
const dirty = computed(() =>
  editableRoles.value.filter(
    (r) => [...(matrix[r.role] ?? [])].sort().join() !== [...r.modules].sort().join(),
  ),
)
function toggle(role: string, mod: string) {
  const cur = matrix[role] ?? []
  matrix[role] = cur.includes(mod) ? cur.filter((m) => m !== mod) : [...cur, mod]
}
function saveModules() {
  const changes = dirty.value.map((r) => ({ role: r.role, modules: [...(matrix[r.role] ?? [])] }))
  run(async () => {
    for (const c of changes) await monitoringApi.setRoleModules(c.role, c.modules)
    await loadSession() // the signed-in administrator's own navigation never changes, but stay in sync
  }, t('users.modulesSaved'))
}
function resetModules() {
  for (const r of roles.value) matrix[r.role] = [...r.modules]
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>{{ t('nav.users') }}</h1>
      <p class="lede">{{ t('users.lede') }}</p>
    </header>
    <p v-if="loadError" class="error">{{ t('common.loadFailed') }}</p>
    <p
      v-if="message"
      :class="message.ok ? 'ok' : 'error'"
      role="status"
      data-testid="users-message"
    >
      {{ message.text }}
    </p>

    <PanelBox :title="t('users.register')">
      <form class="st-stack" data-testid="user-form" @submit.prevent="register">
        <div class="st-form">
          <label class="st-field">
            <span>{{ t('users.userId') }}</span>
            <input
              v-model.trim="form.user_id"
              class="st-input"
              autocomplete="off"
              data-testid="new-user-id"
            />
          </label>
          <label class="st-field">
            <span>{{ t('users.displayName') }}</span>
            <input v-model="form.display_name" class="st-input" data-testid="new-user-name" />
          </label>
          <label class="st-field">
            <span>{{ t('users.role') }}</span>
            <select v-model="form.role" class="st-select" data-testid="new-user-role">
              <option v-for="r in ROLES" :key="r" :value="r">{{ t(`models.roles.${r}`) }}</option>
            </select>
          </label>
          <label class="st-field">
            <span>{{ t('users.password', { n: MIN_PASSWORD }) }}</span>
            <input
              v-model="form.password"
              type="password"
              class="st-input"
              autocomplete="new-password"
              data-testid="new-user-password"
            />
          </label>
          <label class="st-field">
            <span>{{ t('users.confirm') }}</span>
            <input
              v-model="form.confirm"
              type="password"
              class="st-input"
              autocomplete="new-password"
              data-testid="new-user-confirm"
            />
          </label>
        </div>
        <div class="row">
          <button
            type="submit"
            class="st-button primary"
            :disabled="busy"
            data-testid="new-user-submit"
          >
            {{ t('users.registerButton') }}
          </button>
          <span v-if="formTouched && formError" class="error">{{ formError }}</span>
        </div>
      </form>
    </PanelBox>

    <PanelBox :title="t('users.accounts', { n: users.length })">
      <div class="st-scroll">
        <table class="st-table" data-testid="users-table">
          <thead>
            <tr>
              <th>{{ t('users.userId') }}</th>
              <th>{{ t('users.displayName') }}</th>
              <th>{{ t('users.role') }}</th>
              <th>{{ t('users.status') }}</th>
              <th>{{ t('users.createdAt') }}</th>
              <th>{{ t('users.actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in users" :key="u.user_id" :data-user="u.user_id">
              <td class="st-mono">
                {{ u.user_id }}
                <span v-if="isSelf(u)" class="st-note">{{ t('users.you') }}</span>
              </td>
              <td>{{ u.display_name }}</td>
              <td>
                <select
                  class="st-select"
                  :value="u.role"
                  :disabled="busy || isSelf(u)"
                  :aria-label="t('users.role')"
                  data-testid="user-role"
                  @change="changeRole(u, ($event.target as HTMLSelectElement).value)"
                >
                  <option v-for="r in ROLES" :key="r" :value="r">
                    {{ t(`models.roles.${r}`) }}
                  </option>
                </select>
              </td>
              <td>
                <span :class="u.active ? 'ok' : 'muted'">{{
                  u.active ? t('users.active') : t('users.inactive')
                }}</span>
              </td>
              <td>{{ fmtDate(u.created_at, false) }}</td>
              <td>
                <div class="actions">
                  <button type="button" class="link" :disabled="busy" @click="rename(u)">
                    {{ t('users.rename') }}
                  </button>
                  <button type="button" class="link" :disabled="busy" @click="resetPassword(u)">
                    {{ t('users.resetPassword') }}
                  </button>
                  <button
                    type="button"
                    class="link"
                    :disabled="busy || isSelf(u)"
                    data-testid="user-toggle"
                    @click="toggleActive(u)"
                  >
                    {{ u.active ? t('users.deactivate') : t('users.activate') }}
                  </button>
                  <button
                    type="button"
                    class="link danger"
                    :disabled="busy || isSelf(u)"
                    data-testid="user-delete"
                    @click="remove(u)"
                  >
                    {{ t('users.delete') }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </PanelBox>

    <PanelBox :title="t('users.modules')">
      <p class="st-note">{{ t('users.modulesHint') }}</p>
      <div class="st-scroll">
        <table class="st-table matrix" data-testid="modules-table">
          <thead>
            <tr>
              <th>{{ t('users.module') }}</th>
              <th v-for="r in roles" :key="r.role" class="center">
                {{ t(`models.roles.${r.role}`) }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in MODULES" :key="m">
              <td>{{ t(`nav.${m}`) }}</td>
              <td v-for="r in roles" :key="r.role" class="center">
                <input
                  type="checkbox"
                  :checked="(matrix[r.role] ?? []).includes(m)"
                  :disabled="!r.editable || busy"
                  :aria-label="`${t(`models.roles.${r.role}`)} · ${t(`nav.${m}`)}`"
                  :data-module="`${r.role}:${m}`"
                  @change="toggle(r.role, m)"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="row">
        <button
          type="button"
          class="st-button primary"
          :disabled="busy || !dirty.length"
          data-testid="modules-save"
          @click="saveModules"
        >
          {{ t('users.saveModules') }}
        </button>
        <button type="button" class="st-button" :disabled="!dirty.length" @click="resetModules">
          {{ t('users.reset') }}
        </button>
      </div>
    </PanelBox>
  </div>
</template>

<style scoped>
.page {
  display: grid;
  gap: var(--space-4);
  max-width: 1200px;
}
.page-head {
  display: grid;
  gap: var(--space-2);
}
h1 {
  font-size: var(--text-xl);
}
.lede {
  color: var(--ink-soft);
  font-size: var(--text-sm);
}
.row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  flex-wrap: wrap;
  margin-top: var(--space-3);
}
.actions {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
}
.link {
  border: 0;
  background: none;
  padding: 0;
  font: inherit;
  font-size: var(--text-sm);
  color: var(--accent);
  cursor: pointer;
}
.link:disabled {
  color: var(--ink-faint);
  cursor: not-allowed;
}
.link.danger:not(:disabled) {
  color: var(--health-critical);
}
.center {
  text-align: center;
}
.matrix td:first-child {
  white-space: nowrap;
}
.ok {
  color: var(--health-normal);
}
.muted {
  color: var(--ink-faint);
}
.error {
  color: var(--health-critical);
}
</style>

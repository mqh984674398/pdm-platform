<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { fetchHealth, type HealthResponse } from '@/api/health'
import { loadSession, session, signOut } from '@/api/session'
import SegmentedControl from '@/components/base/SegmentedControl.vue'
import SignIn from '@/components/shell/SignIn.vue'
import { setLocale, type Locale } from '@/i18n'
import { canOpen, NAV, NAV_GROUPS } from '@/router/nav'
import { useTheme, type ThemeChoice } from '@/composables/useTheme'

const { t, locale } = useI18n()
const route = useRoute()
const theme = useTheme()
const sidebarOpen = ref(
  typeof window === 'undefined' || !window.matchMedia
    ? true
    : window.matchMedia('(min-width: 861px)').matches,
)
const backend = ref<HealthResponse | null>(null)
const backendChecked = ref(false)

const lang = computed<Locale>({
  get: () => locale.value as Locale,
  set: (v) => setLocale(v),
})
const langOptions = [
  { value: 'zh-CN' as Locale, label: '中文' },
  { value: 'en-US' as Locale, label: 'EN' },
]
const themeOptions = computed(() => [
  { value: 'system' as ThemeChoice, label: t('shell.themeSystem') },
  { value: 'light' as ThemeChoice, label: t('shell.themeLight') },
  { value: 'dark' as ThemeChoice, label: t('shell.themeDark') },
])
const title = computed(() =>
  route.name === 'design' ? t('design.title') : route.name ? t(`nav.${String(route.name)}`) : '',
)

const needsSignIn = computed(() => session.mode === 'local' && !session.user)
const nav = computed(() => NAV.filter((n) => canOpen(n.name, session.role, session.modules)))
const groups = computed(() => NAV_GROUPS.filter((g) => nav.value.some((n) => n.group === g)))
const allowed = computed(
  () => !route.name || canOpen(String(route.name), session.role, session.modules),
)

onMounted(async () => {
  loadSession()
  backend.value = await fetchHealth()
  backendChecked.value = true
})
</script>

<template>
  <div class="shell" :class="{ collapsed: !sidebarOpen }">
    <aside class="sidebar" :aria-hidden="!sidebarOpen">
      <div class="brand">
        <svg viewBox="0 0 24 24" class="brand-mark" aria-hidden="true">
          <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2" />
          <path d="M5 13h4l2-5 3 9 2-4h3" fill="none" stroke="currentColor" stroke-width="2" />
        </svg>
        <span class="brand-name">{{ t('app.name') }}</span>
      </div>
      <nav>
        <div v-for="group in groups" :key="group" class="nav-group">
          <h2 class="nav-heading">{{ t(`nav.${group}`) }}</h2>
          <RouterLink
            v-for="item in nav.filter((n) => n.group === group)"
            :key="item.name"
            :to="item.path"
            class="nav-item"
            :data-nav="item.name"
          >
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <path
                :d="item.icon"
                fill="none"
                stroke="currentColor"
                stroke-width="1.4"
                stroke-linejoin="round"
              />
            </svg>
            {{ t(`nav.${item.name}`) }}
          </RouterLink>
        </div>
      </nav>
      <footer class="sidebar-foot" data-testid="backend-status">
        <span class="dot" :class="{ ok: backend, down: backendChecked && !backend }"></span>
        <template v-if="!backendChecked">{{ t('home.checking') }}</template>
        <template v-else-if="backend">
          {{ t('home.backendOk', { version: backend.version }) }}
        </template>
        <template v-else>{{ t('home.backendDown') }}</template>
      </footer>
    </aside>

    <div class="main">
      <header class="toolbar">
        <button
          class="icon-button"
          type="button"
          :aria-label="t('shell.toggleSidebar')"
          :aria-expanded="sidebarOpen"
          @click="sidebarOpen = !sidebarOpen"
        >
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <rect
              x="1.5"
              y="2.5"
              width="13"
              height="11"
              rx="2"
              fill="none"
              stroke="currentColor"
              stroke-width="1.3"
            />
            <path d="M6 2.5v11" stroke="currentColor" stroke-width="1.3" />
          </svg>
        </button>
        <span class="toolbar-title">{{ title }}</span>
        <div class="toolbar-controls">
          <SegmentedControl
            v-model="lang"
            :options="langOptions"
            :label="t('shell.language')"
            data-testid="lang-switch"
          />
          <SegmentedControl v-model="theme" :options="themeOptions" :label="t('shell.theme')" />
          <span v-if="session.mode === 'local' && session.user" class="who" data-testid="who">
            {{ session.user }} ({{ t(`models.roles.${session.role}`) }})
            <button type="button" class="link" data-testid="sign-out" @click="signOut()">
              {{ t('auth.signOut') }}
            </button>
          </span>
        </div>
      </header>
      <main class="content">
        <SignIn v-if="needsSignIn" />
        <template v-else-if="session.mode !== 'unknown'">
          <RouterView v-if="allowed" />
          <div v-else class="no-access" data-testid="no-access">
            <p>{{ t('shell.noAccess') }}</p>
            <RouterLink v-if="nav[0]" :to="nav[0].path">{{ t(`nav.${nav[0].name}`) }}</RouterLink>
          </div>
        </template>
      </main>
    </div>
    <footer class="app-footer" data-testid="app-footer">
      {{ t('app.copyright') }}
    </footer>
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: 232px 1fr;
  grid-template-rows: minmax(0, 1fr) auto;
  height: 100%;
  transition: grid-template-columns var(--dur) var(--ease);
}
.shell.collapsed {
  grid-template-columns: 0 1fr;
}
.sidebar {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--sidebar);
  backdrop-filter: saturate(160%) blur(20px);
  border-right: 1px solid var(--line);
  min-width: 0;
}
.brand {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-4) var(--space-4) var(--space-3);
  font-weight: 600;
  white-space: nowrap;
}
.brand-mark {
  width: 22px;
  height: 22px;
  color: var(--accent);
  flex: none;
}
nav {
  flex: 1;
  overflow-y: auto;
  padding: 0 var(--space-2);
}
.nav-group {
  margin-top: var(--space-3);
}
.nav-heading {
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--ink-faint);
  padding: 0 var(--space-2) var(--space-1);
}
.nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 5px var(--space-2);
  border-radius: var(--radius-control);
  color: var(--ink);
  font-size: var(--text-sm);
  white-space: nowrap;
}
.nav-item svg {
  width: 16px;
  height: 16px;
  color: var(--ink-soft);
  flex: none;
}
.nav-item:hover {
  background: rgb(125 135 146 / 12%);
}
.nav-item.router-link-exact-active {
  background: var(--accent);
  color: #fff;
}
.nav-item.router-link-exact-active svg {
  color: #fff;
}
.sidebar-foot {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-xs);
  color: var(--ink-soft);
  border-top: 1px solid var(--line);
  white-space: nowrap;
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--health-unknown);
  flex: none;
}
.dot.ok {
  background: var(--health-normal);
}
.dot.down {
  background: var(--health-critical);
}
.main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  height: 48px;
  padding: 0 var(--space-4);
  border-bottom: 1px solid var(--line);
  background: var(--surface);
}
.toolbar-title {
  font-weight: 600;
}
.toolbar-controls {
  margin-left: auto;
  display: flex;
  gap: var(--space-2);
}
.who {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--ink-soft);
}
.link {
  border: 0;
  background: none;
  padding: 0;
  font: inherit;
  color: var(--accent);
  cursor: pointer;
}
.icon-button {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--ink-soft);
  cursor: pointer;
}
.icon-button:hover {
  background: var(--surface-inset);
}
.icon-button svg {
  width: 16px;
  height: 16px;
}
.content {
  flex: 1;
  overflow: auto;
  padding: var(--space-5);
}
.no-access {
  display: grid;
  gap: var(--space-2);
  justify-items: start;
  color: var(--ink-soft);
}
/* Fixed site footer: its own grid row, so it never scrolls with or covers the page content. */
.app-footer {
  grid-column: 1 / -1;
  padding: 6px var(--space-4);
  border-top: 1px solid var(--line);
  background: var(--surface);
  color: var(--ink-soft);
  font-size: var(--text-xs);
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
@media (max-width: 860px) {
  .shell,
  .shell.collapsed {
    grid-template-columns: 1fr;
  }
  .sidebar {
    position: fixed;
    inset: 0 auto 0 0;
    width: 232px;
    z-index: 10;
    transform: translateX(-100%);
    transition: transform var(--dur) var(--ease);
  }
  .shell:not(.collapsed) .sidebar {
    transform: none;
    box-shadow: var(--shadow-raised);
  }
  .toolbar-controls :deep(.segmented:last-child) {
    display: none;
  }
  .content {
    padding: var(--space-4);
  }
}
</style>

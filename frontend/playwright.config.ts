import { existsSync } from 'node:fs'
import { defineConfig } from '@playwright/test'

// Set PW_CHROMIUM_PATH to reuse a pre-installed Chromium instead of downloading one.
const executablePath = process.env.PW_CHROMIUM_PATH || undefined
// The Studio tests run against the real backend on the simulated source (T011). PDM_PYTHON picks the
// interpreter that has the backend installed; the backend venv is used when present.
const python =
  process.env.PDM_PYTHON ||
  (existsSync('../backend/.venv/bin/python') ? '../backend/.venv/bin/python' : 'python3')
const API_PORT = 8765

export default defineConfig({
  testDir: 'tests/e2e',
  outputDir: 'test-results',
  use: { baseURL: 'http://127.0.0.1:4173', locale: 'zh-CN', launchOptions: { executablePath } },
  // Promoting a configuration changes health for every component, so the registry test runs alone,
  // after everything else, on the shared demo server.
  projects: [
    { name: 'main', testIgnore: /models\.spec\.ts/ },
    { name: 'registry', testMatch: /models\.spec\.ts/, dependencies: ['main'] },
  ],
  webServer: [
    {
      // Fresh demo database on every run; it seeds one signal-config version (the T019 bench signal).
      command: `${python} ../backend/scripts/demo_server.py --db test-results/e2e-demo.db --port ${API_PORT}`,
      url: `http://127.0.0.1:${API_PORT}/api/health`,
      reuseExistingServer: false,
      timeout: 180_000,
    },
    {
      // Deterministic stand-in for a local Ollama (T027); no model runs in CI.
      command: `${python} ../backend/scripts/fake_ollama.py --port 11435`,
      url: 'http://127.0.0.1:11435/api/version',
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: 'npm run preview',
      url: 'http://127.0.0.1:4173',
      reuseExistingServer: true,
      timeout: 120_000,
      env: { PDM_API_URL: `http://127.0.0.1:${API_PORT}` },
    },
  ],
})

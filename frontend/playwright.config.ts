import { defineConfig } from '@playwright/test'

// Set PW_CHROMIUM_PATH to reuse a pre-installed Chromium instead of downloading one.
const executablePath = process.env.PW_CHROMIUM_PATH || undefined

export default defineConfig({
  testDir: 'tests/e2e',
  outputDir: 'test-results',
  use: { baseURL: 'http://127.0.0.1:4173', launchOptions: { executablePath } },
  webServer: {
    command: 'npm run preview',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: true,
  },
})

import { expect, test, type Page } from '@playwright/test'

async function next(page: Page, title: string) {
  await page.getByTestId('step-next').click()
  await expect(page.getByTestId('step-title')).toHaveText(title)
}

// Runs against the real backend and the simulated source (T011); the database is fresh per run.
test('ordinary user completes the full data source workflow without SQL', async ({ page }) => {
  await page.goto('/datasource')
  await page.getByTestId('lang-switch').getByRole('radio', { name: 'EN' }).click()
  await expect(page.getByTestId('step-title')).toHaveText('Connection')
  await expect(page.getByTestId('step-next')).toBeDisabled()

  await page.getByTestId('test-connection').click()
  await expect(page.getByTestId('connection-checks').locator('li')).toHaveCount(4)
  await next(page, 'Schema')
  await expect(page.getByTestId('schema-columns')).toContainText('value_double')

  await next(page, 'Device and signals')
  await page.locator('[data-device="SIM-S13"]').click()
  await expect(page.locator('[data-key]')).toHaveCount(4)

  await next(page, 'Query template')
  await page.locator('[data-template="telemetry-by-key-range"]').click()
  await expect(page.getByTestId('template-sql-locked')).toBeVisible()
  await expect(page.getByTestId('template-sql')).toHaveCount(0)

  await next(page, 'Field mapping')
  await expect(page.locator('[data-field="time_field"]')).toHaveValue('ts')
  await next(page, 'Units')
  await expect(page.locator('[data-unit-row="M01_BS1_TRQ"]')).toContainText('N*m')
  await next(page, 'Signal groups')
  await next(page, 'Preview')
  await expect(page.getByTestId('preview-chart').locator('canvas')).toBeVisible()

  const qualityReport = page.waitForResponse((r) => r.url().endsWith('/api/quality/report'))
  await next(page, 'Sampling and quality')
  expect((await qualityReport).status()).toBe(200) // backend L4 report, not the offline summary
  await expect(page.locator('[data-quality="M01_BS1_TRQ"] [data-flag="MISSING"]')).toBeVisible()
  await expect(page.locator('[data-quality="M01_CY1_EXT"] [data-flag="DUPLICATE"]')).toBeVisible()
  await expect(page.locator('[data-quality="M01_BS1_SPD"]')).toContainText('No issues')

  await next(page, 'Components')
  await expect(page.locator('[data-component-for="M01_CY1_EXT"]')).toHaveValue('M01-CY1')
  await next(page, 'Chart templates')
  await page.locator('[data-chart="HISTOGRAM"]').click()
  await next(page, 'Save version')

  await expect(page.getByTestId('save-version')).toBeDisabled()
  await page.getByTestId('version-comment').fill('Bring in SIM-S13 drive and clamp signals')
  await page.getByTestId('save-version').click()
  await expect(page.getByTestId('saved-status')).toHaveText('Saved as version 1')
  const rows = page.getByTestId('version-history').locator('tbody tr')
  await expect(rows).toHaveCount(1)
  await expect(rows.first()).toContainText('Bring in SIM-S13')
  await expect(rows.first()).toContainText('sha256:')

  // The backend now holds the saved configuration: four SIM-S13 signals, grouped and charted.
  const resp = await page.request.get('/api/signal-config', {
    headers: { 'X-PDM-User': 'e2e', 'X-PDM-Role': 'viewer' },
  })
  const { version, content } = await resp.json()
  expect(version.comment).toBe('Bring in SIM-S13 drive and clamp signals')
  expect(content.mappings.map((m: { device_id: string }) => m.device_id)).toEqual(
    Array(4).fill('SIM-S13'),
  )
  expect(content.signals).toHaveLength(4)
  expect(content.visualizations.map((v: { chart: string }) => v.chart)).toContain('HISTOGRAM')
})

test('query text is shown to administrators only', async ({ page }) => {
  await page.goto('/datasource')
  await page.getByTestId('role-switch').getByRole('radio').nth(1).click()
  await page.getByTestId('test-connection').click()
  await page.getByTestId('step-next').click()
  await page.getByTestId('step-next').click()
  await page.locator('[data-device="SIM-S01"]').click()
  await page.getByTestId('step-next').click()
  await page.locator('[data-template="telemetry-incremental"]').click()
  await expect(page.getByTestId('template-sql')).toContainText('ts > :watermark')
})

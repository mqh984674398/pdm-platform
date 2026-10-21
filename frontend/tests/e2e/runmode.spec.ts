import { expect, test } from '@playwright/test'

// D-053: simulation and production are separate run modes; only an administrator switches.
// The test restores the mode so the shared demo server is left as it was found.

const ADMIN = { 'x-pdm-role': 'admin', 'x-pdm-user': 'e2e-admin' }

test('administrator switches to production and no simulated data is listed, then switches back', async ({
  page,
}) => {
  await page.addInitScript(() => localStorage.setItem('pdm-dev-role', 'admin'))
  await page.goto('/datasources')
  await expect(page.getByTestId('run-mode-current')).toContainText('仿真演示')
  await expect(page.getByTestId('run-mode-banner')).toBeVisible()
  await expect(page.getByTestId('ds-list')).toContainText('sim-iot')

  page.once('dialog', (d) => d.accept())
  await page.getByTestId('run-mode-production').click()
  await expect(page.getByTestId('run-mode-current')).toContainText('正式运行')
  await expect(page.getByTestId('run-mode-banner')).toHaveCount(0)
  await expect(page.getByTestId('run-mode-badge')).toContainText('正式运行')
  // nothing simulated is listed: not the source, not the demo machines
  await expect(page.getByTestId('ds-list')).not.toContainText('sim-iot')
  const machines = await (await page.request.get('/api/machines', { headers: ADMIN })).json()
  expect(machines.filter((m: { is_simulated: boolean }) => m.is_simulated)).toEqual([])
  const sources = await (await page.request.get('/api/datasources', { headers: ADMIN })).json()
  expect(sources.filter((s: { is_simulated: boolean }) => s.is_simulated)).toEqual([])

  page.once('dialog', (d) => d.accept())
  await page.getByTestId('run-mode-simulation').click()
  await expect(page.getByTestId('run-mode-current')).toContainText('仿真演示')
})

test('a role without administrator rights cannot switch the run mode', async ({ request }) => {
  const r = await request.put('/api/run-mode', {
    headers: { 'X-PDM-User': 'e2e', 'X-PDM-Role': 'engineer' },
    data: { mode: 'production' },
  })
  expect(r.status()).toBe(403)
})

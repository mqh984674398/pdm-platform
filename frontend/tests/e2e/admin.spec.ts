import { expect, test } from '@playwright/test'

// D-033 user administration and UI-05 signal setup, on the demo server (development login).

test('administrator registers, changes and deletes an account', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('pdm-dev-role', 'admin'))
  await page.goto('/users')
  await expect(page.locator('h1')).toHaveText('用户与权限')
  const id = `e2e-${Date.now()}`
  await page.getByTestId('new-user-id').fill(id)
  await page.getByTestId('new-user-name').fill('E2E user')
  await page.getByTestId('new-user-role').selectOption('maintenance')
  await page.getByTestId('new-user-password').fill('long enough pw')
  await page.getByTestId('new-user-confirm').fill('long enough pw')
  await page.getByTestId('new-user-submit').click()
  const row = page.locator(`tr[data-user="${id}"]`)
  await expect(row).toBeVisible()
  await row.getByTestId('user-role').selectOption('engineer')
  await expect(page.getByTestId('users-message')).toContainText(id)
  await expect(row.getByTestId('user-role')).toHaveValue('engineer')
  page.once('dialog', (d) => d.accept())
  await row.getByTestId('user-delete').click()
  await expect(row).toHaveCount(0)
  // the module matrix: administrator column is fixed; edits can be undone without saving
  const adminBox = page.locator('[data-module="admin:overview"]')
  await expect(adminBox).toBeChecked()
  await expect(adminBox).toBeDisabled()
  await page.locator('[data-module="viewer:models"]').uncheck()
  await expect(page.getByTestId('modules-save')).toBeEnabled()
  await page.getByRole('button', { name: '撤销修改' }).click()
  await expect(page.locator('[data-module="viewer:models"]')).toBeChecked()
})

test('administration is hidden from other roles', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('[data-nav="overview"]')).toBeVisible()
  await expect(page.locator('[data-nav="users"]')).toHaveCount(0)
  await page.goto('/users')
  await expect(page.getByTestId('no-access')).toBeVisible()
})

test('signal setup shows the saved mapping, a preview and versions', async ({ page }) => {
  await page.goto('/signals?signal=BENCH.torque')
  await expect(page.locator('h1')).toHaveText('信号配置')
  await expect(page.getByTestId('placeholder')).toHaveCount(0)
  await expect(page.getByTestId('signal-mapping')).toContainText('sim-bench')
  await expect(page.getByTestId('signal-quality')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId('signal-versions')).toBeVisible()
  await expect(page.getByTestId('app-footer')).toHaveText('© 2026 MYS-TC-VSE. All rights reserved')
})

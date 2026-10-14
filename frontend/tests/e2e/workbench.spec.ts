import { expect, test } from '@playwright/test'

// D-044..D-046: an administrator drafts, validates, publishes and activates a prediction
// configuration for one component from the plant structure screen. It changes the decision engine of
// one demo component, so it runs with the plant test, after the screens that count the demo fleet.

test('administrator takes a recommended configuration through validate, publish and activate', async ({
  page,
}) => {
  await page.addInitScript(() => localStorage.setItem('pdm-dev-role', 'admin'))
  await page.goto('/plant')
  await page.locator('[data-machine]').first().click()
  const row = page.locator('[data-component]').first()
  await row.getByTestId('component-configure').click()
  const wb = page.getByTestId('config-workbench')
  await expect(wb).toBeVisible()
  await wb.getByTestId('wb-start').click()
  await expect(page.getByTestId('wb-pipeline')).toContainText('engineering_rules')
  await wb.getByTestId('wb-compile').click()
  await expect(page.getByTestId('wb-pipeline')).toContainText('将生效')
  await wb.getByTestId('wb-validate').click()
  await expect(page.getByTestId('wb-checks')).toBeVisible()
  await expect(page.getByTestId('wb-message')).toContainText('验证通过')
  await wb.getByTestId('wb-comment').fill('e2e release')
  await wb.getByTestId('wb-publish').click()
  await expect(page.getByTestId('wb-message')).toContainText('已发布')
  await wb.getByTestId('wb-activate').click()
  await expect(page.getByTestId('wb-versions')).toContainText('启用中')
})

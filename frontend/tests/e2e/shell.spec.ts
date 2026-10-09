import { expect, test } from '@playwright/test'

test('shell route renders', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('Predictive Maintenance · 预测性维护')).toBeVisible()
  await expect(page.getByTestId('backend-status')).toBeVisible()
})

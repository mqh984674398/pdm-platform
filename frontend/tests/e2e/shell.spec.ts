import { expect, test } from '@playwright/test'

test('navigates all screens and switches language without reload', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByTestId('backend-status')).toBeVisible()
  const marker = await page.evaluate(() => ((window as unknown as { __mark: number }).__mark = 42))
  await page.locator('[data-nav="datasource"]').click()
  await expect(page.locator('h1')).toHaveText('算法配置')
  await page.getByTestId('lang-switch').getByRole('radio', { name: 'EN' }).click()
  await expect(page.locator('h1')).toHaveText('Algorithm configuration')
  expect(await page.evaluate(() => (window as unknown as { __mark: number }).__mark)).toBe(marker)
  await page.locator('[data-nav="alarms"]').click()
  await expect(page.locator('h1')).toHaveText('Alarm review')
  await page.locator('[data-nav="models"]').click()
  await expect(page.locator('h1')).toHaveText('Model versions')
  await page.locator('[data-nav="assistant"]').click()
  await expect(page.locator('h1')).toHaveText('Local assistant')
})

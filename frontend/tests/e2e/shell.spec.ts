import { expect, test } from '@playwright/test'

test('navigates all screens and switches language without reload', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByTestId('backend-status')).toBeVisible()
  const marker = await page.evaluate(() => ((window as unknown as { __mark: number }).__mark = 42))
  await page.locator('[data-nav="datasource"]').click()
  await expect(page.locator('h1')).toHaveText('数据源工作室')
  await page.getByTestId('lang-switch').getByRole('radio', { name: 'EN' }).click()
  await expect(page.locator('h1')).toHaveText('Data Source Studio')
  expect(await page.evaluate(() => (window as unknown as { __mark: number }).__mark)).toBe(marker)
  for (const name of ['overview', 'machine', 'alarms', 'models', 'assistant']) {
    await page.locator(`[data-nav="${name}"]`).click()
    await expect(page.getByTestId('placeholder')).toBeVisible()
  }
})

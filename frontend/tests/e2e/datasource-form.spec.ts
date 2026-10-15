import { expect, test } from '@playwright/test'

// D-054: the data source form lines its inputs up and keeps the explanations out of the way until the
// pointer has rested on an input for a second.

test('inputs share one left edge and the note appears after one second of hovering', async ({
  page,
}) => {
  await page.addInitScript(() => localStorage.setItem('pdm-dev-role', 'admin'))
  await page.goto('/datasources')
  await page.getByTestId('ds-add').click()
  const lefts = await page
    .getByTestId('ds-form')
    .locator('input.st-input, select.st-select')
    .evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().left)))
  expect(lefts, JSON.stringify(lefts)).toEqual(lefts.map(() => lefts[0]))
  // no explanation is printed under the inputs
  await expect(page.getByTestId('ds-form').locator('.st-note:not(.error)')).toHaveCount(0)
  await page.getByTestId('ds-host').hover()
  await page.waitForTimeout(400)
  await expect(page.getByTestId('hint-tip')).toHaveCount(0)
  await expect(page.getByTestId('hint-tip')).toBeVisible({ timeout: 2000 })
  await expect(page.getByTestId('hint-tip')).toContainText('10.')
  await page.mouse.move(5, 5)
  await expect(page.getByTestId('hint-tip')).toHaveCount(0)
})

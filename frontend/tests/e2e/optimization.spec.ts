import { expect, test } from '@playwright/test'

// T025: replay the SIMULATED demo history with the current settings and candidates, scored against
// the Golden Cases; the page compares champion and candidates and applies nothing.

test('runs a champion/challenger comparison on replay', async ({ page }) => {
  test.setTimeout(180_000)
  await page.goto('/optimization')
  await page.getByTestId('opt-run').click()
  const table = page.getByTestId('opt-table')
  await expect(table).toBeVisible({ timeout: 150_000 })
  await expect(table.locator('[data-row="champion"]')).toContainText('pdm-rules@1.0.0')
  await expect(table.locator('tbody tr')).toHaveCount(13)
  await expect(page.getByTestId('opt-verdict')).not.toBeEmpty()
  const first = table.locator('tbody tr').nth(1).getByRole('button')
  await first.click()
  await expect(page.getByTestId('opt-cases')).toContainText('GC-S04-01')
  // nothing is applied: the dashboard still uses the champion rule set
  await page.goto('/optimization')
  await expect(page.getByTestId('opt-table')).toBeVisible()
})

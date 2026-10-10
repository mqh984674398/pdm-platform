import { expect, test } from '@playwright/test'

// T026: a replay-recommended configuration is submitted, passes the gates, is promoted by an
// administrator only, and is rolled back in one step. Runs after all other specs (it changes health).

test('promote a gated candidate as admin, then roll it back', async ({ page }) => {
  test.setTimeout(240_000)
  await page.goto('/optimization')
  await page.getByTestId('opt-run').click()
  await expect(page.getByTestId('opt-table')).toBeVisible({ timeout: 150_000 })
  await page.getByTestId('opt-propose').click()
  await page.getByTestId('opt-proposed').click()
  await expect(page).toHaveURL(/\/models/)

  const kind = page.locator('[data-kind="decision-config"]')
  const cand = kind.locator('[data-version]').first()
  await expect(cand.getByTestId('gate')).toHaveText('已通过检查')
  await expect(kind.getByTestId('champion')).toContainText('decision-config.v1')

  // engineers cannot promote
  await cand.getByTestId('decision-comment').fill('replay shows fewer missed windows')
  await cand.getByTestId('promote').click()
  await expect(cand.getByRole('status')).toContainText('管理员')

  await page.getByTestId('dev-role').selectOption('admin')
  await cand.getByTestId('decision-comment').fill('approved after review')
  await cand.getByTestId('promote').click()
  await expect(kind.getByTestId('champion')).toContainText('+OPT-')

  await kind.getByTestId('rollback-comment').fill('restore the previous configuration')
  await kind.getByTestId('rollback').click()
  await expect(kind.getByTestId('champion')).toContainText('pdm-rules@1.0.0 ·')
  await expect(kind.getByTestId('champion')).not.toContainText('+OPT-')
  await page.getByTestId('dev-role').selectOption('engineer')
})

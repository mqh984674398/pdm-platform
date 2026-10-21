import { expect, test } from '@playwright/test'

test('overview to machine map to component history', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('[data-machine]')).toHaveCount(11)
  await expect(page.getByTestId('demo-notice')).toBeVisible()

  await page.locator('[data-machine="A02"]').click()
  await expect(page).toHaveURL(/\/machine\/A02/)
  await expect(page.locator('h1')).toHaveText('2号装配机')

  const station = page.locator('[data-component="A02-BS1"]')
  await expect(station).toHaveAttribute('data-health', 'CRITICAL')
  // a component opens its history; every level has a way back to the one above
  await station.click()
  await expect(page).toHaveURL(/\/component\/A02-BS1/)
  await expect(page.locator('[data-detail="A02-BS1"]')).toBeVisible()
  await page.getByTestId('lang-switch').getByRole('radio', { name: 'EN' }).click()
  await expect(page.getByTestId('back-button')).toContainText('Assembly machine 2')
  await page.getByTestId('back-button').click()
  await expect(page).toHaveURL(/\/machine\/A02/)
  await expect(page.locator('h1')).toHaveText('Assembly machine 2')
  await page.getByTestId('back-button').click()
  await expect(page).toHaveURL(/\/$|\/\?/)
  await expect(page.locator('[data-machine]')).toHaveCount(11)
})

test('component stations are keyboard selectable', async ({ page }) => {
  await page.goto('/machine/A06')
  await page.locator('[data-component="A06-BS2"]').focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/component\/A06-BS2/)
  await expect(page.locator('[data-detail="A06-BS2"]')).toBeVisible()
})

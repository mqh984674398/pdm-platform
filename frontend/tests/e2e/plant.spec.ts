import { expect, test } from '@playwright/test'

// D-037/D-038 plant structure. It adds a machine to the shared demo server, so it runs after the
// screens that count the demo fleet (playwright.config.ts).

test('administrator builds the plant structure in drawers', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('pdm-dev-role', 'admin'))
  const sfx = Date.now().toString(36)
  await page.goto('/plant')
  await expect(page.locator('h1')).toHaveText('配置工作台')
  await page.getByTestId('add-workshop-open').click()
  const ws = page.getByTestId('add-workshop')
  await ws.getByPlaceholder('编号', { exact: true }).fill(`WS-${sfx}`)
  await ws.getByPlaceholder('中文名称').fill(`车间${sfx}`)
  await ws.getByRole('button').click()
  await page.locator(`[data-node="WS-${sfx}"]`).click()
  const pr = page.getByTestId('add-process')
  await pr.getByPlaceholder('编号', { exact: true }).fill(`P-${sfx}`)
  await pr.getByPlaceholder('中文名称').fill('总装')
  await pr.getByRole('button').click()
  await page.locator(`[data-node="P-${sfx}"]`).click()
  const mc = page.getByTestId('add-machine')
  await mc.getByPlaceholder('编号', { exact: true }).fill(`M-${sfx}`)
  await mc.getByPlaceholder('中文名称').fill('测试机台')
  await mc.getByPlaceholder('数据库设备 ID').fill('SIM-S13')
  await mc.getByRole('button').click()
  await page.locator(`[data-machine="M-${sfx}"]`).click()
  for (const n of ['1', '2']) {
    const f = page.getByTestId('add-component')
    await f.getByPlaceholder('编号', { exact: true }).fill(`M-${sfx}-BS${n}`)
    await f.getByPlaceholder('中文名称').fill(`丝杠${n}`)
    await f.getByPlaceholder('传动链编号').fill(`DC-${sfx}`)
    await f.getByRole('button').click()
    await expect(page.locator(`[data-component="M-${sfx}-BS${n}"]`)).toBeVisible()
  }
  await expect(page.getByTestId('plant-components')).toContainText('共用（2 个部件）')
  // tree nodes carry their own actions: a component node shows under its machine
  await expect(page.locator(`[data-comp-node="M-${sfx}-BS1"]`)).toBeVisible()
  await page.getByTestId('side-drawer').getByRole('button', { name: '关闭' }).click()
  await expect(page.getByTestId('side-drawer')).toHaveCount(0)
})

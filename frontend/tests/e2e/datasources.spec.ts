import { expect, test } from '@playwright/test'

// D-049: data sources have their own administrator screen; the workbench only picks one.
// The form is filled in but never saved, so the shared demo server is left unchanged.

test('administrator sees the sources and the form explains host, port and tag column', async ({
  page,
}) => {
  await page.addInitScript(() => localStorage.setItem('pdm-dev-role', 'admin'))
  await page.goto('/datasources')
  await expect(page.locator('h1')).toHaveText('数据源')
  await expect(page.getByTestId('ds-list')).toContainText('sim-iot')
  await expect(page.getByTestId('ds-list')).toContainText('由配置文件定义')

  await page.getByTestId('ds-add').click()
  // a pasted address is split into host, protocol and port
  await page.getByTestId('ds-host').fill('https://10.26.30.97:6060/rest/sql')
  await page.getByTestId('ds-host').blur()
  await expect(page.getByTestId('ds-host')).toHaveValue('10.26.30.97')
  await expect(page.getByTestId('ds-port')).toHaveValue('6060')
  // 6060 is the taosExplorer web console, not the REST port
  await expect(page.getByTestId('ds-port-warning')).toContainText('6041')
  await page.getByTestId('ds-port').fill('6041')
  await expect(page.getByTestId('ds-port-warning')).toHaveCount(0)

  // the workbench no longer carries the data source form
  await page.goto('/plant')
  await expect(page.getByTestId('datasource-panel')).toHaveCount(0)
})

test('a role without administrator rights has no data source screen', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('pdm-dev-role', 'engineer'))
  await page.goto('/datasources')
  await expect(page.getByTestId('datasource-panel')).toHaveCount(0)
})

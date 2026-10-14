import { expect, test } from '@playwright/test'

// D-044..D-047: an administrator drafts, validates, publishes and activates a prediction
// configuration from the plant structure screen. It changes the decision engine of one demo
// component, so it runs with the plant test, after the screens that count the demo fleet.

const ADMIN = { 'x-pdm-role': 'admin', 'x-pdm-user': 'e2e-admin' }

test('administrator takes a recommended configuration through validate, publish and activate', async ({
  page,
}) => {
  await page.addInitScript(() => localStorage.setItem('pdm-dev-role', 'admin'))
  await page.goto('/plant')
  // the machine's drawer lists its components; "Configure" closes it and opens the workflow
  await page.locator('[data-machine]').first().click()
  await page.locator('[data-component]').first().getByTestId('component-configure').click()
  await expect(page.getByTestId('side-drawer')).toHaveCount(0)
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

test('step 2 shows the mapped signal, edits its parameters and previews the real data', async ({
  page,
}) => {
  await page.addInitScript(() => localStorage.setItem('pdm-dev-role', 'admin'))
  // a machine on the device of the demo bench signal, so there is a mapped signal to show
  const cfg = await (await page.request.get('/api/signal-config', { headers: ADMIN })).json()
  const device = cfg.content.mappings.find(
    (m: { signal_id: string }) => m.signal_id === 'BENCH.torque',
  ).device_id
  const mid = `WB-${Date.now().toString(36)}`
  const node = (id: string, parent: string | null, level: string) =>
    page.request.put(`/api/plant-nodes/${id}`, {
      headers: ADMIN,
      data: { node_id: id, parent_id: parent, level, name: { zh: id, en: id }, sort: 0 },
    })
  expect((await node(`${mid}-W`, null, 'WORKSHOP')).status()).toBe(200)
  expect((await node(`${mid}-P`, `${mid}-W`, 'PROCESS')).status()).toBe(200)
  const made = await page.request.post('/api/plant-machines', {
    headers: ADMIN,
    data: {
      machine_id: mid,
      process_id: `${mid}-P`,
      name: { zh: '工作台测试机', en: 'Workbench test' },
      device_id: device,
    },
  })
  expect(made.status(), await made.text()).toBe(201)
  const comp = await page.request.put(`/api/plant-machines/${mid}/components/${mid}-BS1`, {
    headers: ADMIN,
    data: { component_id: `${mid}-BS1`, type: 'BALL_SCREW', name: { zh: '丝杠', en: 'Screw' } },
  })
  expect(comp.status(), await comp.text()).toBe(200)
  await page.goto('/plant')
  // the component node in the tree opens its configuration directly
  await page.locator(`[data-comp-node="${mid}-BS1"]`).click()
  const wb = page.getByTestId('config-workbench')
  await wb.getByTestId('wb-start').click()
  const row = wb.locator('[data-signal="BENCH.torque"]')
  await expect(row).toBeVisible()
  await row.getByRole('textbox').first().fill('N*m')
  await row.getByRole('button', { name: '保存' }).click()
  await expect(page.getByTestId('wb-message')).toContainText('信号参数已保存')
  await wb.locator('[data-signal="BENCH.torque"]').getByTestId('wb-preview').click()
  await expect(wb.getByTestId('wb-preview-box')).toContainText('最近一小时')
  // a component without recorded data cannot pass validation, and the screen says so
  await wb.getByTestId('wb-validate').click()
  await expect(page.getByTestId('wb-message')).toContainText('验证未通过')
})

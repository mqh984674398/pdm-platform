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
  await page.locator('[data-machine="A01"]').click() // a demo machine that has components
  await page.locator('[data-component]').first().getByTestId('component-configure').click()
  await expect(page.getByTestId('side-drawer')).toHaveCount(0)
  const wb = page.getByTestId('config-workbench')
  await expect(wb).toBeVisible()
  await wb.getByTestId('wb-start').click()
  await expect(page.getByTestId('wb-pipeline')).toContainText('engineering_rules')
  await wb.getByTestId('wb-compile').click()
  await expect(page.getByTestId('wb-pipeline')).toContainText('将生效')
  // the check says what it covers and lists what the component still lacks to run on real data
  await expect(wb.getByTestId('wb-runtime')).toContainText('当前运行条件')
  await wb.getByTestId('wb-validate').click()
  await expect(page.getByTestId('wb-checks')).toBeVisible()
  // all four checks are listed with what they test, and replay names its prerequisites
  await expect(page.locator('[data-testid="wb-checks"] [data-check]')).toHaveCount(4)
  await expect(page.locator('[data-check="replay"]')).toContainText('历史回放')
  await expect(page.getByTestId('replay-prereq')).toContainText('回放需要')
  await expect(page.getByTestId('wb-message')).toContainText('验证通过')
  await wb.getByTestId('wb-comment').fill('e2e release')
  await wb.getByTestId('wb-publish').click()
  await expect(page.getByTestId('wb-message')).toContainText('已发布')
  await wb.getByTestId('wb-activate').click()
  await expect(page.getByTestId('wb-versions')).toContainText('启用中')
})

test('step 2 binds the signal to the component and leaves its parameters to the signal page', async ({
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
  // bind the component to a source and device, read the proposed signals and map one of them
  await wb.getByTestId('map-suggest').click()
  const suggested = wb.getByTestId('map-suggestions').locator('[data-suggest="BENCH.torque"]')
  await suggested.getByRole('checkbox').check()
  await wb.getByTestId('map-save').click()
  await expect(wb.getByTestId('map-message')).toContainText('信号映射已保存')
  await wb.getByTestId('wb-start').click()
  const row = wb.locator('[data-signal="BENCH.torque"]')
  await expect(row).toBeVisible()
  // D-053: unit, sampling and range are shown, not edited here; the Signal configuration page owns them
  await expect(row.getByRole('textbox')).toHaveCount(0)
  await expect(row.getByTestId('wb-edit-signal')).toHaveAttribute(
    'href',
    /\/signals\?signal=BENCH\.torque/,
  )
  // a component without recorded data cannot pass validation, and the screen says so
  await wb.getByTestId('wb-validate').click()
  await expect(page.getByTestId('wb-message')).toContainText('验证未通过')
  // the failing step is named with what to do about it
  await expect(page.locator('[data-fix]').first()).toBeVisible()
})

test('a new component goes from the plant tree to an active prediction configuration', async ({
  page,
}) => {
  await page.addInitScript(() => localStorage.setItem('pdm-dev-role', 'admin'))
  const sfx = Date.now().toString(36)
  const [ws, pr, mc] = [`NW-${sfx}`, `NP-${sfx}`, `NM-${sfx}`]
  const cid = `${mc}-BS1`
  await page.goto('/plant')
  // 1. structure: workshop → process → machine bound to a demo device → component, all in drawers
  await page.getByTestId('add-workshop-open').click()
  const addWs = page.getByTestId('add-workshop')
  await addWs.getByPlaceholder('编号', { exact: true }).fill(ws)
  await addWs.getByPlaceholder('中文名称').fill('新车间')
  await addWs.getByRole('button').click()
  await page.locator(`[data-node="${ws}"]`).click()
  const addPr = page.getByTestId('add-process')
  await addPr.getByPlaceholder('编号', { exact: true }).fill(pr)
  await addPr.getByPlaceholder('中文名称').fill('新工序')
  await addPr.getByRole('button').click()
  await page.locator(`[data-node="${pr}"]`).click()
  const addMc = page.getByTestId('add-machine')
  await addMc.getByPlaceholder('编号', { exact: true }).fill(mc)
  await addMc.getByPlaceholder('中文名称').fill('新机台')
  await addMc.getByPlaceholder('数据库设备 ID').fill('SIM-S03')
  await addMc.getByRole('button').click()
  await page.locator(`[data-machine="${mc}"]`).click()
  const addC = page.getByTestId('add-component')
  await addC.getByPlaceholder('编号', { exact: true }).fill(cid)
  await addC.getByPlaceholder('中文名称').fill('新丝杠')
  await addC.getByRole('button').click()
  await page.getByTestId('side-drawer').getByRole('button', { name: '关闭' }).click()
  await page.locator(`[data-comp-node="${cid}"]`).click()
  const wb = page.getByTestId('config-workbench')
  await expect(wb).toBeVisible()
  await expect(wb.getByTestId('ready-install')).toContainText('✗')

  // 2. data: source and device are preset from the machine; map the screw's two signals
  await wb.getByTestId('map-source').selectOption('sim-fleet')
  await expect(wb.getByTestId('map-device')).toHaveValue('SIM-S03')
  await wb.getByTestId('map-suggest').click()
  for (const sig of ['A03-BS1.speed', 'A03-BS1.torque'])
    await wb.locator(`[data-suggest="${sig}"]`).getByRole('checkbox').check()
  await wb.getByTestId('map-save').click()
  await expect(wb.getByTestId('map-message')).toContainText('信号映射已保存')
  await expect(wb.getByTestId('ready-signals')).toContainText('2 个')

  // 3. installation date, features from the data source, verified healthy reference
  await wb.getByTestId('install-date').fill('2026-04-01')
  await wb.getByTestId('install-save').click()
  await expect(wb.getByTestId('ready-install')).toContainText('2026-04-01')
  await wb.getByTestId('run-pipeline').click()
  await expect(wb.getByTestId('pipeline-result')).toContainText('新增')
  await expect(wb.getByTestId('ready-features')).toContainText('✓')
  await wb.getByTestId('verify-comment').fill('e2e healthy period')
  await wb.getByTestId('verify-submit').click()
  await expect(wb.getByTestId('ready-reference')).toContainText('✓')

  // 4. recommended draft → validate (data, compile, replay, simulation) → publish → activate
  await wb.getByTestId('wb-start').click()
  await wb.getByTestId('wb-validate').click()
  await expect(page.getByTestId('wb-message')).toContainText('验证通过')
  await expect(page.getByTestId('wb-checks').locator('li.ok')).toHaveCount(4)
  await wb.getByTestId('wb-comment').fill('first release')
  await wb.getByTestId('wb-publish').click()
  await wb.getByTestId('wb-activate').click()
  await expect(page.getByTestId('wb-versions')).toContainText('启用中')
})

test('a component with an installation record can be deleted after the dialog names what goes with it', async ({
  page,
}) => {
  await page.addInitScript(() => localStorage.setItem('pdm-dev-role', 'admin'))
  const sfx = Date.now().toString(36)
  const [ws, pr, mc] = [`DW-${sfx}`, `DP-${sfx}`, `DM-${sfx}`]
  const cid = `${mc}-BS1`
  const put = (path: string, data: unknown) =>
    page.request.put(path, { headers: ADMIN, data }).then((r) => r.status())
  const node = (id: string, parent: string | null, level: string) =>
    put(`/api/plant-nodes/${id}`, {
      node_id: id,
      parent_id: parent,
      level,
      name: { zh: id, en: id },
      sort: 0,
    })
  expect(await node(ws, null, 'WORKSHOP')).toBe(200)
  expect(await node(pr, ws, 'PROCESS')).toBe(200)
  const made = await page.request.post('/api/plant-machines', {
    headers: ADMIN,
    data: { machine_id: mc, process_id: pr, name: { zh: '删除测试机', en: 'Delete test' } },
  })
  expect(made.status(), await made.text()).toBe(201)
  expect(
    await put(`/api/plant-machines/${mc}/components/${cid}`, {
      component_id: cid,
      type: 'BALL_SCREW',
      name: { zh: '丝杠', en: 'Screw' },
    }),
  ).toBe(200)
  const inst = await page.request.post(`/api/components/${cid}/lifecycles`, {
    headers: { ...ADMIN, 'x-pdm-role': 'engineer' },
    data: { installed_at: '2026-10-01T00:00:00Z' },
  })
  expect(inst.status(), await inst.text()).toBe(201)
  await page.goto('/plant')
  const dialogs: string[] = []
  page.on('dialog', (d) => {
    dialogs.push(d.message())
    void d.accept()
  })
  await page
    .locator(`[data-comp-node="${cid}"]`)
    .locator('xpath=ancestor::div[contains(@class,"line")][1]')
    .getByRole('button', { name: '删除' })
    .click()
  await expect(page.getByTestId('plant-message')).toContainText('已删除')
  expect(dialogs[0]).toContain('安装记录')
  await expect(page.locator(`[data-comp-node="${cid}"]`)).toHaveCount(0)
})

test('the workbench lists steps 1 and 2 in order before any draft exists', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('pdm-dev-role', 'admin'))
  const sfx = Date.now().toString(36)
  const [ws, pr, mc] = [`OW-${sfx}`, `OP-${sfx}`, `OM-${sfx}`]
  const cid = `${mc}-BS1`
  const node = (id: string, parent: string | null, level: string) =>
    page.request.put(`/api/plant-nodes/${id}`, {
      headers: ADMIN,
      data: { node_id: id, parent_id: parent, level, name: { zh: id, en: id }, sort: 0 },
    })
  expect((await node(ws, null, 'WORKSHOP')).status()).toBe(200)
  expect((await node(pr, ws, 'PROCESS')).status()).toBe(200)
  expect(
    (
      await page.request.post('/api/plant-machines', {
        headers: ADMIN,
        data: { machine_id: mc, process_id: pr, name: { zh: '顺序测试机', en: 'Order test' } },
      })
    ).status(),
  ).toBe(201)
  expect(
    (
      await page.request.put(`/api/plant-machines/${mc}/components/${cid}`, {
        headers: ADMIN,
        data: { component_id: cid, type: 'BALL_SCREW', name: { zh: '丝杠', en: 'Screw' } },
      })
    ).status(),
  ).toBe(200)
  await page.goto('/plant')
  await page.locator(`[data-comp-node="${cid}"]`).click()
  const wb = page.getByTestId('config-workbench')
  const heads = wb.locator('h3')
  await expect(heads.nth(0)).toContainText('1 ·')
  await expect(heads.nth(1)).toContainText('2 ·')
  // steps 3-7 need a draft and the screen says how to get one
  await expect(wb.getByText('步骤 3–7')).toBeVisible()
  await wb.getByTestId('wb-start').click()
  await expect(wb.locator('h3', { hasText: '3 ·' })).toBeVisible()
  const numbers = await heads.allTextContents()
  const steps = numbers.map((x) => x.match(/^(\d) ·/)?.[1]).filter(Boolean)
  expect(steps).toEqual(['1', '2', '3', '4', '5', '6', '7'])
})

test('the algorithm models page lists the library, deep adapters and plugins', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('pdm-dev-role', 'admin'))
  await page.goto('/algorithms')
  await expect(page.getByTestId('alg-table')).toContainText('工程规则')
  await page.locator('[data-alg="engineering-rules"]').getByRole('button').click()
  await expect(page.getByTestId('alg-deep')).toContainText('LSTM')
  await expect(page.getByTestId('alg-no-plugins')).toBeVisible()
  await page.getByTestId('alg-cat-DL').click()
  await expect(page.locator('[data-alg="engineering-rules"]')).toHaveCount(0)
})

import { expect, test } from '@playwright/test'

// D-054: the overview has one sub-page per workshop; administrators reorder machines by a 500 ms long
// press and drag, and can set a background picture. Runs in the project that changes the demo plant.

const ADMIN = { 'x-pdm-role': 'admin', 'x-pdm-user': 'e2e-admin' }
const PNG =
  'iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAEElEQVR4nGM4YWAARwzEcQDqwxKBeqG2lgAAAABJRU5ErkJggg=='

async function makeWorkshop(page: import('@playwright/test').Page, id: string, name: string) {
  const put = (nodeId: string, parent: string | null, level: string, label: string) =>
    page.request.put(`/api/plant-nodes/${nodeId}`, {
      headers: ADMIN,
      data: { node_id: nodeId, parent_id: parent, level, name: { zh: label, en: label }, sort: 0 },
    })
  expect((await put(`${id}-W`, null, 'WORKSHOP', name)).status()).toBe(200)
  expect((await put(`${id}-P`, `${id}-W`, 'PROCESS', `${name}工序`)).status()).toBe(200)
  for (const m of ['A', 'B', 'C']) {
    const r = await page.request.post('/api/plant-machines', {
      headers: ADMIN,
      data: {
        machine_id: `${id}-${m}`,
        process_id: `${id}-P`,
        name: { zh: `${id}机${m}`, en: `${id} ${m}` },
      },
    })
    expect(r.status(), await r.text()).toBe(201)
  }
}

const ids = (page: import('@playwright/test').Page) =>
  page
    .locator('[data-machine]')
    .evaluateAll((els) => els.map((e) => e.getAttribute('data-machine')))

test('machines are grouped by workshop, reordered by long press and drag, and given a background', async ({
  page,
}) => {
  const id = `OV${Date.now().toString(36).toUpperCase()}`
  await page.addInitScript(() => localStorage.setItem('pdm-dev-role', 'admin'))
  await makeWorkshop(page, id, '总装车间')
  await page.goto('/')
  await page.locator(`[data-workshop="${id}-W"]`).click()
  await expect(page.locator('[data-machine]')).toHaveCount(3)
  expect(await ids(page)).toEqual([`${id}-A`, `${id}-B`, `${id}-C`])

  // a short press is an ordinary click: the machine opens
  await page.locator(`[data-machine="${id}-A"]`).click()
  await expect(page).toHaveURL(new RegExp(`/machine/${id}-A`))
  await expect(page.getByTestId('back-button')).toBeVisible()
  await page.getByTestId('back-button').click()
  await expect(page.locator(`[data-workshop="${id}-W"]`)).toHaveAttribute('aria-selected', 'true')

  await expect(page.locator('[data-machine]')).toHaveCount(3)
  // hold 500 ms, then drag the first machine onto the third
  const box = async (mid: string) => (await page.locator(`[data-machine="${mid}"]`).boundingBox())!
  await page.waitForTimeout(400) // let the tiles settle
  const a = await box(`${id}-A`)
  const c = await box(`${id}-C`)
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2)
  await page.mouse.down()
  await page.waitForTimeout(650)
  await page.mouse.move(c.x + c.width / 2, c.y + c.height / 2, { steps: 12 })
  await page.mouse.up()
  await expect.poll(() => ids(page)).toEqual([`${id}-B`, `${id}-C`, `${id}-A`])
  // the drag did not open the machine, and the order is stored
  await expect(page).not.toHaveURL(/\/machine\//)
  await page.reload()
  await page.locator(`[data-workshop="${id}-W"]`).click()
  expect(await ids(page)).toEqual([`${id}-B`, `${id}-C`, `${id}-A`])

  // background picture: stored, shown behind the component statuses
  await page.locator(`[data-machine="${id}-B"]`).hover()
  await page
    .locator(`[data-machine="${id}-B"]`)
    .getByTestId('tile-background-file')
    .setInputFiles({ name: 'bg.png', mimeType: 'image/png', buffer: Buffer.from(PNG, 'base64') })
  await expect(page.getByRole('alert')).toHaveCount(0)
  await expect(page.locator(`[data-machine="${id}-B"]`)).toHaveClass(/withBg/)
  const layout = await (await page.request.get('/api/machine-layout', { headers: ADMIN })).json()
  expect(layout.find((m: { machine_id: string }) => m.machine_id === `${id}-B`).background).toMatch(
    /^data:image\/jpeg;base64,/,
  )
})

test('a viewer sees the workshop pages but cannot drag or set backgrounds', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('pdm-dev-role', 'viewer'))
  await page.goto('/')
  await expect(page.getByTestId('workshop-tab').first()).toBeVisible()
  await expect(page.getByTestId('overview-admin-hint')).toHaveCount(0)
  await expect(page.getByTestId('tile-background')).toHaveCount(0)
})

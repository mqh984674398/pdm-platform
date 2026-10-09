import { expect, test, type Page, type Route } from '@playwright/test'

// T019. The analysis test runs against the demo backend's SIMULATED bench signal (1,100,000 points at
// 1 s). The baseline and maintenance tests mock the monitoring API, since the demo database has no
// pipeline output until T020.

test('analysis chart renders 1.1M points downsampled and loads detail on zoom', async ({
  page,
}) => {
  const t0 = Date.now()
  await page.goto('/analysis?signal=BENCH.torque')
  const note = page.getByTestId('downsample-note')
  await expect(note).toHaveAttribute('data-downsampled', 'true')
  await expect(note).toContainText('1,100,000')
  const chart = page.getByTestId('ts-chart')
  await expect(chart).not.toHaveAttribute('data-points', '0')
  const firstRender = Date.now() - t0
  const overviewPoints = Number(await chart.getAttribute('data-points'))
  expect(overviewPoints).toBeLessThanOrEqual(2000)

  const box = (await chart.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 3)
  const t1 = Date.now()
  for (let i = 0; i < 12; i++) await page.mouse.wheel(0, -400)
  // the zoomed range is fetched again: fewer source points behind the visible part
  await expect(note).not.toContainText('1,100,000', { timeout: 10_000 })
  const zoomed = Date.now() - t1
  await expect(page.getByTestId('chart-loading')).toHaveCount(0)

  console.log(
    `PERF analysis: first render ${firstRender} ms (incl. page load), zoom+detail ${zoomed} ms, ` +
      `overview ${overviewPoints} points`,
  )
  expect(firstRender).toBeLessThan(5000)
  expect(zoomed).toBeLessThan(5000)

  const download = page.waitForEvent('download')
  await page.getByTestId('export-csv').click()
  expect((await download).suggestedFilename()).toContain('_SIMULATED')
})

const H = 3600_000
const T0 = Date.parse('2026-02-01T00:00:00Z')
const iso = (ms: number) => new Date(ms).toISOString()
const json = (body: unknown) => (route: Route) =>
  route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })

async function mockMonitoring(page: Page) {
  await page.route(
    '**/api/machines',
    json([{ machine_id: 'M1', name: { zh: '模拟机', en: 'Sim machine' } }]),
  )
  await page.route(
    '**/api/machines/M1/components',
    json([{ component_id: 'M1-BS1', name: { zh: '滚珠丝杠1', en: 'Ball screw 1' } }]),
  )
  const window = (i: number) => ({ start: iso(T0 + i * H), end: iso(T0 + (i + 1) * H) })
  await page.route(
    '**/api/components/M1-BS1/baselines',
    json([
      {
        baseline_id: 'BL-1',
        kind: 'VERIFIED_HEALTHY',
        component_id: 'M1-BS1',
        lifecycle_id: 'LC-1',
        feature_ref: 'ball_screw@1.1.0',
        window: { start: iso(T0), end: iso(T0 + 24 * H) },
        stats: { torque_residual: { mean: 0, std: 1, count: 24 } },
        regime_stats: {},
        verified_by: 'demo-engineer',
        is_simulated: true,
      },
    ]),
  )
  await page.route('**/api/components/M1-BS1/degradation*', (route) =>
    json({
      component_id: 'M1-BS1',
      feature: 'torque_residual',
      segments: [
        {
          lifecycle_id: 'LC-1',
          reference_baseline_id: 'BL-1',
          points: Array.from({ length: 48 }, (_, i) => ({
            window: window(i),
            value: i < 24 ? 0 : (i - 24) * 0.3,
            adaptive_mean: i < 24 ? 0 : (i - 24) * 0.1,
          })),
        },
      ],
      steps: [{ at: iso(T0 + 30 * H), type: 'LUBRICATION' }],
      is_simulated: true,
    })(route),
  )
  await page.route('**/api/alarms*', json([]))
  await page.route(
    '**/api/components/M1-BS1/maintenance-events',
    json([
      {
        event_id: 'ME-1',
        component_id: 'M1-BS1',
        lifecycle_id: 'LC-1',
        type: 'LUBRICATION',
        performed_at: iso(T0 + 30 * H),
        notes: '',
        is_simulated: true,
      },
    ]),
  )
  await page.route(
    '**/api/maintenance-workflows*',
    json([
      {
        workflow_id: 'WF-1',
        event_id: 'ME-1',
        transitions: [
          { to_state: 'MAINTENANCE_EVENT', at: iso(T0 + 30 * H), by: 'demo-engineer', comment: '' },
          {
            to_state: 'STABILIZATION',
            at: iso(T0 + 30 * H),
            by: 'system:maintenance-impact',
            comment: '',
          },
        ],
      },
    ]),
  )
}

test('baseline comparison shows the verified reference and adaptive baseline', async ({ page }) => {
  await mockMonitoring(page)
  await page.goto('/baselines')
  await expect(page.getByTestId('reference-list')).toContainText('demo-engineer')
  await expect(page.getByTestId('ts-chart')).toHaveAttribute('data-points', /^(9[0-9]|1\d\d)$/)
  await expect(page.getByTestId('no-reference')).toHaveCount(0)
})

test('maintenance timeline shows the event and its workflow steps', async ({ page }) => {
  await mockMonitoring(page)
  await page.goto('/maintenance')
  const timeline = page.getByTestId('maintenance-timeline')
  await expect(timeline).toContainText('润滑')
  await expect(page.getByTestId('workflow-ME-1')).toContainText('稳定期')
})

import { expect, test } from '@playwright/test'

// T020: the dashboard reads health computed by the backend from the SIMULATED demo fleet
// (simulated adapter -> features -> rules -> alarms). Every machine replays one G3 scenario.

test('every demo machine shows computed health with the simulated badge', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('[data-machine]')).toHaveCount(11)
  await expect(page.getByTestId('demo-notice')).toContainText('模拟')
  for (const [machine, scenario] of [
    ['A01', 'S01'], // healthy
    ['A02', 'S04'], // torque drift
    ['A03', 'S03'], // long-term aging against the frozen reference
    ['A05', 'S12'], // replacement
    ['A09', 'S09'], // lubrication improvement
    ['A10', 'S10'], // lubrication deterioration
    ['A11', 'S11'], // partial repair
  ]) {
    await expect(page.locator(`[data-machine="${machine}"]`)).toContainText(`SIM-${scenario}`)
  }
})

test('component history shows the evidence behind its health', async ({ page }) => {
  await page.goto('/component/A02-BS1')
  const detail = page.locator('[data-detail="A02-BS1"]')
  await expect(detail.locator('[data-health]').first()).toHaveAttribute('data-health', 'CRITICAL')
  await expect(page.getByTestId('health-reason')).toContainText('ST-TORQUE')
  await expect(detail.locator('[data-trend="ST-TORQUE"]')).toBeVisible()
  const trail = page.getByTestId('evidence-trail')
  await expect(trail.locator('[data-source="STATISTIC"]').first()).toContainText('ST-TORQUE')
  await expect(trail).toContainText('demo-engineer (SIMULATED)')
  await expect(trail.locator('[data-source="RULE"]')).not.toHaveCount(0)
})

test('maintenance outcome review is visible for lubrication deterioration', async ({ page }) => {
  await page.goto('/maintenance?c=A10-BS1')
  const wf = page.getByTestId('workflow-A10-SIM-ME-0001')
  await expect(wf).toContainText('需复核')
  await page.goto('/component/A10-BS1')
  await expect(
    page.getByTestId('evidence-trail').locator('[data-source="MAINTENANCE"]'),
  ).toContainText('DETERIORATED')
})

test('an alarm is acknowledged and resolved with the outcome recorded', async ({ page }) => {
  await page.goto('/alarms?c=A04-CY1')
  await page.getByTestId('lang-switch').getByRole('radio', { name: 'EN' }).click()
  const card = page.locator('[data-alarm][data-status="RAISED"]').first()
  const id = await card.getAttribute('data-alarm')
  const alarm = page.locator(`[data-alarm="${id}"]`)
  await alarm.getByTestId('alarm-ack').click()
  await expect(alarm).toHaveAttribute('data-status', 'ACKNOWLEDGED')

  await alarm.getByTestId('alarm-resolve').click()
  await expect(alarm.getByRole('alert')).toContainText('Enter the outcome')
  await alarm.getByTestId('alarm-comment').fill('Replaced the cylinder seal; re-check tomorrow')
  await alarm.getByTestId('alarm-resolve').click()
  await expect(alarm).toHaveCount(0) // resolved alarms leave the open list

  await page.getByRole('radio', { name: 'All' }).click()
  await expect(alarm).toHaveAttribute('data-status', 'RESOLVED')
  await expect(alarm.getByTestId('resolution')).toHaveText(
    'Replaced the cylinder seal; re-check tomorrow',
  )

  const resp = await page.request.get(`/api/alarms?component_id=A04-CY1&status=RESOLVED`, {
    headers: { 'X-PDM-User': 'e2e', 'X-PDM-Role': 'viewer' },
  })
  const resolved = (await resp.json()) as { alarm_id: string; resolved_by: string }[]
  expect(resolved.find((a) => a.alarm_id === id)?.resolved_by).toBe('ui-engineer')
})

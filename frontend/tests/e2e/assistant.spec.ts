import { expect, test } from '@playwright/test'

// T027: configure the local (fake) Ollama, refuse a cloud-routed model, approve a document, and ask
// the assistant about a SIMULATED component. The answer cites the document and keeps the rules' health.

test('local assistant answers with citations and the rules health state', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('pdm-dev-role', 'admin'))
  await page.goto('/assistant')
  await page.getByTestId('llm-endpoint').fill('http://127.0.0.1:11435')
  await page.getByTestId('llm-save').click()
  await expect(page.getByTestId('llm-health')).toContainText('已连接')

  await page.getByTestId('llm-enabled').check()
  await page.getByTestId('llm-chat-model').selectOption('gpt-oss:120b-cloud')
  await page.getByTestId('llm-save').click()
  await expect(page.getByTestId('llm-msg')).toContainText('云端')

  await page.getByTestId('llm-chat-model').selectOption('qwen2.5:7b-instruct')
  await page.getByTestId('llm-embed-model').selectOption('nomic-embed-text:latest')
  await page.getByTestId('llm-save').click()
  await expect(page.getByTestId('llm-msg')).toHaveText('设置已保存。')

  await page.getByTestId('doc-title').fill('滚珠丝杠润滑手册')
  await page
    .getByTestId('doc-text')
    .fill('巡航扭矩缓慢升高时，检查润滑脂并重新润滑丝杠。润滑后扭矩仍高，检查预紧。')
  await page.getByTestId('doc-add').click()
  const row = page.locator('[data-testid="documents"] tbody tr', { hasText: '滚珠丝杠润滑手册' })
  await row.getByTestId('doc-approve').click()
  await expect(row).toContainText('已批准')

  await page.getByTestId('ask-component').selectOption('A02-BS1')
  await page.getByTestId('ask-question').fill('为什么扭矩偏高，应该检查什么？')
  await page.getByTestId('ask-go').click()
  const answer = page.getByTestId('answer')
  await expect(answer).toBeVisible()
  await expect(answer.locator('[data-health]').first()).toHaveAttribute('data-health', 'CRITICAL')
  await expect(page.getByTestId('answer-text')).toContainText('CRITICAL')
  await expect(page.getByTestId('citations')).toContainText('滚珠丝杠润滑手册')
  await page.getByTestId('rate-good').click()
  await expect(page.getByTestId('rated')).toContainText('复核')
})

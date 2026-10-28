import { test, expect } from '@playwright/test'
import path from 'node:path'
import { mkdir } from 'node:fs/promises'

const native = process.env.CATALOG_BROWSER_NATIVE ? JSON.parse(process.env.CATALOG_BROWSER_NATIVE) : null
test.use({ trace: 'off' })

class AccountChoice {
  constructor(page) { this.page = page }
  async open() {
    await this.page.route('**/api/account/subscription', async route => {
      const response = await route.fetch({ url: `${native.url}/api/account/subscription`, headers: { Authorization: `Bearer ${native.token}` } })
      await route.fulfill({ response })
    })
    await this.page.route('**/generate/', async route => {
      const response = await route.fetch({ url: `${native.url}/generate/`, headers: { Authorization: `Bearer ${native.token}` } })
      await route.fulfill({ response })
    })
    // Synthetic preload only; this fetch uses the real JWT/API/native database.
    // Main-process token ownership/DTO filtering have separate Node tests.
    await this.page.route('**/src/main.jsx*', route => route.fulfill({ contentType: 'application/javascript', body: `
      import '/tests/catalog/fixtures/current-plan.jsx';
    ` }))
    await this.page.goto('/')
  }
}

test('current-plan renderer over real JWT and native PostgreSQL', async ({ page }) => {
  test.skip(!native, 'Requires disposable subscription native runner')
  await page.setViewportSize({ width: 1366, height: 768 })
  await new AccountChoice(page).open()
  await expect(page.getByText('Current plan: Free', { exact: true })).toBeVisible()
  await expect(page.getByText('10.0 Auto minutes available', { exact: true })).toBeVisible()
  await expect(page.getByText('Checkout coming soon. Compare plans on our website.')).toBeVisible()
  const card = page.getByRole('heading', { name: 'Buy Credits', exact: true }).locator('..')
  const cardBox = await card.boundingBox()
  const titleBox = await page.getByRole('heading', { name: 'Buy Credits', exact: true }).boundingBox()
  expect(titleBox.y).toBeGreaterThanOrEqual(cardBox.y)
  expect(await page.evaluate(() => document.querySelector('[aria-label="Intervucopilot startup session choices"]').clientHeight)).toBe(560)
  await page.getByRole('button', { name: 'Upgrade', exact: true }).click()
  await expect.poll(() => page.evaluate(() => window.upgradeCalls)).toBe(1)
  // Browser HTTP -> actual JWT -> reviewed native pool -> actual planner ->
  // deterministic provider -> committed transcript. Replay performs no dispatch.
  const answer = await page.evaluate(async body => {
    const send = async () => {
      const response = await fetch('/generate/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      return { status: response.status, data: await response.json() }
    }
    return [await send(), await send()]
  }, native.manual)
  expect(answer.map(x => x.status)).toEqual([200, 200])
  expect(answer[0].data.answer).toContain('Dependency injection')
  expect(answer[1].data.answer).toBe(answer[0].data.answer)
  const directory = path.resolve('../docs/assets/subscriptions')
  await mkdir(directory, { recursive: true })
  await page.screenshot({ path: path.join(directory, 'c132-current-plan-desktop.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: 'Upgrade', exact: true }).scrollIntoViewIfNeeded()
  await expect(page.getByText('Current plan: Free', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  await page.screenshot({ path: path.join(directory, 'c132-current-plan-mobile.png'), fullPage: true })
  await page.evaluate(() => window.switchAccount())
  await expect(page.getByText('Current plan temporarily unavailable', { exact: true })).toBeVisible()
  await expect(page.getByText('Current plan: Free', { exact: true })).toHaveCount(0)
})

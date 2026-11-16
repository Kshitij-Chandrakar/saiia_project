import { test, expect } from '@playwright/test'
import path from 'node:path'

test.beforeEach(async ({ page }) => {
  await page.route('**/*', route => route.request().url().startsWith('http://127.0.0.1:5396') ? route.continue() : route.abort())
  await page.route('**/api/privacy/content/*', route => {
    const action = route.request().url().split('/').at(-1)
    return route.fulfill({ json: { state: action === 'status' ? 'ready' : 'pending', expires_at: new Date(Date.now()+86400000).toISOString() } })
  })
})

test('normal settings export remains unavailable', async ({ page }) => {
  await page.goto('/auth/settings')
  await expect(page.getByRole('button', { name: 'Request account export' })).toBeDisabled()
})

test('privacy center discloses pending acceptance and device limits', async ({ page }) => {
  await page.goto('/auth/settings?disabled')
  await expect(page.getByRole('heading', { name: 'Your privacy choices' })).toBeVisible()
  await expect(page.getByText('Some controls are still being verified.', { exact: false })).toBeVisible()
  await expect(page.getByText('Already downloaded export bytes cannot be recalled.', { exact: false })).toBeVisible()
  for (const [name,width,height] of [['desktop',1440,1000],['mobile',390,844]]) {
    await page.setViewportSize({width,height})
    if (process.env.C15_EXPORT_CAPTURE_DIR) await page.screenshot({path:path.join(process.env.C15_EXPORT_CAPTURE_DIR,`${name}-privacy-center.png`),fullPage:true})
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
})

test('reload recovers only the current account export receipt', async ({ page }) => {
  const id='20000000-0000-4000-8000-000000000001'
  await page.goto('/auth/export-fixture')
  await page.evaluate(value => sessionStorage.setItem('intervucopilot.export-request.10000000-0000-4000-8000-000000000001',value),id)
  await page.reload()
  await page.getByRole('button',{name:'Check export request status'}).click()
  await expect(page.getByText('Export status: ready.',{exact:false})).toBeVisible()
})

test('export confirmation, focus restoration and duplicate click prevention', async ({ page }) => {
  let confirms = 0
  await page.route('**/api/privacy/content/confirm', route => { confirms++; return route.fulfill({ json: { state: 'requested' } }) })
  await page.goto('/auth/export-fixture')
  await page.getByRole('button', { name: 'Request account export' }).click()
  const dialog = page.getByRole('dialog')
  await expect(page.getByRole('heading', { name: 'Confirm your account export' })).toBeFocused()
  await expect(page.getByRole('button', { name: 'Create private export' })).toBeDisabled()
  await page.getByLabel('Verify your password').fill('synthetic-only')
  await page.getByRole('button', { name: 'Verify identity' }).click()
  await page.getByLabel('Type export to confirm').fill('Export')
  await expect(page.getByRole('button', { name: 'Create private export' })).toBeDisabled()
  await page.getByLabel('Type export to confirm').fill('export')
  await page.getByRole('button', { name: 'Create private export' }).evaluate(button => { button.click(); button.click() })
  await expect(dialog).not.toBeVisible()
  expect(confirms).toBe(1)
  await expect(page.getByRole('button', { name: 'Request account export' })).toBeFocused()
  await expect(page.getByText('Export status: pending.', { exact: false })).toBeVisible()
})

test('failure never claims success and account switching closes dialog', async ({ page }) => {
  await page.goto('/auth/export-fixture')
  await page.getByRole('button', { name: 'Request account export' }).click()
  await page.getByLabel('Verify your password').fill('synthetic-only')
  await page.getByRole('button', { name: 'Verify identity' }).click()
  await page.getByLabel('Type export to confirm').fill('export')
  await page.route('**/api/privacy/content/confirm', route => route.abort())
  await page.getByRole('button', { name: 'Create private export' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.getByRole('dialog').getByRole('alert')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Download private archive' })).toHaveCount(0)
  await page.evaluate(() => window.switchSyntheticAccount())
  await expect(page.getByRole('dialog')).not.toBeVisible()
})

for (const [name, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
  test(`${name} mailbox export preview and keyboard containment`, async ({ page }) => {
    await page.setViewportSize({ width, height })
    await page.goto('/auth/export-fixture?google')
    await page.getByRole('button', { name: 'Request account export' }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByText('Fresh mailbox verification is not Google reauthentication or MFA.')).toBeVisible()
    await page.getByRole('button', { name: 'Send mailbox code' }).click()
    await expect(page.getByRole('button', { name: 'Resend mailbox code' })).toBeVisible()
    await page.getByRole('button', { name: 'Cancel', exact: true }).focus()
    await page.keyboard.press('Tab')
    await page.keyboard.press('Tab')
    await expect.poll(() => page.evaluate(() => document.querySelector('dialog').contains(document.activeElement))).toBe(true)
    if (process.env.C15_EXPORT_CAPTURE_DIR) await page.screenshot({ path: path.join(process.env.C15_EXPORT_CAPTURE_DIR, `${name}-export.png`), fullPage: true, animations: 'disabled' })
    await page.keyboard.press('Escape')
    await expect(dialog).not.toBeVisible()
  })
}

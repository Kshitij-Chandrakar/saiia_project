import { test, expect } from '@playwright/test'
import path from 'node:path'
const captures = process.env.C15_CAPTURE_DIR ? path.resolve(process.env.C15_CAPTURE_DIR) : null

class PrivacyPage {
  constructor(page) { this.page = page; this.dialog = page.getByRole('dialog'); this.delete = page.getByRole('button', { name: 'Yes, Delete My Account', exact: true }) }
  async open() { await this.page.goto('/auth/settings'); await this.page.getByRole('button', { name: 'Delete Account', exact: true }).click() }
  async verify() { await this.page.getByRole('dialog').getByLabel('Reauthenticate with your password').fill('synthetic-only'); await this.page.getByRole('button', { name: 'Verify identity' }).click(); await expect(this.page.getByText('Identity verified.', { exact: false })).toBeVisible() }
  async type() { await this.page.getByRole('dialog').getByLabel('Type delete to confirm').fill('delete') }
}

test.beforeEach(async ({ page }) => {
  await page.route('**/*', route => route.request().url().startsWith('http://127.0.0.1:5396') ? route.continue() : route.abort())
  await page.route('**/api/privacy/deletion/*', route => route.fulfill({ json: { request_id: 'synthetic', expires_at: new Date(Date.now() + 300000).toISOString(), state: route.request().url().endsWith('/otp_start') ? 'otp_sent' : /\/(challenge|otp_verify|otp_ready)$/.test(route.request().url()) ? 'awaiting_confirmation' : 'accepted_restricted', cleanup_state: 'pending', content_erased: false } }))
})

test('profile menu leads to settings and feature defaults remain closed', async ({ page }) => {
  await page.goto('/auth/settings?disabled')
  await page.getByRole('button', { name: 'Profile menu' }).click()
  await expect(page.getByRole('link', { name: 'Settings', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Delete Account', exact: true })).toBeDisabled()
})

test('exact text, reauth, keyboard containment and restored focus', async ({ page }) => {
  const ui = new PrivacyPage(page); await ui.open()
  await expect(page.getByRole('heading', { name: 'Delete your account?' })).toBeFocused()
  await expect(page.getByRole('heading', { name: 'Delete your account?' })).toBeVisible()
  await ui.type(); await expect(ui.delete).toBeDisabled()
  await ui.verify(); await expect(ui.delete).toBeEnabled()
  await page.getByRole('dialog').getByLabel('Type delete to confirm').fill('Delete'); await expect(ui.delete).toBeDisabled()
  await page.keyboard.press('Escape'); await expect(ui.dialog).not.toBeVisible()
  await expect(page.getByRole('button', { name: 'Delete Account', exact: true })).toBeFocused()
})

test('duplicate clicks cannot submit twice; accepted means pending cleanup', async ({ page }) => {
  let finish, calls = 0
  await page.route('**/api/privacy/deletion/confirm', async route => { calls++; await new Promise(resolve => { finish = resolve }); await route.fulfill({ json: { state: 'accepted_restricted', cleanup_state: 'pending', content_erased: false } }) })
  const ui = new PrivacyPage(page); await ui.open(); await ui.verify(); await ui.type()
  await page.evaluate(() => localStorage.setItem('sb-synthetic-auth-token', JSON.stringify({ user: { id: '10000000-0000-4000-8000-000000000001' } })))
  await ui.delete.click(); await expect(page.getByRole('button', { name: 'Confirming…' })).toBeDisabled()
  expect(calls).toBe(1); finish()
  await expect(page).toHaveURL(/privacy-status/)
  await expect(page.getByText('Personal-content cleanup is pending.', { exact: false })).toBeVisible()
  await expect(page.getByText('Further charges may remain possible', { exact: false })).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('sb-synthetic-auth-token'))).toBeNull()
  expect(await page.evaluate(() => sessionStorage.getItem('synthetic-provider-logout'))).toBeNull()
  expect(await page.evaluate(() => sessionStorage.getItem('intervucopilot.privacy-receipt'))).not.toContain('confirmation_token')
})

test('unknown outcome checks same request status without claiming success', async ({ page }) => {
  await page.route('**/api/privacy/deletion/confirm', route => route.fulfill({ status: 503, json: {} }))
  const ui = new PrivacyPage(page); await ui.open(); await ui.verify(); await ui.type(); await ui.delete.click()
  await expect(page.getByRole('alert')).toContainText('could not confirm')
  await expect(ui.delete).toBeDisabled()
  await page.getByRole('button', { name: 'Check request status' }).click()
  await expect(page).toHaveURL(/privacy-status/)
})

test('account switch discards in-flight responses', async ({ page }) => {
  let finish
  await page.route('**/api/privacy/deletion/challenge', async route => { await new Promise(resolve => { finish = resolve }); await route.fulfill({ json: { state: 'awaiting_confirmation' } }) })
  const ui = new PrivacyPage(page); await ui.open()
  await page.getByRole('dialog').getByLabel('Reauthenticate with your password').fill('synthetic-only')
  await page.getByRole('button', { name: 'Verify identity' }).click()
  await expect(page.getByRole('button', { name: 'Verifying…' })).toBeDisabled()
  await page.evaluate(() => window.switchSyntheticAccount()); finish()
  await expect(ui.dialog).not.toBeVisible()
  await expect(page.getByText('Identity verified.', { exact: false })).not.toBeVisible()
})

test('expired prerequisite disables confirmation and asks for reauthentication', async ({ page }) => {
  await page.clock.install()
  const ui = new PrivacyPage(page); await ui.open(); await ui.verify(); await ui.type()
  await expect(ui.delete).toBeEnabled()
  await page.clock.fastForward(300001)
  await expect(ui.delete).toBeDisabled()
  await expect(page.getByRole('alert')).toContainText('expired')
})

for (const [name, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
  test(`${name} settings and dialog previews, no overflow or keyboard escape`, async ({ page }) => {
    await page.setViewportSize({ width, height }); const ui = new PrivacyPage(page)
    await page.goto('/auth/settings'); await page.evaluate(() => document.fonts.ready)
    if (captures) await page.screenshot({ path: path.join(captures, `${name}-settings.png`), fullPage: true, animations: 'disabled' })
    await page.getByRole('button', { name: 'Delete Account', exact: true }).click()
    await ui.verify(); await ui.type()
    await expect(ui.delete).toBeEnabled()
    await ui.dialog.evaluate(node => { node.scrollTop = 0 })
    if (captures) await page.screenshot({ path: path.join(captures, `${name}-dialog.png`), fullPage: true, animations: 'disabled' })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    const box = await ui.dialog.boundingBox(); expect(box.width).toBeLessThanOrEqual(width)
    await ui.delete.focus(); await page.keyboard.press('Tab')
    expect(await ui.dialog.evaluate(node => node.contains(document.activeElement))).toBe(true)
  })
}

test('Google-only account with enrolled authenticator verifies without password or OAuth redirect', async ({ page }) => {
  await page.goto('/auth/settings?google&factor')
  await page.getByRole('button', { name: 'Delete Account', exact: true }).click()
  await expect(page.getByRole('dialog').getByLabel('Reauthenticate with your password')).toHaveCount(0)
  await page.getByRole('dialog').getByLabel('Authenticator code').fill('000000')
  await page.getByRole('button', { name: 'Verify identity' }).click()
  await expect(page.getByRole('alert')).toContainText('authenticator code')
  await page.getByRole('dialog').getByLabel('Authenticator code').fill('123456')
  await page.getByRole('button', { name: 'Verify identity' }).click()
  await expect(page.getByText('Identity verified.', { exact: false })).toBeVisible()
  await expect(page).toHaveURL(/settings/)
  await page.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(page.getByRole('dialog')).not.toBeVisible()
})

test('Google-only email fallback requires a code then final typed confirmation', async ({ page }) => {
  await page.goto('/auth/settings?google')
  await page.getByRole('button', { name: 'Delete Account', exact: true }).click()
  await page.getByRole('button', { name: 'Send email code' }).click()
  await page.getByRole('dialog').getByLabel('Type delete to confirm').fill('delete')
  await expect(page.getByRole('button', { name: 'Yes, Delete My Account', exact: true })).toBeDisabled()
  await page.getByRole('dialog').getByLabel('Email confirmation code').fill('12345678')
  await page.getByRole('button', { name: 'Verify email code' }).click()
  await expect(page.getByRole('dialog').getByRole('status')).toContainText('Mailbox control only')
  await expect(page.getByRole('dialog').getByLabel('Type delete to confirm')).toHaveValue('')
  await expect(page.getByRole('button', { name: 'Yes, Delete My Account', exact: true })).toBeDisabled()
  await page.getByRole('dialog').getByLabel('Type delete to confirm').fill('delete')
  await expect(page.getByRole('button', { name: 'Yes, Delete My Account', exact: true })).toBeEnabled()
  await expect(page.getByRole('dialog').getByLabel('Reauthenticate with your password')).toHaveCount(0)
})

for (const scenario of ['wrong-password', 'wrong-account']) {
  test(`${scenario} cannot enable confirmation`, async ({ page }) => {
    await page.goto(`/auth/settings?${scenario}`)
    await page.getByRole('button', { name: 'Delete Account', exact: true }).click()
    await page.getByRole('dialog').getByLabel('Reauthenticate with your password').fill('synthetic-only')
    await page.getByRole('button', { name: 'Verify identity' }).click()
    await expect(page.getByRole('alert')).toContainText('No deletion was accepted')
    await expect(page.getByRole('button', { name: 'Yes, Delete My Account', exact: true })).toBeDisabled()
    await expect(page.getByRole('dialog').getByLabel('Reauthenticate with your password')).toHaveValue('')
  })
}

test('navigation during operation start cannot resume or confirm deletion', async ({ page }) => {
  let release
  await page.route('**/api/privacy/deletion/begin', async route => { await new Promise(resolve => { release = resolve }); await route.fulfill({ json: {} }).catch(() => {}) })
  const ui = new PrivacyPage(page); await ui.open()
  await page.getByRole('dialog').getByLabel('Reauthenticate with your password').fill('synthetic-only')
  await page.getByRole('button', { name: 'Verify identity' }).click()
  await expect(page.getByRole('button', { name: 'Verifying…' })).toBeDisabled()
  await page.goto('/auth/privacy-status'); release()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByText('No accepted deletion has been verified.')).toBeVisible()
})

test('uncertain challenge retries the same proof and request without automatic deletion', async ({ page }) => {
  const requests = []
  await page.route('**/api/privacy/deletion/challenge', route => {
    requests.push(route.request().postDataJSON())
    return route.fulfill(requests.length === 1 ? { status: 503, json: {} } : { json: { expires_at: new Date(Date.now() + 300000).toISOString(), state: 'awaiting_confirmation' } })
  })
  const ui = new PrivacyPage(page); await ui.open()
  await page.getByRole('dialog').getByLabel('Reauthenticate with your password').fill('synthetic-only')
  await page.getByRole('button', { name: 'Verify identity' }).click()
  await expect(page.getByRole('button', { name: 'Retry identity confirmation' })).toBeEnabled()
  await expect(ui.delete).toBeDisabled()
  await page.getByRole('button', { name: 'Retry identity confirmation' }).click()
  await expect(page.getByText('Identity verified.', { exact: false })).toBeVisible()
  expect(requests).toHaveLength(2); expect(requests[0]).toEqual(requests[1])
  await expect(ui.delete).toBeDisabled()
  await expect(page).toHaveURL(/settings/)
})

for (const [name, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
  test(`${name} Google authenticator preview`, async ({ page }) => {
    await page.setViewportSize({ width, height })
    await page.goto('/auth/settings?google&factor')
    await page.getByRole('button', { name: 'Delete Account', exact: true }).click()
    await expect(page.getByRole('dialog').getByLabel('Authenticator code')).toBeVisible()
    await page.getByRole('dialog').evaluate(node => { node.scrollTop = 0 })
    if (captures) await page.screenshot({ path: path.join(captures, `${name}-google-dialog.png`), fullPage: true, animations: 'disabled' })
  })
}


test('status retries temporary quarantine without claiming completion', async ({ page }) => {
  let attempts = 0
  await page.route('**/api/privacy/deletion/status', route => {
    attempts += 1
    return route.fulfill(attempts === 1 ? { status:503, json:{status:'restore_quarantined'} } : {json:{state:'accepted_restricted',cleanup_state:'pending',content_erased:false}})
  })
  const ui = new PrivacyPage(page); await ui.open(); await ui.verify(); await ui.type(); await ui.delete.click()
  await expect(page.getByRole('heading',{name:'Request accepted. Product access is restricted.'})).toBeVisible()
  await expect(page.getByText('Personal-content cleanup is pending.',{exact:false})).toBeVisible()
  expect(attempts).toBeGreaterThan(1)
  await expect(page.getByText('This does not confirm that all files, backups or processor copies have been erased.',{exact:false})).toBeVisible()
})

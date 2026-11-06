import { test, expect } from '@playwright/test'
import { mkdir } from 'node:fs/promises'

const record = { id: 'resume-owner', original_filename: '<img src=x onerror=alert(1)> long-resume-' + 'candidate-'.repeat(16) + '.txt', status: 'ready', is_active: true }
function session(id = 'owner') {
  const token = `${Buffer.from('{}').toString('base64url')}.${Buffer.from(JSON.stringify({ sub: id, exp: 2524608000 })).toString('base64url')}.synthetic`
  return { access_token: token, refresh_token: 'synthetic-refresh', token_type: 'bearer', expires_at: 2524608000, expires_in: 3600, user: { id, email: `${id}@example.test` } }
}
function deferred() { let resolve; const promise = new Promise(r => { resolve = r }); return { promise, resolve } }
async function fixture(page, { authenticated = false, candidate = false, onboard = false, desktop = false, badUser = false } = {}) {
  const state = { session: session(), requests: [], fail: {}, hold: {}, deleted: false, candidate, onboard }
  await page.addInitScript(({ authenticated, value, desktop }) => {
    if (authenticated) localStorage.setItem('sb-127-auth-token', JSON.stringify(value))
    if (desktop) window.electronAPI = {}
  }, { authenticated, value: state.session, desktop })
  page.on('dialog', dialog => { throw new Error(`Unexpected native dialog: ${dialog.type()}`) })
  await page.route('**/*', async route => {
    const url = new URL(route.request().url()), p = url.pathname, method = route.request().method()
    if (url.origin === 'http://127.0.0.1:5321' && !p.startsWith('/api/')) return route.continue()
    state.requests.push({ path: p, method })
    if (state.hold[p]) await state.hold[p].promise
    if (state.fail[p]) return route.fulfill({ status: state.fail[p], json: { detail: 'synthetic private database error', code: 'unknown' } })
    let value = { items: [], page: 1, limit: 20 }
    if (p === '/auth/v1/user') value = state.session.user
    else if (p === '/auth/v1/logout') value = {}
    else if (p === '/auth/v1/verify') return state.verifySuccess ? route.fulfill({ json: state.session }) : route.fulfill({ status: 503, json: { message: 'synthetic private verification error' } })
    else if (p === '/api/auth/me') value = { user_id: state.session.user.id, email: badUser ? { private: 'synthetic render fault' } : state.session.user.email }
    else if (p === '/api/auth/profile/bootstrap') value = { profile_exists: true, settings_exists: true }
    else if (p === '/api/onboarding') value = { onboarding_completed_at: state.onboard ? null : 'synthetic-complete', onboarding_current_step: state.onboard ? 1 : 5 }
    else if (p === '/api/account/subscription') value = {}
    else if (p === '/api/resumes/current') value = { ready: !state.candidate && !state.deleted, resume: !state.candidate && !state.deleted ? record : null }
    else if (p === '/api/resumes/review-candidate') value = { has_candidate: state.candidate && !state.deleted, resume: state.candidate && !state.deleted ? { ...record, status: 'uploaded', is_active: false } : null }
    else if (p === '/api/resumes' && method === 'GET') value = { items: state.deleted ? [] : [{ ...record, status: state.candidate ? 'uploaded' : 'ready' }] }
    else if (p === '/api/resumes' && method === 'POST') value = { ...record, id: 'new-upload', status: 'uploaded' }
    else if (p.endsWith('/status')) value = { ...record, id: 'new-upload', status: 'uploaded' }
    else if (p.endsWith('/extract')) value = { status: 'needs_review', extraction_attempt: 1, profile: { full_name: 'Synthetic Candidate' }, review_required: true }
    else if (p === '/api/resumes/resume-owner' && method === 'DELETE') { state.deleted = true; value = { deleted: true } }
    else if (p === '/api/email/unsubscribe') value = { success: true }
    else if (!p.startsWith('/api/')) return route.abort()
    return route.fulfill({ json: value })
  })
  return state
}
async function capture(page, name, project) {
  if (process.env.WEBSITE_BRANDING_DEV) return
  await mkdir('../tmp/website-batch3', { recursive: true })
  await page.screenshot({ path: `../tmp/website-batch3/${name}-${project}.png`, fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
}
const requests = (state, method) => state.requests.filter(x => x.method === method)

test('public route titles, static branding, and transitions never use URL data', async ({ page }) => {
  await fixture(page)
  for (const [path, title] of [['/', 'Intervucopilot'], ['/auth/login', 'Sign in'], ['/AUTH/LOGIN/', 'Sign in'], ['/auth/signup', 'Create account'], ['/auth/callback?error=private-value', 'Signing you in'], ['/unsubscribe', 'Email preferences'], ['/auth/checkout', 'Secure checkout']]) {
    await page.goto(path)
    await expect(page).toHaveTitle(title === 'Intervucopilot' ? title : `${title} | Intervucopilot`)
    await expect(page.locator('link[rel="icon"]')).toHaveAttribute('href', '/website-favicon.png')
  }
  await page.goto('/auth/signup')
  await page.getByRole('link', { name: 'Sign in', exact: true }).click()
  await expect(page).toHaveTitle('Sign in | Intervucopilot')
})

test('404 is branded, private, focusable and direct Back stays local', async ({ page }, info) => {
  await fixture(page)
  await page.goto('/unknown/private?token=synthetic-private#secret')
  const heading = page.getByRole('heading', { name: 'Page not found' })
  await expect(heading).toBeFocused()
  await expect(page.getByText('Intervucopilot', { exact: true })).toBeVisible()
  await expect(page.locator('body')).not.toContainText('synthetic-private')
  await capture(page, 'not-found', info.project.name)
  await page.getByRole('button', { name: 'Go back' }).click()
  await expect(page).toHaveURL('http://127.0.0.1:5321/')
  await expect(page).toHaveTitle('Intervucopilot')
})

test('404 Back uses known in-app history; Home works with images unavailable', async ({ page }, info) => {
  await fixture(page)
  await page.goto('/auth/login')
  await expect(page).toHaveTitle('Sign in | Intervucopilot')
  await page.evaluate(() => { history.pushState({ idx: (history.state?.idx || 0) + 1, key: 'synthetic-unknown' }, '', '/unavailable'); dispatchEvent(new PopStateEvent('popstate')) })
  await expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible()
  await page.getByRole('button', { name: 'Go back' }).click()
  await expect(page).toHaveURL(/\/auth\/login$/)
  await page.route('**/*.{png,jpg,svg}', route => route.abort())
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/unknown')
  await expect(page.locator('.wr-mascot')).toBeHidden()
  await expect(page.locator('.wr-brand img')).toBeHidden()
  await capture(page, 'not-found-images-blocked', info.project.name)
  await page.getByRole('link', { name: 'Return home', exact: true }).click()
  await expect(page).toHaveURL('http://127.0.0.1:5321/')
})

test('missing confirmation link uses shared recovery and relevant actions', async ({ page }, info) => {
  await fixture(page)
  await page.goto('/auth/confirm?token_hash=synthetic&type=unsupported')
  await expect(page.getByRole('heading', { name: 'Secure link unavailable' })).toBeVisible()
  expect(new URL(page.url()).search).toBe('')
  await expect(page.locator('.auth-shell')).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Back to sign in' })).toBeVisible()
  await capture(page, 'confirmation-invalid', info.project.name)
})

test('verification service failure is safe and branded', async ({ page }, info) => {
  await fixture(page)
  await page.goto('/auth/confirm?token_hash=synthetic&type=email')
  await expect(page.getByRole('heading', { name: 'Secure link unavailable' })).toBeVisible()
  await expect(page.getByRole('status')).toContainText('verification is unavailable')
  await expect(page.locator('body')).not.toContainText('private verification error')
  await capture(page, 'confirmation-service-error', info.project.name)
})

test('verified email with unfinished setup keeps consent and the dashboard recovery state', async ({ page }, info) => {
  const state = await fixture(page)
  state.verifySuccess = true
  state.fail['/api/auth/profile/bootstrap'] = 503
  await page.addInitScript(() => localStorage.setItem('intervuai.pendingSignupConsent', JSON.stringify({ email: 'owner@example.test', consent: { terms_accepted: true, privacy_accepted: true, marketing_email_opt_in: false, consent_source: 'signup', consent_version: 'c10.6a-v1' } })))
  await page.goto('/auth/confirm?token_hash=synthetic&type=email')
  await expect(page.getByRole('heading', { name: 'Finish setting up your account' })).toBeVisible()
  expect(await page.evaluate(() => Boolean(localStorage.getItem('intervuai.pendingSignupConsent')))).toBe(true)
  await capture(page, 'confirmation-account-setup', info.project.name)
  delete state.fail['/api/auth/profile/bootstrap']
  await page.getByRole('link', { name: 'Continue to dashboard' }).click()
  await expect(page.getByTitle('owner@example.test', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('intervuai.pendingSignupConsent'))).toBe(null)
})

test('resume delete is cancellable with keyboard focus restored', async ({ page }, info) => {
  const state = await fixture(page, { authenticated: true })
  await page.goto('/auth/resume')
  const trigger = page.getByRole('button', { name: 'Delete Resume', exact: true })
  await trigger.click()
  const dialog = page.getByRole('dialog', { name: 'Delete this resume?' })
  await expect(dialog.getByRole('button', { name: 'Keep resume' })).toBeFocused()
  await expect(dialog).toContainText(record.original_filename)
  await expect(dialog.locator('img')).toHaveCount(0)
  await capture(page, 'resume-delete', info.project.name)
  await page.keyboard.press('Shift+Tab')
  expect(await page.evaluate(() => document.activeElement.closest('dialog') !== null)).toBe(true)
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(trigger).toBeFocused()
  expect(requests(state, 'DELETE')).toHaveLength(0)
})

test('delete submission is single, pending is honest, failure retains record', async ({ page }, info) => {
  const state = await fixture(page, { authenticated: true }), hold = deferred()
  state.fail['/api/resumes/resume-owner'] = 503
  state.hold['/api/resumes/resume-owner'] = hold
  await page.goto('/auth/resume')
  await page.getByRole('button', { name: 'Delete Resume', exact: true }).click()
  await page.getByRole('button', { name: 'Delete resume', exact: true }).evaluate(button => { button.click(); button.click() })
  await expect.poll(() => requests(state, 'DELETE').length).toBe(1)
  await expect(page.getByRole('button', { name: 'Deleting resume...' })).toBeDisabled()
  hold.resolve()
  await expect(page.getByRole('alert')).toContainText('Could not delete')
  await expect(page.getByRole('heading', { name: record.original_filename, exact: true })).toBeVisible()
  await capture(page, 'resume-delete-failed', info.project.name)
  delete state.fail['/api/resumes/resume-owner']; delete state.hold['/api/resumes/resume-owner']
  await page.getByRole('button', { name: 'Delete Resume', exact: true }).click()
  await page.getByRole('button', { name: 'Delete resume', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('Resume deleted.')
  expect(requests(state, 'DELETE')).toHaveLength(2)
})

test('account switch invalidates an open confirmation', async ({ page }) => {
  const state = await fixture(page, { authenticated: true })
  await page.goto('/auth/resume')
  await page.getByRole('button', { name: 'Delete Resume', exact: true }).click()
  state.session = session('other-owner')
  await page.evaluate(value => { localStorage.setItem('sb-127-auth-token', JSON.stringify(value)); new BroadcastChannel('sb-127-auth-token').postMessage({ event: 'SIGNED_IN', session: value }) }, state.session)
  await expect(page.getByTitle('other-owner@example.test', { exact: true })).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  expect(requests(state, 'DELETE')).toHaveLength(0)
})

test('draft replacement keeps edits and selected file on cancel or upload failure', async ({ page }, info) => {
  const state = await fixture(page, { authenticated: true, candidate: true })
  await page.goto('/auth/resume')
  await page.getByRole('button', { name: 'Extract Again', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Review Extracted Profile' })).toBeVisible()
  await page.getByRole('textbox', { name: 'Full name', exact: true }).fill('Preserved local edits')
  await page.getByRole('button', { name: 'Close', exact: true }).click()
  await page.getByRole('button', { name: 'Upload Resume', exact: true }).click()
  await page.getByLabel('Resume file', { exact: true }).setInputFiles({ name: 'replacement.txt', mimeType: 'text/plain', buffer: Buffer.from('synthetic only') })
  await page.getByRole('button', { name: 'Upload and Extract' }).click()
  await expect(page.getByRole('dialog', { name: 'Replace your draft?' })).toBeVisible()
  await capture(page, 'resume-replace', info.project.name)
  await page.getByRole('button', { name: 'Keep editing', exact: true }).click()
  expect(requests(state, 'POST').filter(x => x.path === '/api/resumes')).toHaveLength(0)
  await expect(page.getByText('replacement.txt', { exact: true })).toBeVisible()
  state.fail['/api/resumes'] = 503
  await page.getByRole('button', { name: 'Upload and Extract' }).click()
  await page.getByRole('button', { name: 'Replace draft and upload' }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  await page.getByRole('button', { name: 'Retry processing', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Extract this resume again?' })).toBeVisible()
  await capture(page, 'resume-extract-again', info.project.name)
  await page.getByRole('button', { name: 'Keep editing', exact: true }).click()
  await page.getByRole('button', { name: 'Close Upload Resume' }).click()
  await page.getByRole('button', { name: 'Review Profile' }).click()
  await expect(page.getByRole('textbox', { name: 'Full name', exact: true })).toHaveValue('Preserved local edits')
  await page.getByRole('button', { name: 'Close', exact: true }).click()
  await page.getByRole('button', { name: 'Retry resume status', exact: true }).click()
  await page.getByRole('button', { name: 'Extract again', exact: true }).click()
  await expect(page.getByRole('textbox', { name: 'Full name', exact: true })).toHaveValue('Synthetic Candidate')
  expect(state.requests.filter(x => x.path.endsWith('/extract'))).toHaveLength(2)
})

test('onboarding has no unsupported decorative review claims', async ({ page }, info) => {
  await fixture(page, { authenticated: true, onboard: true })
  await page.goto('/auth/onboarding')
  await expect(page.getByRole('button', { name: 'Get Started', exact: true })).toBeVisible()
  await expect(page.locator('body')).not.toContainText('mock reviews')
  await expect(page.locator('body')).not.toContainText('340,000')
  await expect(page.locator('body')).not.toContainText('1,530,000')
  await expect(page.locator('body')).not.toContainText('\\u00b7')
  await capture(page, 'onboarding', info.project.name)
})

test('shared HTML keeps Electron metadata and hides website startup', async ({ page }) => {
  await fixture(page, { desktop: true })
  await page.goto('/auth/login')
  await expect(page).toHaveTitle('Vite + React')
  await expect(page.locator('link[rel="icon"]')).toHaveAttribute('href', '/vite.svg')
  await expect(page.locator('#website-startup')).toBeHidden()
  await expect(page.locator('.website-recovery')).toHaveCount(0)
})

test('no JavaScript still has branded metadata and startup recovery', async ({ browser }, info) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: info.project.use.viewport })
  try {
    const page = await context.newPage()
    await page.route('**/*', route => new URL(route.request().url()).origin === 'http://127.0.0.1:5321' ? route.continue() : route.abort())
    await page.goto('http://127.0.0.1:5321/')
    await expect(page).toHaveTitle('Intervucopilot')
    await expect(page.locator('#website-startup')).toBeVisible()
    await expect(page.getByRole('link', { name: 'Reload page' })).toBeVisible()
  } finally { await context.close() }
})

test('production entry failure keeps static recovery and reload mounts cleanly', async ({ page }, info) => {
  await fixture(page)
  await page.route('**/assets/*.js', route => route.abort())
  await page.goto('/auth/login')
  await expect(page.getByRole('heading', { name: 'The website couldn’t start' })).toBeVisible()
  await expect(page).toHaveTitle('Intervucopilot')
  await capture(page, 'entry-failure', info.project.name)
  await page.unroute('**/assets/*.js')
  await page.getByRole('link', { name: 'Reload page' }).click()
  await expect(page.getByRole('heading', { name: 'Welcome back!', exact: true })).toBeVisible()
  await expect(page.locator('#website-startup')).toHaveCount(0)
  await expect(page).toHaveTitle('Sign in | Intervucopilot')
})

test('render boundary still suppresses private details after metadata changes', async ({ page }) => {
  await fixture(page, { authenticated: true, badUser: true })
  await page.goto('/auth/resume')
  await expect(page.getByRole('heading', { name: 'This page couldn’t open' })).toBeVisible()
  await expect(page).toHaveTitle('Page unavailable | Intervucopilot')
  await expect(page.locator('body')).not.toContainText(/Unexpected Application Error|Hey developer|synthetic render fault/)
  await expect(page.getByRole('link', { name: 'Return home', exact: true })).toBeVisible()
})

test('unsubscribe still scrubs the token and retries only from memory', async ({ page }) => {
  const state = await fixture(page)
  state.fail['/api/email/unsubscribe'] = 503
  await page.goto('/unsubscribe?token=synthetic-in-memory')
  await expect(page.getByRole('button', { name: 'Retry preference update' })).toBeVisible()
  expect(new URL(page.url()).search).toBe('')
  await expect(page).toHaveTitle('Email preferences | Intervucopilot')
  delete state.fail['/api/email/unsubscribe']
  await page.getByRole('button', { name: 'Retry preference update' }).click()
  await expect(page.getByRole('heading', { name: 'Email preference updated' })).toBeVisible()
  expect(state.requests.filter(x => x.path === '/api/email/unsubscribe')).toHaveLength(2)
})

test('logout still reports uncertainty then verifies completion on manual retry', async ({ page }) => {
  const state = await fixture(page, { authenticated: true })
  state.fail['/auth/v1/logout'] = 503
  await page.goto('/auth/logout')
  await expect(page.getByRole('heading', { name: 'Sign-out wasn’t confirmed' })).toBeVisible()
  await expect(page).toHaveTitle('Sign out | Intervucopilot')
  delete state.fail['/auth/v1/logout']
  await page.getByRole('button', { name: 'Retry sign out' }).click()
  await expect(page.getByRole('heading', { name: 'You’re signed out' })).toBeVisible()
})

test('admin boundary retains its previous static metadata', async ({ page }) => {
  await fixture(page)
  await page.goto('/auth/admin/billing')
  await expect(page).toHaveTitle('Vite + React')
  await expect(page.locator('link[rel="icon"]')).toHaveAttribute('href', '/vite.svg')
  await page.goto('/AUTH/ADMIN/BILLING')
  await expect(page).toHaveTitle('Vite + React')
})

test('confirmation remains usable with enlarged text and a long filename', async ({ page }, info) => {
  await fixture(page, { authenticated: true })
  await page.goto('/auth/resume')
  await page.getByRole('button', { name: 'Delete Resume', exact: true }).click()
  await page.addStyleTag({ content: '.wr-dialog p,.wr-dialog button{font-size:28px!important}.wr-dialog h2{font-size:36px!important}' })
  const dialog = page.getByRole('dialog', { name: 'Delete this resume?' })
  const cancel = dialog.getByRole('button', { name: 'Keep resume' })
  await cancel.focus()
  await page.keyboard.press('Tab')
  await expect(dialog.getByRole('button', { name: 'Delete resume', exact: true })).toBeFocused()
  const bounds = await cancel.boundingBox()
  expect(bounds.y + bounds.height).toBeLessThanOrEqual(info.project.use.viewport.height)
  await capture(page, 'resume-enlarged-text', info.project.name)
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
})

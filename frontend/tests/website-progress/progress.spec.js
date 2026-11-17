import { test, expect } from '@playwright/test'
import { mkdir } from 'node:fs/promises'

function session(id = 'owner') {
  const token = `${Buffer.from('{}').toString('base64url')}.${Buffer.from(JSON.stringify({ sub: id, exp: 2524608000 })).toString('base64url')}.synthetic`
  return { access_token: token, refresh_token: 'synthetic-refresh', token_type: 'bearer', expires_at: 2524608000, expires_in: 3600, user: { id, email: 'candidate@example.test' } }
}
function deferred() { let resolve; const promise = new Promise(r => { resolve = r }); return { promise, resolve } }
const operation = id => ({ operation_id: id, state: 'pending', name: 'Plus', currency: 'INR', amount_minor: '47082', interval: 'month', total_count: 12 })

class ProgressPage {
  constructor(page) { this.page = page }
  async capture(name, project) {
    if (process.env.WEBSITE_PROGRESS_DEV) return
    await mkdir('../tmp/website-batch2', { recursive: true })
    await this.page.screenshot({ path: `../tmp/website-batch2/${name}-${project}.png`, fullPage: true })
    expect(await this.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
}

async function fixture(page, { expired = false, consent = false } = {}) {
  const state = { session: session(), hold: {}, requests: [], failures: {}, operation: operation('existing-operation') }
  await page.addInitScript(({ value, expired, consent }) => {
    localStorage.setItem('sb-127-auth-token', JSON.stringify({ ...value, expires_at: expired ? 1 : value.expires_at }))
    if (consent) sessionStorage.setItem('intervuai.googleSignupAttempt', JSON.stringify({ attempt: 'synthetic-attempt', createdAt: Date.now(), consent: { terms_accepted: true, privacy_accepted: true, marketing_email_opt_in: false, consent_source: 'signup', consent_version: 'c10.6a-v1' } }))
  }, { value: state.session, expired, consent })
  await page.route('**/*', async route => {
    const url = new URL(route.request().url()), path = url.pathname, method = route.request().method()
    if (url.origin === 'http://127.0.0.1:5311' && !path.startsWith('/api/')) return route.continue()
    state.requests.push({ path, method, operationId: url.searchParams.get('operation_id') })
    const ownerAtStart = state.session.user.id
    const operationAtStart = state.operation
    const hold = state.hold[path]
    if (hold) await hold.promise
    if (state.failures[path]) return route.fulfill({ status: state.failures[path], json: { detail: 'synthetic private error' } })
    if (path === '/auth/v1/token') return route.fulfill({ json: state.session })
    if (path === '/auth/v1/user') return route.fulfill({ json: state.session.user })
    if (path === '/api/auth/me') return route.fulfill({ json: { user_id: ownerAtStart, email: ownerAtStart + '@example.test' } })
    if (path === '/api/auth/profile/bootstrap') return route.fulfill({ json: { profile_exists: true, settings_exists: true } })
    if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_completed_at: 'synthetic-complete', onboarding_current_step: 5 } })
    if (path === '/api/email/unsubscribe') return route.fulfill({ json: { success: true } })
    if (path === '/api/billing/current' || path === '/api/billing/status') return route.fulfill({ json: operationAtStart })
    if (path === '/api/account/subscription') return route.fulfill({ json: { plan: { name: 'Plus' } } })
    if (path === '/api/resumes/current') return route.fulfill({ json: { ready: false, resume: null } })
    if (path === '/api/resumes/review-candidate') return route.fulfill({ json: { has_candidate: false, resume: null } })
    if (path.startsWith('/api/')) return route.fulfill({ json: { items: [], page: 1, limit: 20 } })
    return route.abort()
  })
  await page.clock.install()
  return state
}
const count = (state, path) => state.requests.filter(r => r.path === path).length

test('ordinary guard completion does not flash stalled recovery', async ({ page }) => {
  await fixture(page)
  await page.goto('/auth/resume')
  await expect(page.getByRole('heading', { name: 'Resumes', exact: true })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Your account check is taking longer' })).toHaveCount(0)
})

test('SDK session wait stays protected, then completes after stall', async ({ page }, info) => {
  const state = await fixture(page, { expired: true })
  const held = deferred(); state.hold['/auth/v1/token'] = held
  await page.goto('/auth/resume')
  await expect.poll(() => count(state, '/auth/v1/token')).toBe(1)
  expect(count(state, '/api/auth/me')).toBe(0)
  await page.clock.fastForward(15001)
  await expect(page.getByRole('button', { name: 'Retry session check' })).toBeVisible()
  await expect(page.getByTitle('owner@example.test', { exact: true })).toHaveCount(0)
  expect(new URL(page.url()).pathname).toBe('/auth/resume')
  await new ProgressPage(page).capture('guard-stalled', info.project.name)
  held.resolve()
  await expect(page.getByTitle('owner@example.test', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Retry session check' })).toHaveCount(0)
})

test('guard repeat retry invalidates older reads and survives navigation', async ({ page }) => {
  const state = await fixture(page), held = deferred()
  state.hold['/api/auth/me'] = held
  await page.goto('/auth/resume')
  await expect.poll(() => count(state, '/api/auth/me')).toBeGreaterThan(0)
  await page.clock.fastForward(15001)
  const before = count(state, '/api/auth/me')
  delete state.hold['/api/auth/me']
  await page.getByRole('button', { name: 'Retry session check' }).evaluate(button => { button.click(); button.click(); button.click() })
  await expect(page.getByTitle('owner@example.test', { exact: true })).toBeVisible()
  expect(count(state, '/api/auth/me')).toBe(before + 1)
  held.resolve()
  await page.goto('/unsubscribe')
  await expect(page.getByRole('status')).toContainText('Reopen the original')
})

test('account switch fences an older held response', async ({ page }) => {
  const state = await fixture(page), held = deferred()
  state.hold['/api/auth/me'] = held
  await page.goto('/auth/resume')
  await expect.poll(() => count(state, '/api/auth/me')).toBeGreaterThan(0)
  delete state.hold['/api/auth/me']; state.session = session('second-owner')
  await page.evaluate(value => {
    localStorage.setItem('sb-127-auth-token', JSON.stringify(value))
    const channel = new BroadcastChannel('sb-127-auth-token'); channel.postMessage({ event: 'SIGNED_IN', session: value }); channel.close()
  }, state.session)
  await expect(page.getByTitle('second-owner@example.test', { exact: true })).toBeVisible()
  const bootstrapCount = count(state, '/api/auth/profile/bootstrap')
  held.resolve()
  await expect(page.getByRole('heading', { name: 'Resumes', exact: true })).toBeVisible()
  expect(count(state, '/api/auth/profile/bootstrap')).toBe(bootstrapCount)
  await expect(page.getByTitle('owner@example.test', { exact: true })).toHaveCount(0)
})

test('pending account setup cannot be duplicated through stalled recovery', async ({ page }) => {
  const state = await fixture(page), held = deferred()
  state.hold['/api/auth/profile/bootstrap'] = held
  await page.goto('/auth/resume')
  await expect.poll(() => count(state, '/api/auth/profile/bootstrap')).toBe(1)
  await page.clock.fastForward(15001)
  await expect(page.getByRole('status').filter({ hasText: 'Your account setup has not finished' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Retry session check' })).toHaveCount(0)
  held.resolve()
  await expect(page.getByTitle('owner@example.test', { exact: true })).toBeVisible()
})

test('callback waits without replay, exposes keyboard-safe exit and accepts late completion', async ({ page }, info) => {
  const state = await fixture(page, { expired: true }), held = deferred()
  state.hold['/auth/v1/token'] = held
  await page.goto('/auth/callback?next=%2Fauth%2Fresume')
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.locator('body')).not.toContainText('LOADING STATE')
  await page.clock.fastForward(15001)
  await expect(page.getByRole('heading', { name: 'Sign-in is taking longer' })).toBeVisible()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Back to sign in' })).toBeFocused()
  await new ProgressPage(page).capture('callback-stalled', info.project.name)
  expect(count(state, '/auth/v1/token')).toBe(1)
  held.resolve()
  await expect(page).toHaveURL(/\/auth\/resume$/)
  expect(count(state, '/auth/v1/token')).toBe(1)
})

test('callback preference retry reuses verified session and clears consent only on success', async ({ page }) => {
  const state = await fixture(page, { consent: true })
  state.failures['/api/auth/profile/bootstrap'] = 503
  await page.goto('/auth/callback?signup_attempt=synthetic-attempt&next=%2Fauth%2Fresume')
  const retry = page.getByRole('button', { name: 'Retry saving signup preferences' })
  await expect(retry).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('intervuai.googleSignupAttempt'))).not.toBeNull()
  const verified = count(state, '/api/auth/me')
  delete state.failures['/api/auth/profile/bootstrap']
  const held = deferred(); state.hold['/api/auth/profile/bootstrap'] = held
  await retry.evaluate(button => { button.click(); button.click() })
  await expect.poll(() => count(state, '/api/auth/profile/bootstrap')).toBe(2)
  await page.clock.fastForward(15001)
  await expect(page.getByRole('heading', { name: 'Sign-in is taking longer' })).toBeVisible()
  expect(count(state, '/api/auth/me')).toBe(verified)
  expect(count(state, '/auth/v1/token')).toBe(0)
  held.resolve()
  await expect(page).toHaveURL(/\/auth\/resume$/)
  expect(await page.evaluate(() => sessionStorage.getItem('intervuai.googleSignupAttempt'))).toBeNull()
})

test('callback Escape navigates away and late completion cannot replay navigation', async ({ page }) => {
  const state = await fixture(page, { expired: true }), held = deferred(); state.hold['/auth/v1/token'] = held
  await page.goto('/auth/callback?next=%2Fauth%2Fresume')
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page).toHaveURL(/\/auth\/login\?next=/)
  // The active login may legitimately redirect a signed-in SDK session. Navigate
  // to a public route before releasing the old callback verification.
  await page.goto('/unsubscribe')
  held.resolve()
  await expect(page).toHaveURL(/\/unsubscribe$/)
})

test('unsubscribe shows progress, accepts delayed response and retains scrubbed URL', async ({ page }, info) => {
  const state = await fixture(page), held = deferred(); state.hold['/api/email/unsubscribe'] = held
  await page.goto('/unsubscribe?token=synthetic-link')
  await expect(page.getByRole('button', { name: 'Retry preference update' })).toBeDisabled()
  await expect(page.getByRole('status')).toContainText('Please wait')
  expect(new URL(page.url()).search).toBe('')
  await new ProgressPage(page).capture('unsubscribe-pending', info.project.name)
  await page.clock.fastForward(10001)
  await expect(page.getByRole('heading', { name: 'Still updating your preference' })).toBeVisible()
  await new ProgressPage(page).capture('unsubscribe-slow', info.project.name)
  expect(count(state, '/api/email/unsubscribe')).toBe(1)
  held.resolve()
  await expect(page.getByRole('heading', { name: 'Email preference updated' })).toBeVisible()
})

test('unsubscribe timeout is uncertain, with only a bounded manual retry', async ({ page }, info) => {
  const state = await fixture(page), held = deferred(); state.hold['/api/email/unsubscribe'] = held
  await page.goto('/unsubscribe?token=synthetic-link')
  await expect.poll(() => count(state, '/api/email/unsubscribe')).toBe(1)
  await page.clock.fastForward(15001)
  await expect(page.getByRole('status')).toContainText('the update may still finish')
  await new ProgressPage(page).capture('unsubscribe-unknown', info.project.name)
  expect(count(state, '/api/email/unsubscribe')).toBe(1)
  delete state.hold['/api/email/unsubscribe']
  await page.getByRole('button', { name: 'Retry preference update' }).evaluate(button => { button.click(); button.click() })
  await expect(page.getByRole('heading', { name: 'Email preference updated' })).toBeVisible()
  expect(count(state, '/api/email/unsubscribe')).toBe(2)
  held.resolve()
})

test('checkout timeout recovery only reads an existing operation', async ({ page }, info) => {
  const state = await fixture(page), held = deferred(); state.hold['/api/billing/current'] = held
  await page.goto('/auth/checkout')
  await expect.poll(() => count(state, '/api/billing/current')).toBeGreaterThan(0)
  await page.clock.fastForward(12001)
  await expect(page.getByRole('button', { name: 'Recover existing checkout' })).toBeVisible()
  await new ProgressPage(page).capture('checkout-stalled', info.project.name)
  const before = count(state, '/api/billing/current')
  delete state.hold['/api/billing/current']
  await page.getByRole('button', { name: 'Recover existing checkout' }).evaluate(button => { button.click(); button.click() })
  await expect(page.getByRole('heading', { name: 'Plus', exact: true })).toBeVisible()
  expect(count(state, '/api/billing/current')).toBe(before + 1)
  expect(state.requests.some(r => r.path.startsWith('/api/billing/') && r.method !== 'GET')).toBe(false)
  held.resolve()
})

test('checkout missing current operation does not create one during recovery', async ({ page }) => {
  const state = await fixture(page), held = deferred(); state.hold['/api/billing/current'] = held
  await page.goto('/auth/checkout?offer=synthetic-offer&price=synthetic-price')
  await expect.poll(() => count(state, '/api/billing/current')).toBeGreaterThan(0)
  await page.clock.fastForward(12001)
  state.operation = null; delete state.hold['/api/billing/current']
  await page.getByRole('button', { name: 'Recover existing checkout' }).click()
  await expect(page.getByRole('status')).toContainText('No existing checkout was found')
  expect(state.requests.some(r => r.path === '/api/billing/checkout')).toBe(false)
  held.resolve()
})

test('saved checkout recovery reads only that existing operation identifier', async ({ page }) => {
  const state = await fixture(page), held = deferred(); state.hold['/api/billing/status'] = held
  await page.addInitScript(() => sessionStorage.setItem('billing.operation.owner', 'saved-operation'))
  await page.goto('/auth/checkout')
  await expect.poll(() => count(state, '/api/billing/status')).toBeGreaterThan(0)
  await page.clock.fastForward(12001)
  const before = count(state, '/api/billing/status')
  delete state.hold['/api/billing/status']; state.operation = operation('saved-operation')
  await page.getByRole('button', { name: 'Recover existing checkout' }).click()
  await expect(page.getByRole('heading', { name: 'Plus', exact: true })).toBeVisible()
  expect(count(state, '/api/billing/status')).toBe(before + 1)
  expect(state.requests.filter(r => r.path.startsWith('/api/billing/')).every(r => r.path === '/api/billing/status' && r.operationId === 'saved-operation' && r.method === 'GET')).toBe(true)
  held.resolve()
})

test('checkout recovery cannot apply an obsolete account response', async ({ page }) => {
  const state = await fixture(page)
  state.failures['/api/billing/current'] = 503
  await page.goto('/auth/checkout')
  await expect(page.getByRole('button', { name: 'Recover existing checkout' })).toBeVisible()
  delete state.failures['/api/billing/current']
  const held = deferred(); state.hold['/api/billing/current'] = held
  await page.getByRole('button', { name: 'Recover existing checkout' }).click()
  await expect(page.getByRole('button', { name: 'Checking existing checkout…' })).toBeDisabled()
  delete state.hold['/api/billing/current']; state.session = session('second-owner')
  state.operation = { ...operation('second-operation'), name: 'Second plan' }
  await page.evaluate(value => {
    localStorage.setItem('sb-127-auth-token', JSON.stringify(value))
    const channel = new BroadcastChannel('sb-127-auth-token'); channel.postMessage({ event: 'SIGNED_IN', session: value }); channel.close()
  }, state.session)
  await expect(page.getByRole('heading', { name: 'Second plan', exact: true })).toBeVisible()
  held.resolve()
  await expect(page.getByRole('heading', { name: 'Plus', exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => sessionStorage.getItem('billing.operation.second-owner'))).toBe('second-operation')
  expect(state.requests.some(r => r.path.startsWith('/api/billing/') && r.method !== 'GET')).toBe(false)
})

test('known guard rejection can retry and recover without timeout sign-out', async ({ page }) => {
  const state = await fixture(page); state.failures['/api/auth/me'] = 503
  await page.goto('/auth/resume')
  await expect(page.getByRole('heading', { name: 'Unable to open your workspace' })).toBeVisible()
  delete state.failures['/api/auth/me']
  await page.getByRole('button', { name: 'Retry session check' }).click()
  await expect(page.getByTitle('owner@example.test', { exact: true })).toBeVisible()
})

test('callback account change invalidates the older verification', async ({ page }) => {
  const state = await fixture(page), held = deferred(); state.hold['/api/auth/me'] = held
  await page.goto('/auth/callback?next=%2Fauth%2Fresume')
  await expect.poll(() => count(state, '/api/auth/me')).toBe(1)
  state.session = session('second-owner')
  await page.evaluate(value => {
    localStorage.setItem('sb-127-auth-token', JSON.stringify(value))
    const channel = new BroadcastChannel('sb-127-auth-token'); channel.postMessage({ event: 'SIGNED_IN', session: value }); channel.close()
  }, state.session)
  await expect(page.getByRole('heading', { name: 'Unable to finish sign-in' })).toBeVisible()
  held.resolve()
  await expect(page).toHaveURL(/\/auth\/callback\?next=/)
  expect(count(state, '/api/auth/profile/bootstrap')).toBe(0)
})

test('reduced motion and missing artwork leave callback recovery usable', async ({ page }, info) => {
  const state = await fixture(page), held = deferred(); state.hold['/api/auth/me'] = held
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.route('**/*.{png,jpg,svg}', route => route.abort())
  await page.goto('/auth/callback')
  await expect(page.getByRole('dialog')).toBeVisible()
  expect(await page.locator('.website-progress-spinner').evaluate(node => getComputedStyle(node).animationName)).toBe('none')
  await page.clock.fastForward(15001)
  await expect(page.getByRole('link', { name: 'Back to sign in' })).toBeVisible()
  await new ProgressPage(page).capture('callback-no-images-reduced-motion', info.project.name)
  held.resolve()
})

test('actual SDK implicit token verification is not replayed by preference recovery', async ({ page }) => {
  const state = await fixture(page, { consent: true })
  state.failures['/api/auth/profile/bootstrap'] = 503
  await page.goto('/auth/callback?signup_attempt=synthetic-attempt&next=%2Fauth%2Fresume#access_token='+state.session.access_token+'&refresh_token=synthetic-refresh&token_type=bearer&expires_in=3600')
  await expect(page.getByRole('button', { name: 'Retry saving signup preferences' })).toBeVisible()
  expect(count(state, '/auth/v1/user')).toBe(1)
  expect(new URL(page.url()).hash).toBe('')
  delete state.failures['/api/auth/profile/bootstrap']
  await page.getByRole('button', { name: 'Retry saving signup preferences' }).click()
  await expect(page).toHaveURL(/\/auth\/resume$/)
  expect(count(state, '/auth/v1/user')).toBe(1)
  expect(count(state, '/auth/v1/token')).toBe(0)
  await page.clock.fastForward(15001)
  await expect(page.getByRole('heading', { name: 'Sign-in is taking longer' })).toHaveCount(0)
})

import { test, expect } from '@playwright/test'
import { mkdir } from 'node:fs/promises'

const root = '../tmp/website-batch1'
const token = `${Buffer.from('{}').toString('base64url')}.${Buffer.from(JSON.stringify({ sub: 'synthetic-owner', exp: 2524608000 })).toString('base64url')}.synthetic`

class RecoveryPage {
  constructor(page) { this.page = page }
  async capture(name, project) {
    if (process.env.WEBSITE_FALLBACK_DEV === '1') return
    await mkdir(root, { recursive: true })
    await this.page.screenshot({ path: `${root}/${name}-${project}.png`, fullPage: true })
    expect(await this.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
}

async function fixture(page, { signedIn = true, badUser = false, onboardingFailure = false, authCode = '', unsubscribeFailure = false, logoutFailure = false } = {}) {
  const state = { onboardingFailure, unsubscribeFailure, logoutFailure, unsubscribeCalls: 0, logoutCalls: 0, onboardingCalls: 0, userCalls: 0, release: null }
  await page.addInitScript(({ token, signedIn }) => {
    if (signedIn) localStorage.setItem('sb-127-auth-token', JSON.stringify({
      access_token: token, refresh_token: 'synthetic-refresh', expires_at: 2524608000,
      expires_in: 360000000, token_type: 'bearer', user: { id: 'synthetic-owner', email: 'candidate@example.test' },
    }))
  }, { token, signedIn })
  // Every non-static request is intercepted. Nothing reaches a provider/backend.
  await page.route('**/*', async route => {
    const url = new URL(route.request().url())
    const p = url.pathname
    if (url.origin === 'http://127.0.0.1:5301' && !p.startsWith('/api/')) return route.continue()
    if (p === '/auth/v1/logout') {
      state.logoutCalls++
      return route.fulfill({ status: state.logoutFailure ? 500 : 204, ...(state.logoutFailure ? { json: { msg: 'synthetic private signout failure' } } : {}) })
    }
    if (p === '/auth/v1/token') return route.fulfill({ status: 400, json: { error_code: authCode, message: 'synthetic private authentication detail' } })
    if (p === '/api/auth/me') {
      state.userCalls++
      return route.fulfill({ json: { user_id: 'synthetic-owner', email: badUser ? { private: 'synthetic render fault' } : 'candidate@example.test' } })
    }
    if (p === '/api/auth/profile/bootstrap') return route.fulfill({ json: { profile_exists: true, settings_exists: true } })
    if (p === '/api/onboarding') {
      state.onboardingCalls++
      if (state.release) await state.release
      return route.fulfill({ status: state.onboardingFailure ? 503 : 200, json: state.onboardingFailure ? { detail: 'private migration db failure' } : { onboarding_current_step: 2, onboarding_completed_at: null } })
    }
    if (p === '/api/email/unsubscribe') {
      state.unsubscribeCalls++
      if (state.release) await state.release
      return route.fulfill({ status: state.unsubscribeFailure ? 503 : 200, json: state.unsubscribeFailure ? { detail: 'private db failure' } : { success: true } })
    }
    if (p === '/api/resumes/current') return route.fulfill({ json: { ready: false, resume: null } })
    if (p === '/api/resumes/review-candidate') return route.fulfill({ json: { has_candidate: false, resume: null } })
    if (p === '/api/resumes' || p === '/api/interview-sessions' || p === '/api/job-contexts') return route.fulfill({ json: { items: [], page: 1, limit: 20 } })
    if (p.startsWith('/api/')) return route.fulfill({ status: 503, json: { detail: 'synthetic private backend detail' } })
    return route.abort()
  })
  return state
}

test('normal production startup removes static fallback', async ({ page }) => {
  await fixture(page, { signedIn: false })
  await page.goto('/auth/login')
  await expect(page.getByRole('heading', { name: 'Welcome back!', exact: true })).toBeVisible()
  await expect(page.locator('#website-startup')).toHaveCount(0)
})

test('production render fault is branded, private and keyboard recoverable', async ({ page }, info) => {
  await fixture(page, { badUser: true })
  await page.goto('/auth/resume')
  await expect(page.getByRole('heading', { name: 'This page couldn’t open' })).toBeVisible()
  await expect(page.getByRole('heading')).toBeFocused()
  await expect(page.locator('#website-startup')).toHaveCount(0)
  await expect(page.locator('body')).not.toContainText(/Unexpected Application Error|Hey developer|synthetic render fault|stack trace/)
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Return home' })).toBeFocused()
  await new RecoveryPage(page).capture('render-failure', info.project.name)
  expect(await page.getByRole('link', { name: 'Return home' }).getAttribute('href')).toBe('/')
  await page.getByRole('link', { name: 'Return home' }).click()
  await expect(page).toHaveURL('http://127.0.0.1:5301/')
  await expect(page.getByRole('heading', { name: 'This page couldn’t open' })).toHaveCount(0)
})

test('failed production entry script has static recovery', async ({ page }, info) => {
  await fixture(page, { signedIn: false })
  await page.route('**/assets/*.js', route => route.abort())
  await page.goto('/auth/login')
  await expect(page.getByRole('heading', { name: 'The website couldn’t start' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Reload page' })).toBeVisible()
  await new RecoveryPage(page).capture('entry-failure', info.project.name)
  await page.unroute('**/assets/*.js')
  await page.getByRole('link', { name: 'Reload page' }).click()
  await expect(page.getByRole('heading', { name: 'Welcome back!', exact: true })).toBeVisible()
  await expect(page.locator('#website-startup')).toHaveCount(0)
})

test('JavaScript disabled is readable without external assets', async ({ browser }, info) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: info.project.use.viewport })
  const page = await context.newPage()
  await page.route('**/*', route => new URL(route.request().url()).origin === 'http://127.0.0.1:5301' ? route.continue() : route.abort())
  await page.goto('http://127.0.0.1:5301/auth/login')
  await expect(page.getByRole('heading', { name: 'JavaScript is turned off' })).toBeVisible()
  await new RecoveryPage(page).capture('javascript-disabled', info.project.name)
  await context.close()
})

test('onboarding retry preserves saved step and fences repeat clicks', async ({ page }, info) => {
  const state = await fixture(page, { onboardingFailure: true })
  await page.goto('/auth/onboarding')
  await expect(page.getByRole('heading', { name: 'Let’s get your setup back' })).toBeVisible()
  await expect(page.locator('body')).not.toContainText(/migration|private/)
  await new RecoveryPage(page).capture('onboarding-failure', info.project.name)
  const before = state.onboardingCalls
  state.onboardingFailure = false
  let release
  state.release = new Promise(resolve => { release = resolve })
  await page.getByRole('button', { name: 'Retry onboarding' }).evaluate(button => { button.click(); button.click(); button.click() })
  await expect.poll(() => state.onboardingCalls).toBe(before + 1)
  release()
  await expect(page.getByRole('heading', { name: 'Add your CV or Resume' })).toBeVisible()
})

test('late onboarding response after navigation cannot show obsolete setup', async ({ page }) => {
  const state = await fixture(page, { onboardingFailure: true })
  await page.goto('/auth/onboarding')
  await expect(page.getByRole('button', { name: 'Retry onboarding' })).toBeVisible()
  let release
  state.release = new Promise(resolve => { release = resolve })
  state.onboardingFailure = false
  await page.getByRole('button', { name: 'Retry onboarding' }).click()
  await expect.poll(() => state.onboardingCalls).toBe(2)
  await page.evaluate(() => {
    history.pushState(null, '', '/auth/resume')
    window.dispatchEvent(new PopStateEvent('popstate'))
  })
  await expect(page.getByRole('heading', { name: 'Resumes', exact: true })).toBeVisible()
  release()
  await expect(page).toHaveURL(/\/auth\/resume$/)
  await expect(page.getByRole('heading', { name: 'Add your CV or Resume' })).toHaveCount(0)
})

for (const [code, message] of [['invalid_credentials', 'Invalid email or password.'], ['unknown_code', 'Sign-in could not be completed. Please try again.']]) {
  test(`safe authentication presentation ${code}`, async ({ page }, info) => {
    await fixture(page, { signedIn: false, authCode: code })
    await page.goto('/auth/login')
    await page.getByLabel('Email address').fill('candidate@example.test')
    await page.getByLabel('Password', { exact: true }).fill('synthetic-password')
    await page.getByRole('button', { name: 'Sign In', exact: true }).click()
    await expect(page.getByText(message, { exact: true })).toBeVisible()
    await expect(page.locator('body')).not.toContainText('synthetic private authentication detail')
    if (code === 'unknown_code') await new RecoveryPage(page).capture('safe-login-error', info.project.name)
  })
}

test('logout rejects, retries once and confirms actual completion', async ({ page }, info) => {
  const state = await fixture(page, { logoutFailure: true })
  await page.goto('/auth/logout')
  await expect(page.getByRole('heading', { name: 'Sign-out wasn’t confirmed' })).toBeVisible()
  expect(state.logoutCalls).toBe(1)
  await new RecoveryPage(page).capture('logout-failure', info.project.name)
  state.logoutFailure = false
  await page.getByRole('button', { name: 'Retry sign out' }).evaluate(button => { button.click(); button.click() })
  await expect(page.getByRole('heading', { name: 'You’re signed out', exact: true })).toBeVisible()
  // The installed SDK removes the local session even after a global request
  // fails. Retrying confirms the browser is signed out without a second call.
  expect(state.logoutCalls).toBe(1)
  expect(await page.evaluate(() => localStorage.getItem('sb-127-auth-token'))).toBeNull()
  await new RecoveryPage(page).capture('logout-complete', info.project.name)
})

test('unsubscribe scrub, bounded memory-only retry and confirmed result', async ({ page }, info) => {
  const state = await fixture(page, { signedIn: false, unsubscribeFailure: true })
  await page.goto('/unsubscribe?token=synthetic-private-link')
  await expect(page.getByRole('button', { name: 'Retry preference update' })).toBeVisible()
  expect(new URL(page.url()).searchParams.has('token')).toBe(false)
  expect(state.unsubscribeCalls).toBe(1)
  expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))).not.toContain('synthetic-private-link')
  await new RecoveryPage(page).capture('unsubscribe-failure', info.project.name)
  state.unsubscribeFailure = false
  let release
  state.release = new Promise(resolve => { release = resolve })
  await page.getByRole('button', { name: 'Retry preference update' }).evaluate(button => { button.click(); button.click() })
  await expect.poll(() => state.unsubscribeCalls).toBe(2)
  await expect(page.getByRole('heading', { name: 'Updating your preference' })).toBeVisible()
  release()
  await expect(page.getByRole('heading', { name: 'Email preference updated' })).toBeVisible()
  await expect(page.getByRole('status')).toContainText('if this link was valid')
  await new RecoveryPage(page).capture('unsubscribe-complete', info.project.name)
  await page.reload()
  await expect(page.getByRole('status')).toContainText('Reopen the original unsubscribe link')
  expect(state.unsubscribeCalls).toBe(2)
  await new RecoveryPage(page).capture('unsubscribe-link-lost', info.project.name)
})

test('unsubscribe does not mistake an unconfirmed result for success', async ({ page }) => {
  await fixture(page, { signedIn: false })
  await page.route('**/api/email/unsubscribe', route => route.fulfill({ json: { success: false } }))
  await page.goto('/unsubscribe?token=synthetic-invalid-link')
  await expect(page.getByRole('status')).toContainText('This link couldn’t update your preference')
  await expect(page.getByRole('heading', { name: 'Email preference updated' })).toHaveCount(0)
})

test('images blocked and runtime chunk failure retain recovery', async ({ page }, info) => {
  await fixture(page, { signedIn: false })
  await page.route('**/*.{png,jpg,svg}', route => route.abort())
  await page.goto('/auth/login')
  await expect(page.locator('#website-startup')).toHaveCount(0)
  await page.evaluate(() => window.dispatchEvent(new Event('vite:preloadError', { cancelable: true })))
  await expect(page.getByRole('heading', { name: 'This page couldn’t open' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Return home' })).toBeVisible()
  await new RecoveryPage(page).capture('images-blocked', info.project.name)
})

test('slow entry remains honest until a module failure is detected', async ({ page }) => {
  await fixture(page, { signedIn: false })
  await page.clock.install()
  let release
  const pending = new Promise(resolve => { release = resolve })
  await page.route('**/assets/*.js', async route => { await pending; await route.abort() })
  await page.goto('/auth/login', { waitUntil: 'commit' })
  await expect(page.getByRole('heading', { name: 'Opening your workspace' })).toBeVisible()
  await page.clock.fastForward(60000)
  await expect(page.getByRole('heading', { name: 'Opening your workspace' })).toBeVisible()
  release()
  await expect(page.getByRole('heading', { name: 'The website couldn’t start' })).toBeVisible()
})

test('unsubscribe stops after three attempts and expires its in-memory retry', async ({ page }) => {
  const state = await fixture(page, { signedIn: false, unsubscribeFailure: true })
  await page.clock.install()
  await page.goto('/unsubscribe?token=synthetic-private-link')
  for (let i = 0; i < 2; i++) {
    await page.getByRole('button', { name: 'Retry preference update' }).click()
  }
  await expect(page.getByRole('status')).toContainText('Reopen the original unsubscribe link')
  expect(state.unsubscribeCalls).toBe(3)
  await page.goto('/unsubscribe?token=synthetic-second-link')
  await expect(page.getByRole('button', { name: 'Retry preference update' })).toBeVisible()
  await page.clock.fastForward(15 * 60 * 1000)
  await expect(page.getByRole('button', { name: 'Retry preference update' })).toHaveCount(0)
  await expect(page.getByRole('status')).toContainText('Reopen the original unsubscribe link')
})

test('sign-out during a held onboarding read cannot restore the previous account', async ({ page }) => {
  const state = await fixture(page, { onboardingFailure: true })
  await page.goto('/auth/onboarding')
  await expect(page.getByRole('button', { name: 'Retry onboarding' })).toBeVisible()
  let release
  state.release = new Promise(resolve => { release = resolve })
  state.onboardingFailure = false
  await page.getByRole('button', { name: 'Retry onboarding' }).click()
  await expect.poll(() => state.onboardingCalls).toBe(2)
  await page.evaluate(() => {
    localStorage.removeItem('sb-127-auth-token')
    const channel = new BroadcastChannel('sb-127-auth-token')
    channel.postMessage({ event: 'SIGNED_OUT', session: null })
    channel.close()
  })
  await expect(page).toHaveURL(url => url.pathname === '/auth/login' && url.searchParams.get('next') === '/auth/dashboard')
  release()
  await expect(page.getByRole('heading', { name: 'Add your CV or Resume' })).toHaveCount(0)
  await expect(page).toHaveURL(url => url.pathname === '/auth/login' && url.searchParams.get('next') === '/auth/dashboard')
})

test('account verification and resume failures hide technical details', async ({ page }, info) => {
  await fixture(page)
  await page.route('**/api/auth/me', route => route.fulfill({ status: 503, json: { detail: 'private infrastructure failure' } }))
  await page.goto('/auth/dashboard')
  await expect(page.getByRole('status')).toHaveText('We could not verify your account. Please try again.')
  await expect(page.locator('body')).not.toContainText('private infrastructure')
  await new RecoveryPage(page).capture('safe-account-error', info.project.name)
  await page.unroute('**/api/auth/me')
  await page.route('**/api/resumes/current', route => route.fulfill({ status: 503, json: { detail: 'private resume service failure' } }))
  await page.goto('/auth/resume')
  await expect(page.getByRole('alert')).toHaveText('We could not load your resume. Please try again.')
  await expect(page.locator('body')).not.toContainText('private resume service')
  await new RecoveryPage(page).capture('safe-resume-error', info.project.name)
})

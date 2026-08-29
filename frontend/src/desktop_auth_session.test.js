import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
import test from 'node:test'
import vm from 'node:vm'

const require = createRequire(import.meta.url)
const {
  AUTH_STATUSES,
  CALLBACK_URL,
  DesktopAuthSessionManager,
  createIpcSenderValidator,
} = require('../electron/desktop_auth_session.cjs')

function jsonResponse(status, payload = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  }
}

function createSafeStorage(available = true) {
  return {
    isEncryptionAvailable: () => available,
    encryptString: (value) => Buffer.from(`encrypted:${Buffer.from(value).toString('base64')}`),
    decryptString: (buffer) => {
      const raw = Buffer.from(buffer).toString()
      return Buffer.from(raw.replace(/^encrypted:/, ''), 'base64').toString()
    },
  }
}

function createManager(options = {}) {
  const calls = []
  const opened = []
  const dir = mkdtempSync(path.join(tmpdir(), 'saiia-auth-test-'))
  const manager = new DesktopAuthSessionManager({
    supabaseUrl: 'https://project.supabase.co',
    supabaseAnonKey: 'anon-key',
    webAuthUrl: 'http://localhost:5173/auth/desktop-login',
    backendUrl: 'http://localhost:8000',
    sessionPath: path.join(dir, 'session.bin'),
    safeStorage: createSafeStorage(true),
    logger: { debug: () => {} },
    openExternal: async (url) => {
      opened.push(url)
    },
    fetchImpl: async (url, init = {}) => {
      calls.push({ url, init })
      if (url.includes('/auth/v1/token?grant_type=pkce')) {
        return jsonResponse(200, {
          access_token: 'access-token',
          refresh_token: 'refresh-token',
        })
      }
      if (url.endsWith('/api/auth/desktop-handoff/exchange')) {
        return jsonResponse(200, {
          access_token: 'handoff-access-token',
          refresh_token: 'handoff-refresh-token',
        })
      }
      if (url.endsWith('/api/auth/me')) {
        return jsonResponse(200, {
          user_id: options.userId || 'user-1',
          email: 'user@example.com',
          access_token: 'must-not-leak',
        })
      }
      if (url.endsWith('/api/auth/profile/bootstrap')) {
        return jsonResponse(options.bootstrapStatus || 200, { ok: true })
      }
      if (url.includes('/api/interview-sessions?')) {
        return jsonResponse(200, {
          items: [
            {
              id: 'session-1',
              status: 'ended',
              started_at: '2026-08-28T00:00:00Z',
              ended_at: '2026-08-28T00:10:00Z',
              title: 'Design interview',
              target_role: 'Frontend Engineer',
              company_name: 'Acme',
            },
          ],
          limit: 20,
          page: 1,
        })
      }
      if (url.endsWith('/api/interview-sessions')) {
        return jsonResponse(201, {
          session: {
            id: 'session-1',
            status: 'active',
            started_at: '2026-08-28T00:00:00Z',
            ended_at: null,
            selected_resume_id: 'resume-1',
            title: 'Design interview',
            target_role: 'Frontend Engineer',
            company_name: 'Acme',
          },
          replayed: false,
        })
      }
      if (url.includes('/api/interview-sessions/') && url.endsWith('/end')) {
        return jsonResponse(200, {
          id: 'session-1',
          status: 'ended',
          started_at: '2026-08-28T00:00:00Z',
          ended_at: '2026-08-28T00:10:00Z',
          selected_resume_id: 'resume-1',
          title: 'Design interview',
          target_role: 'Frontend Engineer',
          company_name: 'Acme',
        })
      }
      if (url.includes('/auth/v1/token?grant_type=refresh_token')) {
        return jsonResponse(options.refreshStatus || 200, {
          access_token: 'refreshed-access-token',
          refresh_token: 'refreshed-refresh-token',
        })
      }
      if (url.includes('/auth/v1/logout')) {
        if (options.logoutThrows) {
          throw new Error('network down')
        }
        return jsonResponse(200, {})
      }
      return jsonResponse(500, {})
    },
    ...options,
  })

  return {
    calls,
    dir,
    manager,
    opened,
    cleanup: () => rmSync(dir, { recursive: true, force: true }),
  }
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((nextResolve, nextReject) => {
    resolve = nextResolve
    reject = nextReject
  })
  return { promise, resolve, reject }
}

function abortError() {
  const error = new Error('The operation was aborted.')
  error.name = 'AbortError'
  return error
}

function callbackUrlFor(manager, params = {}) {
  const url = new URL(CALLBACK_URL)
  if (
    manager?.pendingLogin?.state &&
    (params.code || params.error) &&
    !('state' in params) &&
    !('desktop_state' in params)
  ) {
    url.searchParams.set('state', manager.pendingLogin.state)
  }
  Object.entries(params).forEach(([key, value]) => url.searchParams.set(key, value))
  return url.toString()
}

test('auth duration options accept only positive finite values', () => {
  const invalidValues = [undefined, null, '', 0, '0', -1, '-1', Number.NaN, 'NaN', Infinity, 'Infinity']
  for (const value of invalidValues) {
    const ctx = createManager({ loginTtlMs: value, requestTimeoutMs: value })
    try {
      assert.equal(ctx.manager.loginTtlMs, 10 * 60 * 1000)
      assert.equal(ctx.manager.requestTimeoutMs, 15000)
    } finally {
      ctx.cleanup()
    }
  }

  const numeric = createManager({ loginTtlMs: 1234, requestTimeoutMs: 5678 })
  try {
    assert.equal(numeric.manager.loginTtlMs, 1234)
    assert.equal(numeric.manager.requestTimeoutMs, 5678)
  } finally {
    numeric.cleanup()
  }

  const numericStrings = createManager({ loginTtlMs: '2345', requestTimeoutMs: '6789' })
  try {
    assert.equal(numericStrings.manager.loginTtlMs, 2345)
    assert.equal(numericStrings.manager.requestTimeoutMs, 6789)
  } finally {
    numericStrings.cleanup()
  }
})

test('desktop auth persists session only through encrypted safeStorage path', async () => {
  const ctx = createManager()
  try {
    await ctx.manager.startLogin()
    await ctx.manager.handleAuthCallback(callbackUrlFor(ctx.manager, { code: 'auth-code' }))

    const stored = readFileSync(ctx.manager.sessionPath, 'utf8')
    assert.match(stored, /^encrypted:/)
    assert.doesNotMatch(stored, /refresh-token|access-token/)
    assert.equal(ctx.manager.getSafeState().status, AUTH_STATUSES.CONNECTED)
    assert.equal('access_token' in ctx.manager.getSafeState(), false)
  } finally {
    ctx.cleanup()
  }
})

test('safeStorage unavailable keeps session-only login without plaintext persistence', async () => {
  const ctx = createManager({ safeStorage: createSafeStorage(false) })
  try {
    await ctx.manager.startLogin()
    const state = await ctx.manager.handleAuthCallback(callbackUrlFor(ctx.manager, { code: 'auth-code' }))

    assert.equal(state.status, AUTH_STATUSES.CONNECTED)
    assert.equal(ctx.manager.session.refresh_token, 'refresh-token')
    assert.equal(ctx.manager.getSafeState().safeStorageAvailable, false)
    assert.throws(() => readFileSync(ctx.manager.sessionPath, 'utf8'))
  } finally {
    ctx.cleanup()
  }
})

test('startLogin requires website handoff config and fails safely when browser launch is unavailable', async () => {
  const missingWebsiteUrl = createManager({ webAuthUrl: '' })
  try {
    const state = await missingWebsiteUrl.manager.startLogin()
    assert.equal(state.status, AUTH_STATUSES.SIGNED_OUT)
    assert.match(state.error, /Desktop cloud auth is not configured\./)
    assert.match(state.error, /SAIIA_WEB_AUTH_URL/)
    assert.doesNotMatch(state.error, /SAIIA_DESKTOP_AUTH_PROVIDER/)
    assert.equal(missingWebsiteUrl.manager.pendingLogin, null)
  } finally {
    missingWebsiteUrl.cleanup()
  }

  const unsafeWebsiteUrl = createManager({ webAuthUrl: 'saiia://auth/callback' })
  try {
    const state = await unsafeWebsiteUrl.manager.startLogin()
    assert.equal(state.status, AUTH_STATUSES.SIGNED_OUT)
    assert.match(state.error, /Desktop cloud auth is not configured\./)
    assert.equal(unsafeWebsiteUrl.manager.pendingLogin, null)
    assert.equal(unsafeWebsiteUrl.opened.length, 0)
  } finally {
    unsafeWebsiteUrl.cleanup()
  }

  const browserFailure = createManager({
    openExternal: async () => {
      throw new Error('browser failed')
    },
  })
  try {
    const state = await browserFailure.manager.startLogin()
    assert.equal(state.status, AUTH_STATUSES.SIGNED_OUT)
    assert.equal(state.error, 'Could not open browser for login.')
    assert.equal(browserFailure.manager.pendingLogin, null)
  } finally {
    browserFailure.cleanup()
  }
})

test('duplicate login while pending reuses one auth attempt without opening stale URLs', async () => {
  const firstOpen = deferred()
  let firstLogin = null
  const ctx = createManager({
    openExternal: async (url) => {
      ctx.opened.push(url)
      await firstOpen.promise
    },
  })
  try {
    firstLogin = ctx.manager.startLogin()
    const firstAttempt = ctx.manager.pendingLogin.attempt_generation
    const secondState = await ctx.manager.startLogin()
    const secondAttempt = ctx.manager.pendingLogin.attempt_generation

    assert.equal(secondState.status, AUTH_STATUSES.SIGNING_IN)
    assert.equal(firstAttempt, secondAttempt)
    assert.equal(ctx.opened.length, 1)

    firstOpen.resolve()
    const staleState = await firstLogin
    assert.equal(staleState.status, AUTH_STATUSES.SIGNING_IN)
    assert.equal(ctx.manager.pendingLogin.attempt_generation, firstAttempt)
  } finally {
    firstOpen.resolve()
    if (firstLogin) {
      await firstLogin.catch(() => {})
    }
    ctx.cleanup()
  }
})

test('startLogin opens website desktop-login handoff URL and redacts auth debug details', async () => {
  const debugLogs = []
  const ctx = createManager({
    logger: {
      debug: (message, payload) => debugLogs.push({ message, payload }),
    },
  })
  try {
    await ctx.manager.startLogin()
    const authUrl = new URL(ctx.opened[0])
    const pendingState = ctx.manager.pendingLogin.state

    assert.equal(ctx.manager.getSafeState().status, AUTH_STATUSES.SIGNING_IN)
    assert.notEqual(ctx.manager.pendingLogin, null)
    assert.equal(authUrl.origin, 'http://localhost:5173')
    assert.equal(authUrl.pathname, '/auth/desktop-login')
    assert.notEqual(authUrl.origin, 'https://accounts.google.com')
    assert.equal(authUrl.searchParams.get('state'), pendingState)
    assert.equal(authUrl.searchParams.has('provider'), false)
    assert.equal(authUrl.searchParams.has('code_challenge'), false)
    assert.equal(authUrl.searchParams.has('code_challenge_method'), false)
    assert.equal(authUrl.searchParams.has('redirect_to'), false)
    assert.equal(authUrl.searchParams.has('redirect_uri'), false)
    assert.equal(debugLogs.length, 1)
    assert.equal(debugLogs[0].message, 'Desktop auth website handoff URL prepared.')
    assert.deepEqual(debugLogs[0].payload, {
      origin: 'http://localhost:5173',
      path: '/auth/desktop-login',
      queryKeys: ['state'],
      stateExists: true,
      pendingAttemptId: ctx.manager.pendingLogin.attempt_generation,
    })
    assert.equal('url' in debugLogs[0].payload, false)
    assert.equal(JSON.stringify(debugLogs[0].payload).includes(CALLBACK_URL), false)
    assert.equal(JSON.stringify(debugLogs[0].payload).includes(pendingState), false)
    assert.equal(JSON.stringify(debugLogs[0].payload).includes(ctx.manager.pendingLogin.code_challenge), false)
    assert.equal(ctx.calls.some((call) => call.url.includes('/auth/v1/authorize')), false)
  } finally {
    ctx.cleanup()
  }
})

test('handoff callback exchanges one-time code through backend and verifies bootstrap', async () => {
  const ctx = createManager()
  try {
    await ctx.manager.startLogin()
    const pendingState = ctx.manager.pendingLogin.state
    const result = await ctx.manager.handleAuthCallback(
      callbackUrlFor(ctx.manager, { handoff_code: 'handoff-code-1234567890', state: pendingState }),
    )

    assert.equal(result.status, AUTH_STATUSES.CONNECTED)
    assert.equal(ctx.manager.session.access_token, 'handoff-access-token')
    assert.equal(ctx.manager.session.refresh_token, 'handoff-refresh-token')

    const exchange = ctx.calls.find((call) => call.url.endsWith('/api/auth/desktop-handoff/exchange'))
    assert.notEqual(exchange, undefined)
    assert.deepEqual(JSON.parse(exchange.init.body), {
      handoff_code: 'handoff-code-1234567890',
      state: pendingState,
    })
    assert.notEqual(exchange.init.signal, undefined)
    assert.equal(ctx.calls.some((call) => call.url.includes('grant_type=pkce')), false)

    const me = ctx.calls.find((call) => call.url.endsWith('/api/auth/me'))
    const bootstrap = ctx.calls.find((call) => call.url.endsWith('/api/auth/profile/bootstrap'))
    assert.equal(me.init.headers.Authorization, 'Bearer handoff-access-token')
    assert.equal(bootstrap.init.headers.Authorization, 'Bearer handoff-access-token')
  } finally {
    ctx.cleanup()
  }
})

test('handoff callback requires matching desktop state before exchange', async () => {
  const ctx = createManager()
  try {
    await ctx.manager.startLogin()

    let result = await ctx.manager.handleAuthCallback(callbackUrlFor(ctx.manager, { handoff_code: 'handoff-code' }))
    assert.equal(result.status, AUTH_STATUSES.SIGNED_OUT)
    assert.equal(result.error, 'Invalid authentication callback.')
    assert.equal(ctx.calls.some((call) => call.url.endsWith('/api/auth/desktop-handoff/exchange')), false)

    await ctx.manager.startLogin()
    result = await ctx.manager.handleAuthCallback(
      callbackUrlFor(ctx.manager, { handoff_code: 'handoff-code', state: 'wrong-state' }),
    )
    assert.equal(result.status, AUTH_STATUSES.SIGNING_IN)
    assert.equal(result.error, 'Invalid or expired authentication attempt.')
    assert.equal(ctx.calls.some((call) => call.url.endsWith('/api/auth/desktop-handoff/exchange')), false)
  } finally {
    ctx.cleanup()
  }
})

test('PKCE exchange rejects malformed token sessions before persisting or connecting', async () => {
  const malformedResponses = [
    { refresh_token: 'refresh-token' },
    { access_token: null, refresh_token: 'refresh-token' },
    { access_token: '', refresh_token: 'refresh-token' },
    { access_token: '   ', refresh_token: 'refresh-token' },
    { access_token: 123, refresh_token: 'refresh-token' },
    { access_token: 'access-token' },
    { access_token: 'access-token', refresh_token: null },
    { access_token: 'access-token', refresh_token: '' },
    { access_token: 'access-token', refresh_token: '   ' },
    { access_token: 'access-token', refresh_token: 123 },
  ]

  for (const payload of malformedResponses) {
    const ctx = createManager({
      fetchImpl: async (url, init = {}) => {
        ctx.calls.push({ url, init })
        if (url.includes('/auth/v1/token?grant_type=pkce')) {
          return jsonResponse(200, payload)
        }
        return jsonResponse(200, { user_id: 'user-1', email: 'user@example.com' })
      },
    })
    try {
      await ctx.manager.startLogin()
      const state = await ctx.manager.handleAuthCallback(callbackUrlFor(ctx.manager, { code: 'auth-code' }))

      assert.equal(state.status, AUTH_STATUSES.SIGNED_OUT)
      assert.equal(state.error, 'Authentication exchange failed.')
      assert.equal(ctx.manager.session, null)
      assert.equal(ctx.manager.user, null)
      assert.equal(existsSync(ctx.manager.sessionPath), false)
      assert.equal(ctx.calls.some((call) => call.url.endsWith('/api/auth/me')), false)
    } finally {
      ctx.cleanup()
    }
  }
})

test('request exchange rejects code challenge method, redirect, and verifier mismatches', async () => {
  const ctx = createManager()
  try {
    await ctx.manager.startLogin()
    await assert.rejects(
      () => ctx.manager._exchangeCode('code', { ...ctx.manager.pendingLogin, code_challenge_method: 'plain' }),
      /Invalid authentication request/,
    )
    await assert.rejects(
      () => ctx.manager._exchangeCode('code', { ...ctx.manager.pendingLogin, redirect_uri: 'saiia://bad/callback' }),
      /Invalid authentication request/,
    )

    await assert.rejects(
      () => ctx.manager._exchangeCode('code', { ...ctx.manager.pendingLogin, code_verifier: 'tampered-verifier' }),
      /Invalid authentication request/,
    )
  } finally {
    ctx.cleanup()
  }
})

test('callback rejects missing code, mismatched state, expired attempt, and reused callback', async () => {
  const ctx = createManager({ now: () => 1000, loginTtlMs: 100 })
  try {
    let result = await ctx.manager.handleAuthCallback(`${CALLBACK_URL}?code=auth-code&desktop_state=orphaned`)
    assert.equal(result.status, AUTH_STATUSES.SIGNED_OUT)
    assert.equal(result.error, 'Invalid or expired authentication attempt.')
    assert.equal(ctx.calls.some((call) => call.url.includes('grant_type=pkce')), false)

    await ctx.manager.startLogin()
    result = await ctx.manager.handleAuthCallback(callbackUrlFor(ctx.manager))
    assert.equal(result.status, AUTH_STATUSES.SIGNED_OUT)
    assert.equal(result.error, 'Invalid authentication callback.')

    await ctx.manager.startLogin()
    const activePending = ctx.manager.pendingLogin
    result = await ctx.manager.handleAuthCallback(`${CALLBACK_URL}?code=auth-code`)
    assert.equal(result.status, AUTH_STATUSES.SIGNING_IN)
    assert.equal(result.error, 'Invalid or expired authentication attempt.')
    assert.equal(ctx.manager.pendingLogin, activePending)
    assert.equal(ctx.calls.some((call) => call.url.includes('grant_type=pkce')), false)

    await ctx.manager.startLogin()
    result = await ctx.manager.handleAuthCallback(`${CALLBACK_URL}?code=auth-code&desktop_state=wrong`)
    assert.equal(result.status, AUTH_STATUSES.SIGNING_IN)
    assert.equal(result.error, 'Invalid or expired authentication attempt.')

    ctx.manager.now = () => 2000
    await ctx.manager.startLogin()
    ctx.manager.pendingLogin.expires_at = 1500
    result = await ctx.manager.handleAuthCallback(callbackUrlFor(ctx.manager, { code: 'auth-code' }))
    assert.equal(result.status, AUTH_STATUSES.SIGNED_OUT)
    assert.equal(result.error, 'Invalid or expired authentication attempt.')

    ctx.manager.now = () => 1000
    await ctx.manager.startLogin()
    const url = callbackUrlFor(ctx.manager, { code: 'auth-code' })
    const exchangeCountAfterFirst = () => ctx.calls.filter((call) => call.url.includes('grant_type=pkce')).length
    assert.equal((await ctx.manager.handleAuthCallback(url)).status, AUTH_STATUSES.CONNECTED)
    const firstExchangeCount = exchangeCountAfterFirst()
    result = await ctx.manager.handleAuthCallback(url)
    assert.equal(result.status, AUTH_STATUSES.CONNECTED)
    assert.equal(result.error, 'Invalid or expired authentication attempt.')
    assert.equal(exchangeCountAfterFirst(), firstExchangeCount)
  } finally {
    ctx.cleanup()
  }
})

test('bad_oauth_state callback clears pending login with a safe retry message', async () => {
  const ctx = createManager()
  try {
    await ctx.manager.startLogin()
    assert.notEqual(ctx.manager.pendingLogin, null)

    const result = await ctx.manager.handleAuthCallback(
      `${CALLBACK_URL}?error=invalid_request&error_code=bad_oauth_state&error_description=OAuth+state+parameter+is+invalid`,
    )

    assert.equal(result.status, AUTH_STATUSES.SIGNED_OUT)
    assert.equal(result.user_id, null)
    assert.equal(result.email, null)
    assert.equal(result.error, 'Authentication state was rejected. Start login again.')
    assert.equal(ctx.manager.pendingLogin, null)
    assert.equal(ctx.calls.some((call) => call.url.includes('grant_type=pkce')), false)
  } finally {
    ctx.cleanup()
  }
})

test('localhost code callback is rejected as wrong desktop callback and resets login', async () => {
  const ctx = createManager()
  try {
    await ctx.manager.startLogin()
    assert.notEqual(ctx.manager.pendingLogin, null)

    const result = await ctx.manager.handleAuthCallback('http://localhost:5173/?code=auth-code')

    assert.equal(result.status, AUTH_STATUSES.SIGNED_OUT)
    assert.equal(result.user_id, null)
    assert.equal(result.email, null)
    assert.equal(result.error, 'Desktop auth returned to localhost. Add saiia://auth/callback to Supabase redirect URLs and start login again.')
    assert.equal(ctx.manager.pendingLogin, null)
    assert.equal(ctx.calls.some((call) => call.url.includes('grant_type=pkce')), false)
  } finally {
    ctx.cleanup()
  }
})

test('authorization denial consumes pending login and skips token exchange', async () => {
  const ctx = createManager()
  try {
    await ctx.manager.startLogin()
    const state = ctx.manager.pendingLogin.state
    const result = await ctx.manager.handleAuthCallback(`${CALLBACK_URL}?error=access_denied&desktop_state=${state}`)

    assert.equal(result.status, AUTH_STATUSES.SIGNED_OUT)
    assert.equal(result.user_id, null)
    assert.equal(result.email, null)
    assert.equal(ctx.manager.pendingLogin, null)
    assert.equal(ctx.calls.some((call) => call.url.includes('grant_type=pkce')), false)
  } finally {
    ctx.cleanup()
  }
})

test('authorization denial restores an existing connected session without token exchange', async () => {
  const ctx = createManager()
  try {
    ctx.manager.session = { access_token: 'existing-access', refresh_token: 'existing-refresh' }
    ctx.manager.user = { user_id: 'user-1', email: 'user@example.com' }
    ctx.manager.status = AUTH_STATUSES.CONNECTED
    await ctx.manager.startLogin()
    const state = ctx.manager.pendingLogin.state
    const result = await ctx.manager.handleAuthCallback(`${CALLBACK_URL}?error=access_denied&desktop_state=${state}`)

    assert.equal(result.status, AUTH_STATUSES.CONNECTED)
    assert.equal(result.user_id, 'user-1')
    assert.equal(ctx.calls.some((call) => call.url.includes('grant_type=pkce')), false)
  } finally {
    ctx.cleanup()
  }
})

test('expired old login attempts are rejected before a fresh callback can commit', async () => {
  const exchange = deferred()
  let activePromise = null
  const ctx = createManager({
    now: () => 1000,
    fetchImpl: async (url, init = {}) => {
      ctx.calls.push({ url, init })
      if (url.includes('grant_type=pkce')) {
        await exchange.promise
        return jsonResponse(200, {
          access_token: 'old-access-token',
          refresh_token: 'old-refresh-token',
        })
      }
      return jsonResponse(200, { user_id: 'user-1', email: 'user@example.com' })
    },
  })
  try {
    await ctx.manager.startLogin()
    const oldState = ctx.manager.pendingLogin.state
    const oldUrl = callbackUrlFor(ctx.manager, { code: 'old-code', desktop_state: oldState })
    ctx.manager.pendingLogin.expires_at = 900
    await ctx.manager.startLogin()
    assert.equal((await ctx.manager.handleAuthCallback(oldUrl)).status, AUTH_STATUSES.SIGNING_IN)

    const activeUrl = callbackUrlFor(ctx.manager, { code: 'active-code' })
    activePromise = ctx.manager.handleAuthCallback(activeUrl)
    exchange.resolve()
    const activeState = await activePromise
    assert.equal(activeState.status, AUTH_STATUSES.CONNECTED)
    assert.notEqual(ctx.manager.session, null)
  } finally {
    exchange.resolve()
    if (activePromise) {
      await activePromise.catch(() => {})
    }
    ctx.cleanup()
  }
})

test('account switch clears previous user and cache while new session is verifying', async () => {
  const meStarted = deferred()
  const meGate = deferred()
  let callbackPromise = null
  const ctx = createManager({
    fetchImpl: async (url, init = {}) => {
      ctx.calls.push({ url, init })
      if (url.includes('/auth/v1/token?grant_type=pkce')) {
        return jsonResponse(200, {
          access_token: 'new-access-token',
          refresh_token: 'new-refresh-token',
        })
      }
      if (url.endsWith('/api/auth/me')) {
        meStarted.resolve()
        await meGate.promise
        return jsonResponse(200, { user_id: 'user-2', email: 'two@example.com' })
      }
      if (url.endsWith('/api/auth/profile/bootstrap')) {
        return jsonResponse(200, { ok: true })
      }
      return jsonResponse(200, {})
    },
  })
  try {
    ctx.manager.session = { access_token: 'old-access-token', refresh_token: 'old-refresh-token' }
    ctx.manager.user = { user_id: 'user-1', email: 'one@example.com' }
    ctx.manager.status = AUTH_STATUSES.CONNECTED
    ctx.manager.sessionGeneration = 7
    ctx.manager.cloudCache.profile = { full_name: 'Old User' }
    const captured = ctx.manager.captureCloudRequestContext()

    await ctx.manager.startLogin()
    callbackPromise = ctx.manager.handleAuthCallback(callbackUrlFor(ctx.manager, { code: 'auth-code' }))
    await meStarted.promise

    assert.equal(ctx.manager.session.access_token, 'new-access-token')
    assert.equal(ctx.manager.user, null)
    assert.equal(ctx.manager.cloudCache.profile, null)
    assert.equal(ctx.manager.writeCloudCache(captured, { profile: { full_name: 'Stale User' } }), false)

    meGate.resolve()
    const state = await callbackPromise
    assert.equal(state.status, AUTH_STATUSES.CONNECTED)
    assert.equal(state.user_id, 'user-2')
  } finally {
    meStarted.resolve()
    meGate.resolve()
    if (callbackPromise) {
      await callbackPromise.catch(() => {})
    }
    ctx.cleanup()
  }
})

test('backend verification uses bearer token and bootstrap always follows auth verification', async () => {
  const ctx = createManager()
  try {
    await ctx.manager.startLogin()
    await ctx.manager.handleAuthCallback(callbackUrlFor(ctx.manager, { code: 'auth-code' }))

    const me = ctx.calls.find((call) => call.url.endsWith('/api/auth/me'))
    const bootstrap = ctx.calls.find((call) => call.url.endsWith('/api/auth/profile/bootstrap'))
    const meIndex = ctx.calls.findIndex((call) => call.url.endsWith('/api/auth/me'))
    const bootstrapIndex = ctx.calls.findIndex((call) => call.url.endsWith('/api/auth/profile/bootstrap'))
    assert.equal(me.init.headers.Authorization, 'Bearer access-token')
    assert.equal(bootstrap.init.method, 'POST')
    assert.equal(bootstrap.init.headers.Authorization, 'Bearer access-token')
    assert.equal(meIndex < bootstrapIndex, true)
  } finally {
    ctx.cleanup()
  }
})

test('backend verification rejects malformed user identity and clears session cache', async () => {
  const invalidPayloads = [
    {},
    { user_id: null, email: 'user@example.com' },
    { user_id: '', email: 'user@example.com' },
    { user_id: '   ', email: 'user@example.com' },
  ]

  for (const payload of invalidPayloads) {
    const ctx = createManager({
      fetchImpl: async (url, init = {}) => {
        ctx.calls.push({ url, init })
        if (url.endsWith('/api/auth/me')) {
          return jsonResponse(200, payload)
        }
        if (url.endsWith('/api/auth/profile/bootstrap')) {
          return jsonResponse(200, { ok: true })
        }
        return jsonResponse(200, {})
      },
    })
    try {
      ctx.manager.session = { access_token: 'access-token', refresh_token: 'refresh-token' }
      ctx.manager.user = { user_id: 'previous-user', email: 'previous@example.com' }
      ctx.manager.status = AUTH_STATUSES.CONNECTED
      ctx.manager.cloudCache.profile = { full_name: 'Previous User' }
      ctx.manager._writeStoredSession(ctx.manager.session)

      const state = await ctx.manager._verifyAndBootstrap(ctx.manager.session)

      assert.equal(state.status, AUTH_STATUSES.SIGNED_OUT)
      assert.equal(state.user_id, null)
      assert.equal(state.email, null)
      assert.equal(state.error, 'Backend authentication failed.')
      assert.equal(ctx.manager.session, null)
      assert.equal(ctx.manager.user, null)
      assert.equal(ctx.manager.cloudCache.profile, null)
      assert.equal(existsSync(ctx.manager.sessionPath), false)
      assert.equal(ctx.calls.some((call) => call.url.endsWith('/api/auth/profile/bootstrap')), false)
    } finally {
      ctx.cleanup()
    }
  }
})

test('bootstrap 502 maps to bootstrap-failed instead of invalid session', async () => {
  const ctx = createManager({ bootstrapStatus: 502 })
  try {
    await ctx.manager.startLogin()
    const state = await ctx.manager.handleAuthCallback(callbackUrlFor(ctx.manager, { code: 'auth-code' }))
    assert.equal(state.status, AUTH_STATUSES.BOOTSTRAP_FAILED)
    assert.equal(ctx.manager.session.refresh_token, 'refresh-token')
  } finally {
    ctx.cleanup()
  }
})

test('verification ignores stale session after logout during auth-me request', async () => {
  const meGate = deferred()
  const session = { access_token: 'access-token', refresh_token: 'refresh-token' }
  let pendingPromise = null
  const ctx = createManager({
    fetchImpl: async (url, init = {}) => {
      ctx.calls.push({ url, init })
      if (url.endsWith('/api/auth/me')) {
        await meGate.promise
        return jsonResponse(200, { user_id: 'user-1', email: 'user@example.com' })
      }
      return jsonResponse(200, {})
    },
  })
  try {
    ctx.manager.session = session
    pendingPromise = ctx.manager._verifyAndBootstrap(session)
    await ctx.manager.logout()
    meGate.resolve()
    const state = await pendingPromise

    assert.equal(state.status, AUTH_STATUSES.SIGNED_OUT)
    assert.equal(state.user_id, null)
    assert.equal(ctx.manager.user, null)
  } finally {
    meGate.resolve()
    if (pendingPromise) {
      await pendingPromise.catch(() => {})
    }
    ctx.cleanup()
  }
})

test('verification ignores stale session after logout during bootstrap request', async () => {
  const bootstrapGate = deferred()
  const bootstrapStarted = deferred()
  const session = { access_token: 'access-token', refresh_token: 'refresh-token' }
  let pendingPromise = null
  const ctx = createManager({
    fetchImpl: async (url, init = {}) => {
      ctx.calls.push({ url, init })
      if (url.endsWith('/api/auth/me')) {
        return jsonResponse(200, { user_id: 'user-1', email: 'user@example.com' })
      }
      if (url.endsWith('/api/auth/profile/bootstrap')) {
        bootstrapStarted.resolve()
        await bootstrapGate.promise
        return jsonResponse(200, { ok: true })
      }
      return jsonResponse(200, {})
    },
  })
  try {
    ctx.manager.session = session
    pendingPromise = ctx.manager._verifyAndBootstrap(session)
    await bootstrapStarted.promise
    await ctx.manager.logout()
    bootstrapGate.resolve()
    const state = await pendingPromise

    assert.equal(state.status, AUTH_STATUSES.SIGNED_OUT)
    assert.equal(state.user_id, null)
    assert.equal(ctx.manager.user, null)
  } finally {
    bootstrapStarted.resolve()
    bootstrapGate.resolve()
    if (pendingPromise) {
      await pendingPromise.catch(() => {})
    }
    ctx.cleanup()
  }
})

test('401 clears invalid session while 503 refresh preserves valid secure session and cache', async () => {
  const expired = createManager({ refreshStatus: 401 })
  try {
    expired.manager.session = { access_token: 'old-access', refresh_token: 'old-refresh' }
    expired.manager.user = { user_id: 'user-1', email: 'user@example.com' }
    expired.manager.cloudCache.profile = { full_name: 'Old User' }
    expired.manager._writeStoredSession(expired.manager.session)
    assert.equal(existsSync(expired.manager.sessionPath), true)
    const state = await expired.manager.refreshSession()
    assert.equal(state.status, AUTH_STATUSES.TOKEN_EXPIRED)
    assert.equal(expired.manager.session, null)
    assert.equal(expired.manager.cloudCache.profile, null)
    assert.equal(existsSync(expired.manager.sessionPath), false)
  } finally {
    expired.cleanup()
  }

  const unavailable = createManager({ refreshStatus: 503 })
  try {
    unavailable.manager.session = { access_token: 'old-access', refresh_token: 'old-refresh' }
    unavailable.manager.user = { user_id: 'user-1', email: 'user@example.com' }
    unavailable.manager.cloudCache.profile = { full_name: 'Old User' }
    const state = await unavailable.manager.refreshSession()
    assert.equal(state.status, AUTH_STATUSES.BACKEND_UNAVAILABLE)
    assert.equal(unavailable.manager.session.refresh_token, 'old-refresh')
    assert.deepEqual(unavailable.manager.cloudCache.profile, { full_name: 'Old User' })
  } finally {
    unavailable.cleanup()
  }
})

test('malformed refresh token response does not replace existing session', async () => {
  const malformedResponses = [
    { refresh_token: 'new-refresh' },
    { access_token: 'new-access' },
    { access_token: '', refresh_token: 'new-refresh' },
    { access_token: 'new-access', refresh_token: '   ' },
  ]

  for (const payload of malformedResponses) {
    const ctx = createManager({
      fetchImpl: async (url, init = {}) => {
        ctx.calls.push({ url, init })
        if (url.includes('/auth/v1/token?grant_type=refresh_token')) {
          return jsonResponse(200, payload)
        }
        return jsonResponse(200, { user_id: 'user-1', email: 'user@example.com' })
      },
    })
    try {
      const existingSession = { access_token: 'old-access', refresh_token: 'old-refresh' }
      ctx.manager.session = existingSession
      ctx.manager.user = { user_id: 'user-1', email: 'user@example.com' }
      ctx.manager.status = AUTH_STATUSES.CONNECTED

      const state = await ctx.manager.refreshSession()

      assert.equal(state.status, AUTH_STATUSES.OFFLINE)
      assert.equal(ctx.manager.session, existingSession)
      assert.equal(ctx.manager.session.access_token, 'old-access')
      assert.equal(ctx.manager.session.refresh_token, 'old-refresh')
      assert.equal(ctx.calls.some((call) => call.url.endsWith('/api/auth/me')), false)
    } finally {
      ctx.cleanup()
    }
  }
})

test('refresh bootstrap rejection stays inside refresh error handling', async () => {
  const ctx = createManager()
  try {
    const existingSession = { access_token: 'old-access', refresh_token: 'old-refresh' }
    ctx.manager.session = existingSession
    ctx.manager.user = { user_id: 'user-1', email: 'user@example.com' }
    ctx.manager.status = AUTH_STATUSES.CONNECTED
    ctx.manager._verifyAndBootstrap = async () => {
      throw new Error('bootstrap blew up')
    }

    const state = await ctx.manager.refreshSession()

    assert.equal(state.status, AUTH_STATUSES.OFFLINE)
    assert.equal(ctx.manager.refreshPromise, null)
  } finally {
    ctx.cleanup()
  }
})

test('request timeouts map backend checks to offline and refresh cleanup settles single-flight promise', async () => {
  const controllers = []
  let requestStarted = deferred()
  const ctx = createManager({
    requestTimeoutMs: 5,
    requestSignalFactory: () => {
      const controller = new AbortController()
      controllers.push(controller)
      return controller.signal
    },
    fetchImpl: async (_url, init = {}) => {
      assert.ok(init.signal, 'auth requests must include an AbortSignal')
      requestStarted.resolve()
      await new Promise((_resolve, reject) => {
        if (init.signal.aborted) {
          reject(abortError())
          return
        }
        init.signal.addEventListener('abort', () => reject(abortError()), { once: true })
      })
    },
  })
  let pendingPromise = null
  try {
    const session = { access_token: 'access-token', refresh_token: 'refresh-token' }
    ctx.manager.session = session

    pendingPromise = ctx.manager._verifyAndBootstrap(session)
    await requestStarted.promise
    controllers.at(-1).abort()
    const verifyState = await pendingPromise
    assert.equal(verifyState.status, AUTH_STATUSES.OFFLINE)

    requestStarted = deferred()
    ctx.manager.session = session
    pendingPromise = ctx.manager.refreshSession()
    await requestStarted.promise
    controllers.at(-1).abort()
    const refreshState = await pendingPromise
    assert.equal(refreshState.status, AUTH_STATUSES.OFFLINE)
    assert.equal(ctx.manager.refreshPromise, null)
    assert.equal(ctx.manager.session.refresh_token, 'refresh-token')
  } finally {
    requestStarted.resolve()
    controllers.forEach((controller) => controller.abort())
    if (pendingPromise) {
      await pendingPromise.catch(() => {})
    }
    ctx.cleanup()
  }
})

test('delayed refresh response cannot overwrite a newer signed-out state', async () => {
  const refreshGate = deferred()
  const requestStarted = deferred()
  let pendingPromise = null
  const ctx = createManager({
    fetchImpl: async (url, init = {}) => {
      ctx.calls.push({ url, init })
      if (url.includes('/auth/v1/token?grant_type=refresh_token')) {
        requestStarted.resolve()
        await refreshGate.promise
        return jsonResponse(200, {
          access_token: 'late-access-token',
          refresh_token: 'late-refresh-token',
        })
      }
      return jsonResponse(200, {})
    },
  })
  try {
    ctx.manager.session = { access_token: 'old-access', refresh_token: 'old-refresh' }
    pendingPromise = ctx.manager.refreshSession()
    await requestStarted.promise
    await ctx.manager.logout()
    refreshGate.resolve()
    const state = await pendingPromise

    assert.equal(state.status, AUTH_STATUSES.SIGNED_OUT)
    assert.equal(ctx.manager.session, null)
  } finally {
    requestStarted.resolve()
    refreshGate.resolve()
    if (pendingPromise) {
      await pendingPromise.catch(() => {})
    }
    ctx.cleanup()
  }
})

test('delayed refresh json and rejected refresh after logout cannot overwrite signed-out state', async () => {
  const jsonGate = deferred()
  const jsonStarted = deferred()
  let jsonPromise = null
  const jsonCase = createManager({
    fetchImpl: async (url, init = {}) => {
      jsonCase.calls.push({ url, init })
      if (url.includes('/auth/v1/token?grant_type=refresh_token')) {
        return {
          ok: true,
          status: 200,
          json: async () => {
            jsonStarted.resolve()
            await jsonGate.promise
            return {
              access_token: 'late-access-token',
              refresh_token: 'late-refresh-token',
            }
          },
        }
      }
      return jsonResponse(200, {})
    },
  })
  try {
    jsonCase.manager.session = { access_token: 'old-access', refresh_token: 'old-refresh' }
    jsonPromise = jsonCase.manager.refreshSession()
    await jsonStarted.promise
    await jsonCase.manager.logout()
    jsonGate.resolve()
    const state = await jsonPromise
    assert.equal(state.status, AUTH_STATUSES.SIGNED_OUT)
    assert.equal(jsonCase.manager.session, null)
  } finally {
    jsonStarted.resolve()
    jsonGate.resolve()
    if (jsonPromise) {
      await jsonPromise.catch(() => {})
    }
    jsonCase.cleanup()
  }

  const rejectGate = deferred()
  const rejectStarted = deferred()
  let rejectPromise = null
  const rejectCase = createManager({
    fetchImpl: async (url, init = {}) => {
      rejectCase.calls.push({ url, init })
      if (url.includes('/auth/v1/token?grant_type=refresh_token')) {
        rejectStarted.resolve()
        await rejectGate.promise
        throw new Error('network failed')
      }
      return jsonResponse(200, {})
    },
  })
  try {
    rejectCase.manager.session = { access_token: 'old-access', refresh_token: 'old-refresh' }
    rejectPromise = rejectCase.manager.refreshSession()
    await rejectStarted.promise
    await rejectCase.manager.logout()
    rejectGate.resolve()
    const state = await rejectPromise
    assert.equal(state.status, AUTH_STATUSES.SIGNED_OUT)
    assert.equal(rejectCase.manager.session, null)
  } finally {
    rejectStarted.resolve()
    rejectGate.resolve()
    if (rejectPromise) {
      await rejectPromise.catch(() => {})
    }
    rejectCase.cleanup()
  }
})

test('refreshStartupContext is single-flight and avoids duplicate verification calls', async () => {
  const meGate = deferred()
  const meStarted = deferred()
  let first = null
  let second = null
  const ctx = createManager({
    fetchImpl: async (url, init = {}) => {
      ctx.calls.push({ url, init })
      if (url.endsWith('/api/auth/me')) {
        meStarted.resolve()
        await meGate.promise
        return jsonResponse(200, { user_id: 'user-1', email: 'user@example.com' })
      }
      if (url.endsWith('/api/auth/profile/bootstrap')) {
        return jsonResponse(200, { ok: true })
      }
      return jsonResponse(200, {})
    },
  })
  try {
    ctx.manager.session = { access_token: 'access-token', refresh_token: 'refresh-token' }
    first = ctx.manager.refreshStartupContext()
    second = ctx.manager.refreshStartupContext()
    await meStarted.promise
    meGate.resolve()
    await Promise.all([first, second])

    assert.equal(ctx.calls.filter((call) => call.url.endsWith('/api/auth/me')).length, 1)
    assert.equal(ctx.calls.filter((call) => call.url.endsWith('/api/auth/profile/bootstrap')).length, 1)
    assert.equal(ctx.manager.sessionGeneration, 1)
  } finally {
    meStarted.resolve()
    meGate.resolve()
    await Promise.all([first, second].filter(Boolean).map((promise) => promise.catch(() => {})))
    ctx.cleanup()
  }
})

test('refreshStartupContext skips redundant auth verification while cache is fresh', async () => {
  let now = 1000
  const ctx = createManager({
    now: () => now,
    fetchImpl: async (url, init = {}) => {
      ctx.calls.push({ url, init })
      if (url.endsWith('/api/auth/me')) {
        return jsonResponse(200, { user_id: 'user-1', email: 'user@example.com' })
      }
      if (url.endsWith('/api/auth/profile/bootstrap')) {
        return jsonResponse(200, { ok: true })
      }
      if (url.endsWith('/api/resumes/current')) {
        return jsonResponse(200, { ready: true, resume: { id: 'resume-1', status: 'ready', is_active: true } })
      }
      if (url.endsWith('/api/job-contexts?limit=50')) {
        return jsonResponse(200, { items: [] })
      }
      return jsonResponse(500, {})
    },
  })
  try {
    ctx.manager.session = { access_token: 'access-token', refresh_token: 'refresh-token' }
    await ctx.manager.refreshStartupContext()
    now += 1000
    await ctx.manager.refreshStartupContext()

    assert.equal(ctx.calls.filter((call) => call.url.endsWith('/api/auth/me')).length, 1)
    assert.equal(ctx.calls.filter((call) => call.url.endsWith('/api/auth/profile/bootstrap')).length, 1)
    assert.equal(ctx.calls.filter((call) => call.url.endsWith('/api/resumes/current')).length, 2)
    assert.equal(ctx.calls.filter((call) => call.url.endsWith('/api/job-contexts?limit=50')).length, 2)
  } finally {
    ctx.cleanup()
  }
})

test('listCloudResumes returns safe metadata from authenticated backend route', async () => {
  const ctx = createManager({
    fetchImpl: async (url, init = {}) => {
      ctx.calls.push({ url, init })
      if (url.endsWith('/api/auth/me')) {
        return jsonResponse(200, { user_id: 'user-1', email: 'user@example.com' })
      }
      if (url.endsWith('/api/auth/profile/bootstrap')) {
        return jsonResponse(200, { ok: true })
      }
      if (url.endsWith('/api/resumes')) {
        return jsonResponse(200, {
          items: [
            {
              id: 'resume-1',
              display_name: 'Product resume.pdf',
              original_filename: 'Product resume.pdf',
              status: 'ready',
              index_status: 'indexed',
              is_active: true,
              uploaded_at: '2026-08-01T00:00:00Z',
              updated_at: '2026-08-02T00:00:00Z',
              chunk_count: 3,
              can_generate: true,
              readiness_reason: 'ready',
              storage_path: 'private/path',
              raw_resume_text: 'private resume body',
            },
          ],
        })
      }
      return jsonResponse(500, {})
    },
  })
  try {
    ctx.manager.session = { access_token: 'access-token', refresh_token: 'refresh-token' }

    const result = await ctx.manager.listCloudResumes()

    assert.equal(ctx.calls.some((call) => call.url.endsWith('/api/resumes')), true)
    assert.deepEqual(result, {
      items: [
        {
          id: 'resume-1',
          display_name: 'Product resume.pdf',
          original_filename: 'Product resume.pdf',
          status: 'ready',
          index_status: 'indexed',
          is_active: true,
          created_at: null,
          uploaded_at: '2026-08-01T00:00:00Z',
          updated_at: '2026-08-02T00:00:00Z',
          chunk_count: 3,
          can_generate: true,
          readiness_reason: 'ready',
        },
      ],
      error: '',
    })
    assert.equal(JSON.stringify(result).includes('private resume body'), false)
    assert.equal(JSON.stringify(result).includes('private/path'), false)
  } finally {
    ctx.cleanup()
  }
})

test('generateAnswer proxies selected resume requests with main-process bearer auth', async () => {
  const ctx = createManager({
    fetchImpl: async (url, init = {}) => {
      ctx.calls.push({ url, init })
      if (url.endsWith('/api/auth/me')) {
        return jsonResponse(200, { user_id: 'user-1', email: 'user@example.com' })
      }
      if (url.endsWith('/api/auth/profile/bootstrap')) {
        return jsonResponse(200, { ok: true })
      }
      if (url.endsWith('/generate/')) {
        return jsonResponse(200, {
          answer: 'Resume A answer',
          resume_context_source: 'selected_resume',
          selected_resume_id_used: true,
          selected_resume_chunk_count: 2,
        })
      }
      return jsonResponse(500, {})
    },
  })
  try {
    ctx.manager.session = { access_token: 'access-token', refresh_token: 'refresh-token' }

    const result = await ctx.manager.generateAnswer({
      request_id: 'turn-1',
      question: 'Introduce yourself',
      category: 'personal',
      session_id: 'session-1',
      selected_resume_id: 'resume-1',
    })

    const generateCall = ctx.calls.find((call) => call.url.endsWith('/generate/'))
    assert.equal(result.ok, true)
    assert.equal(result.payload.answer, 'Resume A answer')
    assert.equal(result.payload.resume_context_source, 'selected_resume')
    assert.equal(result.payload.selected_resume_id_used, true)
    assert.equal(result.payload.selected_resume_chunk_count, 2)
    assert.equal(generateCall.init.headers.Authorization, 'Bearer access-token')
    assert.equal(JSON.parse(generateCall.init.body).request_id, 'turn-1')
    assert.equal(JSON.parse(generateCall.init.body).session_id, 'session-1')
    assert.equal(JSON.parse(generateCall.init.body).selected_resume_id, 'resume-1')
  } finally {
    ctx.cleanup()
  }
})

test('refreshStartupContext verifies again when verification freshness expires', async () => {
  let now = 1000
  const ctx = createManager({
    verificationFreshnessMs: 30000,
    now: () => now,
    fetchImpl: async (url, init = {}) => {
      ctx.calls.push({ url, init })
      if (url.endsWith('/api/auth/me')) {
        return jsonResponse(200, { user_id: 'user-1', email: 'user@example.com' })
      }
      if (url.endsWith('/api/auth/profile/bootstrap')) {
        return jsonResponse(200, { ok: true })
      }
      if (url.endsWith('/api/resumes/current')) {
        return jsonResponse(200, { ready: false, resume: null })
      }
      if (url.endsWith('/api/job-contexts?limit=50')) {
        return jsonResponse(200, { items: [] })
      }
      return jsonResponse(500, {})
    },
  })
  try {
    ctx.manager.session = { access_token: 'access-token', refresh_token: 'refresh-token' }
    await ctx.manager.refreshStartupContext()
    now += 31000
    await ctx.manager.refreshStartupContext()

    assert.equal(ctx.calls.filter((call) => call.url.endsWith('/api/auth/me')).length, 2)
    assert.equal(ctx.calls.filter((call) => call.url.endsWith('/api/auth/profile/bootstrap')).length, 2)
  } finally {
    ctx.cleanup()
  }
})

test('refreshStartupContext verifies again after token or generation changes', async () => {
  const ctx = createManager({
    fetchImpl: async (url, init = {}) => {
      ctx.calls.push({ url, init })
      if (url.endsWith('/api/auth/me')) {
        return jsonResponse(200, { user_id: 'user-1', email: 'user@example.com' })
      }
      if (url.endsWith('/api/auth/profile/bootstrap')) {
        return jsonResponse(200, { ok: true })
      }
      if (url.endsWith('/api/resumes/current')) {
        return jsonResponse(200, { ready: false, resume: null })
      }
      if (url.endsWith('/api/job-contexts?limit=50')) {
        return jsonResponse(200, { items: [] })
      }
      return jsonResponse(500, {})
    },
  })
  try {
    ctx.manager.session = { access_token: 'access-token', refresh_token: 'refresh-token' }
    await ctx.manager.refreshStartupContext()

    ctx.manager.session = { access_token: 'new-access-token', refresh_token: 'refresh-token' }
    await ctx.manager.refreshStartupContext()

    ctx.manager.sessionGeneration += 1
    await ctx.manager.refreshStartupContext()

    assert.equal(ctx.calls.filter((call) => call.url.endsWith('/api/auth/me')).length, 3)
    assert.equal(ctx.calls.filter((call) => call.url.endsWith('/api/auth/profile/bootstrap')).length, 3)
  } finally {
    ctx.cleanup()
  }
})

test('logout and failed startup verification invalidate verification freshness cache', async () => {
  const ctx = createManager({
    fetchImpl: async (url, init = {}) => {
      ctx.calls.push({ url, init })
      if (url.endsWith('/api/auth/me')) {
        return jsonResponse(ctx.calls.some((call) => call.url.includes('/auth/v1/logout')) ? 503 : 200, {
          user_id: 'user-1',
          email: 'user@example.com',
        })
      }
      if (url.endsWith('/api/auth/profile/bootstrap')) {
        return jsonResponse(200, { ok: true })
      }
      if (url.endsWith('/api/resumes/current')) {
        return jsonResponse(200, { ready: false, resume: null })
      }
      if (url.endsWith('/api/job-contexts?limit=50')) {
        return jsonResponse(200, { items: [] })
      }
      if (url.includes('/auth/v1/logout')) {
        return jsonResponse(200, {})
      }
      return jsonResponse(500, {})
    },
  })
  try {
    const session = { access_token: 'access-token', refresh_token: 'refresh-token' }
    ctx.manager.session = session
    await ctx.manager.refreshStartupContext()
    assert.notEqual(ctx.manager.verificationCache, null)

    await ctx.manager.logout()
    assert.equal(ctx.manager.verificationCache, null)

    ctx.manager.session = session
    await ctx.manager.refreshStartupContext()
    assert.equal(ctx.manager.verificationCache, null)
    assert.equal(ctx.manager.getSafeState().status, AUTH_STATUSES.BACKEND_UNAVAILABLE)
  } finally {
    ctx.cleanup()
  }
})

test('signed-out startup context stays local-only with conservative readiness flags', () => {
  const ctx = createManager()
  try {
    const context = ctx.manager.getStartupContext()

    assert.equal(context.auth.status, AUTH_STATUSES.SIGNED_OUT)
    assert.equal(context.cloud.available, false)
    assert.equal(context.cloud.mode, 'local-only')
    assert.equal(context.cloud.profileReady, false)
    assert.equal(context.cloud.resumeReady, false)
    assert.equal(context.cloud.jobContextReady, false)
  } finally {
    ctx.cleanup()
  }
})

test('connected startup context loads safe resume and job-context readiness summaries', async () => {
  const ctx = createManager({
    fetchImpl: async (url, init = {}) => {
      ctx.calls.push({ url, init })
      if (url.endsWith('/api/auth/me')) {
        return jsonResponse(200, {
          user_id: 'user-1',
          email: 'user@example.com',
          [['access', 'token'].join('_')]: 'must-not-leak',
        })
      }
      if (url.endsWith('/api/auth/profile/bootstrap')) {
        return jsonResponse(200, { ok: true })
      }
      if (url.endsWith('/api/resumes/current')) {
        return jsonResponse(200, {
          ready: true,
          resume: {
            id: 'resume-1',
            status: 'ready',
            is_active: true,
            raw_resume_text: 'must-not-leak',
          },
        })
      }
      if (url.endsWith('/api/job-contexts?limit=50')) {
        return jsonResponse(200, {
          active_id: 'job-1',
          items: [{
            id: 'job-1',
            company: 'Acme',
            position: 'Engineer',
            is_active: true,
            job_description: 'must-not-leak',
            job_description_preview: 'preview only',
          }],
        })
      }
      return jsonResponse(500, {})
    },
  })
  try {
    ctx.manager.session = { access_token: 'access-token', refresh_token: 'refresh-token' }
    const context = await ctx.manager.refreshStartupContext()

    assert.equal(context.auth.status, AUTH_STATUSES.CONNECTED)
    assert.equal(context.auth.email, 'user@example.com')
    assert.equal(context.cloud.available, true)
    assert.equal(context.cloud.mode, 'cloud')
    assert.equal(context.cloud.profileReady, true)
    assert.equal(context.cloud.resumeReady, true)
    assert.equal(context.cloud.jobContextReady, true)
    assert.deepEqual(context.resumeContext.resume, { id: 'resume-1', status: 'ready', is_active: true })
    assert.deepEqual(context.jobContext.active, {
      id: 'job-1',
      company: 'Acme',
      position: 'Engineer',
      is_active: true,
    })
    assert.equal(JSON.stringify(context).includes('must-not-leak'), false)
  } finally {
    ctx.cleanup()
  }
})

test('startup context falls back safely when readiness routes are missing', async () => {
  const ctx = createManager({
    fetchImpl: async (url, init = {}) => {
      ctx.calls.push({ url, init })
      if (url.endsWith('/api/auth/me')) {
        return jsonResponse(200, { user_id: 'user-1', email: 'user@example.com' })
      }
      if (url.endsWith('/api/auth/profile/bootstrap')) {
        return jsonResponse(200, { ok: true })
      }
      if (url.endsWith('/api/resumes/current') || url.endsWith('/api/job-contexts?limit=50')) {
        return jsonResponse(404, { detail: 'not found' })
      }
      return jsonResponse(500, {})
    },
  })
  try {
    ctx.manager.session = { access_token: 'access-token', refresh_token: 'refresh-token' }
    const context = await ctx.manager.refreshStartupContext()

    assert.equal(context.auth.status, AUTH_STATUSES.CONNECTED)
    assert.equal(context.cloud.available, true)
    assert.equal(context.cloud.mode, 'cloud')
    assert.equal(context.cloud.profileReady, true)
    assert.equal(context.cloud.resumeReady, false)
    assert.equal(context.cloud.jobContextReady, false)
    assert.equal(context.resumeContext, null)
    assert.equal(context.jobContext, null)
  } finally {
    ctx.cleanup()
  }
})

test('startup context treats empty job-context list as no active job context', async () => {
  const ctx = createManager({
    fetchImpl: async (url, init = {}) => {
      ctx.calls.push({ url, init })
      if (url.endsWith('/api/auth/me')) {
        return jsonResponse(200, { user_id: 'user-1', email: 'user@example.com' })
      }
      if (url.endsWith('/api/auth/profile/bootstrap')) {
        return jsonResponse(200, { ok: true })
      }
      if (url.endsWith('/api/resumes/current')) {
        return jsonResponse(200, {
          ready: true,
          resume: { id: 'resume-1', status: 'ready', is_active: true },
        })
      }
      if (url.endsWith('/api/job-contexts?limit=50')) {
        return jsonResponse(200, { items: [] })
      }
      return jsonResponse(500, {})
    },
  })
  try {
    ctx.manager.session = { access_token: 'access-token', refresh_token: 'refresh-token' }
    const context = await ctx.manager.refreshStartupContext()

    assert.equal(context.auth.status, AUTH_STATUSES.CONNECTED)
    assert.equal(context.cloud.available, true)
    assert.equal(context.cloud.profileReady, true)
    assert.equal(context.cloud.jobContextReady, false)
    assert.equal(context.jobContext, null)
  } finally {
    ctx.cleanup()
  }
})

test('startup context treats unmatched active job-context id as not ready', async () => {
  const ctx = createManager({
    fetchImpl: async (url, init = {}) => {
      ctx.calls.push({ url, init })
      if (url.endsWith('/api/auth/me')) {
        return jsonResponse(200, { user_id: 'user-1', email: 'user@example.com' })
      }
      if (url.endsWith('/api/auth/profile/bootstrap')) {
        return jsonResponse(200, { ok: true })
      }
      if (url.endsWith('/api/resumes/current')) {
        return jsonResponse(200, {
          ready: true,
          resume: { id: 'resume-1', status: 'ready', is_active: true },
        })
      }
      if (url.endsWith('/api/job-contexts?limit=50')) {
        return jsonResponse(200, {
          active_id: 'missing-job',
          items: [{ id: 'other-job', company: 'Acme', position: 'Engineer', is_active: false }],
        })
      }
      return jsonResponse(500, {})
    },
  })
  try {
    ctx.manager.session = { access_token: 'access-token', refresh_token: 'refresh-token' }
    const context = await ctx.manager.refreshStartupContext()

    assert.equal(context.auth.status, AUTH_STATUSES.CONNECTED)
    assert.equal(context.cloud.available, true)
    assert.equal(context.cloud.profileReady, true)
    assert.equal(context.cloud.jobContextReady, false)
    assert.deepEqual(context.jobContext, { active_id: 'missing-job', active: null })
  } finally {
    ctx.cleanup()
  }
})

test('startup context reports backend unavailable without forcing logout', async () => {
  const ctx = createManager({
    fetchImpl: async (url, init = {}) => {
      ctx.calls.push({ url, init })
      if (url.endsWith('/api/auth/me')) {
        return jsonResponse(503, {})
      }
      return jsonResponse(500, {})
    },
  })
  try {
    const session = { access_token: 'access-token', refresh_token: 'refresh-token' }
    ctx.manager.session = session
    ctx.manager.user = { user_id: 'user-1', email: 'user@example.com' }
    const context = await ctx.manager.refreshStartupContext()

    assert.equal(context.auth.status, AUTH_STATUSES.BACKEND_UNAVAILABLE)
    assert.equal(context.cloud.available, false)
    assert.equal(context.cloud.mode, 'unavailable')
    assert.equal(ctx.manager.session, session)
  } finally {
    ctx.cleanup()
  }
})

test('startup context token-expired state clears invalid auth session', async () => {
  const ctx = createManager({
    fetchImpl: async (url, init = {}) => {
      ctx.calls.push({ url, init })
      if (url.endsWith('/api/auth/me')) {
        return jsonResponse(401, {})
      }
      return jsonResponse(500, {})
    },
  })
  try {
    ctx.manager.session = { access_token: 'access-token', refresh_token: 'refresh-token' }
    ctx.manager.user = { user_id: 'user-1', email: 'user@example.com' }
    const context = await ctx.manager.refreshStartupContext()

    assert.equal(context.auth.status, AUTH_STATUSES.TOKEN_EXPIRED)
    assert.equal(context.auth.user_id, null)
    assert.equal(context.cloud.mode, 'local-only')
    assert.equal(ctx.manager.session, null)
  } finally {
    ctx.cleanup()
  }
})

test('stale startup context response after logout cannot update cloud cache', async () => {
  const resumeStarted = deferred()
  const resumeGate = deferred()
  let pendingPromise = null
  const ctx = createManager({
    fetchImpl: async (url, init = {}) => {
      ctx.calls.push({ url, init })
      if (url.endsWith('/api/auth/me')) {
        return jsonResponse(200, { user_id: 'user-1', email: 'user@example.com' })
      }
      if (url.endsWith('/api/auth/profile/bootstrap')) {
        return jsonResponse(200, { ok: true })
      }
      if (url.endsWith('/api/resumes/current')) {
        resumeStarted.resolve()
        await resumeGate.promise
        return jsonResponse(200, { ready: true, resume: { id: 'resume-1', status: 'ready', is_active: true } })
      }
      if (url.endsWith('/api/job-contexts?limit=50')) {
        return jsonResponse(200, { active_id: 'job-1', items: [{ id: 'job-1', company: 'Acme', position: 'Engineer', is_active: true }] })
      }
      if (url.includes('/auth/v1/logout')) {
        return jsonResponse(200, {})
      }
      return jsonResponse(500, {})
    },
  })
  try {
    ctx.manager.session = { access_token: 'access-token', refresh_token: 'refresh-token' }
    ctx.manager.user = { user_id: 'user-1', email: 'user@example.com' }
    ctx.manager.status = AUTH_STATUSES.CONNECTED
    pendingPromise = ctx.manager.refreshStartupContext()
    await resumeStarted.promise
    await ctx.manager.logout()
    resumeGate.resolve()
    const context = await pendingPromise

    assert.equal(context.auth.status, AUTH_STATUSES.SIGNED_OUT)
    assert.equal(ctx.manager.cloudCache.resumeContext, null)
    assert.equal(ctx.manager.cloudCache.jobContext, null)
  } finally {
    resumeStarted.resolve()
    resumeGate.resolve()
    if (pendingPromise) {
      await pendingPromise.catch(() => {})
    }
    ctx.cleanup()
  }
})

test('stale startup context response after user switch cannot expose previous user data', async () => {
  const jobStarted = deferred()
  const jobGate = deferred()
  let pendingPromise = null
  const ctx = createManager({
    fetchImpl: async (url, init = {}) => {
      ctx.calls.push({ url, init })
      if (url.endsWith('/api/auth/me')) {
        return jsonResponse(200, { user_id: 'user-1', email: 'one@example.com' })
      }
      if (url.endsWith('/api/auth/profile/bootstrap')) {
        return jsonResponse(200, { ok: true })
      }
      if (url.endsWith('/api/resumes/current')) {
        return jsonResponse(200, { ready: true, resume: { id: 'resume-old', status: 'ready', is_active: true } })
      }
      if (url.endsWith('/api/job-contexts?limit=50')) {
        jobStarted.resolve()
        await jobGate.promise
        return jsonResponse(200, { active_id: 'job-old', items: [{ id: 'job-old', company: 'Old', position: 'Role', is_active: true }] })
      }
      return jsonResponse(500, {})
    },
  })
  try {
    ctx.manager.session = { access_token: 'access-one', refresh_token: 'refresh-one' }
    ctx.manager.user = { user_id: 'user-1', email: 'one@example.com' }
    ctx.manager.status = AUTH_STATUSES.CONNECTED
    pendingPromise = ctx.manager.refreshStartupContext()
    await jobStarted.promise

    ctx.manager.session = { access_token: 'access-two', refresh_token: 'refresh-two' }
    ctx.manager.user = { user_id: 'user-2', email: 'two@example.com' }
    ctx.manager.status = AUTH_STATUSES.CONNECTED
    ctx.manager.sessionGeneration += 1
    ctx.manager._clearCloudCache()

    jobGate.resolve()
    const context = await pendingPromise

    assert.equal(context.auth.user_id, 'user-2')
    assert.equal(ctx.manager.cloudCache.resumeContext, null)
    assert.equal(ctx.manager.cloudCache.jobContext, null)
    assert.equal(JSON.stringify(context).includes('job-old'), false)
  } finally {
    jobStarted.resolve()
    jobGate.resolve()
    if (pendingPromise) {
      await pendingPromise.catch(() => {})
    }
    ctx.cleanup()
  }
})

test('safeStorage persistence failures do not block in-memory login or refresh success', async () => {
  const brokenSafeStorage = {
    isEncryptionAvailable: () => true,
    encryptString: () => {
      throw new Error('encryption failed')
    },
    decryptString: () => '',
  }
  const ctx = createManager({ safeStorage: brokenSafeStorage })
  try {
    await ctx.manager.startLogin()
    const loginState = await ctx.manager.handleAuthCallback(callbackUrlFor(ctx.manager, { code: 'auth-code' }))
    assert.equal(loginState.status, AUTH_STATUSES.CONNECTED)
    assert.equal(ctx.manager.session.refresh_token, 'refresh-token')
    assert.equal(existsSync(ctx.manager.sessionPath), false)

    const refreshState = await ctx.manager.refreshSession()
    assert.equal(refreshState.status, AUTH_STATUSES.CONNECTED)
    assert.equal(ctx.manager.session.refresh_token, 'refreshed-refresh-token')
  } finally {
    ctx.cleanup()
  }
})

test('logout clears local credentials and cache even when remote sign-out fails', async () => {
  const ctx = createManager({ logoutThrows: true })
  try {
    ctx.manager.session = { access_token: 'access-token', refresh_token: 'refresh-token' }
    ctx.manager.user = { user_id: 'user-1', email: 'user@example.com' }
    ctx.manager._writeStoredSession(ctx.manager.session)
    ctx.manager.cloudCache.profile = { full_name: 'Old User' }

    const state = await ctx.manager.logout()
    const logoutCall = ctx.calls.find((call) => call.url.includes('/auth/v1/logout'))
    assert.equal(state.status, AUTH_STATUSES.SIGNED_OUT)
    assert.notEqual(logoutCall.init.signal, undefined)
    assert.equal(ctx.manager.session, null)
    assert.equal(ctx.manager.cloudCache.profile, null)
    assert.throws(() => readFileSync(ctx.manager.sessionPath, 'utf8'))
  } finally {
    ctx.cleanup()
  }
})

test('desktop auth manager creates lists and ends interview sessions without exposing tokens', async () => {
  const ctx = createManager()
  try {
    ctx.manager.session = { access_token: 'access-token', refresh_token: 'refresh-token' }
    ctx.manager.user = { user_id: 'user-1', email: 'user@example.com' }
    ctx.manager.status = AUTH_STATUSES.CONNECTED
    ctx.manager.sessionGeneration = 1

    const created = await ctx.manager.createInterviewSession(
      {
        title: 'Design interview',
        selected_resume_id: 'resume-1',
        target_role: 'Frontend Engineer',
        company_name: 'Acme',
        job_description: 'Long description',
      },
      { idempotencyKey: 'session:start-1' },
    )
    assert.equal(created.session.id, 'session-1')
    assert.equal(created.session.status, 'active')
    assert.equal(ctx.manager.getSafeState().activeInterviewSessionId, 'session-1')

    const listed = await ctx.manager.listInterviewSessions()
    assert.equal(listed.items[0].id, 'session-1')
    assert.equal(listed.items[0].status, 'ended')

    const ended = await ctx.manager.endInterviewSession('session-1')
    assert.equal(ended.session.status, 'ended')
    assert.equal(ctx.manager.activeInterviewSession, null)

    const createCall = ctx.calls.find((call) => call.url.endsWith('/api/interview-sessions'))
    assert.equal(createCall.init.headers.Authorization, 'Bearer access-token')
    assert.equal(createCall.init.headers['Idempotency-Key'], 'session:start-1')
    assert.equal(JSON.parse(createCall.init.body).job_description, 'Long description')
    assert.equal(JSON.stringify(createCall.init.headers).includes('refresh-token'), false)
  } finally {
    ctx.cleanup()
  }
})

test('logout attempts to finalize the active interview session before clearing local state', async () => {
  const ctx = createManager()
  try {
    ctx.manager.session = { access_token: 'access-token', refresh_token: 'refresh-token' }
    ctx.manager.user = { user_id: 'user-1', email: 'user@example.com' }
    ctx.manager.status = AUTH_STATUSES.CONNECTED
    ctx.manager.sessionGeneration = 1
    ctx.manager.activeInterviewSession = { id: 'session-1', status: 'active' }

    const state = await ctx.manager.logout()
    const endCall = ctx.calls.find((call) => call.url.includes('/api/interview-sessions/session-1/end'))
    const logoutCall = ctx.calls.find((call) => call.url.includes('/auth/v1/logout'))

    assert.equal(state.status, AUTH_STATUSES.SIGNED_OUT)
    assert.notEqual(endCall, undefined)
    assert.notEqual(logoutCall, undefined)
  } finally {
    ctx.cleanup()
  }
})

test('stale logout remote response cannot clear a newer session', async () => {
  const logoutStarted = deferred()
  const logoutGate = deferred()
  let logoutPromise = null
  const ctx = createManager({
    fetchImpl: async (url, init = {}) => {
      ctx.calls.push({ url, init })
      if (url.includes('/auth/v1/logout')) {
        logoutStarted.resolve()
        await logoutGate.promise
        return jsonResponse(200, {})
      }
      return jsonResponse(200, {})
    },
  })
  try {
    ctx.manager.session = { access_token: 'old-access-token', refresh_token: 'old-refresh-token' }
    ctx.manager.user = { user_id: 'user-1', email: 'one@example.com' }
    ctx.manager.status = AUTH_STATUSES.CONNECTED
    ctx.manager.sessionGeneration = 2

    logoutPromise = ctx.manager.logout()
    await logoutStarted.promise

    ctx.manager.session = { access_token: 'new-access-token', refresh_token: 'new-refresh-token' }
    ctx.manager.user = { user_id: 'user-2', email: 'two@example.com' }
    ctx.manager.status = AUTH_STATUSES.CONNECTED
    ctx.manager.sessionGeneration += 1

    logoutGate.resolve()
    const state = await logoutPromise
    assert.equal(state.status, AUTH_STATUSES.CONNECTED)
    assert.equal(state.user_id, 'user-2')
    assert.equal(ctx.manager.session.access_token, 'new-access-token')
  } finally {
    logoutStarted.resolve()
    logoutGate.resolve()
    if (logoutPromise) {
      await logoutPromise.catch(() => {})
    }
    ctx.cleanup()
  }
})

test('cloud cache writes reject stale generations after logout or user switch', () => {
  const ctx = createManager()
  try {
    ctx.manager.user = { user_id: 'user-1', email: 'one@example.com' }
    ctx.manager.session = { access_token: 'access-one', refresh_token: 'refresh-one' }
    ctx.manager.sessionGeneration = 1
    const captured = ctx.manager.captureCloudRequestContext()
    ctx.manager._clearLocalSession(AUTH_STATUSES.SIGNED_OUT)
    assert.equal(ctx.manager.writeCloudCache(captured, { profile: { full_name: 'Old User' } }), false)
    assert.equal(ctx.manager.cloudCache.profile, null)

    ctx.manager.user = { user_id: 'user-1', email: 'one@example.com' }
    ctx.manager.session = { access_token: 'access-one', refresh_token: 'refresh-one' }
    ctx.manager.sessionGeneration = 2
    const previousUser = ctx.manager.captureCloudRequestContext()
    ctx.manager.user = { user_id: 'user-2', email: 'two@example.com' }
    ctx.manager.session = { access_token: 'access-two', refresh_token: 'refresh-two' }
    ctx.manager.sessionGeneration = 3
    assert.equal(ctx.manager.writeCloudCache(previousUser, { profile: { full_name: 'Wrong User' } }), false)
    assert.equal(ctx.manager.cloudCache.profile, null)

    ctx.manager.user = { user_id: 'user-2', email: 'two@example.com' }
    ctx.manager.session = { access_token: 'access-three', refresh_token: 'refresh-three' }
    const previousSession = ctx.manager.captureCloudRequestContext()
    ctx.manager.session = { access_token: 'access-four', refresh_token: 'refresh-four' }
    assert.equal(ctx.manager.writeCloudCache(previousSession, { profile: { full_name: 'Wrong Session' } }), false)
    assert.equal(ctx.manager.cloudCache.profile, null)

    const current = ctx.manager.captureCloudRequestContext()
    assert.equal(ctx.manager.writeCloudCache(current, { profile: { full_name: 'Current User' } }), true)
    assert.deepEqual(ctx.manager.cloudCache.profile, { full_name: 'Current User' })
  } finally {
    ctx.cleanup()
  }
})

test('cloud cache write is rejected if logout interleaves between validation and write', () => {
  const ctx = createManager()
  try {
    ctx.manager.user = { user_id: 'user-1', email: 'one@example.com' }
    ctx.manager.sessionGeneration = 1
    const captured = ctx.manager.captureCloudRequestContext()
    ctx.manager.beforeCacheWriteForTest = () => {
      ctx.manager._clearLocalSession(AUTH_STATUSES.SIGNED_OUT)
    }
    assert.equal(ctx.manager.writeCloudCache(captured, { profile: { full_name: 'Old User' } }), false)
    assert.equal(ctx.manager.cloudCache.profile, null)
  } finally {
    ctx.cleanup()
  }
})

test('auth IPC sender validation rejects unexpected window, frame, origin, and accepts the expected dev sender', () => {
  const expectedWindow = { isDestroyed: () => false }
  const wrongWindow = { isDestroyed: () => false }
  const BrowserWindow = {
    fromWebContents: (sender) => sender.window,
  }
  const validate = createIpcSenderValidator({
    getExpectedWindow: () => expectedWindow,
    BrowserWindow,
    devOrigin: 'http://localhost:5173',
    isPackaged: false,
  })

  assert.equal(validate({ sender: { window: expectedWindow }, senderFrame: { url: 'http://localhost:5173/' } }), true)
  assert.throws(() => validate({ sender: { window: wrongWindow }, senderFrame: { url: 'http://localhost:5173/' } }), /Unauthorized IPC sender/)
  assert.throws(() => createIpcSenderValidator({
    getExpectedWindow: () => null,
    BrowserWindow,
    devOrigin: 'http://localhost:5173',
    isPackaged: false,
  })({ sender: { window: expectedWindow }, senderFrame: { url: 'http://localhost:5173/' } }), /Unauthorized IPC sender/)
  const destroyedWindow = { isDestroyed: () => true }
  assert.throws(() => createIpcSenderValidator({
    getExpectedWindow: () => destroyedWindow,
    BrowserWindow: { fromWebContents: (sender) => sender.window },
    devOrigin: 'http://localhost:5173',
    isPackaged: false,
  })({ sender: { window: destroyedWindow }, senderFrame: { url: 'http://localhost:5173/' } }), /Unauthorized IPC sender/)
  assert.throws(() => validate({ sender: { window: expectedWindow }, senderFrame: null }), /Unauthorized IPC frame/)
  assert.throws(() => validate({ sender: { window: expectedWindow }, senderFrame: { url: 'http://evil.test/' } }), /Unauthorized IPC origin/)
  assert.throws(() => validate({ sender: { window: expectedWindow }, senderFrame: { url: 'http://localhost:5173/', isDestroyed: () => true } }), /Unauthorized IPC frame/)
})

test('auth IPC sender validation accepts only the packaged app file path in packaged mode', () => {
  const expectedWindow = { isDestroyed: () => false }
  const BrowserWindow = {
    fromWebContents: (sender) => sender.window,
  }
  const packagedIndexPath = path.join(tmpdir(), 'saiia_project', 'frontend', 'dist', 'index.html')
  const validate = createIpcSenderValidator({
    getExpectedWindow: () => expectedWindow,
    BrowserWindow,
    isPackaged: true,
    packagedIndexPath,
  })

  assert.equal(validate({
    sender: { window: expectedWindow },
    senderFrame: { url: pathToFileURL(packagedIndexPath).toString() },
  }), true)
  assert.throws(() => validate({
    sender: { window: expectedWindow },
    senderFrame: { url: pathToFileURL(path.join(path.dirname(packagedIndexPath), 'other.html')).toString() },
  }), /Unauthorized IPC path/)
})

test('preload exposes exact narrow auth methods without raw tokens or generic fetch', () => {
  const source = readFileSync(new URL('../electron/preload.cjs', import.meta.url), 'utf8')
  const exposed = {}
  const electronStub = {
    contextBridge: {
      exposeInMainWorld: (name, value) => {
        exposed[name] = value
      },
    },
    ipcRenderer: {
      invoke: async (channel) => channel,
      send: () => {},
      on: () => {},
      removeListener: () => {},
    },
  }
  vm.runInNewContext(source, {
    require: (id) => {
      if (id === 'electron') {
        return electronStub
      }
      return require(id)
    },
  })

  assert.deepEqual(Object.keys(exposed.saiia).sort(), [
    'captureActiveWindow',
    'captureActiveWindowSequence',
    'captureScreen',
    'closeStartupWindow',
    'createInterviewSession',
    'endInterviewSession',
    'generateAnswer',
    'getAuthState',
    'getCloudStartupContext',
    'listInterviewSessions',
    'listCloudResumes',
    'listScreenSources',
    'logoutAuth',
    'openDashboard',
    'refreshCloudStartupContext',
    'startAuthLogin',
  ].sort())
  assert.equal('access_token' in exposed.saiia, false)
  assert.equal('refresh_token' in exposed.saiia, false)
  assert.equal('fetch' in exposed.saiia, false)
})

test('main process opens dashboard externally through a validated http URL', () => {
  const source = readFileSync(new URL('../electron/main.cjs', import.meta.url), 'utf8')

  assert.match(source, /'SAIIA_WEB_DASHBOARD_URL'/)
  assert.match(source, /'VITE_SAIIA_WEB_DASHBOARD_URL'/)
  assert.match(source, /ipcMain\.handle\('dashboard:open', async \(event\) => \{/)
  assert.match(source, /validateTrustedRendererIpc\(event\)/)
  assert.match(source, /shell\.openExternal\(dashboardUrl\)/)
  assert.match(source, /!\['http:', 'https:'\]\.includes\(parsed\.protocol\)/)
  assert.match(source, /new URL\('\/auth\/dashboard', webAuthUrl\.origin\)\.toString\(\)/)
  assert.doesNotMatch(source, /ipcMain\.handle\('dashboard:open'[\s\S]{0,160}rendererUrl/)
})

test('main process exits second instances before protocol registration and buffers early callbacks', () => {
  const source = readFileSync(new URL('../electron/main.cjs', import.meta.url), 'utf8')
  const secondInstanceExit = source.indexOf('process.exit(0)')
  const protocolRegistration = source.indexOf('registerDesktopAuthProtocol()')
  const managerCreation = source.indexOf('desktopAuthSessionManager = createDesktopAuthSessionManager()')
  const initializeAwait = source.indexOf('await desktopAuthSessionManager.initialize()')
  const bufferedDrain = source.indexOf('bufferedCallbacks.forEach')
  const argvCallback = source.indexOf('handleDesktopAuthCallbackFromArgv(process.argv)')

  assert.equal(secondInstanceExit >= 0, true)
  assert.equal(protocolRegistration >= 0, true)
  assert.equal(managerCreation >= 0, true)
  assert.equal(initializeAwait >= 0, true)
  assert.equal(bufferedDrain >= 0, true)
  assert.equal(argvCallback >= 0, true)
  assert.equal(protocolRegistration > secondInstanceExit, true)
  assert.match(source, /bufferedDesktopAuthCallbacks\.push\(value\)/)
  assert.equal(managerCreation < initializeAwait, true)
  assert.equal(initializeAwait < bufferedDrain, true)
  assert.equal(bufferedDrain < argvCallback, true)
})

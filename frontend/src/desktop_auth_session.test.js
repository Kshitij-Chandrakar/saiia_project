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
    desktopAuthProvider: 'google',
    backendUrl: 'http://localhost:8000',
    sessionPath: path.join(dir, 'session.bin'),
    safeStorage: createSafeStorage(true),
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
  const promise = new Promise((nextResolve) => {
    resolve = nextResolve
  })
  return { promise, resolve }
}

function callbackUrlFor(manager, params = {}) {
  const url = new URL(CALLBACK_URL)
  Object.entries(params).forEach(([key, value]) => url.searchParams.set(key, value))
  if (!url.searchParams.has('state')) {
    url.searchParams.set('state', manager.pendingLogin.state)
  }
  return url.toString()
}

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

test('startLogin includes configured provider and fails safely when provider or browser launch is unavailable', async () => {
  const missingProvider = createManager({ desktopAuthProvider: '' })
  try {
    const state = await missingProvider.manager.startLogin()
    assert.equal(state.status, AUTH_STATUSES.SIGNED_OUT)
    assert.equal(state.error, 'Desktop cloud auth is not configured.')
    assert.equal(missingProvider.manager.pendingLogin, null)
  } finally {
    missingProvider.cleanup()
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

test('PKCE request uses configured provider, S256, exact redirect_uri, and original code_verifier during exchange', async () => {
  const ctx = createManager()
  try {
    await ctx.manager.startLogin()
    const authUrl = new URL(ctx.opened[0])
    const storedVerifier = ctx.manager.pendingLogin.code_verifier

    assert.equal(ctx.manager.getSafeState().status, AUTH_STATUSES.SIGNING_IN)
    assert.notEqual(ctx.manager.pendingLogin, null)
    assert.equal(authUrl.searchParams.get('provider'), 'google')
    assert.equal(authUrl.searchParams.get('code_challenge_method'), 'S256')
    assert.equal(authUrl.searchParams.get('redirect_uri'), CALLBACK_URL)

    await ctx.manager.handleAuthCallback(callbackUrlFor(ctx.manager, { code: 'auth-code' }))
    const exchange = ctx.calls.find((call) => call.url.includes('grant_type=pkce'))
    assert.equal(JSON.parse(exchange.init.body).code_verifier, storedVerifier)
  } finally {
    ctx.cleanup()
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

test('callback rejects missing state, missing code without auth error, mismatched, expired, and reused state', async () => {
  const ctx = createManager({ now: () => 1000, loginTtlMs: 100 })
  try {
    await ctx.manager.startLogin()
    let result = await ctx.manager.handleAuthCallback(`${CALLBACK_URL}?code=auth-code`)
    assert.equal(result.status, AUTH_STATUSES.SIGNED_OUT)
    assert.equal(result.error, 'Invalid authentication callback.')

    await ctx.manager.startLogin()
    result = await ctx.manager.handleAuthCallback(callbackUrlFor(ctx.manager))
    assert.equal(result.status, AUTH_STATUSES.SIGNED_OUT)
    assert.equal(result.error, 'Invalid authentication callback.')

    await ctx.manager.startLogin()
    result = await ctx.manager.handleAuthCallback(`${CALLBACK_URL}?code=auth-code&state=wrong`)
    assert.equal(result.status, AUTH_STATUSES.SIGNED_OUT)
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
    assert.equal((await ctx.manager.handleAuthCallback(url)).status, AUTH_STATUSES.CONNECTED)
    result = await ctx.manager.handleAuthCallback(url)
    assert.equal(result.status, AUTH_STATUSES.CONNECTED)
    assert.equal(result.error, 'Invalid or expired authentication attempt.')
  } finally {
    ctx.cleanup()
  }
})

test('authorization denial consumes pending login and skips token exchange', async () => {
  const ctx = createManager()
  try {
    await ctx.manager.startLogin()
    const state = ctx.manager.pendingLogin.state
    const result = await ctx.manager.handleAuthCallback(`${CALLBACK_URL}?error=access_denied&state=${state}`)

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
    const result = await ctx.manager.handleAuthCallback(`${CALLBACK_URL}?error=access_denied&state=${state}`)

    assert.equal(result.status, AUTH_STATUSES.CONNECTED)
    assert.equal(result.user_id, 'user-1')
    assert.equal(ctx.calls.some((call) => call.url.includes('grant_type=pkce')), false)
  } finally {
    ctx.cleanup()
  }
})

test('overlapping login attempts reject old callbacks and discard old exchange commits', async () => {
  const exchange = deferred()
  const ctx = createManager({
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
    const oldUrl = callbackUrlFor(ctx.manager, { code: 'old-code' })
    await ctx.manager.startLogin()
    assert.equal((await ctx.manager.handleAuthCallback(oldUrl)).status, AUTH_STATUSES.SIGNED_OUT)

    const activeUrl = callbackUrlFor(ctx.manager, { code: 'active-code' })
    const activePromise = ctx.manager.handleAuthCallback(activeUrl)
    await ctx.manager.startLogin()
    exchange.resolve()
    await activePromise
    assert.equal(ctx.manager.session, null)
  } finally {
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
    const promise = ctx.manager._verifyAndBootstrap(session)
    await ctx.manager.logout()
    meGate.resolve()
    const state = await promise

    assert.equal(state.status, AUTH_STATUSES.SIGNED_OUT)
    assert.equal(state.user_id, null)
    assert.equal(ctx.manager.user, null)
  } finally {
    ctx.cleanup()
  }
})

test('verification ignores stale session after logout during bootstrap request', async () => {
  const bootstrapGate = deferred()
  const session = { access_token: 'access-token', refresh_token: 'refresh-token' }
  const ctx = createManager({
    fetchImpl: async (url, init = {}) => {
      ctx.calls.push({ url, init })
      if (url.endsWith('/api/auth/me')) {
        return jsonResponse(200, { user_id: 'user-1', email: 'user@example.com' })
      }
      if (url.endsWith('/api/auth/profile/bootstrap')) {
        await bootstrapGate.promise
        return jsonResponse(200, { ok: true })
      }
      return jsonResponse(200, {})
    },
  })
  try {
    ctx.manager.session = session
    const promise = ctx.manager._verifyAndBootstrap(session)
    await new Promise((resolve) => setImmediate(resolve))
    await ctx.manager.logout()
    bootstrapGate.resolve()
    const state = await promise

    assert.equal(state.status, AUTH_STATUSES.SIGNED_OUT)
    assert.equal(state.user_id, null)
    assert.equal(ctx.manager.user, null)
  } finally {
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

test('request timeouts map backend checks to offline and refresh cleanup settles single-flight promise', async () => {
  const ctx = createManager({
    requestTimeoutMs: 1,
    fetchImpl: async (_url, init = {}) => {
      await new Promise((_resolve, reject) => {
        init.signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true })
      })
    },
  })
  try {
    ctx.manager.session = { access_token: 'old-access', refresh_token: 'old-refresh' }
    assert.equal((await ctx.manager._backendJson('/api/auth/me', 'GET', 'old-access')).status, 0)

    const state = await ctx.manager.refreshSession()
    assert.equal(state.status, AUTH_STATUSES.OFFLINE)
    assert.equal(ctx.manager.refreshPromise, null)
    assert.equal(ctx.manager.session.refresh_token, 'old-refresh')
  } finally {
    ctx.cleanup()
  }
})

test('delayed refresh response cannot overwrite a newer signed-out state', async () => {
  const refreshGate = deferred()
  const ctx = createManager({
    fetchImpl: async (url, init = {}) => {
      ctx.calls.push({ url, init })
      if (url.includes('/auth/v1/token?grant_type=refresh_token')) {
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
    const promise = ctx.manager.refreshSession()
    await ctx.manager.logout()
    refreshGate.resolve()
    const state = await promise

    assert.equal(state.status, AUTH_STATUSES.SIGNED_OUT)
    assert.equal(ctx.manager.session, null)
  } finally {
    ctx.cleanup()
  }
})

test('refreshStartupContext is single-flight and avoids duplicate verification calls', async () => {
  const meGate = deferred()
  const ctx = createManager({
    fetchImpl: async (url, init = {}) => {
      ctx.calls.push({ url, init })
      if (url.endsWith('/api/auth/me')) {
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
    const first = ctx.manager.refreshStartupContext()
    const second = ctx.manager.refreshStartupContext()
    meGate.resolve()
    await Promise.all([first, second])

    assert.equal(ctx.calls.filter((call) => call.url.endsWith('/api/auth/me')).length, 1)
    assert.equal(ctx.calls.filter((call) => call.url.endsWith('/api/auth/profile/bootstrap')).length, 1)
    assert.equal(ctx.manager.sessionGeneration, 1)
  } finally {
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
    assert.equal(state.status, AUTH_STATUSES.SIGNED_OUT)
    assert.equal(ctx.manager.session, null)
    assert.equal(ctx.manager.cloudCache.profile, null)
    assert.throws(() => readFileSync(ctx.manager.sessionPath, 'utf8'))
  } finally {
    ctx.cleanup()
  }
})

test('cloud cache writes reject stale generations after logout or user switch', () => {
  const ctx = createManager()
  try {
    ctx.manager.user = { user_id: 'user-1', email: 'one@example.com' }
    ctx.manager.sessionGeneration = 1
    const captured = ctx.manager.captureCloudRequestContext()
    ctx.manager._clearLocalSession(AUTH_STATUSES.SIGNED_OUT)
    assert.equal(ctx.manager.writeCloudCache(captured, { profile: { full_name: 'Old User' } }), false)
    assert.equal(ctx.manager.cloudCache.profile, null)

    ctx.manager.user = { user_id: 'user-1', email: 'one@example.com' }
    ctx.manager.sessionGeneration = 2
    const previousUser = ctx.manager.captureCloudRequestContext()
    ctx.manager.user = { user_id: 'user-2', email: 'two@example.com' }
    ctx.manager.sessionGeneration = 3
    assert.equal(ctx.manager.writeCloudCache(previousUser, { profile: { full_name: 'Wrong User' } }), false)

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
  assert.throws(() => createIpcSenderValidator({
    getExpectedWindow: () => ({ isDestroyed: () => true }),
    BrowserWindow: { fromWebContents: () => ({ isDestroyed: () => true }) },
    devOrigin: 'http://localhost:5173',
    isPackaged: false,
  })({ sender: { window: expectedWindow }, senderFrame: { url: 'http://localhost:5173/' } }), /Unauthorized IPC sender/)
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
    'getAuthState',
    'getCloudStartupContext',
    'listScreenSources',
    'logoutAuth',
    'refreshCloudStartupContext',
    'startAuthLogin',
  ].sort())
  assert.equal('access_token' in exposed.saiia, false)
  assert.equal('refresh_token' in exposed.saiia, false)
  assert.equal('fetch' in exposed.saiia, false)
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
  assert.equal(protocolRegistration > secondInstanceExit, true)
  assert.match(source, /bufferedDesktopAuthCallbacks\.push\(value\)/)
  assert.equal(managerCreation < initializeAwait, true)
  assert.equal(initializeAwait < bufferedDrain, true)
  assert.equal(bufferedDrain < argvCallback, true)
})

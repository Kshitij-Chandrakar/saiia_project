const crypto = require('crypto')
const fs = require('fs')
const path = require('path')
const { fileURLToPath } = require('url')

const AUTH_STATUSES = Object.freeze({
  SIGNED_OUT: 'signed-out',
  SIGNING_IN: 'signing-in',
  CONNECTED: 'connected',
  TOKEN_EXPIRED: 'token-expired',
  OFFLINE: 'offline',
  BOOTSTRAP_FAILED: 'bootstrap-failed',
  BACKEND_UNAVAILABLE: 'backend-unavailable',
})

const CALLBACK_URL = 'saiia://auth/callback'
const DEFAULT_BACKEND_URL = 'http://localhost:8000'
const DEFAULT_LOGIN_TTL_MS = 10 * 60 * 1000
const DEFAULT_REQUEST_TIMEOUT_MS = 15000

function base64Url(buffer) {
  return Buffer.from(buffer)
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/g, '')
}

function randomToken(bytes = 32) {
  return base64Url(crypto.randomBytes(bytes))
}

function createCodeChallenge(verifier) {
  return base64Url(crypto.createHash('sha256').update(verifier).digest())
}

function safeUser(user = null) {
  if (!user || typeof user !== 'object') {
    return { user_id: null, email: null }
  }
  return {
    user_id: typeof user.user_id === 'string' ? user.user_id : null,
    email: typeof user.email === 'string' ? user.email : null,
  }
}

function safeErrorMessage(value, fallback = '') {
  const text = String(value || fallback || '').trim()
  return text ? text.slice(0, 160) : ''
}

function normalizeOrigin(url) {
  try {
    return new URL(String(url || '')).origin
  } catch {
    return ''
  }
}

function createIpcSenderValidator(options) {
  const {
    getExpectedWindow,
    BrowserWindow,
    devOrigin = 'http://localhost:5173',
    isPackaged = false,
    packagedIndexPath = '',
  } = options
  const expectedDevOrigin = normalizeOrigin(devOrigin)
  const expectedFilePath = packagedIndexPath ? path.resolve(packagedIndexPath) : ''

  function validate(event) {
    const expectedWindow = getExpectedWindow?.()
    const actualWindow = BrowserWindow?.fromWebContents?.(event?.sender)
    if (!expectedWindow || !actualWindow || actualWindow !== expectedWindow || actualWindow.isDestroyed?.()) {
      throw new Error('Unauthorized IPC sender.')
    }

    const frame = event?.senderFrame
    if (!frame || frame.isDestroyed?.()) {
      throw new Error('Unauthorized IPC frame.')
    }

    const frameUrl = String(frame.url || '')
    let parsed
    try {
      parsed = new URL(frameUrl)
    } catch {
      throw new Error('Unauthorized IPC origin.')
    }

    if (!isPackaged) {
      if (parsed.origin !== expectedDevOrigin) {
        throw new Error('Unauthorized IPC origin.')
      }
      return true
    }

    if (parsed.protocol !== 'file:') {
      throw new Error('Unauthorized IPC origin.')
    }
    if (expectedFilePath && path.resolve(fileURLToPath(parsed)) !== expectedFilePath) {
      throw new Error('Unauthorized IPC path.')
    }
    return true
  }

  return validate
}

class DesktopAuthSessionManager {
  constructor(options = {}) {
    this.supabaseUrl = String(options.supabaseUrl || '').replace(/\/+$/, '')
    this.supabaseAnonKey = String(options.supabaseAnonKey || '')
    this.backendUrl = String(options.backendUrl || DEFAULT_BACKEND_URL).replace(/\/+$/, '')
    this.desktopAuthProvider = String(options.desktopAuthProvider || '').trim()
    this.redirectUri = String(options.redirectUri || CALLBACK_URL)
    this.loginTtlMs = Number(options.loginTtlMs || DEFAULT_LOGIN_TTL_MS)
    this.requestTimeoutMs = Number(options.requestTimeoutMs || DEFAULT_REQUEST_TIMEOUT_MS)
    this.fetchImpl = options.fetchImpl || fetch
    this.openExternal = options.openExternal || (async () => {})
    this.safeStorage = options.safeStorage || null
    this.sessionPath = options.sessionPath || ''
    this.now = options.now || (() => Date.now())
    this.beforeCacheWriteForTest = options.beforeCacheWriteForTest || null

    this.status = AUTH_STATUSES.SIGNED_OUT
    this.error = ''
    this.session = null
    this.user = null
    this.pendingLogin = null
    this.loginAttemptGeneration = 0
    this.sessionGeneration = 0
    this.refreshPromise = null
    this.startupRefreshPromise = null
    this.cloudCache = this._emptyCloudCache()
  }

  _emptyCloudCache() {
    return {
      profile: null,
      settings: null,
      startupContext: null,
      resumeContext: null,
      jobContext: null,
    }
  }

  getSafeState() {
    const user = this.status === AUTH_STATUSES.SIGNED_OUT ? safeUser(null) : safeUser(this.user)
    return {
      status: this.status,
      user_id: user.user_id,
      email: user.email,
      error: this.error,
      safeStorageAvailable: this._canPersist(),
    }
  }

  async initialize() {
    const loaded = this._readStoredSession()
    if (!loaded) {
      this.status = AUTH_STATUSES.SIGNED_OUT
      return this.getSafeState()
    }
    this.session = loaded
    return this.refreshSession()
  }

  async startLogin() {
    const previous = {
      status: this.status,
      error: this.error,
      session: this.session,
      user: this.user,
    }
    try {
      this._requireAuthConfig()
    } catch (error) {
      return this._restoreAfterLoginLaunchFailure(previous, error.message)
    }
    this.loginAttemptGeneration += 1
    const attemptGeneration = this.loginAttemptGeneration
    const codeVerifier = randomToken(48)
    const codeChallenge = createCodeChallenge(codeVerifier)
    const state = randomToken(24)
    this.pendingLogin = {
      code_verifier: codeVerifier,
      code_challenge: codeChallenge,
      code_challenge_method: 'S256',
      state,
      redirect_uri: this.redirectUri,
      expires_at: this.now() + this.loginTtlMs,
      attempt_generation: attemptGeneration,
      consumed: false,
    }
    this.status = AUTH_STATUSES.SIGNING_IN
    this.error = ''
    try {
      await this.openExternal(this._buildAuthUrl(this.pendingLogin))
    } catch {
      return this._restoreAfterLoginLaunchFailure(previous, 'Could not open browser for login.')
    }
    return this.getSafeState()
  }

  _buildAuthUrl(record) {
    const authUrl = new URL(`${this.supabaseUrl}/auth/v1/authorize`)
    authUrl.searchParams.set('redirect_uri', record.redirect_uri)
    authUrl.searchParams.set('response_type', 'code')
    authUrl.searchParams.set('code_challenge', record.code_challenge)
    authUrl.searchParams.set('code_challenge_method', record.code_challenge_method)
    authUrl.searchParams.set('state', record.state)
    authUrl.searchParams.set('provider', this.desktopAuthProvider)
    return authUrl.toString()
  }

  async handleAuthCallback(rawUrl) {
    let parsed
    try {
      parsed = new URL(String(rawUrl || ''))
    } catch {
      return this._authFailure('Invalid authentication callback.')
    }
    if (`${parsed.protocol}//${parsed.host}${parsed.pathname}` !== this.redirectUri) {
      return this._authFailure('Invalid authentication callback.')
    }

    const state = parsed.searchParams.get('state') || ''
    const code = parsed.searchParams.get('code') || ''
    const authError = parsed.searchParams.get('error') || ''
    if (!state) {
      return this._authFailure('Invalid authentication callback.')
    }

    const record = this._consumePendingLogin(state)
    if (!record) {
      return this._authFailure('Invalid or expired authentication attempt.')
    }

    if (authError && !code) {
      if (this.session && this.user) {
        this.status = AUTH_STATUSES.CONNECTED
        this.error = 'Authentication was cancelled.'
        return this.getSafeState()
      }
      this._clearLocalSession(AUTH_STATUSES.SIGNED_OUT, 'Authentication was cancelled.')
      return this.getSafeState()
    }
    if (!code) {
      return this._authFailure('Invalid authentication callback.')
    }

    let session
    try {
      session = await this._exchangeCode(code, record)
    } catch {
      return this._authFailure('Authentication exchange failed.')
    }
    if (record.attempt_generation !== this.loginAttemptGeneration) {
      return this.getSafeState()
    }
    this.session = session
    this._writeStoredSession(session)
    return this._verifyAndBootstrap(session)
  }

  _consumePendingLogin(state) {
    const record = this.pendingLogin
    if (!record || record.consumed || record.state !== state || record.expires_at <= this.now()) {
      return null
    }
    record.consumed = true
    this.pendingLogin = null
    return record
  }

  async _exchangeCode(code, record) {
    if (record.code_challenge_method !== 'S256') {
      throw new Error('Invalid authentication request.')
    }
    if (record.redirect_uri !== this.redirectUri) {
      throw new Error('Invalid authentication request.')
    }
    if (createCodeChallenge(record.code_verifier) !== record.code_challenge) {
      throw new Error('Invalid authentication request.')
    }
    const response = await this.fetchImpl(`${this.supabaseUrl}/auth/v1/token?grant_type=pkce`, {
      method: 'POST',
      headers: this._supabaseHeaders(),
      body: JSON.stringify({
        auth_code: code,
        code_verifier: record.code_verifier,
      }),
    })
    if (!response.ok) {
      throw new Error('Authentication exchange failed.')
    }
    return response.json()
  }

  async refreshSession() {
    if (this.refreshPromise) {
      return this.refreshPromise
    }
    this.refreshPromise = this._refreshSessionOnce().finally(() => {
      this.refreshPromise = null
    })
    return this.refreshPromise
  }

  async _refreshSessionOnce() {
    if (!this.session?.refresh_token) {
      this._clearLocalSession(AUTH_STATUSES.SIGNED_OUT)
      return this.getSafeState()
    }
    const refreshSession = this.session
    const refreshGeneration = this.sessionGeneration
    try {
      const response = await this.fetchImpl(`${this.supabaseUrl}/auth/v1/token?grant_type=refresh_token`, {
        method: 'POST',
        headers: this._supabaseHeaders(),
        body: JSON.stringify({ refresh_token: this.session.refresh_token }),
        signal: this._requestSignal(),
      })
      if (this.session !== refreshSession || this.sessionGeneration !== refreshGeneration) {
        return this.getSafeState()
      }
      if ([400, 401, 403].includes(response.status)) {
        this._clearLocalSession(AUTH_STATUSES.TOKEN_EXPIRED, 'Session expired. Please log in again.')
        return this.getSafeState()
      }
      if (response.status === 503) {
        this.status = AUTH_STATUSES.BACKEND_UNAVAILABLE
        this.error = 'Cloud authentication is temporarily unavailable.'
        return this.getSafeState()
      }
      if (!response.ok) {
        this.status = AUTH_STATUSES.OFFLINE
        this.error = 'Cloud authentication is temporarily unavailable.'
        return this.getSafeState()
      }
      const session = await response.json()
      this.session = session
      this._writeStoredSession(session)
      return this._verifyAndBootstrap(session)
    } catch {
      this.status = AUTH_STATUSES.OFFLINE
      this.error = 'Cloud authentication is temporarily unavailable.'
      return this.getSafeState()
    }
  }

  async _verifyAndBootstrap(session) {
    const entrySession = session
    const entryGeneration = this.sessionGeneration
    const verified = await this._backendJson('/api/auth/me', 'GET', session.access_token)
    if (this.session !== entrySession || this.sessionGeneration !== entryGeneration) {
      return this.getSafeState()
    }
    if (verified.status === 401) {
      this._clearLocalSession(AUTH_STATUSES.TOKEN_EXPIRED, 'Session expired. Please log in again.')
      return this.getSafeState()
    }
    if (verified.status === 503 || verified.status === 0) {
      this.status = verified.status === 503 ? AUTH_STATUSES.BACKEND_UNAVAILABLE : AUTH_STATUSES.OFFLINE
      this.error = 'Backend is temporarily unavailable.'
      return this.getSafeState()
    }
    if (!verified.ok) {
      this.status = AUTH_STATUSES.BACKEND_UNAVAILABLE
      this.error = 'Backend authentication failed.'
      return this.getSafeState()
    }

    const nextUser = safeUser(verified.payload)
    if (this.user?.user_id && nextUser.user_id && this.user.user_id !== nextUser.user_id) {
      this._clearCloudCache()
    }
    this.user = nextUser
    this.sessionGeneration += 1
    const bootstrapGeneration = this.sessionGeneration

    const bootstrapped = await this._backendJson('/api/auth/profile/bootstrap', 'POST', session.access_token)
    if (
      this.session !== entrySession ||
      this.sessionGeneration !== bootstrapGeneration ||
      this.user?.user_id !== nextUser.user_id
    ) {
      return this.getSafeState()
    }
    if (bootstrapped.status === 502) {
      this.status = AUTH_STATUSES.BOOTSTRAP_FAILED
      this.error = 'Profile setup could not be completed.'
      return this.getSafeState()
    }
    if (bootstrapped.status === 401) {
      this._clearLocalSession(AUTH_STATUSES.TOKEN_EXPIRED, 'Session expired. Please log in again.')
      return this.getSafeState()
    }
    if (bootstrapped.status === 503 || bootstrapped.status === 0) {
      this.status = bootstrapped.status === 503 ? AUTH_STATUSES.BACKEND_UNAVAILABLE : AUTH_STATUSES.OFFLINE
      this.error = 'Backend is temporarily unavailable.'
      return this.getSafeState()
    }

    if (!bootstrapped.ok) {
      this.status = AUTH_STATUSES.BACKEND_UNAVAILABLE
      this.error = 'Profile setup could not be completed.'
      return this.getSafeState()
    }

    this.status = AUTH_STATUSES.CONNECTED
    this.error = ''
    return this.getSafeState()
  }

  async _backendJson(route, method, accessToken) {
    try {
      const response = await this.fetchImpl(`${this.backendUrl}${route}`, {
        method,
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
        signal: this._requestSignal(),
      })
      const payload = await response.json().catch(() => ({}))
      return { ok: response.ok, status: response.status, payload }
    } catch {
      return { ok: false, status: 0, payload: {} }
    }
  }

  async logout() {
    const session = this.session
    try {
      if (session?.access_token) {
        await this.fetchImpl(`${this.supabaseUrl}/auth/v1/logout`, {
          method: 'POST',
          headers: {
            ...this._supabaseHeaders(),
            Authorization: `Bearer ${session.access_token}`,
          },
        })
      }
    } catch {
      // Local cleanup is mandatory even when remote sign-out fails.
    } finally {
      this._clearLocalSession(AUTH_STATUSES.SIGNED_OUT)
    }
    return this.getSafeState()
  }

  getStartupContext() {
    return {
      auth: this.getSafeState(),
      profile: this.cloudCache.profile,
      settings: this.cloudCache.settings,
      startupContext: this.cloudCache.startupContext,
      resumeContext: this.cloudCache.resumeContext,
      jobContext: this.cloudCache.jobContext,
    }
  }

  async refreshStartupContext() {
    if (this.startupRefreshPromise) {
      return this.startupRefreshPromise
    }
    this.startupRefreshPromise = this._refreshStartupContextOnce().finally(() => {
      this.startupRefreshPromise = null
    })
    return this.startupRefreshPromise
  }

  async _refreshStartupContextOnce() {
    if (this.session?.access_token) {
      await this._verifyAndBootstrap(this.session)
    }
    return this.getStartupContext()
  }

  captureCloudRequestContext() {
    return {
      session_generation: this.sessionGeneration,
      user_id: this.user?.user_id || null,
    }
  }

  writeCloudCache(captured, nextCache) {
    if (typeof this.beforeCacheWriteForTest === 'function') {
      this.beforeCacheWriteForTest()
    }
    if (
      !captured ||
      captured.session_generation !== this.sessionGeneration ||
      !captured.user_id ||
      captured.user_id !== this.user?.user_id
    ) {
      return false
    }
    this.cloudCache = {
      ...this.cloudCache,
      ...nextCache,
    }
    return true
  }

  _clearLocalSession(status, message = '') {
    this.loginAttemptGeneration += 1
    this.sessionGeneration += 1
    this.pendingLogin = null
    this.session = null
    this.user = null
    this.status = status
    this.error = safeErrorMessage(message)
    this._clearCloudCache()
    this._deleteStoredSession()
  }

  _clearCloudCache() {
    this.cloudCache = this._emptyCloudCache()
  }

  _canPersist() {
    return Boolean(this.safeStorage?.isEncryptionAvailable?.())
  }

  _readStoredSession() {
    if (!this._canPersist() || !this.sessionPath || !fs.existsSync(this.sessionPath)) {
      return null
    }
    try {
      const encrypted = fs.readFileSync(this.sessionPath)
      return JSON.parse(this.safeStorage.decryptString(encrypted))
    } catch {
      return null
    }
  }

  _writeStoredSession(session) {
    if (!this._canPersist() || !this.sessionPath) {
      return
    }
    try {
      const encrypted = this.safeStorage.encryptString(JSON.stringify(session))
      fs.mkdirSync(path.dirname(this.sessionPath), { recursive: true })
      fs.writeFileSync(this.sessionPath, encrypted, { mode: 0o600 })
      try {
        fs.chmodSync(this.sessionPath, 0o600)
      } catch {}
    } catch {}
  }

  _deleteStoredSession() {
    if (!this.sessionPath) {
      return
    }
    try {
      fs.rmSync(this.sessionPath, { force: true })
    } catch {}
  }

  _supabaseHeaders() {
    return {
      apikey: this.supabaseAnonKey,
      'Content-Type': 'application/json',
    }
  }

  _requireAuthConfig() {
    if (!this.supabaseUrl || !this.supabaseAnonKey || !this.desktopAuthProvider) {
      throw new Error('Desktop cloud auth is not configured.')
    }
  }

  _authFailure(message, options = {}) {
    if (options.clearPending) {
      this.pendingLogin = null
    }
    if (this.session && this.user) {
      this.status = AUTH_STATUSES.CONNECTED
      this.error = safeErrorMessage(message, 'Authentication failed.')
      return this.getSafeState()
    }
    this.session = null
    this.user = null
    this.status = AUTH_STATUSES.SIGNED_OUT
    this.error = safeErrorMessage(message, 'Authentication failed.')
    return this.getSafeState()
  }

  _restoreAfterLoginLaunchFailure(previous, message) {
    this.pendingLogin = null
    this.session = previous.session || null
    this.user = previous.session && previous.user ? previous.user : null
    this.status = this.session && this.user ? previous.status : AUTH_STATUSES.SIGNED_OUT
    if (this.status === AUTH_STATUSES.SIGNING_IN) {
      this.status = AUTH_STATUSES.SIGNED_OUT
      this.user = null
    }
    this.error = safeErrorMessage(message, 'Authentication failed.')
    return this.getSafeState()
  }

  _requestSignal() {
    if (this.requestTimeoutMs > 0 && typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function') {
      return AbortSignal.timeout(this.requestTimeoutMs)
    }
    return undefined
  }
}

module.exports = {
  AUTH_STATUSES,
  CALLBACK_URL,
  DesktopAuthSessionManager,
  createCodeChallenge,
  createIpcSenderValidator,
}

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
const DEFAULT_WEB_AUTH_URL = 'http://localhost:5173/auth/desktop-login'
const DEFAULT_LOGIN_TTL_MS = 10 * 60 * 1000
const DEFAULT_REQUEST_TIMEOUT_MS = 15000
const DEFAULT_VERIFICATION_FRESHNESS_MS = 30000
const DESKTOP_STATE_PARAM = 'desktop_state'
const MISSING_DESKTOP_AUTH_CONFIG_MESSAGE =
  'Desktop cloud auth is not configured. Set SUPABASE_URL or VITE_SUPABASE_URL, SUPABASE_ANON_KEY or VITE_SUPABASE_ANON_KEY, and SAIIA_WEB_AUTH_URL or VITE_SAIIA_WEB_AUTH_URL in the environment that launches Electron.'

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

function validPositiveNumber(value, fallback) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

function isNonEmptyString(value) {
  return typeof value === 'string' && value.trim().length > 0
}

function validateAuthSession(value) {
  if (!value || typeof value !== 'object') {
    throw new Error('Invalid authentication session.')
  }
  if (!isNonEmptyString(value.access_token) || !isNonEmptyString(value.refresh_token)) {
    throw new Error('Invalid authentication session.')
  }
  return value
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
    this.supabaseUrl = String(options.supabaseUrl ?? '').replace(/\/+$/, '')
    this.supabaseAnonKey = String(options.supabaseAnonKey ?? '')
    this.backendUrl = String(options.backendUrl ?? DEFAULT_BACKEND_URL).replace(/\/+$/, '')
    this.webAuthUrl = String(options.webAuthUrl ?? DEFAULT_WEB_AUTH_URL).trim()
    this.redirectUri = String(options.redirectUri || CALLBACK_URL)
    this.loginTtlMs = validPositiveNumber(options.loginTtlMs, DEFAULT_LOGIN_TTL_MS)
    this.requestTimeoutMs = validPositiveNumber(options.requestTimeoutMs, DEFAULT_REQUEST_TIMEOUT_MS)
    this.verificationFreshnessMs = validPositiveNumber(options.verificationFreshnessMs, DEFAULT_VERIFICATION_FRESHNESS_MS)
    this.requestSignalFactory = options.requestSignalFactory || null
    this.fetchImpl = options.fetchImpl || fetch
    this.openExternal = options.openExternal || (async () => {})
    this.logger = options.logger || console
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
    this.verificationCache = null
    this.cloudCache = this._emptyCloudCache()
  }

  _emptyCloudCache() {
    return {
      profile: null,
      settings: null,
      startupContext: this._buildCloudSummary(),
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
    if (this._pendingLoginIsActive()) {
      return this.getSafeState()
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
      const authUrl = this._buildAuthUrl(this.pendingLogin)
      this._logWebsiteHandoffUrlDebug(authUrl, this.pendingLogin)
      await this.openExternal(authUrl)
    } catch {
      if (
        this.loginAttemptGeneration !== attemptGeneration ||
        !this.pendingLogin ||
        this.pendingLogin.attempt_generation !== attemptGeneration
      ) {
        return this.getSafeState()
      }
      return this._restoreAfterLoginLaunchFailure(previous, 'Could not open browser for login.')
    }
    return this.getSafeState()
  }

  _buildAuthUrl(record) {
    const authUrl = new URL(this.webAuthUrl)
    authUrl.searchParams.set('state', record.state)
    return authUrl.toString()
  }

  _logWebsiteHandoffUrlDebug(rawUrl, record = null) {
    if (!this.logger || typeof this.logger.debug !== 'function') {
      return
    }
    try {
      const authUrl = new URL(rawUrl)
      this.logger.debug('Desktop auth website handoff URL prepared.', {
        origin: authUrl.origin,
        path: authUrl.pathname,
        queryKeys: Array.from(new Set(authUrl.searchParams.keys())).sort(),
        stateExists: authUrl.searchParams.has('state'),
        pendingAttemptId: record?.attempt_generation || null,
      })
    } catch {}
  }

  async handleAuthCallback(rawUrl) {
    let parsed
    try {
      parsed = new URL(String(rawUrl || ''))
    } catch {
      return this._authFailure('Invalid authentication callback.')
    }
    if (`${parsed.protocol}//${parsed.host}${parsed.pathname}` !== this.redirectUri) {
      if (
        (parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1') &&
        parsed.searchParams.has('code')
      ) {
        return this._failPendingAuth('Desktop auth returned to localhost. Add saiia://auth/callback to Supabase redirect URLs and start login again.')
      }
      return this._authFailure('Invalid authentication callback.')
    }

    const state = parsed.searchParams.get(DESKTOP_STATE_PARAM) || parsed.searchParams.get('state') || ''
    const handoffCode = parsed.searchParams.get('handoff_code') || ''
    const code = parsed.searchParams.get('code') || ''
    const authError = parsed.searchParams.get('error') || ''
    const authErrorCode = parsed.searchParams.get('error_code') || ''
    if (authErrorCode === 'bad_oauth_state') {
      return this._failPendingAuth('Authentication state was rejected. Start login again.')
    }
    if (!state && !code && !handoffCode) {
      return this._authFailure('Invalid authentication callback.')
    }

    if (handoffCode && !state) {
      return this._authFailure('Invalid authentication callback.')
    }

    const record = this._consumePendingLogin(state)
    if (!record) {
      if (this._pendingLoginIsActive()) {
        this.error = 'Invalid or expired authentication attempt.'
        return this.getSafeState()
      }
      return this._authFailure('Invalid or expired authentication attempt.')
    }

    if (authError && !code && !handoffCode) {
      if (this.session && this.user) {
        this.status = AUTH_STATUSES.CONNECTED
        this.error = 'Authentication was cancelled.'
        return this.getSafeState()
      }
      this._clearLocalSession(AUTH_STATUSES.SIGNED_OUT, 'Authentication was cancelled.')
      return this.getSafeState()
    }
    if (handoffCode) {
      let session
      try {
        session = await this._exchangeHandoffCode(handoffCode, record)
      } catch {
        return this._authFailure('Authentication exchange failed.')
      }
      return this._installExchangedSession(session, record)
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
    return this._installExchangedSession(session, record)
  }

  _consumePendingLogin(state) {
    const record = this.pendingLogin
    if (!record || record.consumed || record.expires_at <= this.now()) {
      return null
    }
    if (!state || record.state !== state) {
      return null
    }
    record.consumed = true
    this.pendingLogin = null
    return record
  }

  _pendingLoginIsActive() {
    const record = this.pendingLogin
    return Boolean(
      record &&
      !record.consumed &&
      record.expires_at > this.now() &&
      this.status === AUTH_STATUSES.SIGNING_IN
    )
  }

  _failPendingAuth(message) {
    this.pendingLogin = null
    if (this.session && this.user) {
      this.status = AUTH_STATUSES.CONNECTED
      this.error = safeErrorMessage(message, 'Authentication failed.')
      return this.getSafeState()
    }
    this._clearLocalSession(AUTH_STATUSES.SIGNED_OUT, message)
    return this.getSafeState()
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
      signal: this._requestSignal(),
    })
    if (!response.ok) {
      throw new Error('Authentication exchange failed.')
    }
    return validateAuthSession(await response.json())
  }

  async _exchangeHandoffCode(handoffCode, record) {
    const response = await this.fetchImpl(`${this.backendUrl}/api/auth/desktop-handoff/exchange`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        handoff_code: handoffCode,
        state: record.state,
      }),
      signal: this._requestSignal(),
    })
    if (!response.ok) {
      throw new Error('Authentication exchange failed.')
    }
    return validateAuthSession(await response.json())
  }

  _installExchangedSession(session, record) {
    if (record.attempt_generation !== this.loginAttemptGeneration) {
      return this.getSafeState()
    }
    this.session = session
    this.sessionGeneration += 1
    this.user = null
    this._clearCloudCache()
    this._writeStoredSession(session)
    return this._verifyAndBootstrap(session)
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
    let refreshedSession = null
    const isStaleRefresh = () => (
      this.session !== refreshSession &&
      this.session !== refreshedSession
    ) || this.sessionGeneration !== refreshGeneration
    try {
      const response = await this.fetchImpl(`${this.supabaseUrl}/auth/v1/token?grant_type=refresh_token`, {
        method: 'POST',
        headers: this._supabaseHeaders(),
        body: JSON.stringify({ refresh_token: refreshSession.refresh_token }),
        signal: this._requestSignal(),
      })
      if (isStaleRefresh()) {
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
      const session = validateAuthSession(await response.json())
      if (isStaleRefresh()) {
        return this.getSafeState()
      }
      refreshedSession = session
      this.session = session
      this._writeStoredSession(session)
      return await this._verifyAndBootstrap(session)
    } catch {
      if (isStaleRefresh()) {
        return this.getSafeState()
      }
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
      this._clearVerificationCache()
      this.status = verified.status === 503 ? AUTH_STATUSES.BACKEND_UNAVAILABLE : AUTH_STATUSES.OFFLINE
      this.error = 'Backend is temporarily unavailable.'
      return this.getSafeState()
    }
    if (!verified.ok) {
      this._clearVerificationCache()
      this.status = AUTH_STATUSES.BACKEND_UNAVAILABLE
      this.error = 'Backend authentication failed.'
      return this.getSafeState()
    }

    const nextUser = safeUser(verified.payload)
    if (!isNonEmptyString(nextUser.user_id)) {
      this._clearLocalSession(AUTH_STATUSES.SIGNED_OUT, 'Backend authentication failed.')
      return this.getSafeState()
    }
    if (this.user?.user_id && nextUser.user_id && this.user.user_id !== nextUser.user_id) {
      this._clearVerificationCache()
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
      this._clearVerificationCache()
      this.status = AUTH_STATUSES.BOOTSTRAP_FAILED
      this.error = 'Profile setup could not be completed.'
      return this.getSafeState()
    }
    if (bootstrapped.status === 401) {
      this._clearLocalSession(AUTH_STATUSES.TOKEN_EXPIRED, 'Session expired. Please log in again.')
      return this.getSafeState()
    }
    if (bootstrapped.status === 503 || bootstrapped.status === 0) {
      this._clearVerificationCache()
      this.status = bootstrapped.status === 503 ? AUTH_STATUSES.BACKEND_UNAVAILABLE : AUTH_STATUSES.OFFLINE
      this.error = 'Backend is temporarily unavailable.'
      return this.getSafeState()
    }

    if (!bootstrapped.ok) {
      this._clearVerificationCache()
      this.status = AUTH_STATUSES.BACKEND_UNAVAILABLE
      this.error = 'Profile setup could not be completed.'
      return this.getSafeState()
    }

    this.status = AUTH_STATUSES.CONNECTED
    this.error = ''
    this._storeVerificationCache(session, nextUser.user_id)
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
    const logoutLoginGeneration = this.loginAttemptGeneration
    const logoutSessionGeneration = this.sessionGeneration
    try {
      if (session?.access_token) {
        await this.fetchImpl(`${this.supabaseUrl}/auth/v1/logout`, {
          method: 'POST',
          headers: {
            ...this._supabaseHeaders(),
            Authorization: `Bearer ${session.access_token}`,
          },
          signal: this._requestSignal(),
        })
      }
    } catch {
      // Local cleanup is mandatory even when remote sign-out fails.
    } finally {
      if (
        this.session === session &&
        this.loginAttemptGeneration === logoutLoginGeneration &&
        this.sessionGeneration === logoutSessionGeneration
      ) {
        this._clearLocalSession(AUTH_STATUSES.SIGNED_OUT)
      }
    }
    return this.getSafeState()
  }

  getStartupContext() {
    const cloud = this.status === AUTH_STATUSES.CONNECTED && this.cloudCache.startupContext
      ? this.cloudCache.startupContext
      : this._buildCloudSummary()
    return {
      auth: this.getSafeState(),
      cloud,
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
    if (!this.session?.access_token) {
      return this.getStartupContext()
    }

    if (!this._hasFreshVerification(this.session)) {
      await this._verifyAndBootstrap(this.session)
    }
    if (this.status !== AUTH_STATUSES.CONNECTED || !this.session?.access_token || !this.user?.user_id) {
      return this.getStartupContext()
    }

    const captured = this.captureCloudRequestContext()
    const session = this.session
    const [resumeResult, jobContextResult] = await Promise.all([
      this._loadResumeReadiness(session.access_token),
      this._loadJobContextReadiness(session.access_token),
    ])
    if (!this._cloudRequestStillCurrent(captured)) {
      return this.getStartupContext()
    }

    const unavailable = [resumeResult, jobContextResult].find((result) => result.unavailable)
    const nextCache = {
      startupContext: this._buildCloudSummary({
        available: !unavailable,
        mode: unavailable ? 'unavailable' : 'cloud',
        profileReady: true,
        resumeReady: resumeResult.ready,
        jobContextReady: jobContextResult.ready,
        lastError: unavailable?.message || '',
      }),
      resumeContext: resumeResult.context,
      jobContext: jobContextResult.context,
    }
    this.writeCloudCache(captured, nextCache)
    return this.getStartupContext()
  }

  captureCloudRequestContext() {
    return {
      session_generation: this.sessionGeneration,
      session: this.session || null,
      user_id: this.user?.user_id || null,
    }
  }

  writeCloudCache(captured, nextCache) {
    if (typeof this.beforeCacheWriteForTest === 'function') {
      this.beforeCacheWriteForTest()
    }
    if (!this._cloudRequestStillCurrent(captured)) {
      return false
    }
    this.cloudCache = {
      ...this.cloudCache,
      ...nextCache,
    }
    return true
  }

  _cloudRequestStillCurrent(captured) {
    return Boolean(
      captured &&
      captured.session_generation === this.sessionGeneration &&
      captured.session === (this.session || null) &&
      captured.user_id &&
      captured.user_id === this.user?.user_id,
    )
  }

  _hasFreshVerification(session) {
    return Boolean(
      this.verificationCache &&
      this.status === AUTH_STATUSES.CONNECTED &&
      session &&
      isNonEmptyString(session.access_token) &&
      isNonEmptyString(this.user?.user_id) &&
      this.verificationCache.session_generation === this.sessionGeneration &&
      this.verificationCache.access_token === session.access_token &&
      this.verificationCache.user_id === this.user.user_id &&
      this.now() - this.verificationCache.verified_at <= this.verificationFreshnessMs,
    )
  }

  _storeVerificationCache(session, userId) {
    if (
      this.status !== AUTH_STATUSES.CONNECTED ||
      !session ||
      !isNonEmptyString(session.access_token) ||
      !isNonEmptyString(userId)
    ) {
      this._clearVerificationCache()
      return
    }
    this.verificationCache = {
      session_generation: this.sessionGeneration,
      access_token: session.access_token,
      user_id: userId,
      verified_at: this.now(),
    }
  }

  _clearVerificationCache() {
    this.verificationCache = null
  }

  async _loadResumeReadiness(accessToken) {
    const response = await this._backendJson('/api/resumes/current', 'GET', accessToken)
    if (response.status === 401) {
      this._clearLocalSession(AUTH_STATUSES.TOKEN_EXPIRED, 'Session expired. Please log in again.')
      return this._unavailableReadiness('Session expired. Please log in again.')
    }
    if (response.status === 0 || response.status === 503) {
      return this._unavailableReadiness('Cloud temporarily unavailable.')
    }
    if (!response.ok) {
      return { ready: false, context: null, unavailable: false, message: '' }
    }
    const resume = response.payload?.resume && typeof response.payload.resume === 'object'
      ? {
          id: typeof response.payload.resume.id === 'string' ? response.payload.resume.id : null,
          status: typeof response.payload.resume.status === 'string' ? response.payload.resume.status : '',
          is_active: Boolean(response.payload.resume.is_active),
        }
      : null
    return {
      ready: Boolean(response.payload?.ready && resume),
      context: resume ? { ready: Boolean(response.payload?.ready), resume } : null,
      unavailable: false,
      message: '',
    }
  }

  async _loadJobContextReadiness(accessToken) {
    const response = await this._backendJson('/api/job-contexts?limit=50', 'GET', accessToken)
    if (response.status === 401) {
      this._clearLocalSession(AUTH_STATUSES.TOKEN_EXPIRED, 'Session expired. Please log in again.')
      return this._unavailableReadiness('Session expired. Please log in again.')
    }
    if (response.status === 0 || response.status === 503) {
      return this._unavailableReadiness('Cloud temporarily unavailable.')
    }
    if (!response.ok || !Array.isArray(response.payload?.items)) {
      return { ready: false, context: null, unavailable: false, message: '' }
    }
    const activeId = typeof response.payload.active_id === 'string' ? response.payload.active_id : null
    if (!activeId) {
      return { ready: false, context: null, unavailable: false, message: '' }
    }
    const active = response.payload.items.find((item) => item && typeof item === 'object' && item.id === activeId) || null
    const safeActive = active
      ? {
          id: typeof active.id === 'string' ? active.id : null,
          company: typeof active.company === 'string' ? active.company : '',
          position: typeof active.position === 'string' ? active.position : '',
          is_active: Boolean(active.is_active),
        }
      : null
    return {
      ready: Boolean(activeId && safeActive),
      context: { active_id: activeId, active: safeActive },
      unavailable: false,
      message: '',
    }
  }

  _unavailableReadiness(message) {
    return {
      ready: false,
      context: null,
      unavailable: true,
      message: safeErrorMessage(message, 'Cloud temporarily unavailable.'),
    }
  }

  _buildCloudSummary(overrides = {}) {
    const status = overrides.authStatus || this.status
    const connected = status === AUTH_STATUSES.CONNECTED
    const localOnly = [AUTH_STATUSES.SIGNED_OUT, AUTH_STATUSES.TOKEN_EXPIRED].includes(status)
    const unavailable = [
      AUTH_STATUSES.OFFLINE,
      AUTH_STATUSES.BACKEND_UNAVAILABLE,
      AUTH_STATUSES.BOOTSTRAP_FAILED,
    ].includes(status)
    return {
      available: typeof overrides.available === 'boolean' ? overrides.available : connected,
      mode: overrides.mode || (connected ? 'cloud' : localOnly ? 'local-only' : unavailable ? 'unavailable' : 'local-only'),
      profileReady: typeof overrides.profileReady === 'boolean' ? overrides.profileReady : connected,
      resumeReady: Boolean(overrides.resumeReady),
      jobContextReady: Boolean(overrides.jobContextReady),
      lastError: safeErrorMessage(overrides.lastError || this.error),
    }
  }

  _clearLocalSession(status, message = '') {
    this.loginAttemptGeneration += 1
    this.sessionGeneration += 1
    this.pendingLogin = null
    this.session = null
    this.user = null
    this.status = status
    this.error = safeErrorMessage(message)
    this._clearVerificationCache()
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
    if (!this.supabaseUrl || !this.supabaseAnonKey || !this.webAuthUrl) {
      throw new Error(MISSING_DESKTOP_AUTH_CONFIG_MESSAGE)
    }
    let authUrl
    try {
      authUrl = new URL(this.webAuthUrl)
    } catch {
      throw new Error(MISSING_DESKTOP_AUTH_CONFIG_MESSAGE)
    }
    if (!['http:', 'https:'].includes(authUrl.protocol)) {
      throw new Error(MISSING_DESKTOP_AUTH_CONFIG_MESSAGE)
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
    if (typeof this.requestSignalFactory === 'function') {
      return this.requestSignalFactory()
    }
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

export const DESKTOP_AUTH_STATUSES = Object.freeze({
  SIGNED_OUT: 'signed-out',
  SIGNING_IN: 'signing-in',
  CONNECTED: 'connected',
  TOKEN_EXPIRED: 'token-expired',
  OFFLINE: 'offline',
  BOOTSTRAP_FAILED: 'bootstrap-failed',
  BACKEND_UNAVAILABLE: 'backend-unavailable',
})

export const DESKTOP_AUTH_ERROR_CODES = Object.freeze({
  CONFIGURATION: 'configuration',
  BROWSER_LAUNCH_FAILED: 'browser-launch-failed',
  LOGIN_TIMEOUT: 'login-timeout',
  SESSION_EXPIRED: 'session-expired',
  SERVICE_UNAVAILABLE: 'service-unavailable',
  CANCELED: 'canceled',
  UNKNOWN: 'unknown',
})

const SUPPORTED_DESKTOP_AUTH_STATUSES = new Set(Object.values(DESKTOP_AUTH_STATUSES))
const SUPPORTED_DESKTOP_AUTH_ERROR_CODES = new Set(Object.values(DESKTOP_AUTH_ERROR_CODES))

export function normalizeDesktopAuthState(value = {}) {
  const candidateStatus = String(value?.status || DESKTOP_AUTH_STATUSES.SIGNED_OUT)
  const status = SUPPORTED_DESKTOP_AUTH_STATUSES.has(candidateStatus)
    ? candidateStatus
    : DESKTOP_AUTH_STATUSES.SIGNED_OUT
  const connected = status === DESKTOP_AUTH_STATUSES.CONNECTED
  return {
    status,
    user_id: connected && typeof value?.user_id === 'string' ? value.user_id : null,
    email: connected && typeof value?.email === 'string' ? value.email : null,
    error: typeof value?.error === 'string' ? value.error : '',
    error_code: SUPPORTED_DESKTOP_AUTH_ERROR_CODES.has(value?.error_code) ? value.error_code : '',
  }
}

export function getDesktopStartupErrorView(value = {}) {
  const state = normalizeDesktopAuthState(value?.auth || value)
  const isServiceUnavailable = [
    DESKTOP_AUTH_STATUSES.OFFLINE,
    DESKTOP_AUTH_STATUSES.BACKEND_UNAVAILABLE,
  ].includes(state.status) || state.error_code === DESKTOP_AUTH_ERROR_CODES.SERVICE_UNAVAILABLE

  if (state.status === DESKTOP_AUTH_STATUSES.TOKEN_EXPIRED || state.error_code === DESKTOP_AUTH_ERROR_CODES.SESSION_EXPIRED) {
    return {
      message: 'Your session has expired. Please sign in again to continue.',
      actionLabel: 'Sign in again',
    }
  }
  if (state.error_code === DESKTOP_AUTH_ERROR_CODES.LOGIN_TIMEOUT) {
    return {
      message: 'Sign-in timed out. Please try signing in again.',
      actionLabel: 'Try again',
    }
  }
  if (state.error_code === DESKTOP_AUTH_ERROR_CODES.BROWSER_LAUNCH_FAILED) {
    return {
      message: 'We couldn\'t open your browser. Please try again.',
      actionLabel: 'Try again',
    }
  }
  if (isServiceUnavailable) {
    return {
      message: 'We couldn\'t connect to the sign-in service. Please check your connection and try again.',
      actionLabel: 'Try again',
    }
  }
  if (state.error_code === DESKTOP_AUTH_ERROR_CODES.CONFIGURATION || /Desktop cloud auth is not configured/i.test(state.error)) {
    return {
      message: 'Desktop auth is not configured.',
      actionLabel: 'Try again',
    }
  }
  if (state.error_code === DESKTOP_AUTH_ERROR_CODES.CANCELED || /Authentication was cancelled/i.test(state.error)) {
    return {
      message: 'Sign-in was cancelled. Please try again.',
      actionLabel: 'Try again',
    }
  }
  if (!state.error) {
    return { message: '', actionLabel: 'Login with Intervu AI \u2192' }
  }
  return {
    message: 'We couldn\'t complete sign-in. Please try again.',
    actionLabel: 'Try again',
  }
}

export function normalizeDesktopCloudState(value = {}, authState = normalizeDesktopAuthState()) {
  const connected = authState.status === DESKTOP_AUTH_STATUSES.CONNECTED
  const mode = ['cloud', 'local-only', 'unavailable'].includes(value?.mode) ? value.mode : (
    connected ? 'cloud' : 'local-only'
  )
  return {
    available: connected && Boolean(value?.available),
    mode,
    profileReady: connected && Boolean(value?.profileReady),
    resumeReady: connected && Boolean(value?.resumeReady),
    jobContextReady: connected && Boolean(value?.jobContextReady),
    lastError: typeof value?.lastError === 'string' ? value.lastError : '',
  }
}

export function createDesktopAuthRequestTracker() {
  let currentRequestId = 0
  return {
    start() {
      currentRequestId += 1
      return currentRequestId
    },
    isCurrent(requestId) {
      return requestId === currentRequestId
    },
  }
}

export function getDesktopAuthViewModel(value = {}) {
  const state = normalizeDesktopAuthState(value?.auth || value)
  const cloud = normalizeDesktopCloudState(value?.cloud || value?.startupContext || {}, state)
  const isSigningIn = state.status === DESKTOP_AUTH_STATUSES.SIGNING_IN
  const sessionLike = [
    DESKTOP_AUTH_STATUSES.CONNECTED,
    DESKTOP_AUTH_STATUSES.OFFLINE,
    DESKTOP_AUTH_STATUSES.BACKEND_UNAVAILABLE,
    DESKTOP_AUTH_STATUSES.BOOTSTRAP_FAILED,
  ].includes(state.status)

  const copy = {
    [DESKTOP_AUTH_STATUSES.SIGNED_OUT]: ['Signed out', 'Log in to connect cloud identity. Local desktop tools remain available.'],
    [DESKTOP_AUTH_STATUSES.SIGNING_IN]: ['Signing in', 'Complete login in your browser.'],
    [DESKTOP_AUTH_STATUSES.CONNECTED]: ['Connected', 'Cloud identity is connected.'],
    [DESKTOP_AUTH_STATUSES.TOKEN_EXPIRED]: ['Session expired', 'Session expired. Log in again.'],
    [DESKTOP_AUTH_STATUSES.OFFLINE]: ['Offline', 'Cloud temporarily unavailable. Local desktop tools remain available.'],
    [DESKTOP_AUTH_STATUSES.BACKEND_UNAVAILABLE]: ['Backend unavailable', 'Cloud temporarily unavailable. Local desktop tools remain available.'],
    [DESKTOP_AUTH_STATUSES.BOOTSTRAP_FAILED]: ['Profile setup failed', 'Profile setup could not be completed.'],
  }[state.status] || ['Signed out', 'Log in to connect cloud identity. Local desktop tools remain available.']

  return {
    ...state,
    cloud,
    label: copy[0],
    detail: state.error || copy[1],
    cloudLabel: getCloudReadinessLabel(cloud, state.status),
    cloudDetail: getCloudReadinessDetail(cloud, state.status),
    showLogin: [
      DESKTOP_AUTH_STATUSES.SIGNED_OUT,
      DESKTOP_AUTH_STATUSES.SIGNING_IN,
      DESKTOP_AUTH_STATUSES.TOKEN_EXPIRED,
    ].includes(state.status),
    showLogout: sessionLike,
    showRefresh: sessionLike,
    loginDisabled: isSigningIn,
  }
}

function getCloudReadinessLabel(cloud, status) {
  if (status === DESKTOP_AUTH_STATUSES.SIGNING_IN) {
    return 'Checking cloud'
  }
  if (status === DESKTOP_AUTH_STATUSES.SIGNED_OUT || status === DESKTOP_AUTH_STATUSES.TOKEN_EXPIRED) {
    return 'Local-only mode'
  }
  if (cloud.mode === 'unavailable' || !cloud.available) {
    return 'Cloud unavailable'
  }
  if (cloud.profileReady && cloud.resumeReady && cloud.jobContextReady) {
    return 'Cloud ready'
  }
  if (!cloud.resumeReady) {
    return 'Resume not ready'
  }
  if (!cloud.jobContextReady) {
    return 'Job target not ready'
  }
  return 'Cloud ready'
}

function getCloudReadinessDetail(cloud, status) {
  if (status === DESKTOP_AUTH_STATUSES.SIGNING_IN) {
    return 'Complete login in your browser. Local desktop tools remain available.'
  }
  if (status === DESKTOP_AUTH_STATUSES.SIGNED_OUT || status === DESKTOP_AUTH_STATUSES.TOKEN_EXPIRED) {
    return 'Local desktop tools remain available.'
  }
  if (cloud.mode === 'unavailable' || !cloud.available) {
    return cloud.lastError || 'Cloud temporarily unavailable. Local desktop tools remain available.'
  }
  if (cloud.profileReady && cloud.resumeReady && cloud.jobContextReady) {
    return 'Profile, resume, and job target are available for future startup setup.'
  }
  const missing = []
  if (!cloud.resumeReady) {
    missing.push('resume')
  }
  if (!cloud.jobContextReady) {
    missing.push('job target')
  }
  return missing.length
    ? `Cloud connected. Missing ${missing.join(' and ')} for future startup setup.`
    : 'Cloud connected.'
}

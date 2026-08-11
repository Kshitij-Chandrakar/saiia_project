export const DESKTOP_AUTH_STATUSES = Object.freeze({
  SIGNED_OUT: 'signed-out',
  SIGNING_IN: 'signing-in',
  CONNECTED: 'connected',
  TOKEN_EXPIRED: 'token-expired',
  OFFLINE: 'offline',
  BOOTSTRAP_FAILED: 'bootstrap-failed',
  BACKEND_UNAVAILABLE: 'backend-unavailable',
})

const SUPPORTED_DESKTOP_AUTH_STATUSES = new Set(Object.values(DESKTOP_AUTH_STATUSES))

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
  }
}

export function normalizeDesktopCloudState(value = {}, authState = normalizeDesktopAuthState()) {
  const connected = authState.status === DESKTOP_AUTH_STATUSES.CONNECTED
  const mode = ['cloud', 'local-only', 'unavailable'].includes(value?.mode) ? value.mode : (
    connected ? 'cloud' : 'local-only'
  )
  return {
    available: Boolean(value?.available),
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

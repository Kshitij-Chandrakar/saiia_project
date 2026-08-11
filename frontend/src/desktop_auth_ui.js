export const DESKTOP_AUTH_STATUSES = Object.freeze({
  SIGNED_OUT: 'signed-out',
  SIGNING_IN: 'signing-in',
  CONNECTED: 'connected',
  TOKEN_EXPIRED: 'token-expired',
  OFFLINE: 'offline',
  BOOTSTRAP_FAILED: 'bootstrap-failed',
  BACKEND_UNAVAILABLE: 'backend-unavailable',
})

export function normalizeDesktopAuthState(value = {}) {
  const status = String(value?.status || DESKTOP_AUTH_STATUSES.SIGNED_OUT)
  const connected = status === DESKTOP_AUTH_STATUSES.CONNECTED
  return {
    status,
    user_id: connected && typeof value?.user_id === 'string' ? value.user_id : null,
    email: connected && typeof value?.email === 'string' ? value.email : null,
    error: typeof value?.error === 'string' ? value.error : '',
  }
}

export function getDesktopAuthViewModel(value = {}) {
  const state = normalizeDesktopAuthState(value)
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
    label: copy[0],
    detail: state.error || copy[1],
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

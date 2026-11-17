import { clearAccountOwnedState } from './accountOwnedCleanup'
export const PRIVACY_POLICY = 'c15.2026-10-29.v1'
export const PRIVACY_ENABLED = import.meta.env.VITE_C15_ENABLED === 'true'
export const PRIVACY_EXPORT_ENABLED = import.meta.env.VITE_C15_EXPORT_ENABLED === 'true'
const receiptKey = 'intervucopilot.privacy-receipt'

export function newPrivacyRequest() {
  const capability = () => btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(32)))).replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', '')
  return { request_id: crypto.randomUUID(), confirmation_token: capability(), status_token: capability(), scope: 'whole_account', policy_version: PRIVACY_POLICY }
}

export async function privacyRequest(action, document, token, backendUrl = '', signal) {
  const response = await fetch(`${backendUrl}/api/privacy/deletion/${action}`, {
    method: 'POST', cache: 'no-store', signal: signal || AbortSignal.timeout(12000),
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(document),
  })
  const result = await response.json().catch(() => ({}))
  if (!response.ok) {
    const error = new Error(response.status === 403 ? 'Reauthenticate and try again. The request was not confirmed.' : 'We could not confirm the outcome. Check request status before trying again.')
    error.uncertain = response.status >= 500
    error.status = response.status
    throw error
  }
  return result
}

export function savePrivacyReceipt(document) {
  // Scoped recovery capability only, never an access/refresh token or password.
  sessionStorage.setItem(receiptKey, JSON.stringify({ request_id: document.request_id, status_token: document.status_token }))
}

export function readPrivacyReceipt() {
  try { return JSON.parse(sessionStorage.getItem(receiptKey) || 'null') } catch { return null }
}

export function clearDeletedBrowserState(accountId, email, authStorageKey) {
  return clearAccountOwnedState(accountId, email, authStorageKey)
}

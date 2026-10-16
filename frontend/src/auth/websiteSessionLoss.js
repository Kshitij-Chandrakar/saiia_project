// Display-only logout intent: never stores an account, credential or provider error.
const key = 'intervucopilot.website-logout-intent'
const channelName = 'intervucopilot.website-logout'
let memoryIntent = null

function readIntent() {
  try { return JSON.parse(window.localStorage.getItem(key) || 'null') } catch { return memoryIntent }
}

function publish(intent, id) {
  memoryIntent = intent
  try {
    if (intent) window.localStorage.setItem(key, JSON.stringify(intent))
    else window.localStorage.removeItem(key)
  } catch { /* BroadcastChannel also supports tabs with restricted storage. */ }
  try {
    if (typeof window.BroadcastChannel === 'function') {
      const channel = new window.BroadcastChannel(channelName)
      channel.postMessage({ intent, id }); channel.close()
    }
  } catch { /* Notification bookkeeping must not prevent sign-out. */ }
}

export function watchWebsiteLogoutIntent() {
  if (typeof window.BroadcastChannel !== 'function' || window.electronAPI) return () => {}
  let channel
  try { channel = new window.BroadcastChannel(channelName) } catch { return () => {} }
  channel.onmessage = ({ data }) => {
    if (data?.intent?.id && ['pending', 'complete'].includes(data.intent.phase)) memoryIntent = data.intent
    else if (data?.id === memoryIntent?.id) memoryIntent = null
  }
  return () => channel.close()
}

export function isIntentionalWebsiteLogout() {
  const intent = readIntent(), age = Date.now() - Number(intent?.at)
  const active = Boolean(intent?.id && age >= 0 && age < (intent.phase === 'pending' ? 120000 : 15000))
  if (intent && !active) publish(null, intent.id)
  return active
}

export function clearCompletedWebsiteLogout() {
  const intent = readIntent()
  if (intent?.phase === 'complete') publish(null, intent.id)
}

export async function signOutWebsite(client) {
  if (window.electronAPI) return client.auth.signOut()
  const intent = { id:crypto.randomUUID(), phase:'pending', at:Date.now() }
  publish(intent)
  try {
    const result = await client.auth.signOut()
    if (result.error) {
      if (readIntent()?.id === intent.id) publish(null, intent.id)
    } else if (readIntent()?.id === intent.id) publish({ ...intent, phase:'complete', at:Date.now() })
    return result
  } catch (error) {
    if (readIntent()?.id === intent.id) publish(null, intent.id)
    throw error
  }
}

export function createWebsiteSessionLoss(previouslyAuthenticated, sessionError = null) {
  if (isIntentionalWebsiteLogout()) return null
  // Only an explicit Supabase session-expired code establishes this reason.
  if (sessionError?.code === 'session_expired') return { id:crypto.randomUUID(), reason:'expired' }
  if (previouslyAuthenticated && (!sessionError || ['refresh_token_not_found', 'refresh_token_already_used', 'session_not_found'].includes(sessionError.code))) {
    return { id:crypto.randomUUID(), reason:'signed_out' }
  }
  return null
}

export function validWebsiteSessionLoss(value) {
  return value && typeof value.id === 'string' && /^[a-zA-Z0-9-]{1,80}$/.test(value.id)
    && ['expired', 'signed_out'].includes(value.reason) ? { id:value.id, reason:value.reason } : null
}

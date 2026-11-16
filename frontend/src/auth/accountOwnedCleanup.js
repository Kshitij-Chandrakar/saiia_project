// Keys without verifiable ownership remain intact, including legacy PKCE data.
export function clearAccountOwnedState(account, email, authKey, local, session) {
  const result = { removed: [], preservedUnknown: [] }
  if (local === undefined) { try { local = globalThis.localStorage } catch { result.preservedUnknown.push('local-storage') } }
  if (session === undefined) { try { session = globalThis.sessionStorage } catch { result.preservedUnknown.push('session-storage') } }
  if (typeof account !== 'string' || !/^[A-Za-z0-9-]{1,64}$/.test(account)) return { removed: [], preservedUnknown: ['account-ownership'] }
  function ownedJson(key, ownerOf, category) {
    try {
      const raw = local.getItem(key)
      if (raw === null) return
      const value = JSON.parse(raw), owner = ownerOf(value)
      if (owner === account) { local.removeItem(key); result.removed.push(category) }
      else if (!owner) result.preservedUnknown.push(category)
    } catch { result.preservedUnknown.push(category) }
  }
  ownedJson('candidateProfile', value => value?.user_id, 'profile')
  try { session.removeItem(`billing.operation.${account}`) } catch { result.preservedUnknown.push('billing-operation') }
  for (const scope of ['export', 'session', 'history']) { try { session.removeItem(`intervucopilot.${scope}-request.${account}`) } catch { result.preservedUnknown.push(`${scope}-request`) } }
  try { if (email && local.getItem('intervucopilot.login-email') === email) local.removeItem('intervucopilot.login-email') } catch { /* Storage can be unavailable. */ }
  if (typeof authKey === 'string' && /^sb-[A-Za-z0-9_-]+-auth-token$/.test(authKey)) {
    ownedJson(authKey, value => { const direct = value?.user?.id, legacy = value?.currentSession?.user?.id; return direct && legacy && direct !== legacy ? undefined : direct || legacy }, 'auth-session')
    try { if (local.getItem(`${authKey}-code-verifier`) !== null) result.preservedUnknown.push('legacy-pkce') } catch { /* No guessed deletion. */ }
  }
  return result
}


const restrictionChannel = 'intervucopilot.account-restriction'

export function publishAccountRestriction(account) {
  const message = { account, at: Date.now(), id: crypto.randomUUID() }
  try {
    const channel = new BroadcastChannel(restrictionChannel)
    channel.postMessage(message); channel.close()
  } catch { /* Storage events remain available on older browser engines. */ }
  try { localStorage.setItem(restrictionChannel, JSON.stringify(message)); localStorage.removeItem(restrictionChannel) } catch { /* No persistent subject marker is required. */ }
}

export function watchAccountRestrictions(onRestricted) {
  let channel
  function receive(message) {
    if (typeof message?.account === 'string' && /^[A-Za-z0-9-]{1,64}$/.test(message.account) && Number.isFinite(message.at) && Date.now() >= message.at && Date.now() - message.at < 30000) onRestricted(message.account)
  }
  try { channel = new BroadcastChannel(restrictionChannel); channel.onmessage = ({ data }) => receive(data) } catch { /* Storage fallback below. */ }
  function storage(event) { if (event.key === restrictionChannel && event.newValue) { try { receive(JSON.parse(event.newValue)) } catch { /* Untrusted local display message. */ } } }
  window.addEventListener('storage', storage)
  return () => { channel?.close(); window.removeEventListener('storage', storage) }
}

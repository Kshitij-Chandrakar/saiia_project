export function createOpaqueId(prefix) {
  const safePrefix = String(prefix || 'screen_request').replace(/[^a-z0-9_]/gi, '_')
  const cryptoApi = globalThis.crypto
  if (cryptoApi?.randomUUID) {
    return `${safePrefix}_${cryptoApi.randomUUID()}`
  }
  return `${safePrefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`
}

export function isValidOpaqueId(value, prefix) {
  const text = String(value || '').trim()
  const safePrefix = String(prefix || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(`^${safePrefix}_[a-zA-Z0-9-]{8,80}$`).test(text)
}

export function createPrototypeIds() {
  return {
    operation_id: createOpaqueId('screen_operation'),
    request_id: createOpaqueId('screen_request'),
  }
}

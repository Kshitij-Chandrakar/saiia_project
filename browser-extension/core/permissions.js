export const OPTIONAL_ORIGINS = Object.freeze(['http://*/*', 'https://*/*'])

export function getOriginFromUrl(url) {
  try {
    const parsed = new URL(url)
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return null
    }
    return `${parsed.origin}/*`
  } catch {
    return null
  }
}

export function isRestrictedUrl(url) {
  const text = String(url || '').trim().toLowerCase()
  return (
    !text ||
    text.startsWith('chrome://') ||
    text.startsWith('edge://') ||
    text.startsWith('chrome-extension://') ||
    text.startsWith('edge-extension://') ||
    text.startsWith('devtools://') ||
    text.startsWith('view-source:') ||
    text.startsWith('file://') ||
    text.includes('chrome.google.com/webstore') ||
    text.includes('microsoftedge.microsoft.com/addons')
  )
}

export async function containsHostPermission(chromeApi, url) {
  const origin = getOriginFromUrl(url)
  if (!origin || !chromeApi?.permissions?.contains) {
    return false
  }
  return chromeApi.permissions.contains({ origins: [origin] })
}

export async function requestPagePermission(chromeApi, url) {
  const origin = getOriginFromUrl(url)
  if (!origin || !chromeApi?.permissions?.request) {
    return false
  }
  return chromeApi.permissions.request({ origins: [origin] })
}

export async function requestPrototypeHostPermissions(chromeApi) {
  if (!chromeApi?.permissions?.request) {
    return false
  }
  return chromeApi.permissions.request({ origins: [...OPTIONAL_ORIGINS] })
}

export async function containsPrototypeHostPermissions(chromeApi) {
  if (!chromeApi?.permissions?.contains) {
    return false
  }
  return chromeApi.permissions.contains({ origins: [...OPTIONAL_ORIGINS] })
}

export async function removePagePermission(chromeApi, url) {
  const origin = getOriginFromUrl(url)
  if (!origin || !chromeApi?.permissions?.remove) {
    return false
  }
  return chromeApi.permissions.remove({ origins: [origin] })
}

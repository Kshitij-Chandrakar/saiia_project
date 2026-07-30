import { PROTOCOL_VERSION } from './messages.js'

export const EXTENSION_VERSION = '0.1.0'
export const CAPABILITY_VERSION = 'c0.9.5'

export function createStatus({ browser = 'chromium', permissionGranted = false, lastErrorCode = null } = {}) {
  return {
    protocol_version: PROTOCOL_VERSION,
    extension_version: EXTENSION_VERSION,
    browser,
    installed: true,
    permission_granted: Boolean(permissionGranted),
    desktop_connection: 'not_implemented',
    capabilities: {
      generic_dom_prototype: true,
      active_tab_prototype_test: true,
      electron_bridge: false,
      native_messaging: false,
    },
    last_error_code: lastErrorCode,
  }
}

export class RecentIdSet {
  constructor(limit = 60) {
    this.limit = limit
    this.items = []
    this.set = new Set()
  }

  has(id) {
    return this.set.has(id)
  }

  add(id) {
    const value = String(id || '').trim()
    if (!value || this.set.has(value)) {
      return
    }
    this.items.push(value)
    this.set.add(value)
    while (this.items.length > this.limit) {
      this.set.delete(this.items.shift())
    }
  }
}

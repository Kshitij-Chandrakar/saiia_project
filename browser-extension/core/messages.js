import { ERROR_CODES } from './errors.js'
import { isValidOpaqueId } from './ids.js'
import { LIMITS } from './payload-limits.js'

export const PROTOCOL_VERSION = '1.0'

export const MESSAGE_TYPES = Object.freeze({
  getStatus: 'EXTENSION_GET_STATUS',
  checkPermission: 'EXTENSION_CHECK_PERMISSION',
  requestPermission: 'EXTENSION_REQUEST_PERMISSION',
  testActiveTab: 'EXTENSION_TEST_ACTIVE_TAB',
  contentExtractPage: 'CONTENT_EXTRACT_PAGE',
  contentExtractionResult: 'CONTENT_EXTRACTION_RESULT',
  contentExtractionError: 'CONTENT_EXTRACTION_ERROR',
})

const ALLOWED_TYPES = new Set(Object.values(MESSAGE_TYPES))

export function byteSize(value) {
  return new TextEncoder().encode(JSON.stringify(value ?? null)).length
}

export function createMessage(type, payload = {}) {
  return {
    protocol_version: PROTOCOL_VERSION,
    type,
    message_id: payload.message_id || crypto.randomUUID(),
    ...payload,
  }
}

export function validateMessage(message, { requireOperationIds = false } = {}) {
  if (!message || typeof message !== 'object' || Array.isArray(message)) {
    return { ok: false, error: ERROR_CODES.invalidMessage }
  }
  if (byteSize(message) > LIMITS.maxMessageBytes) {
    return { ok: false, error: ERROR_CODES.payloadTooLarge }
  }
  if (message.protocol_version !== PROTOCOL_VERSION) {
    return { ok: false, error: ERROR_CODES.invalidProtocolVersion }
  }
  if (!ALLOWED_TYPES.has(message.type)) {
    return { ok: false, error: ERROR_CODES.invalidMessage }
  }
  if (!String(message.message_id || '').trim()) {
    return { ok: false, error: ERROR_CODES.invalidMessage }
  }
  if (requireOperationIds) {
    if (!isValidOpaqueId(message.operation_id, 'screen_operation')) {
      return { ok: false, error: ERROR_CODES.invalidMessage }
    }
    if (!isValidOpaqueId(message.request_id, 'screen_request')) {
      return { ok: false, error: ERROR_CODES.invalidMessage }
    }
  }
  return { ok: true, error: null }
}

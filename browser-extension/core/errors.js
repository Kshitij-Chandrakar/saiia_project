export const ERROR_CODES = Object.freeze({
  permissionNotGranted: 'permission_not_granted',
  permissionRevoked: 'permission_revoked',
  activeTabUnavailable: 'active_tab_unavailable',
  restrictedUrl: 'restricted_url',
  unsupportedPage: 'unsupported_page',
  contentScriptInjectionFailed: 'content_script_injection_failed',
  contentScriptUnavailable: 'content_script_unavailable',
  extractionFailed: 'extraction_failed',
  extractionIncomplete: 'extraction_incomplete',
  invalidMessage: 'invalid_message',
  invalidProtocolVersion: 'invalid_protocol_version',
  payloadTooLarge: 'payload_too_large',
  duplicateResponse: 'duplicate_response',
  unknownError: 'unknown_error',
})

export function safeError(code, message, details = null, retryable = true) {
  return {
    code: String(code || ERROR_CODES.unknownError),
    message: String(message || 'Extension prototype request failed.'),
    retryable: Boolean(retryable),
    details: details ? String(details).slice(0, 160) : null,
  }
}

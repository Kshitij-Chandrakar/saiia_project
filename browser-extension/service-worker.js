import { ERROR_CODES, safeError } from './core/errors.js'
import { RecentIdSet } from './core/extension-state.js'
import { createStatus } from './core/extension-state.js'
import { createMessage, MESSAGE_TYPES, validateMessage } from './core/messages.js'
import { containsHostPermission, containsPrototypeHostPermissions, isRestrictedUrl } from './core/permissions.js'
import { buildEnvelope, buildFailedEnvelope, validateEnvelope } from './schemas/screen-intelligence-schema.js'

const recentResponses = new RecentIdSet()

chrome.runtime.onInstalled.addListener(async () => {
  await chrome.storage.local.set({
    setup_version: 'c0.9.5',
    desktop_connection: 'not_implemented',
    last_error_code: null,
  })
})

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message, sender).then(sendResponse)
  return true
})

async function handleMessage(message, sender) {
  const validation = validateMessage(message)
  if (!validation.ok) {
    return { ok: false, error: safeError(validation.error, 'Invalid extension message.') }
  }

  if (message.type === MESSAGE_TYPES.getStatus) {
    return { ok: true, status: await getStatus() }
  }
  if (message.type === MESSAGE_TYPES.checkPermission) {
    return checkActiveTabPermission()
  }
  if (message.type === MESSAGE_TYPES.testActiveTab) {
    return testActiveTabExtraction(message, sender)
  }
  if (message.type === MESSAGE_TYPES.requestPermission) {
    return { ok: false, error: safeError(ERROR_CODES.permissionNotGranted, 'Grant permission from the popup button.') }
  }

  return { ok: false, error: safeError(ERROR_CODES.invalidMessage, 'Unsupported extension command.') }
}

async function getStatus() {
  const activeTab = await getActiveTab()
  const permissionGranted = activeTab?.url
    ? await containsHostPermission(chrome, activeTab.url)
    : await containsPrototypeHostPermissions(chrome)
  const stored = await chrome.storage.local.get(['last_error_code'])
  return createStatus({
    browser: detectBrowser(),
    permissionGranted,
    lastErrorCode: stored.last_error_code || null,
  })
}

async function checkActiveTabPermission() {
  const activeTab = await getActiveTab()
  if (!activeTab?.url) {
    return {
      ok: true,
      permission_granted: await containsPrototypeHostPermissions(chrome),
      origin: null,
    }
  }
  if (isRestrictedUrl(activeTab.url)) {
    return { ok: false, error: safeError(ERROR_CODES.restrictedUrl, 'This browser page cannot be inspected.') }
  }
  return {
    ok: true,
    permission_granted: await containsHostPermission(chrome, activeTab.url),
    origin: safeOrigin(activeTab.url),
  }
}

async function testActiveTabExtraction(message) {
  const operation_id = String(message.operation_id || '').trim()
  const request_id = String(message.request_id || '').trim()
  const idValidation = validateMessage({ ...message, operation_id, request_id }, { requireOperationIds: true })
  if (!idValidation.ok) {
    return { ok: false, error: safeError(idValidation.error, 'Invalid extraction identifiers.') }
  }
  if (recentResponses.has(message.message_id)) {
    return { ok: false, error: safeError(ERROR_CODES.duplicateResponse, 'Duplicate prototype extraction request ignored.') }
  }

  const activeTab = await getActiveTab()
  const browser = buildBrowserMetadata(activeTab)
  if (!activeTab?.id || !activeTab.url) {
    return { ok: false, envelope: buildFailedEnvelope({ operation_id, request_id, browser, code: ERROR_CODES.activeTabUnavailable, message: 'No active tab is available.' }) }
  }
  if (isRestrictedUrl(activeTab.url)) {
    return { ok: false, envelope: buildFailedEnvelope({ operation_id, request_id, browser, code: ERROR_CODES.restrictedUrl, message: 'This browser page cannot be inspected.' }) }
  }
  if (!(await containsHostPermission(chrome, activeTab.url))) {
    return { ok: false, envelope: buildFailedEnvelope({ operation_id, request_id, browser, code: ERROR_CODES.permissionNotGranted, message: 'Page access has not been granted.' }) }
  }

  const started = performance.now()
  try {
    await chrome.scripting.executeScript({ target: { tabId: activeTab.id }, files: ['content-script.js'] })
  } catch {
    return { ok: false, envelope: buildFailedEnvelope({ operation_id, request_id, browser, code: ERROR_CODES.contentScriptInjectionFailed, message: 'Content script could not be injected.' }) }
  }

  try {
    const request = createMessage(MESSAGE_TYPES.contentExtractPage, {
      message_id: message.message_id,
      operation_id,
      request_id,
      requested_source: 'browser_extension',
    })
    const contentResponse = await chrome.tabs.sendMessage(activeTab.id, request)
    const contentValidation = validateMessage(contentResponse, { requireOperationIds: true })
    if (!contentValidation.ok || contentResponse.type !== MESSAGE_TYPES.contentExtractionResult) {
      return { ok: false, envelope: buildFailedEnvelope({ operation_id, request_id, browser, code: ERROR_CODES.contentScriptUnavailable, message: 'Content script returned an invalid response.' }) }
    }
    const envelope = buildEnvelope({
      operation_id,
      request_id,
      browser,
      question: contentResponse.result.question,
      extraction: contentResponse.result.extraction,
      timingMs: Math.round(performance.now() - started),
    })
    const envelopeValidation = validateEnvelope(envelope)
    if (!envelopeValidation.ok) {
      return { ok: false, envelope: buildFailedEnvelope({ operation_id, request_id, browser, code: ERROR_CODES.extractionFailed, message: 'Extracted payload did not match the prototype contract.' }) }
    }
    recentResponses.add(message.message_id)
    await chrome.storage.local.set({ last_error_code: null })
    return { ok: envelope.status === 'ready', envelope }
  } catch {
    await chrome.storage.local.set({ last_error_code: ERROR_CODES.extractionFailed })
    return { ok: false, envelope: buildFailedEnvelope({ operation_id, request_id, browser, code: ERROR_CODES.extractionFailed, message: 'Active tab extraction failed.' }) }
  }
}

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true })
  return tabs?.[0] || null
}

function safeOrigin(url) {
  try {
    return new URL(url).origin
  } catch {
    return null
  }
}

function buildBrowserMetadata(tab) {
  return {
    name: detectBrowser(),
    extension_id: chrome.runtime.id || null,
    tab_id: null,
    window_id: null,
    url_origin: safeOrigin(tab?.url),
    page_title: String(tab?.title || '').slice(0, 180) || null,
  }
}

function detectBrowser() {
  const url = chrome.runtime.getURL('')
  return url.startsWith('chrome-extension://') ? 'chromium' : 'chromium'
}

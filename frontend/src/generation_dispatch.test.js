import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import test from 'node:test'
import { prepareGenerationRequest } from './generation_auth.js'
import { createManualLiveSession } from './manual_live_session.js'

const source = readFileSync(new URL('./App.jsx', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const start = source.indexOf('  const streamGenerateAnswer =')
const code = source.slice(start, source.indexOf('  useEffect(', start))
function harness(config = {}, cloudState = null) {
  const calls = [], values = {}
  const context = {
    desktopAnswerStreamHandlersRef: { current: new Map() }, AbortController, performance, console: { info() {} },
    activeGenerateAbortControllerRef: { current: null }, latestGenerationRequestIdRef: { current: 'request-1' },
    startupSessionConfigRef: { current: config }, fullAnswerRef: { current: '' },
    prepareGenerationRequest, isCurrentRequest: (a, b) => a === b,
    markChatTiming() {}, appendEventLog() {}, stripInternalControlMarkers: (text) => text,
    requestAnimationFrame: () => 1, cancelAnimationFrame() {}, BACKEND_URL: 'http://local',
    window: { saiia: cloudState ? { getCloudStartupContext: async () => cloudState } : undefined },
    fetch: async (url, options) => { calls.push({ url, body: options?.body && JSON.parse(options.body) }); return { ok: true } },
    readNdjsonStream: async (_response, { onEvent }) => {
      onEvent({ type: 'start', request_id: 'request-1' })
      onEvent({ type: 'metadata', metadata: { answer: 'Answer' } })
      onEvent({ type: 'done' })
      return { sawDone: true }
    },
    applyStartupSessionConfig: (next) => { context.startupSessionConfigRef.current = next },
  }
  for (const setter of [...new Set(code.match(/\bset[A-Z]\w+/g))]) {
    context[setter] = (value) => { values[setter] = typeof value === 'function' ? value(values[setter] || {}) : value }
  }
  const stream = vm.runInNewContext(`${code}; streamGenerateAnswer`, context)
  const generate = async (capture, options = {}) => {
    // Manual stop-to-generate has already detected the question; classification/profile precede this stream.
    await context.fetch('http://local/classify/', { body: JSON.stringify({ text: capture.text }) })
    await context.fetch('http://local/api/profile')
    return stream({ ...options, body: { request_id: 'request-1', question: capture.text, session_id: config.activeSessionId || undefined }, requestId: 'request-1' })
  }
  return { context, calls, values, generate }
}
async function manualStop(h) {
  const socket = { readyState: 1, send() {} }
  const recorder = { state: 'inactive', start() { this.state = 'recording' }, stop() { this.state = 'inactive'; this.ondataavailable({ data: new Blob(['audio']) }); this.onstop() } }
  const session = createManualLiveSession({ sessionId: 'manual-1', stream: { getTracks: () => [{ stop() {} }] },
    manualSttProvider: 'openai_whisper', manualLiveSttProvider: 'assemblyai_streaming',
    createTransport: () => ({ socket, pauseAudio() {}, close() {} }), createRecorder: () => recorder,
    onState() {}, onTranscript() {}, detectQuestion: async (text) => text, generate: h.generate,
    transcribe: () => { throw new Error('must not batch transcribe healthy live text') }, finalizeMs: 1,
  })
  socket.onopen()
  socket.onmessage({ data: JSON.stringify({ event: 'turn', transcript: 'What is React?', turn_order: 0, end_of_turn: true }) })
  return session.stop()
}

test('manual live stop sends generate/stream after classify/profile when no cloud session exists', async () => {
  const h = harness()
  await manualStop(h)
  assert.deepEqual(h.calls.map((call) => call.url), ['http://local/classify/', 'http://local/api/profile', 'http://local/generate/stream'])
  assert.equal(h.values.setGenerationDiagnostics.generateRequestSent, true)
  assert.equal(h.values.setGenerationDiagnostics.generationRequestBlocked, false)
})

test('confirmed ended startup session is cleared before local generation dispatch', async () => {
  const h = harness({ activeSessionId: 'ended-1' }, { auth: { status: 'expired', endedInterviewSessionIds: ['ended-1'] }, cloud: { available: false } })
  await manualStop(h)
  const request = h.calls.find((call) => call.url.endsWith('/generate/stream'))
  assert.equal(request.body.session_id, undefined)
  assert.equal(h.context.startupSessionConfigRef.current.activeSessionId, '')
  assert.equal(h.values.setGenerationDiagnostics.activeSessionEnded, true)
  assert.equal(h.values.setGenerationDiagnostics.authRequired, false)
})

test('active invalid session reports classify success but blocks before any generation dispatch', async () => {
  const h = harness({ activeSessionId: 'active-1' }, { auth: { status: 'expired' }, cloud: { available: false } })
  await assert.rejects(manualStop(h), /Sign in again/)
  assert.equal(h.calls.length, 2)
  assert.equal(h.context.startupSessionConfigRef.current.activeSessionId, 'active-1')
  assert.equal(h.values.setGenerationDiagnostics.generateRequestSent, false)
  assert.equal(h.values.setGenerationDiagnostics.generationRequestBlocked, true)
  assert.equal(h.values.setGenerationDiagnostics.generationBlockReason, 'cloud_auth_unavailable')
})

test('missing authenticated stream capability blocks with restart instruction instead of silently buffering', async () => {
  const h = harness({ activeSessionId: 'active-1' }, { auth: { status: 'connected' }, cloud: { available: true } })
  h.context.window.saiia.generateAnswer = async () => { throw new Error('buffered must not be called') }
  await assert.rejects(manualStop(h), /Fully restart Electron/)
  assert.equal(h.calls.length, 2)
  assert.equal(h.values.setGenerationDiagnostics.electron_stream_available, false)
  assert.equal(h.values.setGenerationDiagnostics.generateFallbackRequestSent, false)
})

test('desktop auth failure before network dispatch keeps generate-request-sent false', async () => {
  const h = harness({ activeSessionId: 'active-1' }, { auth: { status: 'connected' }, cloud: { available: true } })
  h.context.window.saiia.generateAnswer = async () => ({ ok: false, generateRequestSent: false, payload: { detail: 'Sign in again.' } })
  await assert.rejects(manualStop(h), /Fully restart Electron/)
  assert.equal(h.calls.length, 2)
  assert.equal(h.values.setGenerationDiagnostics.generateRequestSent, false)
  assert.equal(h.values.setGenerationDiagnostics.generationRequestBlocked, true)
})


test('confirmed local retry dispatches after classification without cloud context and retains active session', async () => {
  const h = harness({ activeSessionId: 'active-1', selectedResumeId: 'resume-1', jobContextId: 'job-1' }, { auth: { status: 'connected' }, cloud: { available: false } })
  await assert.rejects(h.generate({ text: 'Explain CI/CD' }), /valid connection/)
  await h.generate({ text: 'Explain CI/CD' }, { localWithoutSaving: true })
  const request = h.calls.at(-1)
  assert.equal(request.url, 'http://local/generate/stream')
  assert.equal(request.body.session_id, undefined)
  assert.equal(request.body.selected_resume_id, undefined)
  assert.equal(request.body.job_context_id, undefined)
  assert.equal(h.context.startupSessionConfigRef.current.activeSessionId, 'active-1')
  assert.equal(h.values.setGenerationDiagnostics.localWithoutSaving, true)
  assert.equal(h.values.setGenerationDiagnostics.generateStreamRequestSent, true)
})


function recoveryHarness() {
  const pending = { text: 'Explain CI/CD', capturedHistoryEntryId: 'history-1' }
  const context = { recording: false, manualProcessing: false, prepareGenerationRequest, startupSessionConfigRef: { current: { activeSessionId: 'active-1' } },
    pendingManualGenerationRef: { current: pending }, generationRecoveryBusyRef: { current: false },
    profileCacheRef: { current: {} }, profileFetchMsRef: { current: 1 }, performance,
    setGenerationDiagnostics(value) { context.diagnostics = value },
    setManualProcessing() {}, setError(value) { context.error = value }, setStatus(value) { context.status = value },
    applyStartupSessionConfig(value) { context.startupSessionConfigRef.current = value },
    calls: [], classifyAndGenerate: async (request) => { context.calls.push(request) },
    window: { confirm: () => true, saiia: {
      refreshCloudStartupContext: async () => ({ auth: { status: 'connected' }, cloud: { available: true } }),
      endInterviewSession: async () => ({ session: { id: 'active-1', status: 'ended' } }),
    } },
  }
  const start = source.indexOf('  const refreshGenerationCloud =')
  const handlers = vm.runInNewContext(`${source.slice(start, source.indexOf('  useEffect(', start))}; ({ recoverManualGeneration, refreshGenerationCloud })`, context)
  return { context, ...handlers }
}

test('manual local recovery requires confirmation and reuses captured history entry', async () => {
  const h = recoveryHarness()
  h.context.window.confirm = () => false
  await h.recoverManualGeneration('generation-local')
  assert.equal(h.context.calls.length, 0)
  assert.equal(h.context.startupSessionConfigRef.current.activeSessionId, 'active-1')
  h.context.window.confirm = () => true
  await h.recoverManualGeneration('generation-local')
  assert.equal(h.context.calls[0].localWithoutSaving, true)
  assert.equal(h.context.calls[0].capturedHistoryEntryId, 'history-1')
  assert.equal(h.context.pendingManualGenerationRef.current, null)
})

test('confirmed end clears active session before retry; failed end retains active session', async () => {
  const h = recoveryHarness()
  h.context.window.saiia.endInterviewSession = async () => ({ session: null, error: 'Cloud unavailable' })
  await h.recoverManualGeneration('generation-end-session')
  assert.equal(h.context.startupSessionConfigRef.current.activeSessionId, 'active-1')
  assert.equal(h.context.calls.length, 0)
  assert.match(h.context.error, /Cloud unavailable/)
  h.context.window.saiia.endInterviewSession = async () => ({ session: { id: 'active-1', status: 'ended' } })
  await h.recoverManualGeneration('generation-end-session')
  assert.equal(h.context.startupSessionConfigRef.current.activeSessionId, '')
  assert.equal(h.context.calls.length, 1)
})

test('login/refresh reloads safe cloud state and recomputes generation auth diagnostics', async () => {
  const h = recoveryHarness()
  await h.refreshGenerationCloud()
  assert.equal(h.context.diagnostics.authRequired, true)
  assert.equal(h.context.diagnostics.generationRequestBlocked, false)
  assert.equal(h.context.diagnostics.cloudStatusAtGeneration, 'available')
  assert.equal(h.context.profileCacheRef.current, null)
})

test('logout clears cloud selections, pending generation and cached generation auth state', () => {
  const start = source.indexOf('  const resetRuntimeForDesktopLogout =')
  const code = source.slice(start, source.indexOf('  const applyRefinedAnswer', start))
  const context = { pendingManualGenerationRef: { current: {} }, profileCacheRef: { current: {} }, profileFetchMsRef: { current: 1 },
    createQuestionHistoryState: () => ({}), applyStartupSessionConfig(value) { context.config = value },
  }
  for (const name of new Set(code.match(/\b(?:set[A-Z]\w+|stop[A-Z]\w+|clear[A-Z]\w+|reset[A-Z]\w+)\b/g))) context[name] = (value) => { context[name + 'Value'] = value }
  vm.runInNewContext(`${code}; resetRuntimeForDesktopLogout()`, context)
  assert.equal(context.config, null)
  assert.equal(context.pendingManualGenerationRef.current, null)
  assert.equal(context.setGenerationDiagnosticsValue.authRequired, false)
  assert.equal(context.setGenerationDiagnosticsValue.generationRequestBlocked, false)
  assert.equal(context.profileCacheRef.current, null)
})


function authenticatedStreamHarness(started = { ok: true, stream_id: 'stream-1' }) {
  const h = harness({ activeSessionId: 'active-1' }, { auth: { status: 'connected' }, cloud: { available: true } })
  let listener
  h.context.window.saiia.onAnswerStreamEvent = (_id, fn) => { listener = fn; return () => {} }
  h.context.window.saiia.startAnswerStream = async (body) => {
    h.calls.push({ url: 'desktop/generate/stream', body })
    if (started.ok) {
      listener({ event: { type: 'start', request_id: 'request-1' } })
      listener({ event: { type: 'delta', request_id: 'request-1', text: 'First text' } })
      assert.equal(h.values.setAnswer, 'First text', 'answer must be published before done')
      listener({ event: { type: 'metadata', request_id: 'request-1', metadata: { answer: 'First text completed' } } })
      listener({ event: { type: 'done', request_id: 'request-1' } })
    }
    return started
  }
  h.context.requestAnimationFrame = (callback) => { callback(); return 1 }
  h.context.window.saiia.generateAnswer = async (body) => {
    h.calls.push({ url: 'desktop/generate/', body })
    return { ok: true, generateRequestSent: true, payload: { answer: 'Buffered fallback' } }
  }
  return h
}

test('authenticated manual generation prefers stream, displays delta before done and never buffers success', async () => {
  const h = authenticatedStreamHarness()
  await manualStop(h)
  assert.equal(h.calls.at(-1).url, 'desktop/generate/stream')
  assert.equal(h.calls.at(-1).body.session_id, 'active-1')
  assert.equal(h.values.setAnswer, 'First text completed')
  assert.equal(h.values.setGenerationDiagnostics.generate_stream_request_sent, true)
  assert.equal(h.values.setGenerationDiagnostics.generate_non_stream_fallback_used, false)
  assert.equal(h.values.setGenerationDiagnostics.provider_streaming, true)
  assert.ok(h.values.setGenerationDiagnostics.first_delta_received_ms >= 0)
  assert.ok(h.values.setGenerationDiagnostics.first_ui_update_ms >= 0)
})

for (const status of [404, 501, 503]) {
  test(`authenticated pre-delta recoverable stream failure ${status} permits buffered fallback`, async () => {
    const h = authenticatedStreamHarness({ ok: false, status, reason: status === 503 ? 'generation-failed' : 'stream-unavailable', generateRequestSent: true })
    await manualStop(h)
    assert.deepEqual(h.calls.slice(-2).map((call) => call.url), ['desktop/generate/stream', 'desktop/generate/'])
    assert.equal(h.values.setGenerationDiagnostics.generate_non_stream_fallback_used, true)
    assert.ok(h.values.setGenerationDiagnostics.stream_fallback_reason)
  })
}
for (const status of [400, 401, 403, 409]) {
  test(`authenticated stream failure ${status} never retries buffered generation`, async () => {
    const h = authenticatedStreamHarness({ ok: false, status, reason: 'generation-failed', generateRequestSent: true })
    await assert.rejects(manualStop(h))
    assert.equal(h.calls.at(-1).url, 'desktop/generate/stream')
    assert.equal(h.values.setGenerationDiagnostics.generate_non_stream_fallback_used, false)
  })
}


test('failure after useful authenticated deltas never restarts generation through buffered fallback', async () => {
  const h = authenticatedStreamHarness()
  let listener
  h.context.window.saiia.onAnswerStreamEvent = (_id, fn) => { listener = fn; return () => {} }
  h.context.window.saiia.startAnswerStream = async () => {
    h.calls.push({ url: 'desktop/generate/stream' })
    listener({ event: { type: 'delta', request_id: 'request-1', text: 'Partial answer' } })
    listener({ event: { type: 'error', request_id: 'request-1' } })
    listener({ event: { type: 'done', request_id: 'request-1', incomplete: true } })
    return { ok: true, stream_id: 'stream-1' }
  }
  await assert.rejects(manualStop(h), /incomplete/)
  assert.equal(h.calls.at(-1).url, 'desktop/generate/stream')
  assert.equal(h.values.setGenerationDiagnostics.generate_non_stream_fallback_used, false)
  assert.equal(h.values.setAnswer, 'Partial answer')
})


test('manual stream works without a buffered method or renderer token', async () => {
  const h = authenticatedStreamHarness()
  delete h.context.window.saiia.generateAnswer
  await manualStop(h)
  assert.equal(h.calls.at(-1).url, 'desktop/generate/stream')
  assert.equal(h.values.setGenerationDiagnostics.generateStreamRequestSent, true)
  assert.equal(h.values.setGenerationDiagnostics.generateFallbackRequestSent, false)
})

test('electronAPI stream capability is used when the saiia alias is unavailable', async () => {
  const h = authenticatedStreamHarness()
  h.context.window.electronAPI = { ...h.context.window.saiia }
  delete h.context.window.saiia.startAnswerStream
  delete h.context.window.saiia.onAnswerStreamEvent
  await manualStop(h)
  assert.equal(h.calls.at(-1).url, 'desktop/generate/stream')
  assert.equal(h.values.setGenerationDiagnostics.electron_stream_available, true)
})


test('actual preload routes authenticated manual streaming IPC and forwards deltas without renderer credentials', async () => {
  const h = harness({ activeSessionId: 'active-1' }, { auth: { status: 'connected' }, cloud: { available: true } })
  const preloadSource = readFileSync(new URL('../electron/preload.cjs', import.meta.url), 'utf8')
  const listeners = new Map()
  const ipcRenderer = {
    send() {}, on: (channel, fn) => listeners.set(channel, fn), removeListener: (channel) => listeners.delete(channel),
    invoke: async (channel, body) => {
      if (channel === 'cloud:get-startup-context') return { auth: { status: 'connected' }, cloud: { available: true } }
      assert.equal(channel, 'generate:answer:stream:start', 'manual must never choose generate:answer IPC')
      h.calls.push({ url: channel, body })
      assert.equal(body.request_id, 'request-1')
      assert.equal(body.session_id, 'active-1')
      assert.equal(body.access_token, undefined)
      const emit = (event) => listeners.get('generate:answer:stream:event')({}, { client_request_id: body.request_id, event })
      emit({ type: 'delta', text: 'Live answer' })
      assert.equal(h.values.setAnswer, 'Live answer')
      emit({ type: 'metadata', metadata: { answer: 'Live answer completed' } })
      emit({ type: 'done' })
      return { ok: true, stream_id: 'stream-1' }
    },
  }
  vm.runInNewContext(preloadSource, { require: () => ({ ipcRenderer, contextBridge: { exposeInMainWorld: (name, api) => { h.context.window[name] = api } } }) })
  h.context.requestAnimationFrame = (callback) => { callback(); return 1 }
  await manualStop(h)
  assert.equal(h.calls.at(-1).url, 'generate:answer:stream:start')
  assert.equal(h.values.setGenerationDiagnostics.generateStreamRequestSent, true)
  assert.equal(h.values.setGenerationDiagnostics.generateFallbackRequestSent, false)
})

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'
import { createManualLiveSession, getManualFinalTranscript, isManualLiveEnabled } from './manual_live_session.js'
import { createLiveMicTransport } from './live_mic_transport.js'
import { appendQuestionHistoryEntry, createQuestionHistoryEntry, createQuestionHistoryState, updateQuestionHistoryEntry } from './question_history.js'

const appSource = readFileSync(new URL('./App.jsx', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
function setup(options = {}) {
  const states = [], previews = [], generations = [], transcriptions = [], commands = []
  let trackStops = 0, closes = 0, pauses = 0, fallbackCount = 0
  const stream = { getTracks: () => [{ stop: () => trackStops++ }] }
  const socket = { readyState: 1, send: (data) => commands.push(JSON.parse(data)) }
  const recorder = { mimeType: 'audio/webm', state: 'inactive',
    start() { this.state = 'recording' },
    stop() { this.state = 'inactive'; this.ondataavailable({ data: new Blob(['backup']) }); this.onstop() },
  }
  const session = createManualLiveSession({
    sessionId: 'session-1', stream, manualSttProvider: 'openai_whisper', manualLiveSttProvider: 'assemblyai_streaming',
    createTransport: () => ({ socket, pauseAudio: () => pauses++, close: () => { closes++; socket.onclose?.() } }),
    createRecorder: () => recorder,
    transcribe: async (blob) => { transcriptions.push(blob); return { text: options.batchText ?? 'What is React?', transcriptionMs: 12 } },
    detectQuestion: async (text) => text.includes('?') ? text : '',
    generate: async (request) => generations.push(request),
    onState: (state) => states.push(state), onTranscript: (text) => previews.push(text),
    onFallback: () => fallbackCount++, finalizeMs: 5, connectMs: 50,
    ...options,
  })
  socket.onopen?.()
  const turn = (text, order = 0, final = false) => socket.onmessage({ data: JSON.stringify({ event: 'turn', transcript: text, turn_order: order, end_of_turn: final }) })
  return { session, socket, recorder, turn, states, previews, generations, transcriptions, commands,
    counts: () => ({ trackStops, closes, pauses, fallbackCount }) }
}

test('manual live partials update Question while listening without generation or batch STT', (t) => {
  const f = setup(); t.after(() => f.session.cancel())
  f.turn('What is')
  assert.equal(f.previews.at(-1), 'What is')
  assert.equal(f.states.at(-1).phase, 'listening')
  assert.equal(f.states.at(-1).pendingGeneration, false)
  assert.equal(f.generations.length, 0)
  assert.equal(f.transcriptions.length, 0)
  f.turn('What is React?', 0, true)
  assert.equal(f.previews.at(-1), 'What is React?')
  assert.equal(f.generations.length, 0)
})

test('socket closing during finalization preserves received final text without batch fallback', async () => {
  const f = setup()
  f.turn('What is React?', 0, true)
  const stop = f.session.stop()
  f.socket.onclose()
  await stop
  await f.session.stop()
  assert.equal(f.transcriptions.length, 0)
  assert.equal(f.counts().fallbackCount, 0)
  assert.equal(f.generations.length, 1)
  assert.equal(f.generations[0].text, 'What is React?')
})

test('second click waits for final words then generates exactly once for the same history ID', async () => {
  const f = setup()
  f.turn('What is')
  const firstStop = f.session.stop()
  const repeatedStop = f.session.stop()
  assert.equal(firstStop, repeatedStop)
  assert.equal(f.generations.length, 0)
  assert.equal(f.states.at(-1).phase, 'finalizing')
  assert.equal(f.recorder.state, 'inactive')
  assert.equal(f.states.at(-1).pendingGeneration, true)
  assert.deepEqual(f.commands, [{ type: 'force_endpoint' }])
  f.turn('What is React?', 0, true)
  await firstStop
  assert.equal(f.generations.length, 1)
  assert.equal(f.generations[0].text, 'What is React?')
  assert.equal(f.generations[0].historyEntryId, f.states[0].historyEntryId)
  assert.equal(f.transcriptions.length, 0)
  assert.equal(f.counts().fallbackCount, 0)
  await f.session.stop()
  assert.equal(f.generations.length, 1)
})

test('final turn revisions replace text and multiple turns accumulate in order', async () => {
  const f = setup()
  f.turn('Explain React', 0, true)
  f.turn('Explain React hooks.', 0, true)
  f.turn('How do they work?', 1, true)
  assert.equal(getManualFinalTranscript(f.states.at(-1)), 'Explain React hooks. How do they work?')
  await f.session.stop()
  assert.equal(f.generations[0].text, 'Explain React hooks. How do they work?')
})

test('late revision of an older final does not lose the current partial', async () => {
  const f = setup()
  f.turn('Explain hooks.', 0, true)
  f.turn('What is useEffect?', 1)
  f.turn('Explain React hooks.', 0, true)
  assert.equal(f.previews.at(-1), 'Explain React hooks. What is useEffect?')
  await f.session.stop()
  assert.equal(f.generations[0].text, 'Explain React hooks. What is useEffect?')
})

test('empty speech uses batch once and finishes safely without generation', async () => {
  const f = setup({ batchText: '' })
  await f.session.stop()
  assert.equal(f.transcriptions.length, 1)
  assert.equal(f.generations.length, 0)
  assert.equal(f.states.at(-1).phase, 'idle')
  assert.equal(f.previews.at(-1), '')
})

test('Thank you for watching is rejected before question detection or generation', async () => {
  const f = setup({ detectQuestion: () => { throw new Error('must reject locally') } })
  f.turn('Thank you for watching.', 0, true)
  await f.session.stop()
  assert.equal(f.generations.length, 0)
  assert.equal(f.transcriptions.length, 0)
  assert.equal(f.states.at(-1).detectedQuestion, '')
})

test('non-question speech is rejected safely after detection', async () => {
  const f = setup()
  f.turn('Good morning.', 0, true)
  await f.session.stop()
  assert.equal(f.generations.length, 0)
  assert.equal(f.states.at(-1).pendingGeneration, false)
})

test('stream failure preserves backup and transcribes once only on the stop click', async () => {
  const f = setup()
  f.turn('Incomplete live text')
  f.socket.onerror()
  f.socket.onclose()
  assert.equal(f.transcriptions.length, 0)
  assert.equal(f.generations.length, 0)
  await Promise.all([f.session.stop(), f.session.stop()])
  assert.equal(f.transcriptions.length, 1)
  assert.equal(f.transcriptions[0].size, 6)
  assert.equal(f.counts().fallbackCount, 1)
  assert.equal(f.generations.length, 1)
  assert.equal(f.generations[0].transcriptionMs, 12)
  assert.equal(f.generations[0].text, 'What is React?')
})

test('transport setup failure still allows batch fallback', async () => {
  const f = setup({ createTransport: () => { throw new Error('unavailable') } })
  await f.session.stop()
  assert.equal(f.transcriptions.length, 1)
  assert.equal(f.generations.length, 1)
})

test('connection timeout allows backup fallback', async () => {
  const f = setup({ connectMs: 1 })
  await new Promise((resolve) => setTimeout(resolve, 5))
  await f.session.stop()
  assert.equal(f.transcriptions.length, 1)
  assert.equal(f.generations.length, 1)
})

test('cancel while finalizing ignores late events and releases microphone', async () => {
  const f = setup()
  f.turn('What is React?')
  const stop = f.session.stop()
  f.session.cancel()
  f.turn('What is Vue?', 0, true)
  await stop
  assert.equal(f.generations.length, 0)
  assert.equal(f.transcriptions.length, 0)
  assert.ok(f.counts().trackStops > 0)
})

test('cancel during batch fallback prevents late answer generation', async () => {
  let resolveBatch, started
  const batchStarted = new Promise((resolve) => { started = resolve })
  const f = setup({ transcribe: () => { started(); return new Promise((resolve) => { resolveBatch = resolve }) } })
  f.socket.onerror()
  const stop = f.session.stop()
  await batchStarted
  f.session.cancel()
  resolveBatch({ text: 'What is React?' })
  await stop
  assert.equal(f.generations.length, 0)
})

test('generation failure releases resources and cannot be dispatched twice', async () => {
  let attempts = 0
  const f = setup({ generate: async () => { attempts++; throw new Error('generation failed') } })
  f.turn('What is React?', 0, true)
  await assert.rejects(f.session.stop(), /generation failed/)
  await assert.rejects(f.session.stop(), /generation failed/)
  assert.equal(attempts, 1)
  assert.equal(f.states.at(-1).phase, 'error')
  assert.ok(f.counts().trackStops > 0)
})

test('malformed STT payloads are ignored safely', (t) => {
  const f = setup(); t.after(() => f.session.cancel())
  for (const data of ['null', 'not json', '{"event":"turn","transcript":{}}']) f.socket.onmessage({ data })
  assert.equal(f.previews.length, 0)
  assert.equal(f.generations.length, 0)
})

test('shared transport sends PCM only when active; pause permits endpoint control and close cleans resources', () => {
  const sent = []
  let active = true, disconnected = 0, contextClosed = 0, socketClosed = 0
  class Socket {
    static OPEN = 1
    readyState = 1
    send(data) { sent.push(data) }
    close() { socketClosed++ }
  }
  const processor = { connect() {}, disconnect() { disconnected++ } }
  const source = { connect() {}, disconnect() { disconnected++ } }
  class AudioContext {
    sampleRate = 48000
    destination = {}
    createMediaStreamSource() { return source }
    createScriptProcessor() { return processor }
    close() { contextClosed++; return Promise.resolve() }
  }
  const transport = createLiveMicTransport({ stream: {}, url: 'ws://local/ws/auto-stt', isActive: () => active,
    downsample: (_samples, rate, target) => { assert.equal(rate, 48000); assert.equal(target, 16000); return new Int16Array([1, 2]) },
    WebSocketClass: Socket, AudioContextClass: AudioContext })
  const event = { inputBuffer: { getChannelData: () => new Float32Array([0.1]) } }
  processor.onaudioprocess(event)
  assert.equal(sent.length, 1)
  active = false
  processor.onaudioprocess(event)
  assert.equal(sent.length, 1)
  active = true
  transport.pauseAudio()
  processor.onaudioprocess(event)
  assert.equal(sent.length, 1)
  transport.socket.send(JSON.stringify({ type: 'force_endpoint' }))
  transport.close()
  transport.close()
  assert.equal(disconnected, 2)
  assert.equal(contextClosed, 1)
  assert.equal(socketClosed, 1)
  assert.equal(processor.onaudioprocess, null)
})

test('App manual callbacks use the batch endpoint only for fallback and the same history ID for generation', () => {
  const manual = appSource.slice(appSource.indexOf('manualLiveSessionRef.current = createManualLiveSession('), appSource.indexOf("    setStatus('Stopping...')", appSource.indexOf('  const handleRecordToggle')))
  assert.match(manual, /transcribeAudioBlob\(blob, 'manual', isCurrent\)/)
  assert.match(manual, /capturedHistoryEntryId: historyEntryId/)
  assert.doesNotMatch(manual, /processAutoQuestion|startAutoCooldown|scheduleNextAutoCycle/)
  assert.match(manual, /setGenerationStarted\(next.phase === 'generating'\)/)
  assert.match(manual, /onTranscript:.*setTranscript\(text\)/)
  let history = appendQuestionHistoryEntry(createQuestionHistoryState(), createQuestionHistoryEntry({ id: 'manual-1', mode: 'answer', question: 'Q', status: 'pending' }))
  history = appendQuestionHistoryEntry(history, createQuestionHistoryEntry({ id: 'manual-1', mode: 'answer', question: 'Q', status: 'generating', requestId: 'r1' }))
  history = updateQuestionHistoryEntry(history, 'answer', 'manual-1', { fullAnswer: 'A', status: 'complete' }, { requestId: 'r1' })
  assert.equal(history.answer.entries.length, 1)
  assert.equal(history.answer.entries[0].fullAnswer, 'A')
})

test('Auto microphone callbacks retain partial preview, final generation and fallback scheduling', async () => {
  const calls = []
  const socket = { readyState: 1 }
  const context = { WebSocket: { OPEN: 1 }, Date, performance,
    createLiveMicTransport: () => ({ socket }), getBackendWebSocketUrl: (path) => path, downsampleToInt16Mono: () => {},
    autoModeRef: { current: true }, autoModeRunIdRef: { current: 'auto-1' }, autoStreamingClosingRef: { current: false },
    autoStreamingSocketRef: { current: null }, autoStreamingAudioContextRef: {}, autoStreamingSourceNodeRef: {}, autoStreamingProcessorRef: {},
    autoCooldownUntilRef: { current: 0 },
    handleAutoTranscriptFinal: async (request) => calls.push(request),
    scheduleNextAutoCycle: (...args) => calls.push({ fallback: args }),
    stopAutoStreamingBridge: () => { context.autoStreamingSocketRef.current = null },
  }
  for (const name of ['setStreamingError', 'clearTransientStreamingCloseError', 'setPartialAutoTranscript', 'setMicStreamingState',
    'setAnswerPipelineState', 'setMicStreamRestartCount', 'setLastMicStreamRestartReason', 'setAutoStreamingConnected', 'setAutoModeStatus',
    'setStatus', 'keepMicAutoListeningVisual', 'logAutoModeDebug', 'setSttProvider', 'setSttFallbackUsed', 'setSttFallbackReason', 'appendEventLog', 'setError']) {
    context[name] = (...args) => calls.push({ [name]: args })
  }
  const code = appSource.slice(appSource.indexOf('  const startAutoStreamingMic ='), appSource.indexOf('  const startAutoStreamingSystem ='))
  const start = vm.runInNewContext(`${code}; startAutoStreamingMic`, context)
  await start('auto-1', {})
  await socket.onmessage({ data: JSON.stringify({ event: 'turn', transcript: 'What is React?', end_of_turn: false }) })
  assert.ok(calls.some((call) => call.setPartialAutoTranscript?.[0] === 'What is React?'))
  assert.ok(!calls.some((call) => call.text))
  await socket.onmessage({ data: JSON.stringify({ event: 'turn', transcript: 'What is React?', end_of_turn: true }) })
  assert.equal(calls.find((call) => call.text).sourceMode, 'microphone')
  socket.onerror()
  assert.ok(calls.some((call) => call.fallback?.[1] === 'microphone'))
  const autoProcess = appSource.slice(appSource.indexOf('  const processAutoQuestion ='), appSource.indexOf('  const flushPendingAutoQuestion ='))
  assert.match(autoProcess, /await classifyAndGenerate/)
  assert.match(autoProcess, /startAutoCooldown\(runId\)/)
})

function appManualHarness(manualConfig = { manual_stt_provider: 'openai_whisper', manual_live_stt_provider: 'assemblyai_streaming' }) {
  const values = {}, generationRequests = [], batchRequests = [], detectionRequests = []
  let history = createQuestionHistoryState(), stoppedTracks = 0
  const socket = { readyState: 1, send() {} }
  const stream = { getTracks: () => [{ stop: () => stoppedTracks++ }] }
  class Recorder {
    state = 'inactive'
    mimeType = 'audio/webm'
    start() { this.state = 'recording' }
    stop() { this.state = 'inactive'; this.ondataavailable({ data: new Blob(['backup']) }); this.onstop() }
  }
  const code = appSource.slice(appSource.indexOf('  const handleRecordToggle ='), appSource.indexOf('  useEffect(', appSource.indexOf('  const handleRecordToggle =')))
  const context = {
    crypto: { randomUUID: () => 'app-session' }, Date, performance, console,
    audioSourcesRef: { current: { microphone: true, system: false } }, audioPipelineStatusRef: { current: 'idle' },
    pendingManualGenerationRef: { current: null }, manualLiveStartIdRef: { current: '' }, manualLiveSessionRef: { current: null }, streamRef: { current: null },
    autoMode: false, autoProcessing: false, ocrProcessing: false, recording: false,
    getSelectedAudioSourceLabel: () => 'microphone', getPreferredRecorderMimeType: () => '',
    navigator: { mediaDevices: { getUserMedia: async () => stream } }, MediaRecorder: Recorder,
    getBackendWebSocketUrl: (path) => path, downsampleToInt16Mono: () => {},
    isManualLiveEnabled,
    createManualLiveState: (id = '') => ({ sessionId: id, phase: 'idle' }),
    createManualLiveSession: (options) => createManualLiveSession({ ...options, finalizeMs: 5, connectMs: 50 }),
    createLiveMicTransport: () => ({ socket, pauseAudio() {}, close() { socket.onclose?.() } }),
    transcribeAudioBlob: async (blob, mode) => { batchRequests.push({ blob, mode }); return { text: 'What is React?', transcriptionMs: 12 } },
    correctTechnicalQuestionText: (text) => ({ correctedText: text }), BACKEND_URL: 'http://local',
    fetch: async (url, args) => {
      if (url.endsWith('/transcribe/config')) return manualConfig
      detectionRequests.push({ url, body: JSON.parse(args.body) }); return { is_question: true, normalized_question: 'What is React?' }
    },
    parseJsonResponse: async (response) => response,
    classifyAndGenerate: async (request) => {
      generationRequests.push(request)
      history = appendQuestionHistoryEntry(history, createQuestionHistoryEntry({ id: request.capturedHistoryEntryId, mode: 'answer', question: request.text, status: 'generating' }))
      history = updateQuestionHistoryEntry(history, 'answer', request.capturedHistoryEntryId, { fullAnswer: 'React answer', status: 'complete' })
    },
    appendQuestionHistoryEntry, createQuestionHistoryEntry, updateQuestionHistoryEntry,
    setQuestionHistoryState: (fn) => { history = fn(history) },
    normalizePipelineError: (err) => err.message,
  }
  for (const name of [...new Set(code.match(/\bset[A-Z]\w+/g))]) {
    if (context[name]) continue
    context[name] = (value) => {
      values[name] = typeof value === 'function' ? value(values[name] || {}) : value
      if (name === 'setRecording') context.recording = value
      if (name === 'setAudioPipelineStatus') context.audioPipelineStatusRef.current = value
    }
  }
  for (const name of ['clearAudioPipelineIdleReset', 'clearAudioSourceWarning', 'clearProgressiveAnswer', 'resetAnswerMeta', 'resetScreenOcrState', 'appendEventLog']) context[name] = () => {}
  context.stopActiveStream = () => { context.manualLiveStartIdRef.current = ''; context.manualLiveSessionRef.current?.cancel(); context.manualLiveSessionRef.current = null }
  const click = vm.runInNewContext(`${code}; handleRecordToggle`, context)
  const turn = (text, final = false) => socket.onmessage({ data: JSON.stringify({ event: 'turn', transcript: text, turn_order: 0, end_of_turn: final }) })
  return { click, turn, socket, context, values, stream, generationRequests, batchRequests, detectionRequests,
    history: () => history, stoppedTracks: () => stoppedTracks }
}

test('actual App mic clicks preview live, keep generation false, and generate once into the captured history entry', async () => {
  const f = appManualHarness()
  await f.click()
  f.socket.onopen()
  assert.equal(f.values.setStatus, 'Listening...')
  assert.equal(f.values.setRecording, true)
  assert.equal(f.values.setAudioPipelineStatus, 'recording')
  f.turn('What is React?')
  assert.equal(f.values.setTranscript, 'What is React?')
  assert.equal(f.values.setGenerationStarted, false)
  assert.equal(f.generationRequests.length, 0)
  const stop = f.click()
  const repeated = f.click()
  f.turn('What is React?', true)
  await Promise.all([stop, repeated])
  assert.equal(f.generationRequests.length, 1)
  assert.equal(f.batchRequests.length, 0)
  assert.equal(f.history().answer.entries.length, 1)
  assert.equal(f.history().answer.entries[0].fullAnswer, 'React answer')
  assert.equal(f.history().answer.entries[0].id, 'manual-app-session')
  assert.equal(f.values.setManualLiveState.detectedQuestion, 'What is React?')
  assert.equal(f.values.setGenerationStarted, false)
  assert.equal(f.values.setRecording, false)
})

test('actual App fallback calls manual batch STT once and retains its timing', async () => {
  const f = appManualHarness()
  await f.click()
  f.socket.onerror()
  assert.equal(f.batchRequests.length, 0)
  await Promise.all([f.click(), f.click()])
  assert.equal(f.batchRequests.length, 1)
  assert.equal(f.batchRequests[0].mode, 'manual')
  assert.equal(f.generationRequests.length, 1)
  assert.equal(f.generationRequests[0].transcriptionMs, 12)
  assert.equal(f.values.setSttFallbackUsed, true)
})

test('stop during microphone permission request ignores late permission result and releases tracks', async () => {
  const f = appManualHarness()
  let resolvePermission, permissionRequested
  const requested = new Promise((resolve) => { permissionRequested = resolve })
  f.context.navigator.mediaDevices.getUserMedia = () => { permissionRequested(); return new Promise((resolve) => { resolvePermission = resolve }) }
  const starting = f.click()
  await requested
  await f.click()
  resolvePermission(f.stream)
  await starting
  assert.equal(f.stoppedTracks(), 1)
  assert.equal(f.context.manualLiveSessionRef.current, null)
  assert.equal(f.generationRequests.length, 0)
  assert.equal(f.values.setStatus, 'Stopped.')
})

test('backup recorder error does not discard a usable live question', async () => {
  const recorder = { state: 'inactive', start() { this.state = 'recording' }, stop() { this.state = 'inactive'; this.onerror() } }
  const f = setup({ createRecorder: () => recorder })
  f.turn('What is React?', 0, true)
  await f.session.stop()
  assert.equal(f.generations.length, 1)
  assert.equal(f.transcriptions.length, 0)
})

test('backup recorder error during fallback fails safely without generation', async () => {
  const recorder = { state: 'inactive', start() { this.state = 'recording' }, stop() { this.state = 'inactive'; this.onerror() } }
  const f = setup({ createRecorder: () => recorder })
  f.socket.onerror()
  await assert.rejects(f.session.stop(), /backup recording failed/)
  assert.equal(f.generations.length, 0)
  assert.equal(f.states.at(-1).phase, 'error')
  assert.ok(f.counts().trackStops > 0)
})

test('cancel during question detection prevents late generation', async () => {
  let resolveDetection
  let started
  const detectionStarted = new Promise((resolve) => { started = resolve })
  const f = setup({ detectQuestion: () => { started(); return new Promise((resolve) => { resolveDetection = resolve }) } })
  f.turn('What is React?', 0, true)
  const stop = f.session.stop()
  await detectionStarted
  f.session.cancel()
  resolveDetection('What is React?')
  await stop
  assert.equal(f.generations.length, 0)
})

test('microphone permission denial shows safe error and never starts generation', async () => {
  const f = appManualHarness()
  f.context.navigator.mediaDevices.getUserMedia = async () => { throw new Error('denied') }
  await f.click()
  assert.equal(f.values.setStatus, 'Microphone unavailable.')
  assert.equal(f.values.setManualLiveState.phase, 'error')
  assert.equal(f.values.setRecording, false)
  assert.equal(f.generationRequests.length, 0)
})

test('Answer panel shows Listening before text and opens once for a new manual session', () => {
  const overlay = readFileSync(new URL('./components/OverlayWindow.jsx', import.meta.url), 'utf8')
  const panel = readFileSync(new URL('./components/AnswerPanel.jsx', import.meta.url), 'utf8')
  assert.match(overlay, /\[overlayState\.manualLiveState\?\.sessionId\]/)
  assert.match(panel, /title: overlayState\.transcript \|\| \(\['connecting', 'listening'\]/)
  assert.match(panel, /\? 'Listening\.\.\.'/)
})

for (const provider of ['whisper_local', 'openai_whisper']) {
  test(`${provider} without explicit live opt-in captures batch only`, async () => {
    const f = setup({ manualSttProvider: provider, manualLiveSttProvider: 'none', createTransport: () => { throw new Error('privacy boundary breached') } })
    assert.equal(f.states.at(-1).liveProvider, 'none')
    await f.session.stop()
    assert.equal(f.transcriptions.length, 1)
    assert.equal(f.generations.length, 1)
    assert.equal(f.counts().fallbackCount, 0)
  })
}
test('local Whisper blocks streaming even with explicit external live provider', async () => {
  assert.equal(isManualLiveEnabled('whisper_local', 'assemblyai_streaming'), false)
  let transportStarts = 0
  const f = setup({ manualSttProvider: 'whisper_local', createTransport: () => { transportStarts++; throw new Error('external') } })
  await f.session.stop()
  assert.equal(transportStarts, 0)
  assert.equal(f.transcriptions.length, 1)
})
test('explicit AssemblyAI live provider allows openai_whisper preview', () => {
  assert.equal(isManualLiveEnabled('openai_whisper', 'assemblyai_streaming'), true)
  assert.equal(isManualLiveEnabled('openai_whisper', ''), false)
  assert.equal(isManualLiveEnabled('unsupported', 'assemblyai_streaming'), false)
})
test('App uses backend provider gate and disabled preview remains normal batch, not fallback', async () => {
  const f = appManualHarness({ manual_stt_provider: 'whisper_local', manual_live_stt_provider: 'none' })
  await f.click()
  assert.equal(f.socket.onmessage, undefined)
  assert.equal(f.values.setSttProvider, 'whisper_local')
  assert.equal(f.values.setGenerationStarted, false)
  await f.click()
  assert.equal(f.batchRequests.length, 1)
  assert.equal(f.generationRequests.length, 1)
  assert.equal(f.values.setSttFallbackUsed, false)
})
test('configuration fetch failure defaults to batch and never opens external live transport', async () => {
  const f = appManualHarness()
  const fetch = f.context.fetch
  f.context.fetch = (url, args) => url.endsWith('/transcribe/config') ? Promise.reject(new Error('unavailable')) : fetch(url, args)
  await f.click()
  assert.equal(f.socket.onmessage, undefined)
  await f.click()
  assert.equal(f.batchRequests.length, 1)
  assert.equal(f.generationRequests.length, 1)
})
test('new privacy/auth paths do not log secret payloads', () => {
  const auth = readFileSync(new URL('./generation_auth.js', import.meta.url), 'utf8')
  const session = readFileSync(new URL('./manual_live_session.js', import.meta.url), 'utf8')
  assert.doesNotMatch(auth + session, /console\.|logger\.|Authorization|api_key|access_token/)
})


test('early final finishes after revision grace before the 700 ms ceiling, with stop-to-detection timing', async () => {
  const f = setup({ finalizeMs: 700 })
  const stopping = f.session.stop()
  f.turn('What is React?', 0, true)
  await stopping
  const state = f.states.at(-1)
  assert.ok(state.manual_finalization_wait_ms >= 90)
  assert.ok(state.manual_finalization_wait_ms < 650)
  assert.ok(state.manual_final_transcript_received_at >= state.manual_stop_clicked_at)
  assert.equal(state.stop_to_question_detection_ms, state.manual_question_detection_started_at - state.manual_stop_clicked_at)
  assert.ok(state.stop_to_question_detection_ms >= state.manual_finalization_wait_ms)
  assert.equal(f.generations.length, 1)
})

test('no fresh final retains the default 700 ms timeout and uses best partial', async () => {
  const f = setup({ finalizeMs: 700 })
  f.turn('What is React?')
  await f.session.stop()
  assert.ok(f.states.at(-1).manual_finalization_wait_ms >= 690)
  assert.equal(f.generations[0].text, 'What is React?')
})

test('revision during grace replaces the final and repeated Stop generates once; post-close turns are ignored', async () => {
  const f = setup({ finalizeMs: 700 })
  const stopping = f.session.stop()
  f.turn('What is React?', 0, true)
  await new Promise((resolve) => setTimeout(resolve, 60))
  f.turn('What are React hooks?', 0, true)
  assert.equal(f.session.stop(), stopping)
  await stopping
  assert.ok(f.states.at(-1).manual_finalization_wait_ms >= 150)
  assert.equal(f.generations.length, 1)
  assert.equal(f.generations[0].text, 'What are React hooks?')
  f.turn('What is a late revision?', 0, true)
  await f.session.stop()
  assert.equal(f.generations.length, 1)
  assert.equal(getManualFinalTranscript(f.states.at(-1)), 'What are React hooks?')
})

test('an older final cannot complete finalization while a newer partial is outstanding', async () => {
  const f = setup({ finalizeMs: 300 })
  f.turn('Explain hooks.', 0, true)
  f.turn('What is useEffect?', 1)
  const stopping = f.session.stop()
  f.turn('Explain React hooks.', 0, true)
  await stopping
  assert.ok(f.states.at(-1).manual_finalization_wait_ms >= 290)
  assert.equal(f.generations[0].text, 'Explain React hooks. What is useEffect?')
})

test('empty final cannot trigger early completion or generation; empty batch stays safe', async () => {
  const f = setup({ finalizeMs: 150, batchText: '' })
  const stopping = f.session.stop()
  f.turn('   ', 0, true)
  await stopping
  assert.equal(f.generations.length, 0)
  assert.equal(f.transcriptions.length, 1)
  assert.equal(f.states.at(-1).manual_question_detection_started_at, null)
  assert.equal(f.states.at(-1).stop_to_question_detection_ms, null)
})

 test('manual classification or profile failure marks the same history item as error', async () => {
  const f = appManualHarness()
  f.context.classifyAndGenerate = async () => { throw Error('Classification/profile unavailable') }
  await f.click()
  f.socket.onopen()
  f.turn('What is React?', true)
  await f.click()
  assert.equal(f.history().answer.entries.length, 1)
  assert.equal(f.history().answer.entries[0].status, 'error')
 })

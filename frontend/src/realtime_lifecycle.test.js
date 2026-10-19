import test from 'node:test'
import assert from 'node:assert/strict'
import vm from 'node:vm'
import { readFileSync } from 'node:fs'

const app = readFileSync(new URL('./App.jsx', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const names = ['clearCurrentAutoQuestionRun', 'stopAutoStreamingBridge', 'stopActiveStream', 'clearAutoLoop',
  'resetAutoTranscriptBuffer', 'clearPendingAutoQuestion', 'clearPendingCooldownQuestion', 'stopAutoMode', 'stopActiveOperation']
const code = names.map(name => {
  const start = app.indexOf(`  const ${name} = `)
  assert.ok(start >= 0)
  return app.slice(start, app.indexOf('\n  }\n', start) + 4)
}).join('\n')

function fixture(closeGrpc = async () => 'clean') {
  let diagnostics = {}, tracks = 0, grpc = 0, sockets = 0, disconnected = 0, contexts = 0, aborted = 0
  const cleared = new Set(), context = { Promise, WebSocket: { OPEN: 1 },
    clearTimeout: timer => cleared.add(timer), clearInterval: timer => cleared.add(timer),
    createScreenOpaqueId: () => 'stopped', createManualLiveState: () => ({}), logAutoModeDebug: () => {},
    window: { electronAPI: { closeGrpcRealtime: async () => { grpc++; return {} } } } }
  for (const name of new Set(code.match(/\b\w+Ref\b/g))) context[name] = { current: null }
  for (const name of new Set(code.match(/\bset[A-Z]\w+/g))) context[name] = () => {}
  context.setGenerationDiagnostics = update => { diagnostics = update(diagnostics) }
  context.autoStartTokenRef.current = 1
  context.autoModeRunIdRef.current = 'old-run'
  context.autoModeRef.current = true
  context.autoModeSourceRef.current = 'microphone'
  context.streamRef.current = { getTracks: () => [{ stop: () => tracks++ }] }
  context.autoGrpcSessionRef.current = { close: () => { grpc++; return closeGrpc() } }
  context.autoStreamingSocketRef.current = { readyState: 1, send() {}, close: () => sockets++ }
  context.autoStreamingProcessorRef.current = { onaudioprocess() {}, disconnect: () => disconnected++ }
  context.autoStreamingSourceNodeRef.current = { disconnect: () => disconnected++ }
  context.autoStreamingAudioContextRef.current = { close: async () => { contexts++ } }
  context.activeGenerateAbortControllerRef.current = { abort: () => aborted++ }
  for (const name of ['autoLoopTimeoutRef', 'autoCooldownIntervalRef', 'generatingWatchdogTimeoutRef', 'answerReadyResetTimeoutRef', 'refinementPollTimeoutRef']) context[name].current = name
  context.chunksRef.current = ['old audio']
  context.recentAutoTranscriptBufferRef.current = ['old transcript']
  context.pendingAutoQuestionRef.current = { text: 'old question' }
  context.pendingCooldownQuestionRef.current = { text: 'queued question' }
  const { stop, stopActive } = vm.runInNewContext(`${code}\n({stop: stopAutoMode, stopActive: stopActiveOperation})`, context)
  context.stopAutoMode = stop; context.stopActiveOperation = stopActive
  return { stop, stopActive, context, cleared, diagnostics: () => diagnostics,
    counts: () => ({ tracks, grpc, sockets, disconnected, contexts, aborted }) }
}

test('G9 actual renderer Stop releases both transports/tracks/timers/buffers and is idempotent', async () => {
  const f = fixture()
  f.stop(); f.stop()
  await new Promise(resolve => setImmediate(resolve))
  assert.deepEqual(f.counts(), { tracks: 1, grpc: 1, sockets: 1, disconnected: 2, contexts: 1, aborted: 1 })
  for (const name of ['autoLoopTimeoutRef', 'autoCooldownIntervalRef', 'generatingWatchdogTimeoutRef', 'answerReadyResetTimeoutRef', 'refinementPollTimeoutRef']) assert.ok(f.cleared.has(name))
  for (const name of ['streamRef', 'autoGrpcSessionRef', 'autoStreamingSocketRef', 'pendingAutoQuestionRef', 'pendingCooldownQuestionRef']) assert.equal(f.context[name].current, null)
  assert.equal(f.context.recentAutoTranscriptBufferRef.current.length, 0)
  assert.equal(f.context.chunksRef.current.length, 0)
  assert.equal(f.context.autoModeRunIdRef.current, '')
  assert.equal(f.diagnostics().stop_cleanup_status, 'clean')
  assert.equal(f.diagnostics().active_audio_source, 'none')
})
test('G9 late cleanup cannot change diagnostics of a restarted run', async () => {
  let finish
  const f = fixture(() => new Promise(resolve => { finish = resolve }))
  f.stop()
  assert.equal(f.diagnostics().stop_cleanup_status, 'cleaning')
  f.context.autoStartTokenRef.current++ // Existing new-start generation fence.
  finish('clean')
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(f.diagnostics().stop_cleanup_status, 'cleaning')
})

test('combined Stop during transport startup closes the owned RPC before the session factory returns', async () => {
  const f = fixture()
  f.context.autoModeSourceRef.current = 'both'
  f.context.autoStartingRef.current = true
  f.context.autoGrpcSessionRef.current = null
  f.stop()
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(f.counts().grpc, 1)
  assert.equal(f.counts().tracks, 1)
  assert.equal(f.context.autoModeRunIdRef.current, '')
  assert.equal(f.diagnostics().stop_cleanup_status, 'clean')
})
test('G9 old standard generation completion cannot unlock a new run or clear its question', async () => {
  const start = app.indexOf('  const processAutoQuestion = ')
  const processCode = app.slice(start, app.indexOf('\n  }\n', start) + 4)
  let finish, cleared = 0
  const context = { beginAutoQuestionRun: () => true, isContinuousMicAutoActive: () => false,
    logAutoModeDebug: () => {}, clearCurrentAutoQuestionRun: () => cleared++,
    classifyAndGenerate: () => new Promise(resolve => { finish = resolve }),
    isAutoQuestionRunActive: run => context.autoModeRunIdRef.current === run }
  for (const name of new Set(processCode.match(/\b\w+Ref\b/g))) context[name] = { current: null }
  for (const name of new Set(processCode.match(/\bset[A-Z]\w+/g))) context[name] = () => {}
  context.autoModeRunIdRef.current = 'old-run'
  context.autoGenerationInFlightRef.current = false
  const process = vm.runInNewContext(`${processCode}\nprocessAutoQuestion`, context)
  const pending = process('old-run', 'microphone', { text: 'old question', questionRunId: 'old-question', pipelineStarted: 0 })
  context.autoModeRunIdRef.current = 'new-run'
  context.autoGenerationInFlightRef.current = true
  finish()
  await pending
  assert.equal(context.autoGenerationInFlightRef.current, true)
  assert.equal(cleared, 0)
})


function rendererFunction(name) {
  const start = app.indexOf(`  const ${name} = `)
  assert.ok(start >= 0)
  return app.slice(start, app.indexOf('\n  }\n', start) + 4)
}

test('Stop during Auto startup uses the same cancellation path before permission resolves', () => {
  const source = rendererFunction('stopActiveOperation')
  let stops = 0
  const context = { window: { electronAPI: {} }, autoMode: false, clearTimeout() {},
    createManualLiveState: () => ({}), createScreenOpaqueId: () => 'stopped',
    stopAutoMode: () => stops++, stopActiveStream: () => assert.fail('startup must invalidate Auto start') }
  for (const name of new Set(source.match(/\b\w+Ref\b/g))) context[name] = { current: null }
  for (const name of new Set(source.match(/\bset[A-Z]\w+/g))) context[name] = () => {}
  context.autoStartingRef.current = true
  context.autoModeRef.current = false
  vm.runInNewContext(`${source}\nstopActiveOperation()`, context)
  assert.equal(stops, 1)
})

test('session-ended event stops only the matching Auto session before clearing ownership', () => {
  const start = app.indexOf("        if (action === 'cloud-session-ended') {")
  const source = app.slice(start, app.indexOf("        if (['generation-refresh-cloud'", start))
  const calls = []
  const context = { action: 'cloud-session-ended', payload: { payload: { sessionId: 'other' } },
    startupSessionConfigRef: { current: { activeSessionId: 'owned' } },
    autoStartingRef: { current: false }, autoModeRef: { current: true },
    stopAutoMode: () => calls.push('stop'), applyStartupSessionConfig: () => calls.push('clear') }
  const handle = vm.runInNewContext(`() => { ${source} }`, context)
  handle()
  assert.deepEqual(calls, [])
  context.payload.payload.sessionId = 'owned'
  handle()
  assert.deepEqual(calls, ['stop', 'clear'])
})

const main = readFileSync(new URL('../electron/main.cjs', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
function mainHandler(channel, context) {
  const start = main.indexOf(`ipcMain.handle('${channel}',`)
  assert.ok(start >= 0)
  const source = main.slice(start, main.indexOf('\n})', start) + 3)
  let handler
  vm.runInNewContext(source, { ...context, ipcMain: { handle: (_, fn) => { handler = fn } } })
  return handler
}

test('main session end cancels only its matching gRPC connection before cloud I/O', async () => {
  for (const id of ['other', 'owned']) {
    const calls = []
    const handler = mainHandler('cloud:end-interview-session', {
      validateAuthIpc() {}, grpcRealtimeClient: { cloudStart: { active_session_id: 'owned' }, close: () => calls.push('close') },
      desktopAuthSessionManager: { endInterviewSession: async () => { calls.push('cloud'); return { session: { id, status: 'ended' } } } },
      broadcastToolbarAction: () => calls.push('event'),
    })
    await handler({}, id)
    assert.deepEqual(calls, id === 'owned' ? ['close', 'cloud', 'event'] : ['cloud', 'event'])
  }
})

test('main logout cancels gRPC before auth I/O and renderer reset', async () => {
  const calls = []
  const handler = mainHandler('auth:logout', {
    validateAuthIpc() {}, screenContext: { invalidate() {} },
    grpcRealtimeClient: { close: () => calls.push('close') },
    desktopAuthSessionManager: { logout: async () => { calls.push('logout'); return { status: 'signed-out' } } },
    resetStartupFlow: () => calls.push('reset'),
  })
  await handler({})
  assert.deepEqual(calls, ['close', 'logout', 'reset'])
})


test('application session finalization closes gRPC even for a local session', async () => {
  const start = main.indexOf('async function finalizeActiveInterviewSession(')
  const source = main.slice(start, main.indexOf('\n}\n', start) + 2)
  let closed = 0
  const finalize = vm.runInNewContext(`${source}\nfinalizeActiveInterviewSession`, {
    screenContext: { invalidate() {} }, grpcRealtimeClient: { close: () => closed++ },
    desktopAuthSessionManager: { hasActiveInterviewSession: () => false },
  })
  assert.equal((await finalize()).skipped, true)
  assert.equal(closed, 1)
})


function sessionEnd(f, sessionId = 'owned') {
  const start = app.indexOf("        if (action === 'cloud-session-ended') {")
  const source = app.slice(start, app.indexOf("        if (['generation-refresh-cloud'", start))
  const context = f.context
  context.action = 'cloud-session-ended'
  context.payload = { payload: { sessionId } }
  context.startupSessionConfigRef = { current: { activeSessionId: 'owned' } }
  context.applyStartupSessionConfig = next => {
    assert.equal(context.autoModeRunIdRef.current, '')
    assert.equal(context.manualLiveStartIdRef.current || '', '')
    context.startupSessionConfigRef.current = next
  }
  vm.runInNewContext(`(() => { ${source} })()`, context)
}

for (const source of ['microphone', 'both']) for (const starting of [true, false]) test(`matching session end cancels ${starting ? 'starting' : 'active'} ${source} Auto through current refs`, () => {
  const f = fixture()
  f.context.autoModeSourceRef.current = source
  f.context.autoStartingRef.current = starting
  f.context.autoModeRef.current = !starting
  f.context.autoMode = false // A stale closure must not determine mode.
  sessionEnd(f)
  assert.equal(f.context.startupSessionConfigRef.current.activeSessionId, '')
  assert.equal(f.context.autoStartTokenRef.current, 2)
  assert.equal(f.context.autoModeRunIdRef.current, '')
  assert.equal(f.counts().grpc, 1)
  assert.equal(f.counts().tracks, 1)
})

for (const recording of [true, false]) test(`matching session end cancels manual ${recording ? 'capture' : 'generation'} despite stale Auto closure`, async () => {
  const f = fixture(), context = f.context
  context.autoStartingRef.current = context.autoModeRef.current = false
  context.autoMode = true // Previous Auto render; manual currently owns the operation.
  context.autoModeRunIdRef.current = ''
  context.autoGrpcSessionRef.current = context.autoStreamingSocketRef.current = null
  context.autoStreamingProcessorRef.current = context.autoStreamingSourceNodeRef.current = context.autoStreamingAudioContextRef.current = null
  context.manualLiveStartIdRef.current = 'manual'
  let canceled = 0, recorderStops = 0, restored = 0
  context.manualLiveSessionRef.current = { cancel: () => canceled++ }
  const controller = new AbortController()
  context.activeGenerateAbortControllerRef.current = controller
  context.latestGenerationRequestIdRef.current = 'old-manual-request'
  context.mediaRecorderRef.current = recording ? { state: 'recording', stop: () => recorderStops++ } : null
  const transcriptCallback = app.match(/onTranscript: \(text\) => \{ if \(isCurrent\(\)\) setTranscript\(text\) \}/)[0]
  const lateTranscript = vm.runInNewContext(`({${transcriptCallback}}).onTranscript`, {
    isCurrent: () => context.manualLiveStartIdRef.current === 'manual', setTranscript: () => restored++,
  })
  sessionEnd(f)
  assert.equal(canceled, 1)
  assert.equal(recorderStops, recording ? 1 : 0)
  assert.equal(context.manualLiveStartIdRef.current, '')
  assert.equal(controller.signal.aborted, true)
  assert.notEqual(context.latestGenerationRequestIdRef.current, 'old-manual-request')
  lateTranscript('late audio')
  assert.equal(restored, 0)
  assert.equal(context.startupSessionConfigRef.current.activeSessionId, '')
})

test('unrelated session-ended event preserves current operation and identity', () => {
  const f = fixture()
  sessionEnd(f, 'other')
  assert.equal(f.context.startupSessionConfigRef.current.activeSessionId, 'owned')
  assert.equal(f.context.autoModeRunIdRef.current, 'old-run')
  assert.equal(f.context.autoStartTokenRef.current, 1)
  assert.deepEqual(f.counts(), { tracks: 0, grpc: 0, sockets: 0, disconnected: 0, contexts: 0, aborted: 0 })
})

test('matching end during pending Auto/manual permission releases late tracks instead of restoring capture', async () => {
  for (const auto of [true, false]) {
    const f = fixture(), context = f.context
    context.autoStartingRef.current = auto
    context.autoModeRef.current = false
    context.autoModeRunIdRef.current = ''
    context.manualLiveStartIdRef.current = auto ? '' : 'manual'
    const startToken = context.autoStartTokenRef.current
    let resolve, stopped = 0, restored = 0
    const permission = new Promise(done => { resolve = done })
    const guard = auto
      ? app.match(/if \(startToken !== autoStartTokenRef.current\) \{ stream.getTracks\(\).forEach\(track => track.stop\(\)\); return \}/)[0]
      : app.match(/if \(!isCurrent\(\)\) \{ stream.getTracks\(\).forEach\(\(track\) => track.stop\(\)\); return \}/)[0]
    const finish = vm.runInNewContext(`async () => { const stream = await permission; ${guard}; restore() }`, {
      permission, startToken, autoStartTokenRef: context.autoStartTokenRef,
      isCurrent: () => context.manualLiveStartIdRef.current === 'manual', restore: () => restored++,
    })()
    sessionEnd(f)
    resolve({ getTracks: () => [{ stop: () => stopped++ }] })
    await finish
    assert.equal(stopped, 1)
    assert.equal(restored, 0)
  }
})

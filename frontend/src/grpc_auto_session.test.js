import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createGrpcAutoSession, getGrpcAutoBlockReason } from './grpc_auto_session.js'

const enabled = { enabled: true, audioEnabled: true, autoPipelineEnabled: true }
test('G7 flag and cloud/context eligibility preserve existing authenticated paths', () => {
  assert.equal(getGrpcAutoBlockReason({}), 'config_disabled')
  assert.equal(getGrpcAutoBlockReason(enabled), '')
  assert.equal(getGrpcAutoBlockReason(enabled, {activeSessionId:'private'}), 'cloud_session_active')
  assert.equal(getGrpcAutoBlockReason(enabled, {authRequired:true}), 'auth_context_required')
  for (const key of ['selectedResumeId', 'job_context_id']) assert.equal(getGrpcAutoBlockReason(enabled, { [key]: 'private' }), 'selected_context_required')
  assert.equal(getGrpcAutoBlockReason(enabled, {}, 'system'), '')
  assert.equal(getGrpcAutoBlockReason(enabled, { targetRole: 'Engineer' }), 'selected_context_required')
})
function fixture(overrides = {}) {
  let listener, closed = 0, captures = 0, micClosed = 0, statusCalls = 0
  let status = { ...enabled, autoPipelineReady: true, connectionStatus: 'connected', manualRun: 1, autoEventVersion: 0,
    systemAudio: { active_audio_source: 'system' }, questionsDetectedCount: 0, answerCompletedCount: 0, currentAnswer: '' }
  const answers = [], phases = [], errors = [], transcripts = [], fallbacks = [], lifecycle = [], startupFailures = []
  const api = {
    connectGrpcAutoPipeline: async () => status,
    closeGrpcRealtime: async () => { closed++ },
    getGrpcRealtimeStatus: async () => { statusCalls++; return status },
    onGrpcAutoEvent: cb => { listener = cb; return () => { listener = null } },
    ...overrides,
  }
  return { api, answers, phases, errors, transcripts, fallbacks, lifecycle, startupFailures,
    options: { api, stream: {}, onAnswer: x => answers.push(x), onPhase: x => phases.push(x),
      onError: x => errors.push(x), onTranscript: x => transcripts.push(x),
      onFallback: x => fallbacks.push(x), onLifecycle: x => lifecycle.push(x), onStartupFailure: x => startupFailures.push(x),
      createMic: () => ({ start: async () => { captures++ }, close: () => { micClosed++ } }) },
    emit: patch => { status = { ...status, ...patch, autoEventVersion: status.autoEventVersion + 1 }; listener?.(status) },
    counts: () => ({ closed, captures, micClosed, statusCalls, subscribed: !!listener }) }
}
test('G7 partials only preview, deltas render before done, continuous capture and once-only history completion', async () => {
  const f = fixture(), session = await createGrpcAutoSession(f.options)
  f.emit({ currentTranscript: 'partial private question' })
  assert.equal(f.answers.length, 0)
  f.emit({ questionsDetectedCount: 1, currentQuestion: 'Explain REST APIs', currentAnswer: '' })
  f.emit({ currentAnswer: 'First delta', autoStatus: 'generating' })
  assert.equal(f.answers.at(-1).answer, 'First delta')
  assert.equal(f.answers.at(-1).status, 'generating')
  f.emit({ currentAnswer: 'First delta complete', answerCompletedCount: 1, autoStatus: 'auto_cooldown' })
  f.emit({})
  assert.equal(f.answers.filter(x => x.status === 'complete').length, 1)
  assert.equal(new Set(f.answers.map(x => x.historyEntryId)).size, 1)
  assert.equal(f.counts().micClosed, 0)
  f.emit({ autoStatus: 'auto_listening' })
  assert.equal(f.phases.at(-1), 'listening')
  f.emit({ questionsDetectedCount: 2, currentQuestion: 'Explain deep learning', currentAnswer: '', autoStatus: 'generating' })
  assert.equal(f.answers.at(-1).answer, '')
  assert.notEqual(f.answers[0].historyEntryId, f.answers.at(-1).historyEntryId)
  session.stop(); session.close()
  assert.equal(f.counts().micClosed, 1)
  assert.equal(f.counts().closed, 1)
  assert.equal(f.counts().subscribed, false)
})

test('G9 failure before audio or question commitment falls back once and releases subscription/capture', async () => {
  const f = fixture(), session = await createGrpcAutoSession(f.options)
  f.emit({ connectionStatus: 'error' }); f.emit({ connectionStatus: 'error' })
  await session.stop()
  assert.deepEqual(f.fallbacks, ['grpc_connection_failed'])
  assert.deepEqual(f.errors, [])
  assert.equal(f.counts().micClosed, 1); assert.equal(f.counts().closed, 1)
  assert.equal(f.counts().subscribed, false)
  assert.equal(f.lifecycle.at(-1).stop_cleanup_status, 'clean')
})
for (const failurePoint of ['detected', 'started', 'delta', 'unobserved_audio']) {
  test(`G9 ${failurePoint} commitment never falls back or duplicates answer/history`, async () => {
    const f = fixture(), session = await createGrpcAutoSession(f.options)
    if (failurePoint === 'unobserved_audio') f.emit({ grpc_audio_sent: true })
    else {
      f.emit({ questionsDetectedCount: 1, currentQuestion: 'Explain transactions' })
      if (failurePoint === 'started') f.emit({ answerStartedCount: 1 })
      if (failurePoint === 'delta') f.emit({ currentAnswer: 'Preserved answer', answerDeltaCount: 1 })
    }
    const answers = structuredClone(f.answers)
    f.emit({ connectionStatus: 'error', lastErrorMessage: 'private upstream error' })
    f.emit({ currentAnswer: 'late answer', answerCompletedCount: 1 })
    await session.close()
    assert.deepEqual(f.fallbacks, [])
    assert.equal(f.errors.length, 1)
    assert.deepEqual(f.answers, answers)
    assert.doesNotMatch(f.errors[0], /private upstream/)
  })
}
test('G9 cloud rejection is distinct from a transport failure and never falls back', async () => {
  const f = fixture(), session = await createGrpcAutoSession(f.options)
  f.emit({ connectionStatus: 'error', cloudAuthStatus: 'failed', cloudBlockedReason: 'cloud_session_ended' })
  assert.deepEqual(f.fallbacks, [])
  assert.match(f.errors[0], /Cloud session unavailable/)
  await session.stop()
})
test('G9 startup failure exposes exact sanitized transport/auth reason', async () => {
  for (const reason of ['grpc_connection_timeout', 'grpc_start_failed', 'cloud_session_invalid']) {
    const f = fixture({ connectGrpcAutoPipeline: async () => ({ connectionStatus: 'error', grpc_last_failure_reason: reason,
      ...(reason === 'cloud_session_invalid' ? { cloudAuthStatus: 'failed', cloudBlockedReason: reason } : {}) }) })
    assert.equal(await createGrpcAutoSession(f.options), null)
    assert.deepEqual(f.startupFailures, [reason]); assert.equal(f.counts().captures, 0)
  }
})
test('G9 capture-start failure after PCM was sent cannot trigger startup fallback', async () => {
  const f = fixture({ getGrpcRealtimeStatus: async () => ({ grpc_audio_sent: true }) })
  const session = await createGrpcAutoSession({ ...f.options, createMic: () => ({ start: async () => { throw Error('resume failed') }, close: () => {} }) })
  assert.equal(session.failed, true); assert.deepEqual(f.fallbacks, [])
  assert.equal(f.errors.length, 1)
  await session.stop()
})
test('G9 stop twice removes cooldown/deadline/polling, restart has fresh question identity', async () => {
  const f = fixture(), session = await createGrpcAutoSession({ ...f.options, pollMs: 1 })
  f.emit({ questionsDetectedCount: 1, currentQuestion: 'old question' })
  f.emit({ answerCompletedCount: 1, currentAnswer: 'old answer' })
  const oldId = f.answers.at(-1).historyEntryId
  await session.stop(); await session.stop()
  const phases = f.phases.length, polls = f.counts().statusCalls
  await new Promise(resolve => setTimeout(resolve, 10))
  assert.equal(f.phases.length, phases); assert.equal(f.counts().statusCalls, polls)
  f.emit({ manualRun: 2, systemAudio: { active_audio_source: 'system' }, questionsDetectedCount: 0, answerCompletedCount: 0, currentAnswer: '', currentTranscript: '' })
  const restarted = await createGrpcAutoSession(f.options)
  f.emit({ questionsDetectedCount: 1, currentQuestion: 'fresh question' })
  assert.notEqual(f.answers.at(-1).historyEntryId, oldId)
  assert.equal(f.answers.at(-1).answer, '')
  await restarted.stop()
})
test('G7 unavailable startup permits fallback without starting audio', async () => {
  const f = fixture({ connectGrpcAutoPipeline: async () => { throw Error('token secret') } })
  assert.equal(await createGrpcAutoSession(f.options), null)
  assert.equal(f.counts().captures, 0)
  assert.equal(f.counts().closed, 1)
})
test('G7 midstream failure is sanitized and stops instead of duplicate fallback generation', async () => {
  const f = fixture(), session = await createGrpcAutoSession(f.options)
  f.emit({ questionsDetectedCount: 1, connectionStatus: 'error', lastErrorMessage: 'token secret transcript' })
  assert.equal(f.errors.length, 1)
  assert.doesNotMatch(f.errors[0], /secret|token|transcript/)
  assert.equal(f.counts().micClosed, 1)
  session.close()
})
test('G7 guards changing cloud ownership and stale run snapshots', async () => {
  const f = fixture(); let allowed = true
  const session = await createGrpcAutoSession({ ...f.options, canContinue: () => allowed })
  f.emit({ manualRun: 99, questionsDetectedCount: 1, currentAnswer: 'stale' })
  assert.equal(f.answers.length, 0)
  allowed = false; f.emit({ manualRun: 1 })
  assert.equal(f.errors.length, 1)
  session.close()
})
test('main Auto route reuses existing answer/overlay state and closes on Stop and unmount', () => {
  const app = readFileSync(new URL('./App.jsx', import.meta.url), 'utf8')
  assert.match(app, /createGrpcAutoSession\(\{ api: window.electronAPI/)
  assert.match(app, /setAnswer\(entry.answer\)/)
  assert.match(app, /entry.status === 'complete'\) setQuestionHistoryState/)
  assert.match(app, /autoGrpcSessionRef.current\?\.close\(\)/)
  assert.match(app, /autoPipeline === 'gRPC realtime'/)
  const code = readFileSync(new URL('./grpc_auto_session.js', import.meta.url), 'utf8')
  assert.doesNotMatch(code, /console\.|logger\.|processAutoQuestion|classifyAndGenerate/)
})


test('G7 watchdog polling never overlaps and Stop removes polling', async () => {
  const f = fixture(); let calls = 0, resolve
  f.api.getGrpcRealtimeStatus = () => { calls++; return new Promise(done => { resolve = done }) }
  const session = await createGrpcAutoSession({ ...f.options, pollMs: 1 })
  await new Promise(done => setTimeout(done, 15))
  assert.equal(calls, 1)
  session.close()
  resolve({ connectionStatus: 'error' })
  await new Promise(done => setTimeout(done, 10))
  assert.equal(calls, 1)
  assert.equal(f.errors.length, 0)
})

test('G7 precise eligibility priorities never detach cloud ownership', () => {
  assert.equal(getGrpcAutoBlockReason(enabled,{activeSessionId:'owned',authRequired:true,selectedResumeId:'owned'},'system'),'cloud_session_active')
  assert.equal(getGrpcAutoBlockReason({...enabled,enabled:false},{activeSessionId:'owned'}),'cloud_session_active')
  assert.equal(getGrpcAutoBlockReason(enabled,{generationAuthRequired:true}),'auth_context_required')
  assert.equal(getGrpcAutoBlockReason(enabled,{},'both'),'')
  assert.equal(getGrpcAutoBlockReason(enabled,{},'none'),'unsupported_source')
  assert.equal(getGrpcAutoBlockReason({...enabled,audioEnabled:false}),'grpc_unavailable')
  assert.equal(getGrpcAutoBlockReason({...enabled,autoPipelineEnabled:false},{activeSessionId:'owned'}),'config_disabled')
})

test('G7 safe active-session presence diagnostics retain exact ownership reason', () => {
  assert.equal(getGrpcAutoBlockReason(enabled,{activeSessionIdPresent:true,authRequired:true}),'cloud_session_active')
  assert.equal(getGrpcAutoBlockReason(enabled,{activeSessionIdPresent:true,activeSessionEnded:true}), '')
})

// Execute the actual renderer action with no cloud/network API in scope.
test('local test action suspends context in memory, restores it, and refuses active runs', async () => {
  const { default: vm } = await import('node:vm')
  const source = readFileSync(new URL('./App.jsx', import.meta.url), 'utf8')
  const body = source.split('  const toggleLocalTestSession = () => {')[1].split('\n  const beginScreenOperation')[0].split('\n  }')[0]
  const cloud = { activeSessionId: 'session', selectedResumeId: 'resume', jobContextId: 'context' }
  const context = {
    autoGrpcStatus: enabled, autoMode: false, autoProcessing: false, recording: false,
    manualProcessing: false, isManualGenerating: false, ocrProcessing: false,
    localTestSession: false, cloudTestSnapshotRef: { current: null },
    startupSessionConfigRef: { current: cloud }, profileCacheRef: { current: {} },
    setStartupSessionConfig: () => {}, setStatus: () => {},
    setLocalTestSession: value => { context.localTestSession = value },
    setGenerationDiagnostics: update => { context.diagnostics = update({}) },
  }
  const run = () => vm.runInNewContext(`(function(){${body.replace('import.meta.env.DEV', 'true')}})()`, context)
  run()
  assert.equal(context.diagnostics.activeSessionIdPresent, false)
  assert.equal(context.diagnostics.authRequired, false)
  assert.equal(context.diagnostics.localWithoutSaving, true)
  assert.equal(getGrpcAutoBlockReason(enabled, context.startupSessionConfigRef.current), '')
  assert.equal(cloud.activeSessionId, 'session')
  context.autoMode = true; run()
  assert.equal(context.localTestSession, true)
  context.autoMode = false; run()
  assert.equal(context.startupSessionConfigRef.current, cloud)
  assert.equal(getGrpcAutoBlockReason(enabled, cloud), 'cloud_session_active')
  assert.equal(context.cloudTestSnapshotRef.current, null)
  assert.match(source, /onToggleLocalTestSession=\{import\.meta\.env\.DEV && autoGrpcStatus\?\.autoPipelineEnabled/)
})

test('G8 allows verified cloud Auto only behind both flags and keeps exact rejected reason', () => {
  const cloud = { activeSessionId: 'session', authRequired: true, selectedResumeId: 'resume' }
  assert.equal(getGrpcAutoBlockReason(enabled, cloud), 'cloud_session_active')
  const status = { ...enabled, cloudContextPipelineEnabled: true, cloudAuthStatus: 'verified' }
  assert.equal(getGrpcAutoBlockReason(status, cloud), '')
  assert.equal(getGrpcAutoBlockReason({ ...status, cloudAuthAvailable: false }, cloud), 'auth_unavailable')
  assert.equal(getGrpcAutoBlockReason({ ...status, cloudAuthStatus: 'failed', cloudBlockedReason: 'cloud_session_ended' }, cloud), 'cloud_session_ended')
  assert.equal(getGrpcAutoBlockReason(status, cloud, 'system'), '')
  assert.equal(getGrpcAutoBlockReason({ ...status, autoPipelineEnabled: false }, cloud), 'config_disabled')
})

test('Computer factory creates no microphone and never falls back after capture startup', async () => {
  const f = fixture()
  const session = await createGrpcAutoSession({ ...f.options, source: 'system' })
  assert.equal(f.counts().captures, 0)
  f.emit({ connectionStatus: 'error', grpc_audio_sent: false })
  assert.equal(f.fallbacks.length, 0)
  assert.equal(f.errors.length, 1)
  await session.close()
  assert.equal(f.counts().micClosed, 0)
  assert.equal(await createGrpcAutoSession({ ...f.options, source: 'both' }), null)
})

test('Computer factory reports cleanup failure and ignores late events', async () => {
  const f = fixture({ closeGrpcRealtime: async () => ({ systemCleanupStatus: 'failed' }) })
  const session = await createGrpcAutoSession({ ...f.options, source: 'system' })
  assert.equal(await session.close(), 'failed')
  f.emit({ questionsDetectedCount: 1, currentQuestion: 'late' })
  assert.equal(f.answers.length, 0)
  assert.equal(f.lifecycle.at(-1).stop_cleanup_status, 'failed')
})

test('generation failure clears one turn without closing capture and next turn completes', async () => {
  const f = fixture(), session = await createGrpcAutoSession(f.options)
  f.emit({ questionsDetectedCount: 1, currentQuestion: 'Explain REST', answerRequestId: 'turn-one' })
  f.emit({ currentAnswer: 'failed partial' })
  f.emit({ currentAnswer: '', answerFailureCode: 'generation_failed', answerFailureRequestId: 'turn-one', autoStatus: 'auto_listening' })
  f.emit({})
  assert.equal(f.answers.filter(x => x.status === 'error').length, 1)
  assert.equal(f.answers.at(-1).answer, '')
  assert.equal(f.answers.at(-1).requestId, 'turn-one')
  assert.equal(f.errors.length, 0)
  assert.equal(f.counts().closed, 0)
  f.emit({ questionsDetectedCount: 2, currentQuestion: 'Explain SQL', answerRequestId: 'turn-two', answerFailureCode: '' })
  f.emit({ currentAnswer: 'final replacement', answerCompletedCount: 1 })
  assert.equal(f.answers.at(-1).status, 'complete')
  assert.equal(f.answers.at(-1).answer, 'final replacement')
  await session.close()
})

test('coalesced new question and failure belongs to that turn, stale failure is ignored', async () => {
  const f = fixture(), session = await createGrpcAutoSession(f.options)
  f.emit({ questionsDetectedCount: 1, currentQuestion: 'first', answerRequestId: 'one',
    answerFailureCode: 'generation_failed', answerFailureRequestId: 'one', currentAnswer: '' })
  assert.equal(f.answers.at(-1).status, 'error')
  assert.equal(f.answers.at(-1).requestId, 'one')
  const oldHistory = f.answers.at(-1).historyEntryId
  f.emit({ questionsDetectedCount: 2, currentQuestion: 'second', answerRequestId: 'two',
    answerFailureCode: 'generation_failed', answerFailureRequestId: 'one' })
  assert.equal(f.answers.at(-1).status, 'generating')
  assert.notEqual(f.answers.at(-1).historyEntryId, oldHistory)
  f.emit({ answerFailureRequestId: 'two' })
  assert.equal(f.answers.at(-1).status, 'error')
  assert.equal(f.answers.at(-1).requestId, 'two')
  await session.close()
})


test('Computer readiness must confirm the system source before accepting the session', async () => {
  const f = fixture({ connectGrpcAutoPipeline: async () => ({ autoPipelineReady: true,
    connectionStatus: 'connected', manualRun: 1, systemAudio: { active_audio_source: 'microphone' } }) })
  assert.equal(await createGrpcAutoSession({ ...f.options, source: 'system' }), null)
  assert.equal(f.counts().captures, 0)
  assert.equal(f.counts().closed, 1)
  assert.equal(f.fallbacks.length, 0)
})


test('Computer failed startup retains an honest cleanup failure without creating capture', async () => {
  const f = fixture({ connectGrpcAutoPipeline: async () => ({ manualRun: 1, connectionStatus: 'error', autoPipelineReady: false }),
    closeGrpcRealtime: async () => ({ systemCleanupStatus: 'failed' }) })
  assert.equal(await createGrpcAutoSession({ ...f.options, source: 'system' }), null)
  assert.equal(f.lifecycle.at(-1).stop_cleanup_status, 'failed')
  assert.equal(f.counts().captures, 0)
  assert.equal(f.fallbacks.length, 0)
})

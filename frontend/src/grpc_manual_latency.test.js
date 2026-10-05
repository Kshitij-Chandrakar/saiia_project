import test from 'node:test'
import assert from 'node:assert/strict'
import vm from 'node:vm'
import { readFileSync } from 'node:fs'
import { createGrpcManualSession, getGrpcManualBlockReason } from './grpc_manual_session.js'

const source = readFileSync(new URL('./App.jsx', import.meta.url), 'utf8')
test('first main/overlay frame is measured once per run, cleanup cancels late measurement', () => {
  const code = source.slice(source.indexOf('function useGrpcFirstVisibleTiming'), source.indexOf('function OverlayWindow()'))
  const reported = [], frames = new Map(), ref = { current: 0 }
  let cleanup, next = 0
  const hook = vm.runInNewContext(`${code}; useGrpcFirstVisibleTiming`, {
    useRef: () => ref, useEffect: effect => { cleanup = effect() }, Date,
    requestAnimationFrame: fn => { frames.set(++next, fn); return next },
    cancelAnimationFrame: id => frames.delete(id),
    window: { electronAPI: { reportGrpcManualUiTiming: async (...args) => reported.push(args) } },
  })
  hook('', 1, 'first_main_ui_update_at')
  assert.equal(frames.size, 0)
  hook('First delta', 1, 'first_main_ui_update_at')
  frames.get(1)(); frames.delete(1)
  hook('Second delta', 1, 'first_main_ui_update_at')
  assert.equal(reported.length, 1)
  assert.equal(typeof reported[0][2], 'number')
  hook('New run', 2, 'first_overlay_update_at')
  cleanup()
  assert.equal(frames.size, 0)
})

test('timing-only renders never duplicate gRPC overlay updates; default flow stays unchanged', () => {
  const code = source.slice(source.indexOf('function useElectronOverlaySync'), source.indexOf('function useGrpcFirstVisibleTiming'))
  const calls = [], ref = { current: null }
  const sync = vm.runInNewContext(`${code}; useElectronOverlaySync`, {
    useRef: () => ref, useEffect: fn => fn(), OVERLAY_PRIVACY_MESSAGE: 'safe',
    window: { electronAPI: { updateOverlayState: state => calls.push(state) } },
  })
  const state = { answer: 'First', manualLiveState: { transport: 'grpc' } }
  sync(state)
  sync({ ...state, generationDiagnostics: { manualTimings: { first_main_ui_update_at: 1 } } })
  assert.equal(calls.length, 1)
  sync({ ...state, answer: 'First second' })
  assert.equal(calls.length, 2)
  sync({ answer: 'Legacy' }); sync({ answer: 'Legacy' })
  assert.equal(calls.length, 4)
})

test('gRPC receipts report timings and growing deltas before completion without repeated state publication', async () => {
  const states = [], answers = [], timings = [], pipelines = []
  const start = Date.now()
  let status = { connectionStatus: 'connected', manualPipelineReady: true, manualRun: 3,
    currentTranscript: 'Preview', currentQuestion: 'Question', currentAnswer: 'First',
    lastAnswerStatus: 'answer_delta', manualTimings: { first_transcript_at: start, question_detected_at: start + 1,
      answer_started_at: start + 2, first_answer_delta_at: start + 3 } }
  const session = await createGrpcManualSession({
    api: { connectGrpcManualPipeline: async () => status, getGrpcRealtimeStatus: async () => status, closeGrpcRealtime: async () => {} },
    options: { sessionId: 'latency', manualStartedAt: start - 10, stream: {}, onState: s => states.push(s), onTranscript() {}, onFallback() {} },
    createLegacy: () => ({ cancel() {} }), createMic: () => ({ start: async () => {}, stop: async () => {}, close() {} }),
    pollMs: 5, onAnswer: event => answers.push(event), onTiming: t => timings.push(t), onPipeline: p => pipelines.push(p),
  })
  const stopping = session.stop()
  await new Promise(resolve => setTimeout(resolve, 20))
  assert.equal(answers.length, 1)
  assert.equal(answers[0].status, 'generating')
  assert.equal(answers[0].manualRun, 3)
  const count = states.length
  await new Promise(resolve => setTimeout(resolve, 20))
  assert.equal(states.length, count)
  status = { ...status, currentAnswer: 'First second' }
  await new Promise(resolve => setTimeout(resolve, 15))
  assert.equal(answers.length, 2)
  status = { ...status, lastAnswerStatus: 'answer_completed', manualTimings: { ...status.manualTimings, answer_completed_at: Date.now() } }
  await stopping
  assert.equal(answers.filter(a => a.status === 'complete').length, 1)
  assert.deepEqual(pipelines, ['gRPC realtime'])
  assert.equal(timings.at(-1).manual_start_at, start - 10)
  assert.equal(typeof timings.at(-1).manual_stop_at, 'number')
  assert.equal(typeof timings.at(-1).answer_completed_at, 'number')
})

test('pipeline eligibility exposes safe reasons rather than pretending context-bound REST is gRPC', () => {
  assert.equal(getGrpcManualBlockReason({}), 'feature_disabled')
  assert.equal(getGrpcManualBlockReason({ manualPipelineEnabled: true }), 'grpc_audio_disabled')
  assert.equal(getGrpcManualBlockReason({ manualPipelineEnabled: true, audioEnabled: true }, { activeSessionId: 'private' }), 'interview_context_requires_existing_flow')
})

test('pushed first delta updates immediately despite a blocked poll; stale/duplicate events cannot overwrite it', async () => {
  let receive, releasePoll, unsubscribed = 0
  const answers = [], states = []
  const ready = { manualRun: 8, manualEventVersion: 0, manualPipelineReady: true, connectionStatus: 'connected' }
  const session = await createGrpcManualSession({
    api: {
      connectGrpcManualPipeline: async () => ready,
      getGrpcRealtimeStatus: () => new Promise(resolve => { releasePoll = resolve }),
      onGrpcManualEvent: fn => { receive = fn; return () => { unsubscribed++ } },
      closeGrpcRealtime: async () => {},
    },
    options: { sessionId: 'push', stream: {}, onState: s => states.push(s), onTranscript() {}, onFallback() {} },
    createLegacy: () => ({ cancel() {} }), createMic: () => ({ start: async () => {}, stop: async () => {}, close() {} }),
    onAnswer: event => answers.push(event), pollMs: 10000,
  })
  const stopped = session.stop()
  await Promise.resolve()
  const delta = { ...ready, manualEventVersion: 2, currentQuestion: 'Question', currentAnswer: 'First', lastAnswerStatus: 'answer_delta' }
  receive(delta)
  assert.equal(answers.length, 1) // No timeout/poll/frame/completion is needed for publication.
  assert.equal(answers[0].answer, 'First')
  assert.equal(answers[0].status, 'generating')
  receive(delta)
  receive({ ...delta, manualRun: 7, currentAnswer: 'Wrong run' })
  receive({ ...delta, manualEventVersion: 1, currentAnswer: 'Old text' })
  assert.equal(answers.length, 1)
  receive({ ...delta, manualEventVersion: 3, currentAnswer: 'First second' })
  assert.equal(answers.length, 2)
  receive({ ...delta, manualEventVersion: 4, currentAnswer: 'Final', lastAnswerStatus: 'answer_completed' })
  await stopped // The unresolved health poll cannot hold up completion.
  assert.equal(unsubscribed, 1)
  assert.equal(answers.filter(a => a.status === 'complete').length, 1)
  releasePoll(ready)
  receive({ ...delta, manualEventVersion: 4, lastAnswerStatus: 'answer_completed' })
  await Promise.resolve()
  assert.equal(answers.length, 3)
  assert.equal(states.at(-1).phase, 'idle')
})

test('hidden overlay does not claim a visible first-frame measurement', () => {
  const code = source.slice(source.indexOf('function useGrpcFirstVisibleTiming'), source.indexOf('function OverlayWindow()'))
  let scheduled = 0
  const hook = vm.runInNewContext(`${code}; useGrpcFirstVisibleTiming`, {
    useRef: () => ({ current: 0 }), useEffect: fn => fn(),
    requestAnimationFrame: () => { scheduled++ },
    window: { electronAPI: { reportGrpcManualUiTiming: async () => {} } },
  })
  hook('First delta', 9, 'first_overlay_update_at', false)
  assert.equal(scheduled, 0)
})

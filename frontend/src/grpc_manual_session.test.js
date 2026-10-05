import test from 'node:test'
import assert from 'node:assert/strict'
import { canUseGrpcManual, createGrpcManualSession } from './grpc_manual_session.js'

const enabled = { manualPipelineEnabled: true, audioEnabled: true }
const tick = () => new Promise(resolve => setTimeout(resolve, 12))
function fixture() {
  let status = { ...enabled, manualPipelineReady: true, connectionStatus: 'connected' }
  const calls = [], states = [], answers = []
  const api = {
    connectGrpcManualPipeline: async () => { calls.push('connect'); return status },
    getGrpcRealtimeStatus: async () => status,
    closeGrpcRealtime: async () => { calls.push('close') },
  }
  const options = { sessionId: 'test', stream: {}, onState: s => states.push(s),
    onTranscript: () => {}, onFallback: () => calls.push('fallback') }
  const createLegacy = opts => {
    calls.push(opts.manualLiveSttProvider === 'none' ? 'backup' : 'legacy')
    return { stop: async () => calls.push('legacyStop'), cancel: () => calls.push('backupCancel') }
  }
  const createMic = opts => {
    assert.equal(opts.ownsStream, false)
    return { start: async () => calls.push('micStart'), stop: async () => calls.push('micStop'), close: () => calls.push('micClose') }
  }
  return { api, calls, states, answers, set: s => { status = { ...status, ...s } },
    start: extras => createGrpcManualSession({ api, options, createLegacy, createMic,
      onAnswer: event => answers.push(event), pollMs: 5, timeoutMs: 150, ...extras }) }
}

test('G6 false preserves legacy routing; cloud context is never detached', () => {
  assert.equal(canUseGrpcManual({ ...enabled, manualPipelineEnabled: false }), false)
  assert.equal(canUseGrpcManual(enabled), true)
  for (const key of ['activeSessionId', 'selectedResumeId', 'jobContextId', 'job_context_id', 'targetRole', 'jobDescription']) {
    assert.equal(canUseGrpcManual(enabled, { [key]: 'present' }), false)
  }
})

test('manual gRPC streams progressive answers into one history id and repeated Stop completes once', async () => {
  const f = fixture(), session = await f.start()
  assert.equal(f.calls.includes('micStart'), true)
  const stopped = session.stop()
  assert.equal(session.stop(), stopped)
  f.set({ currentQuestion: 'Explain realtime systems', currentAnswer: 'First', lastAnswerStatus: 'answer_delta' })
  await tick()
  assert.equal(f.answers[0].answer, 'First')
  assert.equal(f.answers[0].status, 'generating')
  f.set({ currentAnswer: 'First answer', lastAnswerStatus: 'answer_completed' })
  await stopped
  assert.equal(f.answers.at(-1).status, 'complete')
  assert.deepEqual([...new Set(f.answers.map(a => a.historyEntryId))], ['manual-test'])
  assert.equal(f.calls.filter(x => x === 'micStop').length, 1)
  assert.equal(f.calls.includes('legacyStop'), false)
  assert.equal(f.calls.includes('backupCancel'), true)
})

test('connection failure uses existing manual live flow without starting gRPC mic', async () => {
  const f = fixture()
  f.set({ connectionStatus: 'error', manualPipelineReady: false })
  const session = await f.start()
  await session.stop()
  assert.equal(f.calls.includes('legacy'), true)
  assert.equal(f.calls.includes('micStart'), false)
  assert.equal(f.calls.includes('fallback'), true)
})

test('failure while listening uses batch backup exactly once on Stop', async () => {
  const f = fixture(), session = await f.start()
  f.set({ connectionStatus: 'error', lastErrorMessage: 'generic' })
  await tick()
  await Promise.all([session.stop(), session.stop()])
  assert.equal(f.calls.filter(x => x === 'legacyStop').length, 1)
})

test('generation failure never retries REST and marks same entry error safely', async () => {
  const f = fixture(), session = await f.start()
  const stopped = session.stop()
  f.set({ currentQuestion: 'Explain realtime systems', currentAnswer: 'Partial', lastErrorMessage: 'private upstream secret' })
  await assert.rejects(stopped, error => !error.message.includes('private') && /unavailable/.test(error.message))
  assert.equal(f.calls.includes('legacyStop'), false)
  assert.equal(f.answers.at(-1).status, 'error')
})

test('cancel drains no generation, closes resources and ignores late replies', async () => {
  const f = fixture(), session = await f.start()
  session.cancel()
  f.set({ currentAnswer: 'Late answer', lastAnswerStatus: 'answer_completed' })
  await tick()
  assert.equal(f.answers.length, 0)
  assert.equal(f.calls.includes('micClose'), true)
  assert.equal(f.calls.includes('backupCancel'), true)
})

test('empty/non-question completion produces no answer and bounded timeout recovers', async () => {
  const f = fixture(), session = await f.start()
  f.set({ manualStatus: 'manual_no_question' })
  await session.stop()
  assert.equal(f.answers.length, 0)
  const g = fixture(), hanging = await g.start({ timeoutMs: 15 })
  await assert.rejects(hanging.stop(), /unavailable/)
  assert.equal(g.calls.includes('close'), true)
})

test('new cloud selection before Stop returns to existing authenticated generation', async () => {
  const f = fixture(), session = await f.start({ canContinue: () => false })
  await session.stop()
  assert.equal(f.calls.includes('legacyStop'), true)
  assert.equal(f.calls.includes('micStop'), false)
})

test('backup recorder setup failure closes the opened gRPC stream without leaking provider errors', async () => {
  const f = fixture()
  await assert.rejects(f.start({ createLegacy: () => { throw Error('private recorder details') } }), /backup recording unavailable/)
  assert.equal(f.calls.includes('close'), true)
  assert.equal(f.calls.includes('micStart'), false)
})

test('manual status polling never overlaps and canceled late replies cannot update the UI', async () => {
  const f = fixture()
  let resolveStatus, calls = 0
  f.api.getGrpcRealtimeStatus = () => { calls++; return new Promise(resolve => { resolveStatus = resolve }) }
  const session = await f.start()
  await tick(); await tick()
  assert.equal(calls, 1)
  session.cancel()
  resolveStatus({ currentQuestion: 'Late question', currentAnswer: 'Late answer', connectionStatus: 'connected' })
  await tick()
  assert.equal(f.answers.length, 0)
  assert.equal(calls, 1)
})

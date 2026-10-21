import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { createGrpcAutoSession } from './grpc_auto_session.js'
import { mergeOverlaySnapshot } from './overlay_snapshot.js'
import { answerStreamDriver } from '../tests/fixtures/answer_stream_driver.mjs'
const require = createRequire(import.meta.url)
const { AnswerStreamState, uint, fenceOverlayAnswer } = require('../electron/answer_stream_state.cjs')
const id = (revision = '0', attempt = 0, turn = '1') => ({ accepted_turn: turn, display_revision: revision, retry_attempt: 0, provider_attempt: attempt })
async function session(driver, answers) {
  return createGrpcAutoSession({ source: driver.source || 'microphone', stream: { getTracks: () => [], getAudioTracks: () => [] },
    api: { connectGrpcAutoPipeline: () => driver.connect(), getGrpcRealtimeStatus: async () => driver.client.getStatus(),
      onGrpcAutoEvent: fn => driver.subscribe(fn), closeGrpcRealtime: async () => driver.close() },
    createMic: () => ({ start: async () => {}, close() {} }), onAnswer: x => answers.push(x) })
}
for (const source of ['microphone', 'system', 'both']) {
  test(`negotiated ${source}: primary/fallback prefixes, empty reset, canonical and once-only completion`, async t => {
    const driver = answerStreamDriver(source, true), answers = []; driver.source = source
    const ui = await session(driver, answers)
    t.mock.timers.enable({ apis: ['setTimeout'] })
    try {
      assert.equal(driver.client.answerState.version, 1)
      driver.emit('question_detected', { text: 'Synthetic question' })
      driver.emit('answer_started', {})
      driver.emit('answer_delta', { text: 'Primary A' })
      assert.equal(answers.at(-1).answer, '')
      t.mock.timers.tick(16)
      assert.equal(answers.at(-1).answer, 'Primary A')
      assert.equal(answers.at(-1).answerSaved, false)
      driver.emit('answer_delta', { text: ' B' }); t.mock.timers.tick(16)
      assert.equal(answers.at(-1).answer, 'Primary A B')
      driver.emit('answer_delta', { text: ' queued discarded' })
      driver.emit('answer_replaced', { text: '' }, { answer_identity: id('1') })
      assert.equal(answers.at(-1).answer, '')
      t.mock.timers.tick(16)
      assert.equal(answers.at(-1).answer, '')
      driver.emit('answer_delta', { text: 'late primary' }, { answer_identity: id() })
      driver.emit('answer_replaced', { text: '' }, { answer_identity: id('2', 1) })
      driver.emit('answer_delta', { text: 'Fallback A' }); t.mock.timers.tick(16)
      assert.equal(answers.at(-1).answer, 'Fallback A')
      driver.emit('answer_delta', { text: ' B' }); t.mock.timers.tick(16)
      assert.equal(answers.at(-1).answer, 'Fallback A B')
      assert.equal(driver.client.answerCompletedCount, 0)
      driver.emit('answer_delta', { text: ' queued' })
      driver.emit('answer_replaced', { text: 'Validated canonical' }, { answer_identity: id('3', 1) })
      driver.emit('answer_completed', { text: 'Validated canonical' })
      assert.equal(answers.at(-1).answerSaved, true)
      t.mock.timers.tick(16)
      assert.equal(answers.at(-1).answer, 'Validated canonical')
      assert.equal(answers.filter(x => x.status === 'complete').length, 1)
      const count = answers.length
      driver.emit('answer_completed', { text: 'duplicate' })
      driver.emit('question_detected', { text: 'old start' })
      driver.emit('answer_delta', { text: 'terminal late' })
      assert.equal(answers.length, count)
      assert.equal(new Set(answers.map(x => x.historyEntryId)).size, 1)
      assert.ok(answers.at(-1).streamIdentity.terminal)
    } finally { t.mock.timers.reset(); await ui.close(); await driver.close() }
  })
}

test('uint64 identity: gaps accepted; unsafe, duplicate, stale and incompatible events rejected', () => {
  assert.equal(uint('18446744073709551615'), '18446744073709551615')
  for (const value of [9007199254740992, '18446744073709551616', '-1', '1.0', '01']) assert.equal(uint(value), null)
  const state = new AnswerStreamState()
  state.acknowledge({ sequence_number: '1', answer_stream_capabilities: { version: 1 } })
  const event = (sequence, identity = id('0', 0, '9007199254740993'), request_id = 'a') => ({ sequence_number: sequence, answer_identity: identity, request_id })
  assert.ok(state.accept(event('9007199254740993'), 'question_detected'))
  assert.ok(state.accept(event('9007199254740995'), 'answer_delta'))
  assert.equal(state.accept(event('9007199254740995'), 'answer_delta'), false)
  assert.equal(state.accept(event('9007199254740996', id('1', 1, '9007199254740993')), 'answer_delta'), false)
  assert.ok(state.accept(event('9007199254740997', id('1', 1, '9007199254740993')), 'answer_replaced'))
  assert.equal(state.accept(event('9007199254740998'), 'answer_delta'), false)
  assert.ok(state.accept(event('9007199254740999', id('1', 1, '9007199254740993')), 'answer_completed'))
  assert.equal(state.accept(event('9007199254741000'), 'question_detected'), false)
  assert.ok(state.accept(event('9007199254741001', id('0', 0, '9007199254740994'), 'b'), 'question_detected'))
  assert.equal(state.accept(event('9007199254741002', id('1', 1, '9007199254740993')), 'answer_completed'), false)
})

for (const code of ['generation_failed', 'persistence_unavailable', 'generation_processing', 'generation_uncertain', 'generation_stopped']) {
  test(`${code}: terminal clears provisional, healthy connection accepts next turn, Stop cancels pending publication`, async t => {
    const driver = answerStreamDriver('microphone', true), answers = [], ui = await session(driver, answers)
    t.mock.timers.enable({ apis: ['setTimeout'] })
    try {
      driver.emit('question_detected', { text: 'First' })
      driver.emit('answer_delta', { text: 'Unusable' }); t.mock.timers.tick(16)
      driver.emit('answer_error', { code, message: 'PRIVATE provider detail' })
      assert.equal(answers.at(-1).status, 'error'); assert.equal(answers.at(-1).answer, '')
      assert.equal(driver.client.status, 'connected')
      const terminal = driver.snapshots.at(-1), count = answers.length
      // Duplicate polling snapshot must not reopen a terminal turn.
      driver.client.onAutoEvent(terminal)
      driver.client.onAutoEvent({ ...terminal, autoEventVersion: terminal.autoEventVersion - 1 })
      assert.equal(answers.length, count)
      driver.emit('question_detected', { text: 'Next' }, { request_id: 'next-turn', answer_identity: id('0', 0, '2') })
      driver.emit('answer_delta', { text: 'Pending' }, { request_id: 'next-turn' })
      const before = answers.length
      await ui.close(); t.mock.timers.tick(32)
      driver.emit('answer_completed', { text: 'late' }, { request_id: 'next-turn' })
      assert.equal(answers.length, before)
      assert.equal(driver.client.answerState.version, 0)
      assert.doesNotMatch(JSON.stringify(driver.snapshots), /PRIVATE|synthetic-test-only|Authorization|Bearer/)
    } finally { t.mock.timers.reset(); await ui.close(); await driver.close() }
  })
}

test('overlay receiving boundary fences old revision, terminal reopen and old initial/polling snapshots; controls survive', () => {
  const live = { ...id('2', 1), requestId: 'turn', run: 1, epoch: 2, sessionId: 'transport', terminal: false, snapshotVersion: 7 }
  const old = { ...live, display_revision: '0' }
  const current = { answer: '', grpcAnswerIdentity: live }
  const filtered = fenceOverlayAnswer({ answer: 'discarded', transcript: 'old', grpcAnswerIdentity: old, fontSize: 18 }, current, live)
  assert.equal(filtered.answer, undefined); assert.equal(filtered.fontSize, 18)
  assert.equal(fenceOverlayAnswer({ answer: 'fallback', grpcAnswerIdentity: live }, current, live).answer, 'fallback')
  assert.equal(fenceOverlayAnswer({ answer: 'late', grpcAnswerIdentity: live }, current, null).answer, undefined)
  assert.equal(fenceOverlayAnswer({ answer: 'late', grpcAnswerIdentity: live }, current, { ...live, terminal: true }).answer, undefined)
  const final = { answer: 'canonical', overlayPublicationVersion: 9 }
  for (const version of [8, 9]) assert.equal(mergeOverlaySnapshot(final, { answer: 'stale', overlayPublicationVersion: version }), final)
  assert.equal(mergeOverlaySnapshot(final, { answer: 'new', overlayPublicationVersion: 11 }).answer, 'new')
})

for (const boundary of ['disconnect', 'logout', 'session-end']) {
  test(`${boundary} at unchanged snapshot version cancels UI and pending publication`, async t => {
    const driver = answerStreamDriver('microphone', true), answers = []
    let allowed = true, errorCount = 0
    const ui = await createGrpcAutoSession({ api: {
      connectGrpcAutoPipeline: () => driver.connect(), onGrpcAutoEvent: fn => driver.subscribe(fn),
      getGrpcRealtimeStatus: async () => driver.client.getStatus(), closeGrpcRealtime: async () => driver.close(),
    }, stream: {}, createMic: () => ({ start: async () => {}, close() {} }),
    canContinue: () => allowed, onAnswer: x => answers.push(x), onError: () => errorCount++ })
    t.mock.timers.enable({ apis: ['setTimeout'] })
    try {
      driver.emit('question_detected', { text: 'Synthetic' })
      driver.emit('answer_delta', { text: 'A' }); t.mock.timers.tick(16)
      const snapshot = driver.client.getStatus()
      driver.emit('answer_delta', { text: ' pending' })
      if (boundary === 'disconnect') driver.client.fail()
      else allowed = false
      // The last delivered version is unchanged; auth/transport must still be checked.
      driver.client.onAutoEvent({ ...snapshot, ...(boundary === 'disconnect' ? { connectionStatus: 'error' } : {}) })
      assert.equal(errorCount, 1)
      const count = answers.length
      t.mock.timers.tick(32)
      assert.equal(answers.length, count)
    } finally { t.mock.timers.reset(); await ui.close(); await driver.close() }
  })
}

test('reconnect resets negotiation; old epoch events cannot mutate a fresh legacy connection', async () => {
  const driver = answerStreamDriver('microphone', true)
  await driver.connect()
  const oldEpoch = driver.client.epoch, oldSession = driver.client.sessionId
  await driver.close()
  assert.equal(driver.client.answerState.version, 0)
  assert.ok(driver.client.epoch > oldEpoch)
  await driver.connect()
  assert.equal(driver.client.answerState.version, 1)
  driver.emit('question_detected', { text: 'old' }, { session_id: oldSession })
  assert.equal(driver.client.questionsDetectedCount, 0)
  await driver.close()
  const legacy = answerStreamDriver('microphone')
  await legacy.connect()
  assert.equal(legacy.client.answerState.version, 0)
  legacy.emit('answer_replaced', { text: 'unacknowledged' })
  assert.equal(legacy.client.currentAnswer, '')
  await legacy.close()
})

test('overlay receives identity fences even with a higher publication version; invalidation permits a newer question', () => {
  const identity = { ...id('2', 1), requestId: 'turn', run: 1, epoch: 2, sessionId: 'transport', terminal: true, snapshotVersion: 7 }
  const current = { answer: 'canonical', grpcAnswerIdentity: identity, overlayPublicationVersion: 9 }
  const stale = mergeOverlaySnapshot(current, { answer: 'late', grpcAnswerIdentity: { ...identity, display_revision: '1', terminal: false }, overlayPublicationVersion: 10, fontSize: 18 })
  assert.equal(stale.answer, 'canonical'); assert.equal(stale.fontSize, 18)
  const stopped = mergeOverlaySnapshot(stale, { grpcAnswerIdentity: null, overlayPublicationVersion: 11 })
  assert.equal(mergeOverlaySnapshot(stopped, { answer: 'late', grpcAnswerIdentity: identity, overlayPublicationVersion: 12 }).answer, 'canonical')
  const next = mergeOverlaySnapshot(stopped, { answer: 'next', grpcAnswerIdentity: { ...identity, accepted_turn: '2', requestId: 'next', display_revision: '0', terminal: false }, overlayPublicationVersion: 13 })
  assert.equal(next.answer, 'next')
})

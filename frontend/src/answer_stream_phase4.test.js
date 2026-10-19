import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { answerStreamDriver } from '../tests/fixtures/answer_stream_driver.mjs'
import { createGrpcAutoSession } from './grpc_auto_session.js'
import { mergeOverlaySnapshot } from './overlay_snapshot.js'
const { fenceOverlayAnswer } = createRequire(import.meta.url)('../electron/answer_stream_state.cjs')

for (const outcome of ['generating', 'complete', 'error']) {
  test(`question accepted during capture startup retains ${outcome} phase`, async () => {
    const driver = answerStreamDriver('microphone', true), phases = []
    const ui = await createGrpcAutoSession({ api: {
      connectGrpcAutoPipeline: () => driver.connect(), onGrpcAutoEvent: fn => driver.subscribe(fn),
      getGrpcRealtimeStatus: async () => driver.client.getStatus(), closeGrpcRealtime: async () => driver.close(),
    }, stream: {}, onPhase: phase => phases.push(phase), createMic: () => ({
      start: async () => {
        driver.emit('question_detected', { text: 'Synthetic startup question' })
        if (outcome === 'complete') driver.emit('answer_completed', { text: 'Canonical' })
        if (outcome === 'error') driver.emit('answer_error', { code: 'generation_failed' })
      }, close() {},
    }) })
    try { assert.equal(phases.at(-1), { generating: 'generating', complete: 'cooldown', error: 'listening' }[outcome]) }
    finally { await ui.close(); await driver.close() }
  })
}

test('long-answer burst has one bounded publication; Stop drops the next burst', async t => {
  const driver = answerStreamDriver('microphone', true)
  await driver.connect()
  t.mock.timers.enable({ apis: ['setTimeout'] })
  try {
    driver.emit('question_detected', { text: 'Synthetic long question' })
    const before = driver.snapshots.length
    for (let i = 0; i < 1200; i++) driver.emit('answer_delta', { text: 'x'.repeat(256) })
    assert.equal(driver.client.currentAnswer.length, 262144)
    assert.equal(driver.snapshots.length, before)
    t.mock.timers.tick(16)
    assert.equal(driver.snapshots.length, before + 1)
    driver.emit('answer_delta', { text: 'pending' })
    await driver.close(); t.mock.timers.tick(16)
    assert.equal(driver.snapshots.length, before + 1)
  } finally { t.mock.timers.reset(); await driver.close() }
})

test('stale overlay answer cannot reopen generating/error presentation; unrelated controls merge', () => {
  const currentIdentity = { accepted_turn: '1', display_revision: '2', retry_attempt: '0', provider_attempt: '1', run: 1, epoch: 2,
    sessionId: 'transport', requestId: 'turn', terminal: true, snapshotVersion: 9 }
  const current = { answer: 'Canonical', autoProcessing: false, status: 'Complete', grpcAnswerIdentity: currentIdentity, overlayPublicationVersion: 10 }
  const next = { answer: 'Discarded', autoProcessing: true, generationStarted: true, status: 'Generating', error: 'Old error',
    fontSize: 18, grpcAnswerIdentity: { ...currentIdentity, display_revision: '0', provider_attempt: '0', terminal: false }, overlayPublicationVersion: 11 }
  const main = fenceOverlayAnswer(next, current, currentIdentity)
  assert.equal(main.autoProcessing, undefined); assert.equal(main.status, undefined); assert.equal(main.fontSize, 18)
  const rendered = mergeOverlaySnapshot(current, next)
  assert.equal(rendered.answer, 'Canonical'); assert.equal(rendered.autoProcessing, false)
  assert.equal(rendered.status, 'Complete'); assert.equal(rendered.error, undefined); assert.equal(rendered.fontSize, 18)
})

test('test-only network guard rejects external TCP and DNS before a request can leave', async () => {
  const require = createRequire(import.meta.url)
  require('../tests/fixtures/loopback_only.cjs')
  const net = require('node:net'), dns = require('node:dns')
  assert.throws(() => new net.Socket().connect(443, 'example.invalid'), /External network forbidden/)
  assert.throws(() => dns.lookup('example.invalid', () => {}), /External network forbidden/)
})

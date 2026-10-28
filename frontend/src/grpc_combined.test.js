import test from 'node:test'
import assert from 'node:assert/strict'
import { createGrpcAutoSession } from './grpc_auto_session.js'
import { selectRealtimeRoute } from './realtime_router.js'
import { createContinuousDownsampler } from './live_mic_transport.js'
import { createGrpcMicTest } from './grpc_mic_test.js'

const healthy = { enabled: true, audioEnabled: true, autoPipelineEnabled: true,
  grpc_health: 'healthy', grpc_stt_available: true, grpc_answer_available: true,
  grpc_auto_available: true, grpc_combined_audio_available: true }

test('combined is capability-gated and never offers another transport', () => {
  assert.equal(selectRealtimeRoute(healthy, {}, 'both').route, 'grpc_realtime')
  for (const status of [{ ...healthy, grpc_combined_audio_available: false },
    { ...healthy, autoPipelineEnabled: false }, { ...healthy, grpc_health: 'failed' }]) {
    const decision = selectRealtimeRoute(status, {}, 'both')
    assert.equal(decision.route, 'blocked')
    assert.equal(decision.fallbackAvailable, false)
  }
  assert.equal(selectRealtimeRoute(healthy, {}, 'both', false).reason, 'grpc_unavailable')
  assert.equal(selectRealtimeRoute(healthy, { activeSessionEnded: true }, 'both').reason, 'cloud_session_ended')
})

test('continuous microphone conversion preserves fractional boundaries', () => {
  for (const rate of [16000, 44100, 48000]) {
    const input = Float32Array.from({ length: rate }, (_, i) => Math.sin(i / 17) * .5)
    const expected = createContinuousDownsampler()(input, rate)
    const convert = createContinuousDownsampler(), result = []
    for (let i = 0; i < input.length; i += 997) result.push(...convert(input.slice(i, i + 997), rate))
    assert.deepEqual(Int16Array.from(result), expected)
    assert.equal(expected.length, 16000)
  }
})

test('combined microphone discards stale IPC backlog and resumes with fresh frames', async t => {
  let now = 1000, capture, release
  t.mock.method(Date, 'now', () => now)
  const sent = [], status = { audioEnabled: true, connectionStatus: 'connected' }
  const mic = createGrpcMicTest({ continuous: true, ownsStream: false, monotonicNow: () => now,
    getUserMedia: async () => ({}), createCapture: options => { capture = options; return { close() {} } },
    api: { getGrpcRealtimeStatus: async () => status,
      sendGrpcRealtimeAudioChunk: async (_, metadata) => {
        sent.push(metadata.captureTimestampMs)
        if (sent.length === 1) await new Promise(resolve => { release = resolve })
        return status
      } } })
  await mic.start()
  capture.onChunk(new ArrayBuffer(4))
  await new Promise(resolve => setImmediate(resolve))
  capture.onChunk(new ArrayBuffer(4))
  now = 1400; release()
  await new Promise(resolve => setImmediate(resolve))
  assert.deepEqual(sent, [1000])
  capture.onChunk(new ArrayBuffer(4))
  await new Promise(resolve => setImmediate(resolve))
  assert.deepEqual(sent, [1000, 1400])
  mic.close()
})

for (const failure of ['track', 'backend', 'capture-start']) {
  test(`combined ${failure} failure closes both sources once, suppresses late events and never falls back`, async () => {
    let event, ended = null, stopped = 0, captures = 0, closed = 0, fallback = 0, answers = 0, cleanupDone
    let added = 0, removed = 0, micClosed = 0, unsubscribed = 0
    const track = { stop() { stopped++ }, addEventListener(name, listener) {
      assert.equal(name, 'ended'); added++; ended = listener
    }, removeEventListener(name, listener) {
      assert.equal(name, 'ended'); assert.equal(listener, ended); removed++; ended = null
    } }
    const stream = { getTracks: () => [track], getAudioTracks: () => [track] }
    const status = { connectionStatus: 'connected', autoPipelineReady: true, manualRun: 1, autoEventVersion: 0,
      systemAudio: { active_audio_source: 'both' } }
    const api = { connectGrpcAutoPipeline: async () => status,
      closeGrpcRealtime: () => { closed++; return new Promise(resolve => { cleanupDone = resolve }) },
      getGrpcRealtimeStatus: async () => status, onGrpcAutoEvent: cb => { event = cb; return () => { unsubscribed++ } } }
    const session = await createGrpcAutoSession({ api, stream, source: 'both',
      createMic: options => { assert.equal(options.continuous, true); return {
        start: async () => { captures++; if (failure === 'capture-start') throw Error('synthetic') }, close() { micClosed++ } } },
      onAnswer: () => answers++, onFallback: () => fallback++ })
    // Capture startup can fail before any track listener is registered.
    assert.equal(added, failure === 'capture-start' ? 0 : 1)
    const lateEnded = ended
    if (failure === 'track') ended()
    if (failure === 'backend') event({ ...status, connectionStatus: 'disconnected', autoEventVersion: 1 })
    const cleanup = session.close()
    assert.equal(session.stop(), cleanup)
    assert.equal(closed, 1)
    cleanupDone({ systemCleanupStatus: 'clean' })
    await cleanup
    assert.equal(session.close(), cleanup)
    if (failure !== 'capture-start') lateEnded()
    event({ ...status, autoEventVersion: 2, questionsDetectedCount: 1, currentQuestion: 'stale' })
    assert.equal(captures, 1)
    assert.equal(stopped, 1)
    assert.equal(fallback, 0)
    assert.equal(answers, 0)
    assert.equal(ended, null)
    assert.equal(removed, added)
    assert.equal(micClosed, 1)
    assert.equal(unsubscribed, 1)
    assert.equal(closed, 1)
  })
}

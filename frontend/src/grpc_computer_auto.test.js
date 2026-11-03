import test from 'node:test'
import assert from 'node:assert/strict'
import vm from 'node:vm'
import { readFileSync } from 'node:fs'
import { createGrpcAutoSession, getGrpcAutoBlockReason } from './grpc_auto_session.js'
import { selectRealtimeRoute, realtimeRouteDiagnostics, AUTH_BLOCKS } from './realtime_router.js'

const app = readFileSync(new URL('./App.jsx', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const startAt = app.indexOf('  const startAutoMode =')
const source = app.slice(startAt, app.indexOf('  const stopAutoMode =', startAt))

function harness({ capability = true, selected = 'system', healthWait, getUserMedia, createMic } = {}) {
  let connects = 0, closes = 0
  const state = { enabled: true, audioEnabled: true, autoPipelineEnabled: true, grpc_health: 'healthy',
    grpc_stt_available: true, grpc_answer_available: true, grpc_auto_available: true,
    grpc_system_audio_available: capability, grpc_combined_audio_available: capability, autoPipelineReady: true, connectionStatus: 'connected',
    manualRun: 1, autoEventVersion: 0, systemAudio: { active_audio_source: selected } }
  const forbidden = () => assert.fail('Computer Auto must not acquire mic or start a legacy transport')
  const values = {}, context = { console: { error() {} }, Date, Math, Promise, Boolean, Error,
    clearTimeout, clearInterval, setTimeout, setInterval,
    autoModeStatus: 'off', getSelectedAudioSourceLabel: () => selected,
    navigator: { mediaDevices: { getUserMedia: getUserMedia || forbidden } },
    fetchSystemAudioDevices: forbidden, startAutoStreamingSystem: forbidden, startAutoStreamingMic: forbidden,
    captureSystemAutoChunk: forbidden, fetch: forbidden,
    selectRealtimeRoute, realtimeRouteDiagnostics, AUTH_BLOCKS, getGrpcAutoBlockReason,
    createGrpcAutoSession: options => createGrpcAutoSession({ ...options, ...(createMic ? { createMic } : {}) }),
    logAutoModeDebug() {}, normalizePipelineError: error => error.message,
    stopAutoStreamingBridge() {}, stopActiveStream() {}, stopAutoMode() {},
    window: { electronAPI: {
      checkGrpcRealtimeHealth: async () => { if (healthWait) await healthWait; return state },
      connectGrpcAutoPipeline: async options => { assert.equal(options.source, selected); connects++; return state },
      getGrpcRealtimeStatus: async () => state, closeGrpcRealtime: async () => { closes++; return { systemCleanupStatus: 'clean' } },
      onGrpcAutoEvent: () => () => {}, sendGrpcRealtimeAudioChunk: forbidden,
    } },
  }
  for (const name of new Set(source.match(/\b\w+Ref\b/g))) context[name] = { current: null }
  for (const name of new Set(source.match(/\bset[A-Z]\w+/g))) context[name] = value => { values[name] = value }
  for (const name of ['clearProgressiveAnswer', 'resetAnswerMeta', 'resetAutoTranscriptBuffer', 'clearPendingAutoQuestion',
    'clearPendingCooldownQuestion', 'clearCurrentAutoQuestionRun']) context[name] = () => {}
  Object.assign(context, { startupSessionConfigRef: { current: {} }, generationDiagnosticsRef: { current: {} },
    audioSourcesRef: { current: { system: true, microphone: false } } })
  const start = vm.runInNewContext(`${source}\nstartAutoMode`, context)
  return { start, context, values, counts: () => ({ connects, closes }) }
}

test('actual Computer renderer Start uses one gRPC factory with no microphone or system HTTP/WS transport', async () => {
  const f = harness()
  await f.start()
  assert.equal(f.counts().connects, 1)
  assert.equal(f.values.setError, '')
  assert.ok(f.context.autoGrpcSessionRef.current)
  await f.context.autoGrpcSessionRef.current.close()
  assert.equal(f.counts().closes, 1)
})

test('actual Computer renderer blocks missing capability and combined permission denial without alternate capture', async () => {
  for (const options of [{ capability: false }, { selected: 'both' }]) {
    const f = harness(options)
    await f.start()
    assert.equal(f.counts().connects, 0)
    assert.equal(f.context.autoGrpcSessionRef.current, null)
  }
})

test('actual combined renderer acquires one microphone and uses one gRPC factory with no legacy system transport', async () => {
  let acquired = 0, stopped = 0, captured = 0
  const stream = { getTracks: () => [{ stop() { stopped++ } }], getAudioTracks: () => [] }
  const f = harness({ selected: 'both', getUserMedia: async () => { acquired++; return stream },
    createMic: options => { assert.equal(options.continuous, true); return { start: async () => { captured++ }, close() {} } } })
  await f.start()
  assert.equal(acquired, 1)
  assert.equal(captured, 1)
  assert.equal(f.counts().connects, 1)
  assert.equal(f.values.setError, '')
  await f.context.autoGrpcSessionRef.current.close()
  assert.equal(stopped, 1)
})

test('Stop during combined permission wait releases late tracks without opening gRPC', { timeout: 1000 }, async () => {
  let resolve, stopped = 0
  let permissionStarted
  const permissionRequested = new Promise(done => { permissionStarted = done })
  const f = harness({ selected: 'both', getUserMedia: () => new Promise(done => {
    resolve = done
    permissionStarted()
  }) })
  const pending = f.start()
  // Startup awaits status before requesting permission. Stop only once that
  // actual request is pending, rather than assuming it starts synchronously.
  await permissionRequested
  f.context.autoStartTokenRef.current++
  resolve({ getTracks: () => [{ stop() { stopped++ } }] })
  await pending
  assert.equal(stopped, 1)
  assert.equal(f.counts().connects, 0)
  assert.equal(f.context.streamRef.current, null)
  assert.equal(f.context.autoGrpcSessionRef.current, null)
})

test('Stop while Computer health is pending suppresses late startup', async () => {
  let resolve
  const f = harness({ healthWait: new Promise(done => { resolve = done }) })
  const pending = f.start()
  f.context.autoStartTokenRef.current++
  f.context.autoModeRef.current = false
  f.context.autoModeRunIdRef.current = ''
  resolve()
  await pending
  assert.equal(f.counts().connects, 0)
})

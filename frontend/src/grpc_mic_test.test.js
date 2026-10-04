import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { createGrpcMicTest } from './grpc_mic_test.js'
import { createPcmMicCapture, downsampleToInt16Mono } from './live_mic_transport.js'

function fixture(status = { audioEnabled: true, connectionStatus: 'connected' }) {
  let captured, captures = 0, stopped = 0, closed = 0, stops = 0
  const sent = []
  const stream = { getTracks: () => [{ stop: () => stopped++ }] }
  const api = { getGrpcRealtimeStatus: async () => status,
    sendGrpcRealtimeAudioChunk: async (data) => { sent.push(data); return status },
    stopGrpcRealtimeAudio: async () => { stops++; return status } }
  const mic = createGrpcMicTest({ api, getUserMedia: async () => { captures++; return stream },
    createCapture: (options) => { captured = options; return { close: () => closed++ } } })
  return { mic, api, sent, capture: () => captured, counts: () => ({ captures, stopped, closed, stops }) }
}
const flush = () => new Promise(resolve => setImmediate(resolve))

test('diagnostic mic needs audio flag and established connection before requesting permission', async () => {
  for (const status of [{ audioEnabled: false, connectionStatus: 'connected' }, { audioEnabled: true, connectionStatus: 'error' }]) {
    const f = fixture(status)
    await assert.rejects(f.mic.start(), /unavailable/)
    assert.equal(f.counts().captures, 0)
  }
})

test('diagnostic PCM sends bounded IPC and stop releases capture and tracks', async () => {
  const f = fixture()
  await f.mic.start()
  f.capture().onChunk(new ArrayBuffer(4))
  assert.equal(f.capture().isActive(), false)
  await flush()
  assert.equal(f.sent.length, 1)
  assert.equal(f.capture().isActive(), true)
  await f.mic.stop()
  assert.deepEqual(f.counts(), { captures: 1, stopped: 1, closed: 1, stops: 1 })
  assert.equal(f.capture().isActive(), false)
})

test('backend disconnect during audio acknowledgement stops the microphone safely', async () => {
  const f = fixture()
  f.api.sendGrpcRealtimeAudioChunk = async () => { throw Error('private detail') }
  await f.mic.start()
  f.capture().onChunk(new ArrayBuffer(4))
  await flush()
  assert.equal(f.counts().stopped, 1)
  assert.equal(f.counts().closed, 1)
})

test('canceling pending microphone permission releases late tracks without capture', async () => {
  let resolve, stopped = 0
  const mic = createGrpcMicTest({ api: { getGrpcRealtimeStatus: async () => ({ audioEnabled: true, connectionStatus: 'connected' }) },
    getUserMedia: () => new Promise(done => { resolve = done }), createCapture: () => { throw Error('must not capture') } })
  const pending = mic.start()
  await flush()
  mic.close()
  resolve({ getTracks: () => [{ stop: () => stopped++ }] })
  await pending
  assert.equal(stopped, 1)
})

test('shared capture converts floats to mono PCM and cleans Web Audio resources', () => {
  let processor, contextClosed = 0, disconnected = 0
  const node = { connect() {}, disconnect() { disconnected++ } }
  class Context {
    sampleRate = 48000
    createMediaStreamSource() { return node }
    createScriptProcessor() { processor = { ...node }; return processor }
    close() { contextClosed++; return Promise.resolve() }
  }
  const sent = []
  const capture = createPcmMicCapture({ stream: {}, isActive: () => true, AudioContextClass: Context, onChunk: x => sent.push(x) })
  processor.onaudioprocess({ inputBuffer: { getChannelData: () => new Float32Array([1,1,1,-1,-1,-1]) } })
  assert.deepEqual([...new Int16Array(sent[0])], [32767, -32768])
  assert.equal(downsampleToInt16Mono(new Float32Array(0), 48000).length, 0)
  capture.close(); capture.close()
  assert.equal(contextClosed, 1)
  assert.equal(disconnected, 2)
  assert.equal(processor.onaudioprocess, null)
  const source = readFileSync(new URL('./components/MainDiagnosticsWindow.jsx', import.meta.url), 'utf8')
  for (const field of ['audioEnabled', 'audioChunksSent', 'audioBytesSent', 'backendChunksReceived', 'backendBytesReceived', 'lastAudioStatus']) assert.ok(source.includes(`state.${field}`))
})

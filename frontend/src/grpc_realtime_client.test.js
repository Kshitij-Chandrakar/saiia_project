import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { EventEmitter } from 'node:events'
import { readFileSync } from 'node:fs'
const require = createRequire(import.meta.url)
const { GrpcRealtimeClient, registerGrpcRealtimeIpc } = require('../electron/grpc_realtime_client.cjs')

function fixture(env = {}, failure = false) {
  const stream = new EventEmitter(), writes = []
  let calls = 0, canceled = 0, closed = 0
  stream.write = (event) => {
    writes.push(event)
    const kind = event.start_session ? 'ready' : event.ping ? 'pong' : 'status'
    queueMicrotask(() => stream.emit('data', { request_id: event.request_id, [kind]: kind === 'status' ? { code: event.audio_chunk ? 'audio_chunk_received' : 'audio_stopped', total_chunks: writes.filter(x => x.audio_chunk).length, total_audio_bytes: writes.filter(x => x.audio_chunk).reduce((n,x) => n + x.audio_chunk.audio.length, 0) } : {} }))
  }
  stream.cancel = () => { canceled++ }
  const client = new GrpcRealtimeClient({ env, timeoutMs: 30, transportFactory: () => {
    calls++
    return { waitForReady: (_, fn) => queueMicrotask(() => fn(failure ? Error('token private transcript audio secret') : null)),
      StreamInterview: () => stream, close: () => { closed++ } }
  } })
  return { client, stream, writes, counts: () => ({ calls, canceled, closed }) }
}
const enabled = { ELECTRON_GRPC_REALTIME_ENABLED: 'true' }

test('disabled gRPC never loads transport or connects', async () => {
  const f = fixture()
  await f.client.connect(); await f.client.ping()
  assert.equal(f.counts().calls, 0)
  assert.equal(f.client.getStatus().connectionStatus, 'disabled')
})

test('enabled loopback client handshakes, pings, and closes resources', async () => {
  const f = fixture(enabled)
  await Promise.all([f.client.connect(), f.client.connect()])
  assert.equal(f.counts().calls, 1)
  assert.equal(f.client.getStatus().connectionStatus, 'connected')
  assert.equal((await f.client.ping()).lastPingResult, 'pong')
  assert.deepEqual(Object.keys(f.client.getStatus()).sort(), ['audioBytesSent', 'audioChunksSent', 'audioEnabled', 'backendBytesReceived', 'backendChunksReceived', 'connectionStatus', 'currentTranscript', 'enabled', 'finalTranscriptCount', 'lastAudioStatus', 'lastErrorMessage', 'lastPingResult', 'lastTranscriptEventType', 'partialTranscriptCount', 'pcmDiagnostics', 'sttBridgeConnected', 'sttBytesForwarded', 'sttCallbackCount', 'sttChunksForwarded', 'sttEnabled', 'sttProvider', 'sttStatus', 'nonSilentChunks', 'answerStreamEnabled', 'questionsDetectedCount', 'answerStartedCount', 'answerDeltaCount', 'answerCompletedCount', 'lastAnswerStatus', 'answerCategory', 'answerProvider', 'currentQuestion', 'currentAnswer'].sort())
  await f.client.endSession()
  assert.deepEqual(f.counts(), { calls: 1, canceled: 1, closed: 1 })
  assert.equal(f.client.pending.size, 0)
  await f.client.connect()
  await f.client.cancel()
  assert.equal(f.client.getStatus().connectionStatus, 'disconnected')
})

test('non-loopback and invalid port are rejected before transport construction', async () => {
  for (const host of ['0.0.0.0', 'example.test', '127.0.0.1.example.test']) {
    const f = fixture({ ...enabled, ELECTRON_GRPC_REALTIME_HOST: host })
    assert.equal((await f.client.connect()).connectionStatus, 'error')
    assert.equal(f.counts().calls, 0)
  }
  const f = fixture({ ...enabled, ELECTRON_GRPC_REALTIME_PORT: 'invalid' })
  await f.client.connect()
  assert.equal(f.counts().calls, 0)
})

test('closing during a pending ping clears the timer without restoring stale error state', async () => {
  const f = fixture(enabled)
  await f.client.connect()
  f.stream.write = () => {}
  const pendingPing = f.client.ping()
  assert.equal(f.client.pending.size, 1)
  f.client.close()
  await pendingPing
  assert.equal(f.client.pending.size, 0)
  assert.equal(f.client.getStatus().connectionStatus, 'disconnected')
  assert.equal(f.client.getStatus().lastErrorMessage, '')
})

test('audio needs both flags and connection; validated PCM counts and manual stop work', async () => {
  const disabled = fixture(enabled)
  await disabled.client.connect()
  await disabled.client.sendAudioChunk(new Uint8Array(4))
  assert.equal(disabled.writes.filter(e => e.audio_chunk).length, 0)
  disabled.client.close()
  const f = fixture({ ...enabled, ELECTRON_GRPC_AUDIO_ENABLED: 'true' })
  await f.client.sendAudioChunk(new Uint8Array(4))
  assert.equal(f.writes.length, 0)
  await f.client.connect()
  await f.client.sendAudioChunk(new Uint8Array(65538))
  await f.client.sendAudioChunk('private text')
  assert.equal(f.writes.filter(e => e.audio_chunk).length, 0)
  const result = await f.client.sendAudioChunk(new Uint8Array(4))
  assert.equal(result.audioChunksSent, 1)
  assert.equal(result.audioBytesSent, 4)
  assert.equal(result.backendChunksReceived, 1)
  assert.equal(result.backendBytesReceived, 4)
  await f.client.manualStop()
  assert.ok(f.writes.at(-1).manual_stop)
  assert.equal(f.client.getStatus().lastAudioStatus, 'audio_stopped')
  f.client.close()
})

test('connection errors never expose upstream secrets and late stream errors stay safe', async () => {
  const f = fixture(enabled, true)
  const state = await f.client.connect()
  assert.equal(state.connectionStatus, 'error')
  assert.doesNotMatch(state.lastErrorMessage, /token|transcript|audio|secret/)
  assert.equal(f.counts().closed, 1)
  const live = fixture(enabled)
  await live.client.connect()
  live.stream.emit('error', Error('private token'))
  assert.equal(live.client.getStatus().connectionStatus, 'error')
  assert.doesNotMatch(JSON.stringify(live.client.getStatus()), /private token/)
})

test('diagnostics IPC validates sender and exposes only four narrow methods', async () => {
  const handlers = new Map(), f = fixture()
  registerGrpcRealtimeIpc({ handle: (name, fn) => handlers.set(name, fn) }, (event) => { if (!event.trusted) throw Error('untrusted') }, f.client)
  assert.deepEqual([...handlers.keys()], ['grpcRealtime:getStatus', 'grpcRealtime:connect', 'grpcRealtime:ping', 'grpcRealtime:close', 'grpcRealtime:audioChunk', 'grpcRealtime:manualStop'])
  await assert.rejects(handlers.get('grpcRealtime:connect')({ trusted: false }))
  const status = await handlers.get('grpcRealtime:getStatus')({ trusted: true })
  assert.deepEqual(status, f.client.getStatus())
  assert.equal(f.counts().calls, 0)
})

test('packaged proto matches backend source of truth and preload exposes no arbitrary send', () => {
  assert.equal(readFileSync(new URL('../electron/protos/interview_realtime.proto', import.meta.url), 'utf8'),
    readFileSync(new URL('../../backend/protos/interview_realtime.proto', import.meta.url), 'utf8'))
  const preload = readFileSync(new URL('../electron/preload.cjs', import.meta.url), 'utf8')
  for (const channel of ['getStatus', 'connect', 'ping', 'close']) assert.ok(preload.includes(`grpcRealtime:${channel}`))
  assert.equal(preload.includes('grpcRealtime:send'), false)
})

test('STT events update current preview and counts without answer generation', async () => {
  const f = fixture(enabled)
  await f.client.connect()
  f.stream.emit('data', { provider: 'assemblyai_streaming', status: { code: 'stt_enabled' } })
  assert.equal(f.client.getStatus().sttProvider, 'assemblyai_streaming')
  f.stream.emit('data', { provider: 'assemblyai_streaming', partial_transcript: { text: 'private preview' } })
  assert.equal(f.client.getStatus().partialTranscriptCount, 1)
  assert.equal(f.client.getStatus().currentTranscript, 'private preview')
  f.stream.emit('data', { provider: 'assemblyai_streaming', final_transcript: { text: 'final preview' } })
  const state = f.client.getStatus()
  assert.equal(state.finalTranscriptCount, 1)
  assert.equal(state.lastTranscriptEventType, 'final_transcript')
  assert.equal(state.sttEnabled, true)
  assert.equal(state.sttProvider, 'assemblyai_streaming')
  assert.equal(f.writes.length, 1)
  f.client.close()
  assert.equal(f.client.getStatus().currentTranscript, '')
})

test('provider failure before transcripts exposes only a safe diagnostic error', async () => {
  const f = fixture(enabled)
  await f.client.connect()
  f.stream.emit('data', { provider: 'assemblyai_streaming', error: { code: 'stt_unavailable', message: 'private token transcript audio' } })
  assert.equal(f.client.getStatus().connectionStatus, 'error')
  assert.equal(f.client.getStatus().sttProvider, 'assemblyai_streaming')
  assert.match(f.client.getStatus().lastErrorMessage, /AssemblyAI configuration/)
  assert.doesNotMatch(JSON.stringify(f.client.getStatus()), /private token/)
})

test('forwarding telemetry updates independently of transcript events', async () => {
  const f = fixture(enabled)
  await f.client.connect()
  f.stream.emit('data', { provider: 'assemblyai_streaming', status: { stt_chunks_forwarded: '50', stt_bytes_forwarded: '160000', stt_callback_count: '1', non_silent_chunks: '0', stt_bridge_connected: true, stt_status: 'stt_no_transcript_yet' } })
  const status = f.client.getStatus()
  assert.equal(status.sttChunksForwarded, 50)
  assert.equal(status.sttBytesForwarded, 160000)
  assert.equal(status.sttCallbackCount, 1)
  assert.equal(status.sttBridgeConnected, true)
  assert.equal(status.sttStatus, 'stt_no_transcript_yet')
  assert.equal(status.nonSilentChunks, 0)
  f.client.close()
})

test('G4 signed little-endian numeric levels detect silence, clipping, and invalid PCM', async () => {
  const f = fixture({ ...enabled, ELECTRON_GRPC_AUDIO_ENABLED: 'true' })
  await f.client.connect()
  f.client.sttEnabled = true
  await f.client.sendAudioChunk(new Uint8Array(3))
  assert.equal(f.client.getStatus().sttStatus, 'invalid_pcm_format')
  await f.client.sendAudioChunk(new Uint8Array(3200), { inputSampleRate: 16000, inputChannelCount: 1 })
  let d = f.client.getStatus().pcmDiagnostics
  assert.equal(d.rms, 0)
  assert.equal(d.zeroRatio, 1)
  assert.equal(d.durationMs, 100)
  assert.equal(d.backendEvenByteLength, true)
  assert.equal(f.client.getStatus().sttStatus, 'mic_audio_too_low')
  const pcm = new Uint8Array([0, 128, 0, 0, 255, 127])
  await f.client.sendAudioChunk(pcm)
  d = f.client.getStatus().pcmDiagnostics
  assert.equal(d.min, -32768)
  assert.equal(d.max, 32767)
  assert.equal(d.peak, 1)
  assert.ok(d.rms > 0.8)
  assert.equal(d.clippedRatio, 2 / 3)
  assert.equal(d.zeroRatio, 1 / 3)
  f.client.close()
})

test('G5 deltas update experimental preview before completion without production routing', async () => {
  const f = fixture(enabled)
  await f.client.connect()
  f.stream.emit('data', { status: { code: 'answer_stream_enabled' } })
  f.stream.emit('data', { question_detected: { text: 'Explain FastAPI?', category: 'technical' } })
  f.stream.emit('data', { answer_started: { provider: 'openai' } })
  f.stream.emit('data', { answer_delta: { text: 'First ' } })
  let s = f.client.getStatus()
  assert.equal(s.currentAnswer, 'First ')
  assert.equal(s.answerCompletedCount, 0)
  f.stream.emit('data', { answer_delta: { text: 'answer.' } })
  f.stream.emit('data', { answer_completed: { text: 'Final grounded answer.' } })
  s = f.client.getStatus()
  assert.equal(s.answerStreamEnabled, true)
  assert.equal(s.questionsDetectedCount, 1)
  assert.equal(s.answerStartedCount, 1)
  assert.equal(s.answerDeltaCount, 2)
  assert.equal(s.answerCompletedCount, 1)
  assert.equal(s.currentAnswer, 'Final grounded answer.')
  f.stream.emit('data', { answer_error: { message: 'secret token prompt' } })
  assert.equal(f.client.getStatus().connectionStatus, 'connected')
  assert.equal(f.client.getStatus().lastAnswerStatus, 'answer_error')
  assert.doesNotMatch(f.client.getStatus().lastErrorMessage, /secret|token|prompt/)
  f.client.close()
  assert.equal(f.client.getStatus().currentAnswer, '')
})

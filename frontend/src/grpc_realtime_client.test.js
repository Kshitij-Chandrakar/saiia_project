import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { EventEmitter } from 'node:events'
import { readFileSync } from 'node:fs'
const require = createRequire(import.meta.url)
const { GrpcRealtimeClient, registerGrpcRealtimeIpc } = require('../electron/grpc_realtime_client.cjs')

function fixture(env = {}, failure = false, getCloudAuthorization) {
  const stream = new EventEmitter(), writes = []
  let calls = 0, canceled = 0, closed = 0
  const metadata = []
  stream.write = (event) => {
    writes.push(event)
    const kind = event.start_session ? 'ready' : event.ping ? 'pong' : 'status'
    queueMicrotask(() => stream.emit('data', { request_id: event.request_id, [kind]: kind === 'status' ? { code: event.audio_chunk ? 'audio_chunk_received' : 'audio_stopped', total_chunks: writes.filter(x => x.audio_chunk).length, total_audio_bytes: writes.filter(x => x.audio_chunk).reduce((n,x) => n + x.audio_chunk.audio.length, 0) } : {} }))
  }
  stream.cancel = () => { canceled++ }
  const client = new GrpcRealtimeClient({ env, getCloudAuthorization, timeoutMs: 30, transportFactory: () => {
    calls++
    return { waitForReady: (_, fn) => queueMicrotask(() => fn(failure ? Error('token private transcript audio secret') : null)),
      StreamInterview: value => { metadata.push(value); return stream }, close: () => { closed++ } }
  } })
  return { client, stream, writes, metadata, counts: () => ({ calls, canceled, closed }) }
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
  assert.deepEqual(Object.keys(f.client.getStatus()).sort(), ['systemAudio', 'systemAudioPipelineSupported', 'questionIntake', 'cloudAuthAvailable', 'cloudContextPipelineEnabled', 'cloudAuthStatus', 'cloudSessionVerified', 'cloudContextLoaded', 'cloudAnswerSaveStatus', 'cloudBlockedReason', 'autoPipelineEnabled', 'autoPipelineReady', 'autoStatus', 'autoEventVersion', 'manualEventVersion', 'manualRun', 'manualTimings', 'manualPipelineEnabled', 'manualPipelineReady', 'manualStatus', 'audioBytesSent', 'audioChunksSent', 'audioEnabled', 'backendBytesReceived', 'backendChunksReceived', 'connectionStatus', 'currentTranscript', 'enabled', 'finalTranscriptCount', 'lastAudioStatus', 'lastErrorMessage', 'lastPingResult', 'lastTranscriptEventType', 'partialTranscriptCount', 'pcmDiagnostics', 'sttBridgeConnected', 'sttBytesForwarded', 'sttCallbackCount', 'sttChunksForwarded', 'sttEnabled', 'sttProvider', 'sttStatus', 'nonSilentChunks', 'answerStreamEnabled', 'questionsDetectedCount', 'answerStartedCount', 'answerDeltaCount', 'answerCompletedCount', 'lastAnswerStatus', 'answerCategory', 'answerProvider', 'currentQuestion', 'currentAnswer'].sort())
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
  assert.deepEqual([...handlers.keys()], ['grpcRealtime:getStatus', 'grpcRealtime:connect', 'grpcRealtime:connectManual', 'grpcRealtime:connectAuto', 'grpcRealtime:ping', 'grpcRealtime:close', 'grpcRealtime:uiTiming', 'grpcRealtime:audioChunk', 'grpcRealtime:manualStop'])
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
  assert.equal(f.client.getStatus().questionIntake.low_audio_warning, true)
  assert.equal(f.client.getStatus().questionIntake.mic_rms_level, 0)
  assert.equal(f.client.getStatus().questionIntake.mic_peak_level, 0)
  const pcm = new Uint8Array([0, 128, 0, 0, 255, 127])
  await f.client.sendAudioChunk(pcm)
  d = f.client.getStatus().pcmDiagnostics
  assert.equal(d.min, -32768)
  assert.equal(d.max, 32767)
  assert.equal(d.peak, 1)
  assert.equal(f.client.getStatus().questionIntake.mic_peak_level, 1)
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


test('G6 main flag fails closed and manual handshake uses a fresh explicitly acknowledged stream', async () => {
  const disabled = fixture({ ...enabled, ELECTRON_GRPC_AUDIO_ENABLED: 'true' })
  await disabled.client.connectManual()
  assert.equal(disabled.counts().calls, 0)
  const f = fixture({ ...enabled, ELECTRON_GRPC_AUDIO_ENABLED: 'true', USE_GRPC_MANUAL_PIPELINE: 'true' })
  await f.client.connect()
  await f.client.connectManual()
  assert.equal(f.writes.at(-1).start_session.mode, 'manual_pipeline')
  assert.equal(f.counts().canceled, 1)
  assert.equal(f.client.getStatus().manualPipelineReady, false)
  f.stream.emit('data', { status: { code: 'manual_pipeline_ready' } })
  assert.equal(f.client.getStatus().manualPipelineReady, true)
  f.client.close()
})


test('manual timing IPC is numeric-only, sender-validated, run-scoped and first-update-only', async () => {
  const f = fixture({ ...enabled, ELECTRON_GRPC_AUDIO_ENABLED: 'true', USE_GRPC_MANUAL_PIPELINE: 'true' })
  await f.client.connectManual()
  const handlers = new Map(), updates = []
  registerGrpcRealtimeIpc({ handle: (name, fn) => handlers.set(name, fn) }, event => {
    if (!event.trusted) throw Error('untrusted')
  }, f.client, timing => updates.push(timing))
  const report = handlers.get('grpcRealtime:uiTiming'), run = f.client.getStatus().manualRun
  const at = Date.now()
  await assert.rejects(report({ trusted: false }, run, 'first_main_ui_update_at', at))
  for (const [r, field, value] of [[run + 1, 'first_main_ui_update_at', at], [run, 'private_token', at], [run, 'first_main_ui_update_at', 'private'], [run, 'first_main_ui_update_at', at + 10000]]) {
    await report({ trusted: true }, r, field, value)
  }
  assert.equal(updates.length, 0)
  await report({ trusted: true }, run, 'first_main_ui_update_at', at)
  await report({ trusted: true }, run, 'first_main_ui_update_at', at + 1)
  assert.equal(updates.length, 1)
  assert.equal(updates[0].first_main_ui_update_at, at)
  assert.equal(f.client.getStatus().manualTimings.first_main_ui_update_at, at)
  f.client.close()
})


test('manual answer events are pushed immediately through the narrow bridge without raw provider fields', async () => {
  const f = fixture({ ...enabled, ELECTRON_GRPC_AUDIO_ENABLED: 'true', USE_GRPC_MANUAL_PIPELINE: 'true' })
  const pushed = []
  registerGrpcRealtimeIpc({ handle() {} }, () => {}, f.client, undefined, snapshot => pushed.push(snapshot))
  await f.client.connectManual()
  f.stream.emit('data', { question_detected: { text: 'Question' }, private_header: 'secret-key' })
  f.stream.emit('data', { answer_delta: { text: 'First' }, token: 'secret-token' })
  assert.equal(pushed.length, 2)
  assert.equal(pushed[1].currentAnswer, 'First')
  assert.equal(pushed[1].lastAnswerStatus, 'answer_delta')
  assert.equal(pushed[1].manualEventVersion, 2)
  assert.equal(typeof pushed[1].manualTimings.first_answer_delta_at, 'number')
  assert.equal(JSON.stringify(pushed).includes('secret-'), false)
  f.stream.emit('data', { answer_completed: { text: 'Final' } })
  assert.equal(pushed.length, 3)
  assert.equal(pushed[1].currentAnswer, 'First')
  assert.equal(pushed[2].currentAnswer, 'Final')
  f.client.close()
})

test('diagnostic answer events keep existing counters/preview without enabling manual push', async () => {
  const f = fixture({ ...enabled, USE_GRPC_MANUAL_PIPELINE: 'true' })
  let pushes = 0
  f.client.onManualEvent = () => pushes++
  await f.client.connect()
  f.stream.emit('data', { question_detected: { text: 'Question' } })
  f.stream.emit('data', { answer_delta: { text: 'Diagnostic preview' } })
  assert.equal(pushes, 0)
  assert.equal(f.client.getStatus().answerDeltaCount, 1)
  assert.equal(f.client.getStatus().currentAnswer, 'Diagnostic preview')
  f.client.close()
})


test('G7 Auto flag is independent, fresh handshake streams safe snapshots and PCM until closed', async () => {
  const disabled = fixture({ ...enabled, ELECTRON_GRPC_AUDIO_ENABLED: 'true' })
  await disabled.client.connectAuto()
  assert.equal(disabled.counts().calls, 0)
  const f = fixture({ ...enabled, ELECTRON_GRPC_AUDIO_ENABLED: 'true', USE_GRPC_AUTO_PIPELINE: 'true' })
  const write = f.stream.write
  f.stream.write = event => {
    if (event.start_session) f.stream.emit('data', { status: { code: 'auto_pipeline_ready' } })
    write(event)
  }
  const snapshots = []
  f.client.onAutoEvent = snapshot => snapshots.push(snapshot)
  const state = await f.client.connectAuto()
  assert.equal(state.autoPipelineReady, true)
  assert.equal(f.writes[0].start_session.mode, 'auto_pipeline')
  await f.client.sendAudioChunk(new Int16Array(1600).buffer)
  f.stream.emit('data', { question_detected: { text: 'Explain REST APIs' } })
  f.stream.emit('data', { answer_delta: { text: 'First delta' }, secret: 'private key' })
  assert.equal(snapshots.at(-1).currentAnswer, 'First delta')
  assert.equal(snapshots.at(-1).answerCompletedCount, 0)
  assert.doesNotMatch(JSON.stringify(snapshots), /private key|sessionId|request_id/)
  f.stream.emit('data', { answer_completed: { text: 'First delta complete' } })
  assert.equal(f.client.getStatus().connectionStatus, 'connected')
  f.client.close()
  assert.equal(f.client.getStatus().autoPipelineReady, false)
})

test('G8 attaches main-owned metadata only to cloud Auto, with no token in status', async () => {
  const f = fixture({ ...enabled, ELECTRON_GRPC_AUDIO_ENABLED: 'true', USE_GRPC_AUTO_PIPELINE: 'true', USE_GRPC_CLOUD_CONTEXT_PIPELINE: 'true' }, false,
    async () => ({ authorization: 'Bearer mock-private-token', isCurrent: () => true }))
  await f.client.connectAuto({ activeSessionId: '11111111-1111-4111-8111-111111111111', source: 'microphone' })
  assert.deepEqual(f.metadata[0].get('authorization'), ['Bearer mock-private-token'])
  assert.equal(f.writes[0].start_session.cloud_context_requested, true)
  for (const code of ['auth_verified', 'cloud_session_verified', 'cloud_context_loaded', 'answer_saved']) f.stream.emit('data', { status: { code } })
  const status = f.client.getStatus()
  assert.equal(status.cloudAuthStatus, 'verified')
  assert.equal(status.cloudSessionVerified, true)
  assert.equal(status.cloudContextLoaded, true)
  assert.equal(status.cloudAnswerSaveStatus, 'saved')
  assert.doesNotMatch(JSON.stringify(status), /mock-private-token|authorization|Bearer/)
  f.stream.emit('data', { error: { code: 'cloud_session_invalid' } })
  assert.equal(f.client.getStatus().cloudSessionVerified, false)
  assert.equal(f.client.getStatus().cloudContextLoaded, false)
  assert.equal(f.client.getStatus().cloudBlockedReason, 'cloud_session_invalid')
  f.client.close()
})
test('G8 flag off and unavailable auth cannot create a cloud stream', async () => {
  const args = { activeSessionId: '11111111-1111-4111-8111-111111111111', source: 'microphone' }
  const off = fixture({ ...enabled, ELECTRON_GRPC_AUDIO_ENABLED: 'true', USE_GRPC_AUTO_PIPELINE: 'true' })
  assert.equal((await off.client.connectAuto(args)).cloudBlockedReason, 'cloud_context_flag_disabled')
  assert.equal(off.counts().calls, 0)
  const missing = fixture({ ...enabled, ELECTRON_GRPC_AUDIO_ENABLED: 'true', USE_GRPC_AUTO_PIPELINE: 'true', USE_GRPC_CLOUD_CONTEXT_PIPELINE: 'true' })
  const result = await missing.client.connectAuto(args)
  assert.equal(result.cloudAuthStatus, 'failed')
  assert.equal(result.cloudBlockedReason, 'auth_unavailable')
  assert.equal(missing.metadata.length, 0)
  await assert.rejects(missing.client.connectAuto({ ...args, token: 'untrusted' }), /invalid context/)
})
test('G8 expired or switched main auth cancels cloud audio forwarding', async () => {
  let current = true
  const f = fixture({ ...enabled, ELECTRON_GRPC_AUDIO_ENABLED: 'true', USE_GRPC_AUTO_PIPELINE: 'true', USE_GRPC_CLOUD_CONTEXT_PIPELINE: 'true' }, false,
    async () => ({ authorization: 'Bearer mock', isCurrent: () => current }))
  await f.client.connectAuto({ activeSessionId: '11111111-1111-4111-8111-111111111111' })
  f.client.audioChunksSent = 1 // Backend may already have committed a question.
  current = false
  await f.client.sendAudioChunk(new Uint8Array([1, 0]))
  assert.equal(f.writes.filter(value => value.audio_chunk).length, 0)
  assert.equal(f.client.getStatus().cloudBlockedReason, 'auth_unavailable')
  assert.equal(f.counts().closed, 1)
})

test('trusted G8 authorization refuses signing-in and preserves current-account guard', async () => {
  const { DesktopAuthSessionManager } = require('../electron/desktop_auth_session.cjs')
  const method = DesktopAuthSessionManager.prototype.getGrpcCloudAuthorization
  await assert.rejects(method.call({ status: 'signing-in', session: { access_token: 'private' } }), /auth_unavailable/)
  const account = { status: 'connected', session: { access_token: 'private' }, user: { user_id: 'owner' },
    _hasFreshVerification: () => true }
  const auth = await method.call(account)
  assert.equal(auth.isCurrent(), true)
  account.user.user_id = 'changed-owner'
  assert.equal(auth.isCurrent(), false)
})

test('Auto intake counters and bounded last rejection reach renderer without affecting save state', async () => {
  const f = fixture(enabled)
  await f.client.connect()
  f.stream.emit('data', { status: { code: 'question_intake', question_intake: {
    final_transcripts_received: '4', final_transcripts_ignored: '1', last_ignored_reason: 'duplicate',
    detection_attempts: '4', pending_question: true,
  } } })
  assert.equal(f.client.getStatus().questionIntake.last_ignored_reason, 'duplicate')
  assert.equal(f.client.getStatus().questionIntake.pending_question, true)
  assert.equal(f.client.getStatus().cloudAnswerSaveStatus, 'n/a')
  f.client.close()
})

test('system timing and quality status reaches diagnostics without mic data or credentials', async () => {
  const f = fixture(enabled)
  await f.client.connect()
  f.stream.emit('data', { status: { system_audio: { system_chunk_bytes: 3200, system_pcm_duration_ms: 100,
    system_rms: .1, system_first_pcm_chunk_at: 1000, active_audio_source: 'system' }, total_chunks: '3', total_audio_bytes: '9600' } })
  assert.equal(f.client.getStatus().systemAudio.system_chunk_bytes, 3200)
  assert.equal(f.client.getStatus().backendChunksReceived, 3)
  assert.equal(f.client.getStatus().audioChunksSent, 0)
  assert.doesNotMatch(JSON.stringify(f.client.getStatus()), /Bearer|access_token|refresh_token/)
  f.client.close()
})

test('routine reverification retains main-only cloud authorization until token, user or connection changes', async () => {
  const { DesktopAuthSessionManager, AUTH_STATUSES } = require('../electron/desktop_auth_session.cjs')
  const manager = Object.create(DesktopAuthSessionManager.prototype)
  manager.status = AUTH_STATUSES.CONNECTED
  manager.session = { access_token: 'mock-private' }; manager.user = { user_id: 'owner' }
  manager._hasFreshVerification = () => true
  const auth = await manager.getGrpcCloudAuthorization()
  manager.session_generation = 999
  assert.equal(auth.isCurrent(), true)
  manager.session.access_token = 'changed'; assert.equal(auth.isCurrent(), false)
  manager.session.access_token = 'mock-private'; manager.user.user_id = 'other'; assert.equal(auth.isCurrent(), false)
  manager.user.user_id = 'owner'; manager.status = AUTH_STATUSES.SIGNED_OUT; assert.equal(auth.isCurrent(), false)
})
test('stale or missing authorization closes connecting transport safely', async () => {
  for (const auth of [undefined, { isCurrent: () => false }]) {
    const f = fixture({ ...enabled, ELECTRON_GRPC_AUDIO_ENABLED: 'true', USE_GRPC_AUTO_PIPELINE: 'true', USE_GRPC_CLOUD_CONTEXT_PIPELINE: 'true' }, false, async () => auth)
    const result = await f.client.connectAuto({ activeSessionId: '11111111-1111-4111-8111-111111111111' })
    assert.equal(result.connectionStatus, 'error'); assert.equal(result.cloudAuthStatus, 'failed')
    assert.equal(result.cloudBlockedReason, 'auth_unavailable'); assert.equal(f.counts().closed, 1)
    assert.equal(f.metadata.length, 0)
  }
})
test('non-auth provider error preserves verified cloud diagnostics', async () => {
  const f = fixture({ ...enabled, ELECTRON_GRPC_AUDIO_ENABLED: 'true', USE_GRPC_AUTO_PIPELINE: 'true', USE_GRPC_CLOUD_CONTEXT_PIPELINE: 'true' }, false, async () => ({ authorization: 'Bearer mock', isCurrent: () => true }))
  await f.client.connectAuto({ activeSessionId: '11111111-1111-4111-8111-111111111111' })
  for (const code of ['auth_verified', 'cloud_session_verified', 'cloud_context_loaded']) f.stream.emit('data', { status: { code } })
  f.stream.emit('data', { error: { code: 'stt_unavailable' } })
  const status = f.client.getStatus()
  assert.equal(status.cloudAuthStatus, 'verified'); assert.equal(status.cloudSessionVerified, true)
  assert.equal(status.cloudContextLoaded, true); assert.equal(status.cloudBlockedReason, 'none')
  f.client.close()
})
test('visible Auto status uses safe separators', () => {
  const app = readFileSync(new URL('./App.jsx', import.meta.url), 'utf8')
  const diagnostics = readFileSync(new URL('./components/MainDiagnosticsWindow.jsx', import.meta.url), 'utf8')
  assert.ok(app.includes('Auto Mode - gRPC realtime -'))
  assert.ok(!diagnostics.includes('16000 Hz ? mono ?'))
  assert.ok(!diagnostics.includes('Auto gRPC ? local test session'))
})

test('server unavailable before authorization is a transport failure', async () => {
  const f = fixture({ ...enabled, ELECTRON_GRPC_AUDIO_ENABLED: 'true', USE_GRPC_AUTO_PIPELINE: 'true', USE_GRPC_CLOUD_CONTEXT_PIPELINE: 'true' }, true)
  const result = await f.client.connectAuto({ activeSessionId: '11111111-1111-4111-8111-111111111111' })
  assert.equal(result.connectionStatus, 'error')
  assert.notEqual(result.cloudAuthStatus, 'failed')
  assert.equal(result.cloudBlockedReason, 'none')
})
test('stale metadata fails before first audio without hidden reconnect', async () => {
  let first = true
  const f = fixture({ ...enabled, ELECTRON_GRPC_AUDIO_ENABLED: 'true', USE_GRPC_AUTO_PIPELINE: 'true', USE_GRPC_CLOUD_CONTEXT_PIPELINE: 'true' }, false,
    async () => ({ authorization: 'Bearer mock', isCurrent: first ? () => false : () => true }))
  first = false
  const context = { activeSessionId: '11111111-1111-4111-8111-111111111111', selectedResumeId: '22222222-2222-4222-8222-222222222222' }
  await f.client.connectAuto(context)
  f.client.cloudAuthCurrent = () => false
  await f.client.sendAudioChunk(new Uint8Array([1, 0]))
  assert.equal(f.counts().calls, 1)
  assert.equal(f.client.getStatus().connectionStatus, 'error')
  assert.equal(f.client.getStatus().cloudBlockedReason, 'auth_unavailable')
  assert.equal(f.writes.filter(e => e.audio_chunk).length, 0)
  f.client.close()
})

test('transport failure after metadata does not invalidate verified authorization', async () => {
  const f = fixture({ ...enabled, ELECTRON_GRPC_AUDIO_ENABLED: 'true', USE_GRPC_AUTO_PIPELINE: 'true', USE_GRPC_CLOUD_CONTEXT_PIPELINE: 'true' }, false,
    async () => ({ authorization: 'Bearer mock', isCurrent: () => true }))
  f.stream.write = () => { throw Error('transport unavailable') }
  const result = await f.client.connectAuto({ activeSessionId: '11111111-1111-4111-8111-111111111111' })
  assert.equal(result.connectionStatus, 'error')
  assert.notEqual(result.cloudAuthStatus, 'failed')
  assert.equal(result.cloudBlockedReason, 'none')
  assert.equal(f.counts().closed, 1)
})

test('cloud errors use cloud guidance while provider errors keep STT guidance', async () => {
  for (const code of ['token_expired', 'cloud_session_ended', 'session_owner_mismatch', 'stt_unavailable']) {
    const f = fixture(enabled)
    await f.client.connect()
    f.stream.emit('data', { error: { code } })
    assert.equal(f.client.getStatus().lastErrorMessage, code === 'stt_unavailable'
      ? 'Live STT unavailable. Check AssemblyAI configuration and retry.'
      : 'Cloud session unavailable. Sign in again or restart the session.')
  }
})

test('blocked cloud Auto closes a ready local stream without reusing it', async () => {
  for (const cloudEnabled of [false, true]) {
    const f = fixture({ ...enabled, ELECTRON_GRPC_AUDIO_ENABLED: 'true', USE_GRPC_AUTO_PIPELINE: 'true', USE_GRPC_CLOUD_CONTEXT_PIPELINE: String(cloudEnabled) })
    await f.client.connectAuto({})
    f.stream.emit('data', { status: { code: 'auto_pipeline_ready' } })
    assert.equal(f.client.getStatus().autoPipelineReady, true)
    const context = cloudEnabled ? { selectedResumeId: '22222222-2222-4222-8222-222222222222' }
      : { activeSessionId: '11111111-1111-4111-8111-111111111111' }
    const result = await f.client.connectAuto(context)
    assert.equal(result.connectionStatus, 'disconnected')
    assert.equal(result.autoPipelineReady, false)
    assert.equal(result.cloudBlockedReason, cloudEnabled ? 'cloud_session_invalid' : 'cloud_context_flag_disabled')
    assert.equal(f.counts().closed, 1)
    assert.equal(f.counts().calls, 1)
  }
})
test('Auto startup block check reads current diagnostics rather than captured state', () => {
  const source = readFileSync(new URL('./App.jsx', import.meta.url), 'utf8')
  const startup = source.split('const startDiag = generationDiagnosticsRef.current')[1].split('setGenerationDiagnostics')[0]
  for (const field of ['authRequired', 'activeSessionIdPresent', 'activeSessionEnded']) {
    assert.ok(startup.includes(`startDiag.${field}`))
    assert.ok(!startup.includes(`generationDiagnostics.${field}`))
  }
})

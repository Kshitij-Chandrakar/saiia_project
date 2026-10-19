// Test-only transport boundary. Production Electron parsing/publication is intact.
import { EventEmitter } from 'node:events'
import { createRequire } from 'node:module'
const require = createRequire(import.meta.url)
const { GrpcRealtimeClient } = require('../../electron/grpc_realtime_client.cjs')

export function answerStreamDriver(source = 'microphone', negotiated = false) {
  const stream = new EventEmitter()
  const stages = []
  const started = performance.now()
  const mark = stage => { if (stages.length < 128) stages.push({ stage, localMs: performance.now() - started }) }
  const client = new GrpcRealtimeClient({
    env: { ELECTRON_GRPC_REALTIME_ENABLED: 'true', ELECTRON_GRPC_AUDIO_ENABLED: 'true' },
    timeoutMs: 2000,
    getCloudAuthorization: async () => ({ authorization: 'Bearer synthetic-test-only', isCurrent: () => true }),
    transportFactory: () => ({
      waitForReady: (_, done) => queueMicrotask(() => done()),
      StreamInterview: () => stream,
      close() {},
    }),
  })
  client.health = { ...client.health, grpc_health: 'healthy', grpc_system_audio_available: true, grpc_combined_audio_available: true }
  client.systemCleanupStatus = 'clean'
  stream.cancel = () => {}
  stream.write = event => queueMicrotask(() => {
    if (event.start_session) {
      if (negotiated) stream.emit('data', { session_id: event.session_id, sequence_number: '1', answer_stream_capabilities: { version: 1 } })
      stream.emit('data', { ...(negotiated ? { session_id: event.session_id, sequence_number: String(++sequence) } : {}), status: { code: 'auto_pipeline_ready', system_audio: { active_audio_source: source } } })
      stream.emit('data', { ...(negotiated ? { session_id: event.session_id, sequence_number: String(++sequence) } : {}), request_id: event.request_id, ready: {} })
    } else stream.emit('data', { session_id: event.session_id, request_id: event.request_id, status: { code: event.end_session ? 'ended' : 'canceled' } })
  })
  let sequence = 1
  let identity = { accepted_turn: '1', display_revision: '0', retry_attempt: 0, provider_attempt: 0 }
  const snapshots = []
  let publish = () => {}
  client.onAutoEvent = snapshot => {
    mark('electron_publication')
    snapshots.push(snapshot)
    publish(snapshot)
  }
  return {
    client, snapshots, stages, mark,
    subscribe(fn) { publish = fn; return () => { publish = () => {} } },
    emit(kind, payload, overrides = {}) {
      mark('client_receipt')
      if (overrides.answer_identity) identity = { ...overrides.answer_identity }
      stream.emit('data', { session_id: client.sessionId, request_id: 'synthetic-turn',
        ...(negotiated ? { sequence_number: String(++sequence), answer_identity: { ...identity } } : {}), [kind]: payload, ...overrides })
    },
    async connect() { return client.connectAuto({ source, ...(negotiated ? { activeSessionId: '11111111-1111-4111-8111-111111111111' } : {}) }) },
    close() { return client.close() },
  }
}

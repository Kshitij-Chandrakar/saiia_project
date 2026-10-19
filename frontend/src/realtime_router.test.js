import test from 'node:test'
import assert from 'node:assert/strict'
import { selectRealtimeRoute, realtimeRouteDiagnostics } from './realtime_router.js'

const healthy = { enabled: true, audioEnabled: true, autoPipelineEnabled: true, cloudContextPipelineEnabled: true,
  cloudAuthAvailable: true, grpc_health: 'healthy', grpc_stt_available: true, grpc_answer_available: true,
  grpc_auto_available: true, grpc_cloud_context_available: true }

test('G9 local and authenticated cloud microphone prefer healthy gRPC', () => {
  for (const context of [{ localTestWithoutSaving: true }, { activeSessionId: 'session', authRequired: true }]) {
    assert.equal(selectRealtimeRoute(healthy, context).route, 'grpc_realtime')
  }
})
test('G9 system and both sources never enter gRPC even when cloud auth failed or flags disabled', () => {
  for (const source of ['system', 'both']) {
    assert.deepEqual(selectRealtimeRoute({ cloudAuthStatus: 'failed' }, { activeSessionEnded: true }, source),
      { route: 'existing_default', reason: 'system_audio_selected', fallbackAvailable: false })
  }
})
test('G9 health and capability failures select standard route with exact reason', () => {
  for (const reason of ['grpc_health_failed', 'grpc_connection_timeout', 'grpc_unavailable']) {
    const decision = selectRealtimeRoute({ ...healthy, grpc_health: 'unavailable', grpc_health_failure_reason: reason })
    assert.equal(decision.route, 'existing_default'); assert.equal(decision.reason, reason)
    const diagnostics = realtimeRouteDiagnostics(decision, {}, { source: 'microphone', fallbackUsed: true })
    assert.equal(diagnostics.grpc_fallback_reason, reason); assert.equal(diagnostics.grpc_fallback_used, true)
  }
  for (const capability of ['grpc_stt_available', 'grpc_answer_available', 'grpc_auto_available', 'enabled', 'audioEnabled']) {
    assert.equal(selectRealtimeRoute({ ...healthy, [capability]: false }).route, 'existing_default')
  }
  assert.equal(selectRealtimeRoute(healthy, {}, 'microphone', false).reason, 'grpc_unavailable')
  assert.equal(selectRealtimeRoute({ ...healthy, autoPipelineEnabled: false }).reason, 'config_disabled')
})
test('G9 auth/session rejection blocks rather than downgrading context', () => {
  for (const reason of ['auth_unavailable', 'cloud_session_invalid', 'cloud_session_ended', 'session_owner_mismatch', 'cloud_context_rejected']) {
    const decision = selectRealtimeRoute({ ...healthy, cloudAuthStatus: 'failed', cloudBlockedReason: reason }, { activeSessionId: 'session' })
    assert.equal(decision.route, 'blocked'); assert.equal(decision.reason, reason)
  }
  assert.equal(selectRealtimeRoute(healthy, { activeSessionEnded: true }).route, 'blocked')
})
test('G9 fresh routing diagnostics clear transport, commit, cloud and save state', () => {
  const decision = selectRealtimeRoute(healthy, {}, 'system')
  const diagnostics = realtimeRouteDiagnostics(decision, healthy, { runId: 'fresh', source: 'system' })
  assert.equal(diagnostics.auto_run_id, 'fresh')
  assert.equal(diagnostics.cloud_grpc_auth_status, 'not_applicable')
  assert.equal(diagnostics.generation_committed, false)
  assert.equal(diagnostics.question_transport, 'none')
  assert.equal(diagnostics.answer_transport, 'none')
  assert.equal(diagnostics.cloud_session_verified, false)
  assert.equal(diagnostics.cloud_answer_save_status, 'n/a')
  assert.equal(diagnostics.grpc_fallback_used, false)
})

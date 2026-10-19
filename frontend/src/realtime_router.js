import { getGrpcAutoBlockReason } from './grpc_auto_session.js'

export const AUTH_BLOCKS = new Set(['auth_unavailable', 'auth_invalid', 'token_expired', 'session_owner_mismatch',
  'cloud_session_invalid', 'cloud_session_ended', 'selected_context_forbidden', 'cloud_context_rejected'])

// One decision for microphone Auto. System/both never enter the gRPC path.
export function selectRealtimeRoute(status, context = {}, source = 'microphone', transportAvailable = true) {
  const result = (route, reason) => ({ route, reason, fallbackAvailable: route !== 'blocked' && source === 'microphone' })
  if (source === 'system' || source === 'both') return result('existing_default', 'system_audio_selected')
  if (source !== 'microphone') return result('blocked', 'unsupported_source')
  if (context.activeSessionEnded) return result('blocked', 'cloud_session_ended')
  if (context.activeSessionId || context.activeSessionIdPresent) {
    if (!context.activeSessionId) return result('blocked', 'cloud_session_invalid')
    if (status?.cloudAuthStatus === 'failed') return result('blocked', AUTH_BLOCKS.has(status.cloudBlockedReason) ? status.cloudBlockedReason : 'auth_unavailable')
    if (status?.cloudAuthAvailable === false) return result('blocked', 'auth_unavailable')
  }
  const reason = getGrpcAutoBlockReason(status, context, source)
  if (AUTH_BLOCKS.has(reason)) return result('blocked', reason)
  if (!transportAvailable) return result('existing_default', 'grpc_unavailable')
  if (reason) return result('existing_default', reason)
  if (status.grpc_health !== 'healthy') return result('existing_default',
    status.grpc_health_failure_reason && status.grpc_health_failure_reason !== 'none' ? status.grpc_health_failure_reason : 'grpc_health_failed')
  if (!status.grpc_stt_available || !status.grpc_answer_available || !status.grpc_auto_available) return result('existing_default', 'grpc_unavailable')
  if (context.activeSessionId && !status.grpc_cloud_context_available) return result('existing_default', 'grpc_unavailable')
  return result('grpc_realtime', 'microphone_eligible')
}

export function realtimeRouteDiagnostics(decision, status, { runId = '', source = 'none', fallbackUsed = false } = {}) {
  return { realtime_default_route: 'grpc_realtime', selected_realtime_pipeline: decision.route,
    pipeline_selection_reason: decision.reason, grpc_health: status?.grpc_health || 'unknown',
    grpc_connection_status: status?.connectionStatus || 'unavailable',
    grpc_last_failure_reason: status?.grpc_last_failure_reason || 'none',
    grpc_fallback_available: decision.fallbackAvailable, grpc_fallback_used: fallbackUsed,
    grpc_fallback_reason: fallbackUsed ? decision.reason : 'none', active_audio_source: source,
    auto_run_id: runId, question_transport: 'none', answer_transport: 'none', generation_committed: false,
    stop_cleanup_status: 'idle', cloud_grpc_auth_status: source === 'system' ? 'not_applicable' : 'not_started',
    cloud_session_verified: false, cloud_context_loaded: false, cloud_answer_save_status: 'n/a' }
}

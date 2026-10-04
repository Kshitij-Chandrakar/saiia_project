// Cloud-owned context and active sessions always require authenticated generation.
export async function prepareGenerationRequest(body, startupConfig, api, onDiagnostics = () => {}, { localWithoutSaving = false } = {}) {
  const selectedResumeId = String(body.selected_resume_id || startupConfig?.selectedResumeId || '').trim()
  const jobContextId = String(body.job_context_id || startupConfig?.jobContextId || '').trim()
  const startupSessionId = String(startupConfig?.activeSessionId || '').trim()
  const requestBody = { ...body }
  if (selectedResumeId) requestBody.selected_resume_id = selectedResumeId
  if (jobContextId) requestBody.job_context_id = jobContextId
  let cloudAvailable = false
  let cloudState = null
  if (typeof api?.getCloudStartupContext === 'function') {
    try {
      const state = await api.getCloudStartupContext()
      cloudState = state
      cloudAvailable = state?.auth?.status === 'connected' && state?.cloud?.available === true
    } catch { /* Local generation remains available without cloud. */ }
  }
  if (startupSessionId) requestBody.session_id ||= startupSessionId
  const candidateSessionId = String(requestBody.session_id || '').trim()
  const endedIds = Array.isArray(cloudState?.auth?.endedInterviewSessionIds) ? cloudState.auth.endedInterviewSessionIds : []
  const confirmedEnded = (id) => Boolean(id && endedIds.includes(id) && cloudState?.auth?.activeInterviewSessionId !== id)
  const activeSessionEnded = confirmedEnded(candidateSessionId)
  const startupSessionEnded = confirmedEnded(startupSessionId)
  if (activeSessionEnded) {
    delete requestBody.session_id
    if (startupSessionId && !startupSessionEnded) requestBody.session_id = startupSessionId
  }
  if (localWithoutSaving) {
    delete requestBody.session_id
    delete requestBody.selected_resume_id
    delete requestBody.job_context_id
  }
  const authRequired = Boolean(requestBody.selected_resume_id || requestBody.job_context_id || requestBody.session_id)
  const diagnostics = {
    generationRequestBlocked: authRequired && !cloudAvailable,
    generationBlockReason: authRequired && !cloudAvailable ? 'cloud_auth_unavailable' : '',
    activeSessionIdPresent: Boolean(candidateSessionId),
    activeSessionEnded,
    startupSessionEnded,
    authRequired,
    generationAuthRequired: authRequired,
    cloudStatusAtGeneration: cloudAvailable ? 'available' : (cloudState?.auth?.status === 'connected' ? 'unavailable (identity connected)' : (cloudState?.auth?.status || 'unavailable')),
    localWithoutSaving,
    generateStreamRequestSent: false,
    generateFallbackRequestSent: false,
    generateRequestSent: false,
    generate_stream_request_sent: false,
    generate_non_stream_fallback_used: false,
    stream_fallback_reason: '',
    first_delta_received_ms: null,
    first_ui_update_ms: null,
    provider_streaming: false,
  }
  onDiagnostics(diagnostics)
  if (authRequired && !cloudAvailable) {
    throw new Error('Cloud generation requires a valid connection. Sign in again and reconnect to continue the active session, or end the session and clear cloud selections to generate locally.')
  }
  return { requestBody, authRequired }
}

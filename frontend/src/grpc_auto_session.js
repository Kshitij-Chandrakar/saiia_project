import { createGrpcMicTest } from './grpc_mic_test.js'

// Eligibility remains separate from health; realtime_router owns the final decision.
export function getGrpcAutoBlockReason(status, context = {}, source = 'microphone') {
  if (!status?.autoPipelineEnabled) return 'config_disabled'
  if (!['microphone', 'system', 'both'].includes(source)) return 'unsupported_source'
  const cloudSession = Boolean(String(context?.activeSessionId || '').trim() || (context?.activeSessionIdPresent && !context?.activeSessionEnded))
  const cloudAllowed = cloudSession && status.cloudContextPipelineEnabled
  if (cloudSession && !cloudAllowed) return 'cloud_session_active'
  if (cloudAllowed && status.cloudAuthAvailable === false) return 'auth_unavailable'
  if (cloudAllowed && status.cloudAuthStatus === 'failed') return status.cloudBlockedReason || 'auth_unavailable'
  if (!cloudAllowed && (context?.authRequired || context?.generationAuthRequired)) return 'auth_context_required'
  if (!cloudAllowed && ['selectedResumeId', 'selected_resume_id', 'job_context_id', 'jobContextId'].some(key => String(context?.[key] || '').trim())) return 'selected_context_required'
  if (!cloudAllowed && ['targetRole', 'role', 'companyName', 'company', 'jobDescription', 'jobContext'].some(key => String(context?.[key] || '').trim())) return 'selected_context_required'
  if (!status.enabled || !status.audioEnabled) return 'grpc_unavailable'
  return ''
}

export async function createGrpcAutoSession({ api, stream, source = 'microphone', context = {}, onCloudStatus = () => {}, isCurrent = () => true,
  canContinue = () => true, onTranscript = () => {}, onAnswer = () => {},
  onPhase = () => {}, onError = () => {}, onFallback = () => {}, onStartupFailure = () => {}, onLifecycle = () => {},
  createMic = createGrpcMicTest, pollMs = 250 }) {
  if (!['microphone', 'system', 'both'].includes(source) || !isCurrent()) return null
  let connected
  try { connected = await api.connectGrpcAutoPipeline({ activeSessionId: context.activeSessionId || '',
    selectedResumeId: context.selectedResumeId || '', jobContextId: context.jobContextId || '', source }) } catch { /* Cleanup below; source policy controls fallback. */ }
  if (connected) onCloudStatus(connected)
  const allowed = canContinue()
  if (!isCurrent() || !allowed || !connected?.autoPipelineReady || connected.connectionStatus !== 'connected' ||
      (source !== 'microphone' && connected.systemAudio?.active_audio_source !== source)) {
    if (source === 'both') stream?.getTracks?.().forEach(track => track.stop())
    if (connected?.manualRun || isCurrent()) {
      if (source !== 'microphone') onLifecycle({ stop_cleanup_status: 'cleaning' })
      const cleanup = await api.closeGrpcRealtime(connected?.manualRun).catch(() => ({ systemCleanupStatus: 'failed' }))
      if (source !== 'microphone') onLifecycle({ stop_cleanup_status: ['failed', 'cleaning'].includes(cleanup?.systemCleanupStatus) ? 'failed' : 'clean' })
    }
    onStartupFailure(!allowed ? 'auth_unavailable' : connected?.cloudAuthStatus === 'failed' ? connected.cloudBlockedReason || 'auth_unavailable' :
      connected?.grpc_last_failure_reason && connected.grpc_last_failure_reason !== 'none' ? connected.grpc_last_failure_reason : 'grpc_start_failed')
    return null
  }
  let closed = false, inFlight = false, timer, unsubscribe, deadline, cooldownTimer, cleanupPromise
  let currentRequestId = '', lastRevision = '', activeIdentity = null
  let version = -1, questionNumber = 0, completions = 0, completedQuestion = 0, lastText = ''
  let committed = false, audioSent = source !== 'microphone', potentialCommit = false
  const trackListeners = []
  const mic = source === 'system' ? { start: async () => {}, close: () => {} } : createMic({ api, ownsStream: false, continuous: source === 'both', getUserMedia: async () => stream })
  const close = () => {
    if (closed) return cleanupPromise
    closed = true
    onLifecycle({ stop_cleanup_status: 'cleaning' })
    for (const [track, listener] of trackListeners) track.removeEventListener?.('ended', listener)
    if (source === 'both') stream?.getTracks().forEach(track => track.stop())
    clearInterval(timer); clearTimeout(deadline); clearTimeout(cooldownTimer); unsubscribe?.()
    let captureFailed = false
    try { mic.close() } catch { captureFailed = true }
    const cleaned = status => { onLifecycle({ stop_cleanup_status: status }); return status }
    cleanupPromise = api.closeGrpcRealtime(connected.manualRun).then(result => cleaned(captureFailed || result?.systemCleanupStatus === 'failed' || result?.systemCleanupStatus === 'cleaning' ? 'failed' : 'clean'), () => cleaned('failed'))
    lastText = ''; version = -1
    return cleanupPromise
  }
  const fail = (next = {}, failureReason = 'grpc_connection_failed') => {
    if (closed) return
    committed ||= Boolean(next.generation_committed || next.questionsDetectedCount || next.answerStartedCount || next.answerDeltaCount)
    audioSent ||= Boolean(next.grpc_audio_sent || next.audioChunksSent)
    const authBlocked = next.cloudAuthStatus === 'failed' || !canContinue()
    const reason = authBlocked ? next.cloudBlockedReason || 'auth_unavailable' : failureReason
    const cleanup = close()
    // Lost delivery after sending audio cannot prove the backend did not commit.
    // Never replay buffered speech or silently regenerate an uncertain question.
    if (source === 'microphone' && !committed && !audioSent && !potentialCommit && !authBlocked) {
      void cleanup.then(status => {
        if (!isCurrent()) return
        if (status === 'clean') onFallback(reason)
        else onError('Realtime cleanup failed. Stop and restart Auto Mode.')
      })
    }
    else onError(authBlocked ? 'Cloud session unavailable. Sign in again or restart the session.' :
      source !== 'microphone' ? 'Required audio source unavailable. Stop and restart Auto Mode. Check Windows output and the local gRPC backend; no alternate transport was started.' :
      'Realtime connection unavailable. Your displayed answer is preserved. Stop and restart for the next question.',
    { reason, generation_committed: committed, cloud_grpc_auth_status: authBlocked ? 'failed' : next.cloudAuthStatus || 'not_started' })
  }
  const apply = next => {
    if (closed || !isCurrent()) return
    if (next.manualRun !== connected.manualRun || next.autoEventVersion < version) return
    // Connection/auth can change without another answer publication.
    if (!canContinue() || next.connectionStatus !== 'connected' || next.lastErrorMessage) { fail(next); return }
    if (next.autoEventVersion === version) return
    if (next.answerStreamVersion === 1 && next.questionsDetectedCount) {
      const identity = next.answerStreamIdentity
      if (!identity || identity.run !== connected.manualRun || identity.requestId !== next.answerRequestId ||
          !['accepted_turn', 'display_revision', 'retry_attempt', 'provider_attempt'].every(key =>
            /^(0|[1-9][0-9]{0,19})$/.test(identity[key]) && BigInt(identity[key]) < (1n << BigInt(key.endsWith('attempt') ? 32 : 64))) || identity.accepted_turn === '0') return
      if (activeIdentity && (identity.epoch !== activeIdentity.epoch || identity.sessionId !== activeIdentity.sessionId ||
          BigInt(identity.accepted_turn) < BigInt(activeIdentity.accepted_turn) ||
          (identity.accepted_turn === activeIdentity.accepted_turn && (identity.requestId !== activeIdentity.requestId ||
            identity.retry_attempt !== activeIdentity.retry_attempt ||
            BigInt(identity.display_revision) < BigInt(activeIdentity.display_revision) ||
            (activeIdentity.terminal && !identity.terminal))))) return
      activeIdentity = identity
    }
    if (!canContinue()) { fail(next); return }
    onCloudStatus(next)
    audioSent ||= Boolean(next.grpc_audio_sent || next.audioChunksSent)
    committed ||= Boolean(next.generation_committed || next.questionsDetectedCount || next.answerStartedCount || next.answerDeltaCount)
    potentialCommit ||= Boolean(next.currentTranscript)
    onLifecycle({ question_transport: committed ? 'grpc_realtime' : 'none',
      answer_transport: next.question_stage === 'question_detected' ? 'none' : next.answerStartedCount || next.answerDeltaCount || next.answerCompletedCount ? 'grpc_realtime' : 'none',
      generation_committed: committed, question_stage: next.question_stage || (committed ? 'question_detected' : 'idle') })
    if (!canContinue() || next.connectionStatus !== 'connected' || next.lastErrorMessage) { fail(next); return }
    version = next.autoEventVersion
    if (next.currentTranscript) onTranscript(next.currentTranscript)
    if (next.questionsDetectedCount > questionNumber) {
      clearTimeout(cooldownTimer)
      questionNumber = next.questionsDetectedCount
      currentRequestId = next.answerRequestId || ''
      lastText = ''
      onAnswer({ streamIdentity: next.answerStreamIdentity, requestId: next.answerRequestId, question: next.currentQuestion, answer: '', category: next.answerCategory,
        provider: next.answerProvider, status: 'generating', historyEntryId: `auto-grpc-${connected.manualRun}-${next.answerStreamVersion === 1 && next.answerRequestId ? next.answerRequestId : questionNumber}` })
      onPhase('generating')
      clearTimeout(deadline)
      deadline = setTimeout(() => fail(), 95000)
    }
    if (next.answerFailureCode && next.answerRequestId && next.answerFailureRequestId === currentRequestId && questionNumber && completedQuestion !== questionNumber) {
      completedQuestion = questionNumber
      clearTimeout(deadline)
      lastText = ''
      onAnswer({ streamIdentity: next.answerStreamIdentity, requestId: next.answerRequestId, question: next.currentQuestion, answer: '', category: next.answerCategory,
        provider: next.answerProvider, status: 'error', error: next.answerFailureCode,
        historyEntryId: `auto-grpc-${connected.manualRun}-${next.answerStreamVersion === 1 && next.answerRequestId ? next.answerRequestId : questionNumber}` })
      onPhase('listening')
    }
    const complete = next.answerStreamVersion === 1 ? next.lastAnswerStatus === 'answer_completed' : next.answerCompletedCount > completions
    const revision = next.answerStreamIdentity?.display_revision || ''
    if (questionNumber && completedQuestion !== questionNumber && (next.currentAnswer !== lastText || complete || revision !== lastRevision)) {
      lastRevision = revision
      lastText = next.currentAnswer || ''
      onAnswer({ streamIdentity: next.answerStreamIdentity, requestId: next.answerRequestId, question: next.currentQuestion, answer: lastText,
        category: next.answerCategory, provider: next.answerProvider,
        status: complete ? 'complete' : 'generating',
        historyEntryId: `auto-grpc-${connected.manualRun}-${next.answerStreamVersion === 1 && next.answerRequestId ? next.answerRequestId : questionNumber}` })
      if (complete) {
        completedQuestion = questionNumber
        completions = next.answerCompletedCount; clearTimeout(deadline); onPhase('cooldown')
        clearTimeout(cooldownTimer)
        cooldownTimer = setTimeout(() => { if (!closed && isCurrent()) onPhase('listening') }, 4000)
      }
    }
    if (next.autoStatus === 'auto_listening') onPhase('listening')
  }
  if (source === 'both') {
    for (const track of stream?.getAudioTracks?.() || []) {
      const listener = () => fail({}, 'microphone_lost')
      track.addEventListener?.('ended', listener)
      trackListeners.push([track, listener])
      if (track.readyState === 'ended') listener()
    }
  }
  unsubscribe = api.onGrpcAutoEvent?.(apply)
  if (connected.questionsDetectedCount) apply(connected)
  try { if (!closed) await mic.start() } catch {
    // Capture creation/resume can fail after queued PCM has already reached main.
    let next
    try { next = await api.getGrpcRealtimeStatus() } catch { next = { grpc_audio_sent: true } }
    fail(next, 'grpc_start_failed')
    return { close, stop: close, failed: true }
  }
  if (closed || !isCurrent()) { close(); return { close, stop: close, failed: true } }
  if (!questionNumber) onPhase('listening')
  timer = setInterval(async () => {
    if (closed || inFlight) return
    if (!isCurrent()) { close(); return }
    inFlight = true
    try { apply(await api.getGrpcRealtimeStatus()) } catch { if (!closed) { audioSent = true; fail() } }
    finally { inFlight = false }
  }, pollMs)
  return { close, stop: close }
}

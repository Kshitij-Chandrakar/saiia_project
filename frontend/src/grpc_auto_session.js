import { createGrpcMicTest } from './grpc_mic_test.js'

// Cloud ownership/context is intentionally not supported by the G5 protocol.
export function getGrpcAutoBlockReason(status, context = {}, source = 'microphone') {
  if (!status?.autoPipelineEnabled) return 'config_disabled'
  if (String(context?.activeSessionId || '').trim() || (context?.activeSessionIdPresent && !context?.activeSessionEnded)) return 'cloud_session_active'
  if (context?.authRequired || context?.generationAuthRequired) return 'auth_context_required'
  if (['selectedResumeId', 'selected_resume_id', 'job_context_id', 'jobContextId'].some(key => String(context?.[key] || '').trim())) return 'selected_context_required'
  if (source === 'system' || source === 'both') return 'system_audio_selected'
  if (source !== 'microphone') return 'unsupported_source'
  if (['targetRole', 'role', 'companyName', 'company', 'jobDescription', 'jobContext'].some(key => String(context?.[key] || '').trim())) return 'selected_context_required'
  if (!status.enabled || !status.audioEnabled) return 'grpc_unavailable'
  return ''
}

export async function createGrpcAutoSession({ api, stream, isCurrent = () => true,
  canContinue = () => true, onTranscript = () => {}, onAnswer = () => {},
  onPhase = () => {}, onError = () => {}, createMic = createGrpcMicTest, pollMs = 250 }) {
  if (!isCurrent()) return null
  let connected
  try { connected = await api.connectGrpcAutoPipeline() } catch { /* Startup fallback is safe before capture. */ }
  if (!isCurrent() || !canContinue() || !connected?.autoPipelineReady || connected.connectionStatus !== 'connected') {
    await api.closeGrpcRealtime().catch(() => {})
    return null
  }
  let closed = false, inFlight = false, timer, unsubscribe, deadline, cooldownTimer
  let version = -1, questionNumber = 0, completions = 0, completedQuestion = 0, lastText = ''
  const mic = createMic({ api, ownsStream: false, getUserMedia: async () => stream })
  const close = () => {
    if (closed) return
    closed = true
    clearInterval(timer); clearTimeout(deadline); clearTimeout(cooldownTimer); unsubscribe?.()
    mic.close()
    void api.closeGrpcRealtime().catch(() => {})
  }
  const fail = () => {
    if (closed) return
    close()
    // A final may already have committed generation. Never retry it via REST.
    onError('Realtime Auto Mode unavailable. Stop and restart to use the existing flow.')
  }
  const apply = next => {
    if (closed || !isCurrent()) return
    if (!canContinue() || next.connectionStatus !== 'connected' || next.lastErrorMessage) { fail(); return }
    if (next.manualRun !== connected.manualRun || next.autoEventVersion < version) return
    version = next.autoEventVersion
    if (next.currentTranscript) onTranscript(next.currentTranscript)
    if (next.questionsDetectedCount > questionNumber) {
      clearTimeout(cooldownTimer)
      questionNumber = next.questionsDetectedCount
      lastText = ''
      onAnswer({ question: next.currentQuestion, answer: '', category: next.answerCategory,
        provider: next.answerProvider, status: 'generating', historyEntryId: `auto-grpc-${connected.manualRun}-${questionNumber}` })
      onPhase('generating')
      clearTimeout(deadline)
      deadline = setTimeout(fail, 95000)
    }
    if (questionNumber && completedQuestion !== questionNumber && (next.currentAnswer !== lastText || next.answerCompletedCount > completions)) {
      const complete = next.answerCompletedCount > completions
      lastText = next.currentAnswer || ''
      onAnswer({ question: next.currentQuestion, answer: lastText,
        category: next.answerCategory, provider: next.answerProvider,
        status: complete ? 'complete' : 'generating',
        historyEntryId: `auto-grpc-${connected.manualRun}-${questionNumber}` })
      if (complete) {
        completedQuestion = questionNumber
        completions = next.answerCompletedCount; clearTimeout(deadline); onPhase('cooldown')
        clearTimeout(cooldownTimer)
        cooldownTimer = setTimeout(() => { if (!closed && isCurrent()) onPhase('listening') }, 4000)
      }
    }
    if (next.autoStatus === 'auto_listening') onPhase('listening')
  }
  unsubscribe = api.onGrpcAutoEvent?.(apply)
  try { await mic.start() } catch { close(); return null }
  if (closed || !isCurrent()) { close(); return null }
  onPhase('listening')
  timer = setInterval(async () => {
    if (closed || inFlight) return
    if (!isCurrent()) { close(); return }
    inFlight = true
    try { apply(await api.getGrpcRealtimeStatus()) } catch { if (!closed) fail() }
    finally { inFlight = false }
  }, pollMs)
  return { close, stop: close }
}

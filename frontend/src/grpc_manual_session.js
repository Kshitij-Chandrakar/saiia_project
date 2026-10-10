import { createManualLiveSession, createManualLiveState } from './manual_live_session.js'
import { createGrpcMicTest } from './grpc_mic_test.js'

// G5 has no authenticated cloud-context protocol. Never detach cloud resources.
export function getGrpcManualBlockReason(status, context = {}) {
  if (!status?.manualPipelineEnabled) return 'feature_disabled'
  if (!status.audioEnabled) return 'grpc_audio_disabled'
  return ['activeSessionId', 'selectedResumeId', 'job_context_id', 'jobContextId',
      'targetRole', 'role', 'companyName', 'company', 'jobDescription', 'jobContext']
      .some(key => String(context?.[key] || '').trim()) ? 'interview_context_requires_existing_flow' : ''
}

export function canUseGrpcManual(status, context = {}) {
  return !getGrpcManualBlockReason(status, context)
}

export async function createGrpcManualSession({ api, options, isCurrent = () => true,
  createLegacy = createManualLiveSession, createMic = createGrpcMicTest,
  canContinue = () => true, onAnswer = () => {}, onCancel = () => {}, onTiming = () => {}, onPipeline = () => {}, onStatus = () => {}, pollMs = 100, timeoutMs = 95000 }) {
  const timings = { manual_start_at: options.manualStartedAt || Date.now() }
  let timingSignature = ''
  const reportTiming = next => {
    Object.assign(timings, next)
    const signature = JSON.stringify(timings)
    if (signature !== timingSignature) { timingSignature = signature; onTiming({ ...timings }) }
  }
  let connected
  try { connected = await api.connectGrpcManualPipeline() } catch { /* Safe fallback. */ }
  if (!isCurrent()) { await api.closeGrpcRealtime(); return null }
  if (!connected?.manualPipelineReady || connected.connectionStatus !== 'connected') {
    await api.closeGrpcRealtime().catch(() => {})
    options.onFallback()
    onPipeline('REST/WebSocket fallback', 'grpc_connection_unavailable')
    onStatus('gRPC unavailable. Using existing manual flow.')
    return createLegacy(options)
  }

  onPipeline('gRPC realtime', '')
  reportTiming({})
  let canceled = false, fallback = false, inFlight = false, finishing, timer, deadline, unsubscribe
  let eventVersion = -1
  let question = '', lastAnswer = '', stopped = false, terminal = false
  let resolveDone, rejectDone
  const done = new Promise((resolve, reject) => { resolveDone = resolve; rejectDone = reject })
  done.catch(() => {})
  let state = { ...createManualLiveState(options.sessionId), phase: 'listening',
    historyEntryId: `manual-${options.sessionId}`, liveProvider: 'assemblyai_streaming', transport: 'grpc' }
  const publish = patch => {
    state = { ...state, ...patch }
    if (!canceled && isCurrent()) options.onState(state)
  }
  // Reuse the existing batch recorder/detector/generator as a backup, never a second live stream.
  let backup
  try {
    backup = createLegacy({ ...options, manualLiveSttProvider: 'none',
      onState: next => { if (fallback && !canceled && isCurrent()) options.onState({ ...next, transport: 'batch-fallback' }) },
      onTranscript: text => { if (fallback && !canceled && isCurrent()) options.onTranscript(text) } })
  } catch {
    await api.closeGrpcRealtime().catch(() => {})
    throw new Error('Microphone backup recording unavailable. Please retry.')
  }
  const mic = createMic({ api, ownsStream: false, getUserMedia: async () => options.stream })
  const cleanup = async () => {
    clearInterval(timer); clearTimeout(deadline)
    unsubscribe?.()
    unsubscribe = null
    mic.close()
    await api.closeGrpcRealtime().catch(() => {})
  }
  const fail = () => {
    if (canceled || terminal || fallback) return
    // Once Stop is dispatched, the server may already have started generation.
    // An ambiguous disconnect must never cause a second REST generation.
    if (stopped) {
      terminal = true
      publish({ phase: 'error' })
      onAnswer({ question, answer: lastAnswer, status: 'error', historyEntryId: state.historyEntryId })
      rejectDone(new Error('Realtime answer unavailable. Please record the question again.'))
    } else {
      fallback = true
      onPipeline('batch fallback', 'grpc_unavailable_before_stop')
      options.onFallback()
      onStatus('gRPC unavailable. Batch transcription will run when stopped.')
      publish({ phase: 'listening', transport: 'batch-fallback' })
    }
    void cleanup()
  }
  const applyStatus = next => {
    try {
      if (canceled || !isCurrent() || terminal || fallback) return
      if (connected.manualRun != null && next.manualRun !== connected.manualRun) return
      if (Number.isFinite(next.manualEventVersion)) {
        // A pending poll must never overwrite newer pushed deltas/completion.
        if (next.manualEventVersion < eventVersion) return
        eventVersion = next.manualEventVersion
      }
      reportTiming({ ...next.manualTimings, manual_start_at: timings.manual_start_at,
        ...(timings.manual_stop_at ? { manual_stop_at: timings.manual_stop_at } : {}) })
      if (next.currentTranscript && next.currentTranscript !== state.partialTranscript) {
        options.onTranscript(next.currentTranscript)
        publish({ partialTranscript: next.currentTranscript })
      }
      if (next.currentQuestion && next.currentQuestion !== question) {
        question = next.currentQuestion
        publish({ detectedQuestion: question, phase: 'generating' })
      }
      if (next.currentQuestion && (next.currentAnswer !== lastAnswer || next.lastAnswerStatus === 'answer_completed')) {
        lastAnswer = next.currentAnswer || ''
        onAnswer({ question, answer: lastAnswer, category: next.answerCategory, provider: next.answerProvider,
          manualRun: next.manualRun, status: next.lastAnswerStatus === 'answer_completed' ? 'complete' : 'generating', historyEntryId: state.historyEntryId })
      }
      if (next.lastAnswerStatus === 'answer_completed' || next.manualStatus === 'manual_no_question') {
        terminal = true
        publish({ phase: 'idle' })
        onStatus(question ? 'Answer ready.' : 'No clear question detected yet.')
        resolveDone()
      } else if (next.lastErrorMessage || next.connectionStatus !== 'connected') fail()
    } catch { fail() }
  }
  const refresh = async () => {
    if (inFlight || canceled || terminal || fallback) return
    inFlight = true
    try { applyStatus(await api.getGrpcRealtimeStatus()) }
    catch { fail() } finally { inFlight = false }
  }
  try { unsubscribe = api.onGrpcManualEvent?.(applyStatus) } catch { /* Older/preload-unavailable clients retain polling. */ }
  try { await mic.start() } catch { fail() }
  publish({})
  if (!fallback) timer = setInterval(() => { void refresh() }, pollMs)
  let cancelWait
  const cancellation = new Promise(resolve => { cancelWait = resolve })
  return {
    stop() {
      if (finishing) return finishing
      finishing = (async () => {
        if (canceled) return
        if (!canContinue() && !fallback) fail()
        if (fallback) {
          await cleanup()
          return backup.stop()
        }
        stopped = true
        reportTiming({ manual_stop_at: Date.now() })
        publish({ phase: 'finalizing' })
        onStatus('Transcribing...')
        deadline = setTimeout(fail, timeoutMs)
        try {
          await mic.stop()
          if (canceled) return
          if (!terminal && state.phase !== 'generating') onStatus('Detecting question...')
          void refresh()
          await Promise.race([done, cancellation])
        } catch {
          fail()
          if (!canceled) await done
        } finally {
          await cleanup()
          backup.cancel()
        }
      })()
      return finishing
    },
    cancel() {
      canceled = true
      cancelWait()
      if (!terminal) onCancel(state.historyEntryId)
      backup.cancel()
      void cleanup()
    },
  }
}

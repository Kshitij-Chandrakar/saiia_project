export function createManualLiveState(sessionId = '') {
  return { sessionId, phase: 'idle', partialTranscript: '', finalTurns: {}, detectedQuestion: '', pendingGeneration: false, historyEntryId: '', liveProvider: 'none', manual_stop_clicked_at: null, manual_final_transcript_received_at: null, manual_finalization_wait_ms: null, manual_question_detection_started_at: null, stop_to_question_detection_ms: null }
}

export function getManualFinalTranscript(state) {
  return Object.entries(state.finalTurns).sort(([a], [b]) => Number(a) - Number(b)).map(([, text]) => text).join(' ').trim()
}

function previewText(state, partialOrder) {
  const turns = { ...state.finalTurns }
  if (state.partialTranscript) turns[partialOrder] = state.partialTranscript
  return getManualFinalTranscript({ finalTurns: turns })
}

export function isManualLiveEnabled(manualProvider, liveProvider) {
  return liveProvider === 'assemblyai_streaming' && ['groq', 'openai_whisper', 'assemblyai'].includes(manualProvider)
}

// The caller supplies the existing detector, batch STT and authenticated generator.
export function createManualLiveSession({ sessionId, stream, manualSttProvider = '', manualLiveSttProvider = 'none', createTransport, createRecorder, transcribe, detectQuestion, generate, onState, onTranscript, onFallback = () => {}, finalizeMs = 700, connectMs = 5000 }) {
  const liveEnabled = isManualLiveEnabled(manualSttProvider, manualLiveSttProvider)
  const recordingStarted = performance.now()
  let state = { ...createManualLiveState(sessionId), phase: 'connecting', historyEntryId: `manual-${sessionId}`, liveProvider: liveEnabled ? 'assemblyai_streaming' : 'none' }
  let transport, recorder, partialOrder = 0, failed = false, canceled = false, finishing
  let connectTimer, finalizeTimer, revisionTimer, finishWait, closing = false
  const chunks = []
  const publish = (patch) => {
    state = { ...state, ...patch }
    if (!canceled) onState(state)
  }
  const stopTracks = () => stream.getTracks().forEach((track) => track.stop())
  let resolveBackup, rejectBackup
  const backup = new Promise((resolve, reject) => { resolveBackup = resolve; rejectBackup = reject })
  // Recorder errors may arrive before the stop click.
  backup.catch(() => {})
  const fail = () => {
    if (canceled || closing || failed || ['idle', 'error', 'generating'].includes(state.phase)) return
    failed = true
    clearTimeout(connectTimer)
    transport?.close(false)
    onFallback()
    finishWait?.()
    if (state.phase === 'connecting') publish({ phase: 'listening' })
  }
  const release = () => {
    clearTimeout(connectTimer)
    clearTimeout(finalizeTimer)
    clearTimeout(revisionTimer)
    closing = true
    transport?.close()
    stopTracks()
    chunks.length = 0
  }
  try {
    recorder = createRecorder(stream)
    recorder.ondataavailable = ({ data }) => { if (!canceled && data?.size) chunks.push(data) }
    recorder.onstop = () => resolveBackup(new Blob(chunks, { type: recorder.mimeType || 'audio/webm' }))
    recorder.onerror = () => rejectBackup(new Error('Microphone backup recording failed.'))
    recorder.start()
    publish({})
  } catch (error) {
    release()
    throw error
  }
  if (!liveEnabled) {
    publish({ phase: 'listening' })
  } else try {
    transport = createTransport(stream, () => !canceled && ['connecting', 'listening'].includes(state.phase))
    const socket = transport.socket
    socket.onopen = () => {
      if (canceled || failed || state.phase !== 'connecting') return
      clearTimeout(connectTimer)
      publish({ phase: 'listening' })
    }
    socket.onmessage = ({ data }) => {
      if (canceled || closing || failed || !['connecting', 'listening', 'finalizing'].includes(state.phase)) return
      let payload
      try { payload = JSON.parse(String(data)) } catch { return }
      if (!payload || typeof payload !== 'object') return
      if (payload.event === 'error' || payload.event === 'termination') { fail(); return }
      if (payload.event !== 'turn' || typeof payload.transcript !== 'string') return
      const text = payload.transcript.trim().slice(0, 20000)
      if (!text) return
      const order = Number.isSafeInteger(payload.turn_order) && payload.turn_order >= 0 ? payload.turn_order : partialOrder
      if (payload.end_of_turn === true) {
        publish({ manual_final_transcript_received_at: performance.now(), finalTurns: { ...state.finalTurns, [order]: text }, ...(order === partialOrder ? { partialTranscript: '' } : {}) })
        partialOrder = Math.max(partialOrder, order + 1)
      } else {
        if (Object.hasOwn(state.finalTurns, order)) return
        partialOrder = order
        publish({ partialTranscript: text })
      }
      if (state.phase === 'finalizing' && finishWait) {
        clearTimeout(revisionTimer)
        const latestOrder = Math.max(...Object.keys(state.finalTurns).map(Number))
        // Only a final for the newest turn qualifies. Allow 100 ms of quiet for
        // revisions; any new turn restarts this grace, within the original cap.
        if (payload.end_of_turn === true && order === latestOrder && !state.partialTranscript) {
          revisionTimer = setTimeout(() => finishWait?.(), 100)
        }
      }
      onTranscript(previewText(state, partialOrder))
    }
    socket.onerror = fail
    socket.onclose = fail
    connectTimer = setTimeout(fail, connectMs)
  } catch { fail() }

  const stop = () => {
    if (finishing) return finishing
    if (canceled) return Promise.resolve()
    const recordingMs = Number((performance.now() - recordingStarted).toFixed(2))
    const stopClickedAt = performance.now()
    publish({ phase: 'finalizing', pendingGeneration: true, manual_stop_clicked_at: stopClickedAt })
    finishing = (async () => {
      try {
        clearTimeout(connectTimer)
        transport?.pauseAudio()
        if (recorder.state !== 'inactive') recorder.stop()
        // Keep the socket open briefly so the forced final turn can arrive.
        if (!failed && transport) {
          await new Promise((resolve) => {
            finishWait = resolve
            finalizeTimer = setTimeout(resolve, finalizeMs)
            try {
              if (transport.socket.readyState === 1) transport.socket.send(JSON.stringify({ type: 'force_endpoint' }))
              else fail()
            } catch { fail() }
          })
          finishWait = null
          clearTimeout(finalizeTimer)
          clearTimeout(revisionTimer)
        }
        publish({ manual_finalization_wait_ms: performance.now() - stopClickedAt })
        if (canceled) return
        let backupError
        const blob = await backup.catch((error) => { backupError = error; return null })
        if (canceled) return
        let text = previewText(state, partialOrder)
        let capture = { text, transcriptionMs: null, uploadMs: null }
        if (!liveEnabled || failed || !text) {
          if (backupError) throw backupError
          if (liveEnabled && !failed) { failed = true; onFallback() }
          capture = await transcribe(blob)
          text = String(capture.text || '').trim()
        }
        if (canceled) return
        closing = true
        transport?.close()
        stopTracks()
        // Common batch hallucination is never a question.
        const hallucination = /^thank you for watching[.!?\s]*$/i.test(text)
        let question = ''
        if (text && !hallucination) {
          const detectionStartedAt = performance.now()
          publish({ manual_question_detection_started_at: detectionStartedAt, stop_to_question_detection_ms: detectionStartedAt - stopClickedAt })
          question = await detectQuestion(text)
        }
        if (canceled) return
        if (!question) {
          publish({ phase: 'idle', pendingGeneration: false, detectedQuestion: '' })
          onTranscript('')
          return
        }
        publish({ phase: 'generating', detectedQuestion: question, pendingGeneration: false })
        onTranscript(question)
        await generate({ ...capture, recordingMs, text: question, historyEntryId: state.historyEntryId })
        if (!canceled) publish({ phase: 'idle' })
      } catch (error) {
        if (!canceled) publish({ phase: 'error', pendingGeneration: false })
        if (!canceled) throw error
      } finally { release() }
    })()
    return finishing
  }
  const cancel = () => {
    if (canceled) return
    canceled = true
    finishWait?.()
    try {
      if (recorder.state !== 'inactive') recorder.stop()
    } finally {
      resolveBackup(new Blob())
      release()
    }
  }
  return { stop, cancel }
}

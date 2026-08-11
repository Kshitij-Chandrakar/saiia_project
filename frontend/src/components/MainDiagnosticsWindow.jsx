import React, { useEffect, useRef, useState } from 'react'
import { createDesktopAuthRequestTracker, getDesktopAuthViewModel } from '../desktop_auth_ui.js'
import { extractCopyableCode } from '../screen_mode_state.js'

function formatTimeLabel(value) {
  if (!value) {
    return ''
  }
  const date = new Date(value)
  return date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function MetaRow({ label, value }) {
  return (
    <div className="meta-row">
      <span className="meta-row__label">{label}</span>
      <span className="meta-row__value">{value}</span>
    </div>
  )
}

function DesktopAuthStatus() {
  const [authState, setAuthState] = useState(() => getDesktopAuthViewModel())
  const [busyAction, setBusyAction] = useState('')
  const authRequestTrackerRef = useRef(createDesktopAuthRequestTracker())
  const saiiaApi = typeof window !== 'undefined' ? window.saiia : null

  const applyAuthState = (payload, requestId) => {
    if (!authRequestTrackerRef.current.isCurrent(requestId)) {
      return
    }
    setAuthState(getDesktopAuthViewModel(payload))
  }

  const runAuthAction = async (action, task) => {
    if (busyAction || typeof task !== 'function') {
      return
    }
    const requestId = authRequestTrackerRef.current.start()
    setBusyAction(action)
    try {
      applyAuthState(await task(), requestId)
    } catch {
      applyAuthState({ status: 'offline', error: 'Cloud temporarily unavailable.' }, requestId)
    } finally {
      if (authRequestTrackerRef.current.isCurrent(requestId)) {
        setBusyAction('')
      }
    }
  }

  useEffect(() => {
    let active = true
    const requestId = authRequestTrackerRef.current.start()
    const loadStartupContext = saiiaApi?.getCloudStartupContext || saiiaApi?.getAuthState
    loadStartupContext?.()
      .then((state) => {
        if (active) {
          applyAuthState(state, requestId)
        }
      })
      .catch(() => {
        if (active) {
          applyAuthState({ status: 'signed-out' }, requestId)
        }
      })
    return () => {
      active = false
    }
  }, [saiiaApi])

  return (
    <div className="glass-card desktop-auth-card" aria-label="Cloud auth status">
      <div className="desktop-auth-card__body">
        <div>
          <span className="section-label">intervuAI cloud</span>
          <p className="desktop-auth-card__title">{authState.label}</p>
          <p className="desktop-auth-card__detail">{authState.detail}</p>
          {authState.email ? (
            <p className="desktop-auth-card__identity">{authState.email}</p>
          ) : null}
          <p className="desktop-auth-card__cloud">{authState.cloudLabel}</p>
          <p className="desktop-auth-card__detail">{authState.cloudDetail}</p>
        </div>
        <div className="desktop-auth-card__actions">
          {authState.showLogin ? (
            <button
              className="icon-pill"
              type="button"
              disabled={authState.loginDisabled || Boolean(busyAction)}
              onClick={() => runAuthAction('login', saiiaApi?.startAuthLogin)}
            >
              {busyAction === 'login' ? 'Opening login...' : 'Login'}
            </button>
          ) : null}
          {authState.showRefresh ? (
            <button
              className="icon-pill icon-pill--ghost"
              type="button"
              disabled={Boolean(busyAction)}
              onClick={() => runAuthAction('refresh', saiiaApi?.refreshCloudStartupContext)}
            >
              Refresh status
            </button>
          ) : null}
          {authState.showLogout ? (
            <button
              className="icon-pill icon-pill--ghost"
              type="button"
              disabled={Boolean(busyAction)}
              onClick={() => runAuthAction('logout', saiiaApi?.logoutAuth)}
            >
              Logout
            </button>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function getReadableErrorAction(message) {
  const value = String(message || '').trim()
  if (!value) {
    return ''
  }

  if (/active window|identified|target question window|focus the question window/i.test(value)) {
    return 'Focus the question window first, then run Analyze Active Window again. If SAIIA still cannot identify it, use the screen source picker or browser extension path.'
  }

  if (/profile|complete your profile/i.test(value)) {
    return 'Open Setup Profile, complete the required details, then retry the answer.'
  }

  if (/network|failed to fetch|backend|server/i.test(value)) {
    return 'Check that the backend is running and reachable, then retry the request.'
  }

  if (/no clear question|no readable question|no question|problem found/i.test(value)) {
    return 'Bring the full question, examples, and constraints into view, then analyze the screen again.'
  }

  if (/microphone|audio source|system audio|loopback/i.test(value)) {
    return 'Select an audio source, confirm Windows has granted access, then start listening again.'
  }

  return 'Retry the action after fixing the visible cause. Check Live diagnostics below if the same error repeats.'
}

function getRuntimeGuidance({
  status,
  error,
  recording,
  manualProcessing,
  audioPipelineStatus,
  autoMode,
  autoModeStatus,
  answerPipelineState,
  generationStarted,
  generationBlockedReason,
  cooldownRemainingMs,
  pendingCooldownQuestion,
  ocrProcessing,
  screenAnswerLoading,
  screenAnswerGenerated,
  screenError,
  answer,
  transcript,
}) {
  const visibleError = String(error || screenError || '').trim()
  if (visibleError) {
    return {
      tone: 'danger',
      phase: 'Needs attention',
      headline: 'SAIIA could not finish the last action.',
      detail: visibleError,
      action: getReadableErrorAction(visibleError),
      steps: [
        { label: 'Started request', state: 'done' },
        { label: 'Hit a recoverable error', state: 'active' },
        { label: 'Waiting for your next action', state: 'pending' },
      ],
    }
  }

  if (ocrProcessing) {
    return {
      tone: 'info',
      phase: 'Analyzing screen',
      headline: 'Reading the active question window.',
      detail: 'SAIIA is capturing the selected window and extracting the question before generating an answer.',
      action: 'Keep the question window visible until analysis finishes.',
      steps: [
        { label: 'Capture window', state: 'active' },
        { label: 'Extract question', state: 'pending' },
        { label: 'Generate answer', state: 'pending' },
      ],
    }
  }

  if (screenAnswerLoading) {
    return {
      tone: 'info',
      phase: 'Generating screen answer',
      headline: 'Question captured. Building the answer now.',
      detail: 'SAIIA has screen text and is asking the answer model for the final response.',
      action: 'Wait for the answer panel to update.',
      steps: [
        { label: 'Capture window', state: 'done' },
        { label: 'Extract question', state: 'done' },
        { label: 'Generate answer', state: 'active' },
      ],
    }
  }

  if (manualProcessing || audioPipelineStatus === 'transcribing') {
    return {
      tone: 'info',
      phase: 'Transcribing',
      headline: 'Converting speech into a question.',
      detail: 'SAIIA is processing the recording before it classifies and answers it.',
      action: 'Keep the app open while transcription finishes.',
      steps: [
        { label: 'Record audio', state: 'done' },
        { label: 'Transcribe speech', state: 'active' },
        { label: 'Generate answer', state: 'pending' },
      ],
    }
  }

  if (generationStarted || answerPipelineState === 'generating' || audioPipelineStatus === 'generating') {
    return {
      tone: 'info',
      phase: 'Generating answer',
      headline: 'SAIIA is writing the answer.',
      detail: transcript ? `Question: ${transcript}` : 'The answer stream will appear in the overlay when the first text arrives.',
      action: 'Do not start another request until this one finishes.',
      steps: [
        { label: 'Question detected', state: 'done' },
        { label: 'Build prompt', state: 'done' },
        { label: 'Stream answer', state: 'active' },
      ],
    }
  }

  if (answerPipelineState === 'cooldown' || autoModeStatus === 'cooldown') {
    const seconds = Math.max(1, Math.ceil(Number(cooldownRemainingMs || 0) / 1000))
    return {
      tone: 'warning',
      phase: 'Cooldown',
      headline: 'Auto Mode is waiting before the next answer.',
      detail: pendingCooldownQuestion
        ? `Queued next question: ${pendingCooldownQuestion}`
        : `Listening continues. New auto answers resume in about ${seconds}s.`,
      action: 'This prevents duplicate answers from repeated transcripts.',
      steps: [
        { label: 'Previous answer complete', state: 'done' },
        { label: 'Listening during cooldown', state: 'active' },
        { label: 'Next question allowed', state: 'pending' },
      ],
    }
  }

  if (recording || audioPipelineStatus === 'recording') {
    return {
      tone: 'info',
      phase: 'Listening',
      headline: 'SAIIA is listening for the question.',
      detail: autoMode ? 'Auto Mode will detect questions and answer them without another click.' : 'Stop the recording when the question is complete.',
      action: autoMode ? 'Speak naturally and wait for a detected question.' : 'Click Stop & Process after the interviewer finishes.',
      steps: [
        { label: 'Listen', state: 'active' },
        { label: 'Detect question', state: 'pending' },
        { label: 'Generate answer', state: 'pending' },
      ],
    }
  }

  if (screenAnswerGenerated || answer) {
    return {
      tone: 'success',
      phase: 'Ready',
      headline: 'Latest answer is ready.',
      detail: status || 'The overlay has the latest generated answer.',
      action: 'Use the overlay answer, or run another action when the next question appears.',
      steps: [
        { label: 'Question captured', state: 'done' },
        { label: 'Answer generated', state: 'done' },
        { label: 'Ready for next question', state: 'active' },
      ],
    }
  }

  if (generationBlockedReason) {
    return {
      tone: 'warning',
      phase: 'Waiting',
      headline: 'A request is queued or blocked.',
      detail: `Reason: ${generationBlockedReason}`,
      action: 'Wait for the current operation to finish, then retry if nothing starts automatically.',
      steps: [
        { label: 'Question detected', state: 'done' },
        { label: 'Blocked by current state', state: 'active' },
        { label: 'Generate answer', state: 'pending' },
      ],
    }
  }

  return {
    tone: 'neutral',
    phase: 'Idle',
    headline: 'Ready for the next interview prompt.',
    detail: status || 'Choose recording, Auto Mode, Chat, or Analyze Active Window.',
    action: 'Focus the source first: microphone for speech, question window for screen analysis.',
    steps: [
      { label: 'Choose input', state: 'active' },
      { label: 'Capture question', state: 'pending' },
      { label: 'Generate answer', state: 'pending' },
    ],
  }
}

async function copyToClipboard(text) {
  const value = String(text || '')
  if (!value.trim()) {
    return
  }

  if (navigator?.clipboard?.writeText) {
    await navigator.clipboard.writeText(value)
    return
  }

  const textarea = document.createElement('textarea')
  textarea.value = value
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'absolute'
  textarea.style.left = '-9999px'
  document.body.appendChild(textarea)
  textarea.select()
  document.execCommand('copy')
  document.body.removeChild(textarea)
}

function extractCodeBlock(text) {
  const value = String(text || '')
  const match = value.match(/```([\w+-]*)\n([\s\S]*?)```/)
  if (!match) {
    return { language: '', code: '' }
  }

  return {
    language: String(match[1] || '').trim().toLowerCase(),
    code: String(match[2] || '').replace(/\s+$/, ''),
  }
}

export default function MainDiagnosticsWindow(props) {
  const {
    isCollapsed,
    setIsCollapsed,
    fontSize,
    setFontSize,
    overlayVisible,
    handleOverlayToggle,
    recording,
    manualProcessing,
    audioPipelineStatus,
    selectedAudioSource,
    activeAudioSource,
    systemAudioSupported,
    systemAudioDeviceName,
    systemAudioDefaultDeviceName,
    systemAudioInputSampleRate,
    systemAudioSampleRate,
    systemAudioRmsLevel,
    systemAudioPeakLevel,
    systemAudioChunkBytesSent,
    systemAudioDroppedSilenceChunks,
    systemAudioClippingDetected,
    systemAudioQualityWarning,
    systemAudioDebugWavPath,
    systemAudioEffectiveGain,
    systemAudioEnabled,
    microphoneEnabled,
    autoMode,
    autoModeStatus,
    autoModeSource,
    autoStartClicked,
    lastAutoTranscript,
    rawFinalTranscript,
    lastDetectedQuestion,
    acceptedAutoQuestion,
    autoRejectedReason,
    extractedQuestionCandidate,
    polishedQuestionCandidate,
    correctedQuestionCandidate,
    technicalCorrectionsSummary,
    possibleSttError,
    questionCandidateSource,
    questionDetectionInput,
    questionDetectReason,
    isQuestionDetected,
    cooldownRemainingMs,
    recentTranscriptBuffer,
    pendingAutoQuestion,
    pendingCooldownQuestion,
    pendingCooldownQuestionAgeMs,
    cooldownQueueReason,
    queuedQuestionProcessed,
    generationStarted,
    generationBlockedReason,
    isCooldownListening,
    autoStreamingConnected,
    partialAutoTranscript,
    streamingError,
    autoProcessing,
    ocrProcessing,
    handleRecordToggle,
    startAutoMode,
    stopAutoMode,
    handleScreenCapture,
    status,
    error,
    lastError,
    transcript,
    category,
    provider,
    primaryProvider,
    primaryModel,
    refinementProvider,
    refinementModel,
    refinementUsed,
    refinementStatus,
    refinementMessage,
    displayedAnswerSource,
    displayedAutoQuestionRunId,
    currentAutoQuestionRunId,
    micStreamingState,
    answerPipelineState,
    micStreamRestartCount,
    lastMicStreamRestartReason,
    totalPipelineMs,
    pipelineTimings,
    codingRuntimeAudit,
    sttProvider,
    sttFallbackUsed,
    sttFallbackReason,
    performanceMode,
    answer,
    profileSetupUrl,
    ocrText,
    ocrConfidence,
    screenVisionProvider,
    screenVisionModel,
    screenCaptureTarget,
    screenWindowTitle,
    screenProcessName,
    screenImageWidth,
    screenImageHeight,
    rawScreenVisionText,
    rawScreenVisionJson,
    screenCleanedText,
    extractedScreenQuestion,
    screenQuestionType,
    screenConfidence,
    screenCaptureMs,
    screenFallbackOcrUsed,
    screenScreenshotHidSaiiaWindows,
    screenDebugPath,
    screenPlatformDetected,
    screenCropUsed,
    screenCropRegion,
    screenSourceRegion,
    screenExtractionRetryReason,
    screenRejectedUiNoise,
    screenRejectedCodeBoilerplate,
    screenUiNoiseRatio,
    screenRejectReason,
    rawFullWindowVisionJson,
    rawCroppedVisionJson,
    finalExtractedScreenQuestion,
    screenValidProblemFound,
    groqVisionAttempted,
    groqVisionSuccess,
    groqVisionError,
    groqVisionHttpStatus,
    groqVisionRawResponsePreview,
    groqVisionParseError,
    groqVisionTimeout,
    screenFallbackReason,
    screenAnswerGenerated,
    screenError,
    screenAnalyzeMode,
    screenNeedsMoreContent,
    screenFullCaptureEnabled,
    screenFullProblemCaptureUsed,
    screenCaptureCount,
    screenScrollPositions,
    screenDuplicateCaptureStopped,
    screenBottomReached,
    screenRestoredScrollPosition,
    screenDiagramDetected,
    screenChartDetected,
    finalMergedProblem,
    screenForceTechnical,
    screenCodingAnswerMode,
    screenProfileContextUsed,
    screenAutoGenerate,
    screenAnswerText,
    screenCodeAnswer,
    screenCodeLanguage,
    screenAnswerDisplayedInPanel,
    screenAnswerCommittedToOverlay,
    screenPanelMode,
    screenAnswerLoading,
    eventLog,
    refinedAnswer,
    applyRefinedAnswer,
  } = props

  const fallbackScreenAnswerText =
    !screenAnswerText && screenAnswerGenerated ? String(answer || '').trim() : ''
  const progressiveScreenAnswerText =
    screenAnswerCommittedToOverlay && answer ? String(answer || '').trim() : ''
  const effectiveScreenAnswerText = screenAnswerCommittedToOverlay
    ? progressiveScreenAnswerText || fallbackScreenAnswerText
    : screenAnswerText || fallbackScreenAnswerText
  const derivedCodeBlock = !screenCodeAnswer && effectiveScreenAnswerText
    ? extractCodeBlock(effectiveScreenAnswerText)
    : { language: '', code: '' }
  const effectiveScreenCode = screenCodeAnswer || derivedCodeBlock.code
  const effectiveScreenCodeLanguage =
    screenCodeLanguage || derivedCodeBlock.language || (screenCodingAnswerMode ? 'python' : '')
  const copyableScreenCode = extractCopyableCode({
    screenAnswerText: effectiveScreenAnswerText,
    screenCodeAnswer,
    screenCodeLanguage,
  })
  const showScreenAnswerMode =
    screenPanelMode === 'answer' || Boolean(screenAnswerGenerated && effectiveScreenAnswerText)
  const hideGenericDisplayedAnswer = Boolean(showScreenAnswerMode && effectiveScreenAnswerText)
  const screenBusy = Boolean(ocrProcessing || screenAnswerLoading)
  const runtimeGuidance = getRuntimeGuidance({
    status,
    error,
    recording,
    manualProcessing,
    audioPipelineStatus,
    autoMode,
    autoModeStatus,
    answerPipelineState,
    generationStarted,
    generationBlockedReason,
    cooldownRemainingMs,
    pendingCooldownQuestion,
    ocrProcessing,
    screenAnswerLoading,
    screenAnswerGenerated,
    screenError,
    answer,
    transcript,
  })
  const handleUseExtension = async () => {
    await window.electronAPI?.triggerToolbarAction?.('analyze-screen-extension')
  }

  if (isCollapsed) {
    return (
      <div className="glass-window">
        <div className="glass-window__shell glass-window__shell--collapsed">
          <button
            className="diagnostics-handle glass-panel glass-panel--strong"
            onClick={() => setIsCollapsed(false)}
            aria-label="Expand diagnostics panel"
          >
            <span>Open SAIIA</span>
            <span>›</span>
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="glass-window">
      <div className="glass-window__shell glass-panel glass-panel--strong">
        <div className="diagnostics-shell">
          <div className="drag-titlebar">
            <div className="drag-titlebar__meta">
              <h1 className="window-title">SAIIA Runtime Panel</h1>
              <p className="window-subtitle">
                Reading this as: a desktop product surface for live interview support, with a discreet glass language and restrained motion.
              </p>
            </div>

            <div className="titlebar-actions">
              <span className="status-pill">
                <span className="status-pill__dot" />
                {overlayVisible ? 'Overlay visible' : 'Overlay hidden'}
              </span>
              <button
                className="icon-pill icon-pill--ghost"
                onClick={() => setIsCollapsed(true)}
                aria-label="Collapse diagnostics panel"
              >
                ‹
              </button>
            </div>
          </div>

          <div className="diagnostics-scroll">
            <div className="button-row">
              <button
                className="icon-pill"
                onClick={() => window.open(profileSetupUrl, '_blank', 'width=500,height=600')}
              >
                Setup Profile
              </button>

              <button className="icon-pill" onClick={handleOverlayToggle}>
                {overlayVisible ? 'Hide Overlay' : 'Show Overlay'}
              </button>

              <button
                className="icon-pill"
                onClick={handleRecordToggle}
                disabled={autoMode || autoProcessing || ocrProcessing || manualProcessing}
              >
                {manualProcessing
                  ? 'Processing Recording...'
                  : recording && !autoMode
                    ? 'Stop & Process'
                    : 'Start Recording (Fallback)'}
              </button>

              <button
                className="icon-pill"
                onClick={autoMode ? stopAutoMode : startAutoMode}
                disabled={(recording && !autoMode) || ocrProcessing}
              >
                {autoMode ? 'Stop Auto Mode' : 'Start Auto Mode'}
              </button>

              <button
                className="icon-pill"
                onClick={handleScreenCapture}
                disabled={recording || autoMode || autoProcessing || ocrProcessing}
              >
                {ocrProcessing ? 'Analyzing Active Window...' : 'Analyze Active Window'}
              </button>
            </div>

            <div className="range-control glass-card">
              <span className="section-label">Overlay answer font</span>
              <input
                type="range"
                min="10"
                max="30"
                value={fontSize}
                onChange={(event) => setFontSize(Number(event.target.value))}
              />
              <strong>{fontSize}px</strong>
              <span className="window-subtitle">Ctrl+H still toggles the floating overlay.</span>
            </div>

            <p className="diagnostics-note">
              The main panel stays focused on profile access, pipeline diagnostics, OCR review,
              and the latest answer state. The live overlay remains the primary interview
              display.
            </p>

            <DesktopAuthStatus />

            <div className={`glass-card runtime-guide runtime-guide--${runtimeGuidance.tone}`}>
              <div className="runtime-guide__header">
                <span className="runtime-guide__phase">
                  <span className="status-pill__dot" />
                  {runtimeGuidance.phase}
                </span>
                {status ? <span className="runtime-guide__raw">{status}</span> : null}
              </div>
              <div className="runtime-guide__body">
                <div>
                  <p className="runtime-guide__headline">{runtimeGuidance.headline}</p>
                  <p className="runtime-guide__detail">{runtimeGuidance.detail}</p>
                  {runtimeGuidance.action ? (
                    <p className="runtime-guide__action">{runtimeGuidance.action}</p>
                  ) : null}
                </div>
                <div className="runtime-steps" aria-label="Runtime progress">
                  {runtimeGuidance.steps.map((step) => (
                    <div
                      key={step.label}
                      className={`runtime-step runtime-step--${step.state}`}
                    >
                      <span className="runtime-step__marker" />
                      <span>{step.label}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {(ocrText || ocrProcessing || screenAnswerText || screenAnswerLoading) && (
              <div className="glass-card">
                <div className="ocr-preview">
                  <div>
                    <p className="section-title">Captured question preview - read-only diagnostics</p>
                    <p className="diagnostics-note">
                      OCR now sends one screenshot to the screen model and shows the final answer directly.
                    </p>
                  </div>
                  <MetaRow
                    label="Question"
                    value={finalExtractedScreenQuestion || extractedScreenQuestion || ocrText || 'No readable question/problem found yet.'}
                  />

                  {showScreenAnswerMode ? (
                    <div style={{ marginTop: '1rem' }}>
                      <p className="section-label" style={{ marginBottom: '0.5rem' }}>
                        {screenCodingAnswerMode ? 'Coding Solution' : 'Screen Answer'}
                      </p>
                      {effectiveScreenAnswerText ? (
                        <>
                          <div
                            className="scroll-panel"
                            style={{
                              maxHeight: '15rem',
                              whiteSpace: 'pre-wrap',
                              lineHeight: 1.55,
                            }}
                          >
                            {effectiveScreenAnswerText}
                          </div>

                          {effectiveScreenCode ? (
                            <div style={{ marginTop: '0.9rem' }}>
                              <p className="section-label" style={{ marginBottom: '0.5rem' }}>
                                Code{effectiveScreenCodeLanguage ? ` (${effectiveScreenCodeLanguage})` : ''}
                              </p>
                              <div
                                className="scroll-panel"
                                style={{
                                  maxHeight: '14rem',
                                  whiteSpace: 'pre',
                                  fontFamily: 'Consolas, Menlo, Monaco, monospace',
                                  fontSize: '0.92rem',
                                  lineHeight: 1.45,
                                }}
                              >
                                {effectiveScreenCode}
                              </div>
                            </div>
                          ) : null}
                        </>
                      ) : (
                        <p className="diagnostics-note">
                          {screenAnswerLoading ? 'Regenerating screen answer…' : 'Screen answer will appear here after generation.'}
                        </p>
                      )}

                      <div className="form-actions" style={{ marginTop: '1rem' }}>
                        {copyableScreenCode.code ? (
                          <button
                            type="button"
                            className="icon-pill"
                            aria-label="Copy Code"
                            onClick={() => copyToClipboard(copyableScreenCode.code)}
                          >
                            Copy Code
                          </button>
                        ) : null}
                        <button
                          type="button"
                          className="icon-pill"
                          onClick={handleScreenCapture}
                          disabled={screenBusy || recording}
                        >
                          Analyze Screen
                        </button>
                        <button
                          type="button"
                          className="icon-pill"
                          aria-label="Use Browser Extension"
                          onClick={handleUseExtension}
                          disabled={screenBusy}
                        >
                          Extension
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div
                        className="scroll-panel"
                        style={{
                          maxHeight: '10rem',
                          whiteSpace: 'pre-wrap',
                          lineHeight: 1.55,
                        }}
                      >
                        {ocrText || (ocrProcessing ? 'Analyzing question...' : 'No screen answer yet.')}
                      </div>
                      <MetaRow
                        label="Screen confidence"
                        value={
                          screenConfidence != null || ocrConfidence != null
                            ? `${Math.round(((screenConfidence ?? ocrConfidence) || 0) * 100)}%`
                            : 'Not available'
                        }
                      />
                      <div className="form-actions">
                        <button
                          type="button"
                          className="icon-pill"
                          onClick={handleScreenCapture}
                          disabled={screenBusy || recording}
                        >
                          Analyze Screen
                        </button>
                        <button
                          type="button"
                          className="icon-pill"
                          aria-label="Use Browser Extension"
                          onClick={handleUseExtension}
                          disabled={screenBusy}
                        >
                          Extension
                        </button>
                      </div>
                    </>
                  )}
                </div>
              </div>
            )}

            <div className="diagnostics-grid">
              <div className="glass-card">
                <p className="section-title">Live diagnostics</p>
                <div className="meta-list">
                  <MetaRow label="Transcript" value={transcript || 'No transcript yet'} />
                  <MetaRow label="Category" value={category || 'Waiting'} />
                  <MetaRow label="Provider" value={provider || 'Waiting'} />
                  <MetaRow label="Primary provider" value={primaryProvider || provider || 'Waiting'} />
                  <MetaRow label="Primary model" value={primaryModel || 'Waiting'} />
                  <MetaRow
                    label="Refinement provider"
                    value={
                      refinementProvider
                        ? `${refinementProvider} (${refinementStatus || 'pending'})`
                        : refinementStatus || 'Disabled'
                    }
                  />
                  <MetaRow label="Refinement model" value={refinementModel || 'n/a'} />
                  <MetaRow label="Refinement used" value={refinementUsed ? 'true' : 'false'} />
                  <MetaRow label="Displayed answer source" value={displayedAnswerSource || 'Waiting'} />
                  <MetaRow label="Displayed auto run" value={displayedAutoQuestionRunId || 'n/a'} />
                  <MetaRow label="Current auto run" value={currentAutoQuestionRunId || 'n/a'} />
                  <MetaRow
                    label="Selected input source"
                    value={selectedAudioSource || 'none'}
                  />
                  <MetaRow
                    label="Audio pipeline"
                    value={audioPipelineStatus || 'idle'}
                  />
                  <MetaRow
                    label="Auto mode"
                    value={autoMode ? 'on' : 'off'}
                  />
                  <MetaRow
                    label="Auto mode status"
                    value={autoModeStatus || 'off'}
                  />
                  <MetaRow
                    label="Auto mode source"
                    value={autoModeSource || 'none'}
                  />
                  <MetaRow
                    label="Mic streaming connected"
                    value={autoModeSource === 'microphone' && autoStreamingConnected ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="Mic streaming state"
                    value={micStreamingState || 'off'}
                  />
                  <MetaRow
                    label="Answer pipeline state"
                    value={answerPipelineState || 'idle'}
                  />
                  <MetaRow
                    label="Mic auto continuous"
                    value={autoMode && autoModeSource === 'microphone' ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="Mic stream restarts"
                    value={String(micStreamRestartCount || 0)}
                  />
                  <MetaRow
                    label="Last mic restart"
                    value={lastMicStreamRestartReason || 'n/a'}
                  />
                  <MetaRow
                    label="Auto chunk"
                    value={autoModeSource === 'system' ? '3000 ms' : '4000 ms'}
                  />
                  <MetaRow
                    label="Auto cooldown"
                    value="4000 ms"
                  />
                  <MetaRow
                    label="Auto STT provider"
                    value={sttProvider || 'n/a'}
                  />
                  <MetaRow
                    label="Streaming connected"
                    value={autoStreamingConnected ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="Auto start clicked"
                    value={autoStartClicked ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="Cooldown listening"
                    value={isCooldownListening ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="Active audio source"
                    value={activeAudioSource || 'none'}
                  />
                  <MetaRow
                    label="System audio supported"
                    value={systemAudioSupported ? 'Yes' : 'No'}
                  />
                  <MetaRow
                    label="System audio device"
                    value={systemAudioDeviceName || 'Not detected'}
                  />
                  <MetaRow
                    label="Default loopback"
                    value={systemAudioDefaultDeviceName || 'Not detected'}
                  />
                  <MetaRow
                    label="System input rate"
                    value={systemAudioInputSampleRate != null ? `${systemAudioInputSampleRate} Hz` : 'n/a'}
                  />
                  <MetaRow
                    label="System target rate"
                    value={systemAudioSampleRate != null ? `${systemAudioSampleRate} Hz` : 'n/a'}
                  />
                  <MetaRow
                    label="System RMS"
                    value={systemAudioRmsLevel != null ? String(systemAudioRmsLevel) : 'n/a'}
                  />
                  <MetaRow
                    label="System peak"
                    value={systemAudioPeakLevel != null ? String(systemAudioPeakLevel) : 'n/a'}
                  />
                  <MetaRow
                    label="Effective gain"
                    value={systemAudioEffectiveGain != null ? `${systemAudioEffectiveGain}x` : 'n/a'}
                  />
                  <MetaRow
                    label="Bytes sent/sec"
                    value={systemAudioChunkBytesSent ? String(systemAudioChunkBytesSent) : '0'}
                  />
                  <MetaRow
                    label="Dropped chunks"
                    value={String(systemAudioDroppedSilenceChunks || 0)}
                  />
                  <MetaRow
                    label="Clipping detected"
                    value={systemAudioClippingDetected ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="Quality warning"
                    value={systemAudioQualityWarning || 'n/a'}
                  />
                  <MetaRow
                    label="Debug WAV"
                    value={systemAudioDebugWavPath || 'n/a'}
                  />
                  <MetaRow
                    label="analyze_screen_provider"
                    value={screenVisionProvider || 'n/a'}
                  />
                  <MetaRow
                    label="screen_vision_model"
                    value={screenVisionModel || 'n/a'}
                  />
                  <MetaRow
                    label="groq_vision_attempted"
                    value={groqVisionAttempted ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="groq_vision_success"
                    value={groqVisionSuccess ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="groq_vision_error"
                    value={groqVisionError || 'n/a'}
                  />
                  <MetaRow
                    label="groq_vision_http_status"
                    value={groqVisionHttpStatus != null ? String(groqVisionHttpStatus) : 'n/a'}
                  />
                  <MetaRow
                    label="groq_vision_timeout"
                    value={groqVisionTimeout ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="fallback_reason"
                    value={screenFallbackReason || 'n/a'}
                  />
                  <MetaRow
                    label="nvidia_screen_provider_removed"
                    value="true"
                  />
                  <MetaRow
                    label="capture_target"
                    value={screenCaptureTarget || 'active_window'}
                  />
                  <MetaRow
                    label="target_window_title"
                    value={screenWindowTitle || 'n/a'}
                  />
                  <MetaRow
                    label="target_process_name"
                    value={screenProcessName || 'n/a'}
                  />
                  <MetaRow
                    label="screen_platform_detected"
                    value={screenPlatformDetected || 'unknown'}
                  />
                  <MetaRow
                    label="analyze_mode"
                    value={screenAnalyzeMode || 'visible_window'}
                  />
                  <MetaRow
                    label="needs_more_screen_content"
                    value={screenNeedsMoreContent ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="full_capture_enabled"
                    value={screenFullCaptureEnabled ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="full_problem_capture_used"
                    value={screenFullProblemCaptureUsed ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="capture_count"
                    value={String(screenCaptureCount || 1)}
                  />
                  <MetaRow
                    label="scroll_positions"
                    value={screenScrollPositions || 'n/a'}
                  />
                  <MetaRow
                    label="duplicate_capture_stopped"
                    value={screenDuplicateCaptureStopped ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="bottom_reached"
                    value={screenBottomReached ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="restored_scroll_position"
                    value={screenRestoredScrollPosition ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="diagram_detected"
                    value={screenDiagramDetected ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="chart_detected"
                    value={screenChartDetected ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="Image size"
                    value={
                      screenImageWidth && screenImageHeight
                        ? `${screenImageWidth} x ${screenImageHeight}`
                        : 'n/a'
                    }
                  />
                  <MetaRow
                    label="Extracted screen question"
                    value={extractedScreenQuestion || 'n/a'}
                  />
                  <MetaRow
                    label="Screen question type"
                    value={screenQuestionType || 'none'}
                  />
                  <MetaRow
                    label="old_ocr_fallback_used"
                    value={screenFallbackOcrUsed ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="saiia_windows_hidden_before_capture"
                    value={screenScreenshotHidSaiiaWindows ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="screenshot_debug_path"
                    value={screenDebugPath || 'n/a'}
                  />
                  <MetaRow
                    label="crop_used"
                    value={screenCropUsed ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="crop_region"
                    value={screenCropRegion || 'n/a'}
                  />
                  <MetaRow
                    label="source_region"
                    value={screenSourceRegion || 'unknown'}
                  />
                  <MetaRow
                    label="extraction_retry_reason"
                    value={screenExtractionRetryReason || 'n/a'}
                  />
                  <MetaRow
                    label="rejected_ui_noise"
                    value={screenRejectedUiNoise ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="rejected_code_boilerplate"
                    value={screenRejectedCodeBoilerplate ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="ui_noise_ratio"
                    value={screenUiNoiseRatio ? `${Math.round(screenUiNoiseRatio * 100)}%` : '0%'}
                  />
                  <MetaRow
                    label="reject_reason"
                    value={screenRejectReason || 'n/a'}
                  />
                  <MetaRow
                    label="valid_problem_found"
                    value={screenValidProblemFound ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="final_merged_problem"
                    value={finalMergedProblem || 'n/a'}
                  />
                  <MetaRow
                    label="force_technical"
                    value={screenForceTechnical ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="coding_answer_mode"
                    value={screenCodingAnswerMode ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="profile_context_used"
                    value={screenProfileContextUsed ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="screen_auto_generate"
                    value={screenAutoGenerate ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="screen_answer_text"
                    value={screenAnswerText || 'n/a'}
                  />
                  <MetaRow
                    label="screen_code_answer"
                    value={screenCodeAnswer || 'n/a'}
                  />
                  <MetaRow
                    label="screen_code_language"
                    value={screenCodeLanguage || 'n/a'}
                  />
                  <MetaRow
                    label="screen_answer_generated"
                    value={screenAnswerGenerated ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="screen_answer_displayed_in_panel"
                    value={screenAnswerDisplayedInPanel ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="screen_answer_committed_to_overlay"
                    value={screenAnswerCommittedToOverlay ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="screen_error"
                    value={screenError || 'n/a'}
                  />
                  <MetaRow
                    label="audit_request_question_excerpt"
                    value={codingRuntimeAudit?.request_question_excerpt || 'n/a'}
                  />
                  <MetaRow
                    label="audit_full_problem_text_present"
                    value={codingRuntimeAudit?.full_problem_text_present ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="audit_full_problem_text_excerpt"
                    value={codingRuntimeAudit?.full_problem_text_excerpt || 'n/a'}
                  />
                  <MetaRow
                    label="audit_editor_text_present"
                    value={codingRuntimeAudit?.editor_text_present ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="audit_editor_text_excerpt"
                    value={codingRuntimeAudit?.editor_text_excerpt || 'n/a'}
                  />
                  <MetaRow
                    label="audit_generation_question_excerpt"
                    value={codingRuntimeAudit?.generation_question_excerpt || 'n/a'}
                  />
                  <MetaRow
                    label="audit_code_generation_mode"
                    value={codingRuntimeAudit?.code_generation_mode || 'n/a'}
                  />
                  <MetaRow
                    label="audit_function_stub_detected"
                    value={codingRuntimeAudit?.function_stub_detected ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="audit_function_name"
                    value={codingRuntimeAudit?.function_name || 'n/a'}
                  />
                  <MetaRow
                    label="audit_required_stub_preserved"
                    value={codingRuntimeAudit?.required_stub_preserved == null ? 'n/a' : codingRuntimeAudit.required_stub_preserved ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="audit_standalone_solution_rejected"
                    value={codingRuntimeAudit?.standalone_solution_rejected == null ? 'n/a' : codingRuntimeAudit.standalone_solution_rejected ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="audit_code_validation_passed"
                    value={codingRuntimeAudit?.code_validation_passed == null ? 'n/a' : codingRuntimeAudit.code_validation_passed ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="audit_correction_pass_used"
                    value={codingRuntimeAudit?.correction_pass_used == null ? 'n/a' : codingRuntimeAudit.correction_pass_used ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="Capture time"
                    value={screenCaptureMs ? `${screenCaptureMs} ms` : 'n/a'}
                  />
                  <MetaRow
                    label="Total pipeline"
                    value={totalPipelineMs != null ? `${totalPipelineMs} ms` : 'Waiting'}
                  />
                  <MetaRow
                    label="Recording"
                    value={pipelineTimings?.recording_ms != null ? `${pipelineTimings.recording_ms} ms` : 'n/a'}
                  />
                  <MetaRow
                    label="Upload"
                    value={pipelineTimings?.upload_ms != null ? `${pipelineTimings.upload_ms} ms` : 'n/a'}
                  />
                  <MetaRow
                    label="Image prepare"
                    value={pipelineTimings?.image_prepare_ms != null ? `${pipelineTimings.image_prepare_ms} ms` : 'n/a'}
                  />
                  <MetaRow
                    label="Screen model"
                    value={pipelineTimings?.screen_model_ms != null ? `${pipelineTimings.screen_model_ms} ms` : 'n/a'}
                  />
                  <MetaRow
                    label="Response parse"
                    value={pipelineTimings?.response_parse_ms != null ? `${pipelineTimings.response_parse_ms} ms` : 'n/a'}
                  />
                  <MetaRow
                    label="Overlay render"
                    value={pipelineTimings?.overlay_render_ms != null ? `${pipelineTimings.overlay_render_ms} ms` : 'n/a'}
                  />
                  <MetaRow
                    label="Original image"
                    value={pipelineTimings?.original_image_width ? `${pipelineTimings.original_image_width}x${pipelineTimings.original_image_height}` : 'n/a'}
                  />
                  <MetaRow
                    label="Sent image"
                    value={pipelineTimings?.sent_image_width ? `${pipelineTimings.sent_image_width}x${pipelineTimings.sent_image_height}` : 'n/a'}
                  />
                  <MetaRow
                    label="Encoded image"
                    value={pipelineTimings?.encoded_image_bytes ? `${pipelineTimings.encoded_image_bytes} bytes` : 'n/a'}
                  />
                  <MetaRow
                    label="Screen model requests"
                    value={pipelineTimings?.screen_model_request_count ?? 'n/a'}
                  />
                  <MetaRow
                    label="Questions answered"
                    value={pipelineTimings?.questions_answered ?? 'n/a'}
                  />
                  <MetaRow
                    label="Incomplete questions ignored"
                    value={pipelineTimings?.incomplete_questions_ignored ?? 'n/a'}
                  />
                  <MetaRow
                    label="Automatic fallbacks"
                    value={pipelineTimings?.automatic_fallback_count ?? 'n/a'}
                  />
                  <MetaRow
                    label="Correction requests"
                    value={pipelineTimings?.correction_request_count ?? 'n/a'}
                  />
                  <MetaRow
                    label="Transcription"
                    value={pipelineTimings?.transcription_ms != null ? `${pipelineTimings.transcription_ms} ms` : 'n/a'}
                  />
                  <MetaRow
                    label="STT provider"
                    value={sttProvider || pipelineTimings?.stt_provider || 'n/a'}
                  />
                  <MetaRow
                    label="STT fallback"
                    value={sttFallbackUsed || pipelineTimings?.stt_fallback_used ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="Fallback reason"
                    value={sttFallbackReason || pipelineTimings?.stt_fallback_reason || 'n/a'}
                  />
                  <MetaRow
                    label="Streaming error"
                    value={streamingError || 'n/a'}
                  />
                  <MetaRow
                    label="Classification"
                    value={pipelineTimings?.classification_ms != null ? `${pipelineTimings.classification_ms} ms` : 'n/a'}
                  />
                  <MetaRow
                    label="Profile load"
                    value={pipelineTimings?.profile_load_ms != null ? `${pipelineTimings.profile_load_ms} ms` : 'n/a'}
                  />
                  <MetaRow
                    label="RAG"
                    value={pipelineTimings?.rag_ms != null ? `${pipelineTimings.rag_ms} ms` : 'n/a'}
                  />
                  <MetaRow
                    label="Profile context policy"
                    value={pipelineTimings?.profile_context_policy || 'n/a'}
                  />
                  <MetaRow
                    label="Profile context used"
                    value={pipelineTimings?.profile_context_used == null ? 'n/a' : pipelineTimings.profile_context_used ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="Retrieved chunks"
                    value={pipelineTimings?.retrieved_chunk_count == null ? 'n/a' : String(pipelineTimings.retrieved_chunk_count)}
                  />
                  <MetaRow
                    label="Prompt build"
                    value={pipelineTimings?.prompt_build_ms != null ? `${pipelineTimings.prompt_build_ms} ms` : 'n/a'}
                  />
                  <MetaRow
                    label="Primary generation"
                    value={pipelineTimings?.primary_generation_ms != null ? `${pipelineTimings.primary_generation_ms} ms` : 'n/a'}
                  />
                  <MetaRow
                    label="Refinement generation"
                    value={pipelineTimings?.refinement_generation_ms != null ? `${pipelineTimings.refinement_generation_ms} ms` : 'n/a'}
                  />
                  <MetaRow
                    label="Answer received"
                    value={pipelineTimings?.answer_received_ms != null ? `${pipelineTimings.answer_received_ms} ms` : 'n/a'}
                  />
                  <MetaRow
                    label="First visible text"
                    value={pipelineTimings?.time_to_first_visible_text_ms != null ? `${pipelineTimings.time_to_first_visible_text_ms} ms` : 'n/a'}
                  />
                  <MetaRow
                    label="Overlay commit"
                    value={pipelineTimings?.overlay_commit_ms != null ? `${pipelineTimings.overlay_commit_ms} ms` : 'n/a'}
                  />
                  <MetaRow
                    label="Bar reset"
                    value={pipelineTimings?.bar_reset_ms != null ? `${pipelineTimings.bar_reset_ms} ms` : 'n/a'}
                  />
                  <MetaRow
                    label="Question detect"
                    value={pipelineTimings?.question_detect_ms != null ? `${pipelineTimings.question_detect_ms} ms` : 'n/a'}
                  />
                  <MetaRow
                    label="Frontend update"
                    value={pipelineTimings?.frontend_update_ms != null ? `${pipelineTimings.frontend_update_ms} ms` : 'n/a'}
                  />
                  <MetaRow
                    label="Last auto transcript"
                    value={lastAutoTranscript || 'n/a'}
                  />
                  <MetaRow
                    label="Raw final transcript"
                    value={rawFinalTranscript || 'n/a'}
                  />
                  <MetaRow
                    label="Partial transcript"
                    value={partialAutoTranscript || 'n/a'}
                  />
                  <MetaRow
                    label="Recent transcript buffer"
                    value={recentTranscriptBuffer || 'n/a'}
                  />
                  <MetaRow
                    label="Extracted candidate"
                    value={extractedQuestionCandidate || 'n/a'}
                  />
                  <MetaRow
                    label="Polished candidate"
                    value={polishedQuestionCandidate || 'n/a'}
                  />
                  <MetaRow
                    label="Corrected candidate"
                    value={correctedQuestionCandidate || 'n/a'}
                  />
                  <MetaRow
                    label="Corrections"
                    value={technicalCorrectionsSummary || 'n/a'}
                  />
                  <MetaRow
                    label="Possible STT error"
                    value={possibleSttError ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="Candidate source"
                    value={questionCandidateSource || 'n/a'}
                  />
                  <MetaRow
                    label="Detection input"
                    value={questionDetectionInput || 'n/a'}
                  />
                  <MetaRow
                    label="Accepted auto question"
                    value={acceptedAutoQuestion || 'n/a'}
                  />
                  <MetaRow
                    label="Last detected question"
                    value={lastDetectedQuestion || 'n/a'}
                  />
                  <MetaRow
                    label="Is question"
                    value={isQuestionDetected ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="Question detect reason"
                    value={questionDetectReason || 'n/a'}
                  />
                  <MetaRow
                    label="Pending auto question"
                    value={pendingAutoQuestion || 'n/a'}
                  />
                  <MetaRow
                    label="Cooldown active"
                    value={cooldownRemainingMs > 0 ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="Pending cooldown question"
                    value={pendingCooldownQuestion || 'n/a'}
                  />
                  <MetaRow
                    label="Pending cooldown age"
                    value={pendingCooldownQuestionAgeMs ? `${pendingCooldownQuestionAgeMs} ms` : '0 ms'}
                  />
                  <MetaRow
                    label="Cooldown queue reason"
                    value={cooldownQueueReason || 'n/a'}
                  />
                  <MetaRow
                    label="Queued question processed"
                    value={queuedQuestionProcessed ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="Generation started"
                    value={generationStarted ? 'true' : 'false'}
                  />
                  <MetaRow
                    label="Generation blocked"
                    value={generationBlockedReason || 'n/a'}
                  />
                  <MetaRow
                    label="Rejected reason"
                    value={autoRejectedReason || 'n/a'}
                  />
                  <MetaRow
                    label="Cooldown remaining"
                    value={cooldownRemainingMs > 0 ? `${Math.ceil(cooldownRemainingMs / 1000)}s` : '0s'}
                  />
                </div>
              </div>

              <div className="glass-card">
                <p className="section-title">Runtime notes</p>
                <div className="meta-list">
                  <MetaRow
                    label="Mode"
                    value={
                      autoMode
                        ? 'Auto Mode'
                        : manualProcessing
                          ? 'Processing Recording'
                          : recording
                            ? 'Recording'
                            : 'Manual Mode'
                    }
                  />
                  <MetaRow
                    label="Mic selected"
                    value={microphoneEnabled ? 'On' : 'Off'}
                  />
                  <MetaRow
                    label="System selected"
                    value={systemAudioEnabled ? 'On' : 'Off'}
                  />
                  <MetaRow label="Overlay hotkey" value="Ctrl+H" />
                  <MetaRow label="Performance mode" value={performanceMode || 'standard'} />
                  <MetaRow label="Refinement status" value={refinementMessage || 'No refinement update'} />
                  <MetaRow label="Last error" value={lastError || 'No errors recorded'} />
                </div>
                {refinementStatus === 'completed' && refinedAnswer && (
                  <div className="form-actions" style={{ marginTop: '0.9rem' }}>
                    <button className="icon-pill" onClick={applyRefinedAnswer}>
                      Apply Refined Answer
                    </button>
                  </div>
                )}
              </div>
            </div>

            {(rawScreenVisionText || extractedScreenQuestion || screenError) && (
              <div className="glass-card">
                <p className="section-title">Screen Vision Diagnostics</p>
                <div className="meta-list">
                  <MetaRow
                    label="raw_vision_json"
                    value={rawScreenVisionJson || 'n/a'}
                  />
                  <MetaRow
                    label="groq_vision_raw_response_preview"
                    value={groqVisionRawResponsePreview || 'n/a'}
                  />
                  <MetaRow
                    label="groq_vision_parse_error"
                    value={groqVisionParseError || 'n/a'}
                  />
                  <MetaRow
                    label="raw_full_window_vision_json"
                    value={rawFullWindowVisionJson || 'n/a'}
                  />
                  <MetaRow
                    label="raw_cropped_vision_json"
                    value={rawCroppedVisionJson || 'n/a'}
                  />
                  <MetaRow
                    label="raw_vision_text"
                    value={rawScreenVisionText || 'n/a'}
                  />
                  <MetaRow
                    label="extracted_screen_question_cleaned"
                    value={screenCleanedText || 'n/a'}
                  />
                  <MetaRow
                    label="final_extracted_question"
                    value={finalExtractedScreenQuestion || 'n/a'}
                  />
                </div>
              </div>
            )}

            <div className="diagnostics-grid">
              {!hideGenericDisplayedAnswer && (
                <div className="glass-card">
                  <p className="section-title">Displayed answer</p>
                  <div className="answer-preview">
                    {answer || 'The active overlay answer will appear here once SAIIA completes a request.'}
                  </div>
                </div>
              )}

              <div className="glass-card">
                <p className="section-title">Runtime log</p>
                <div className="scroll-panel log-list">
                  {eventLog.length ? (
                    eventLog.map((entry) => (
                      <div
                        key={entry.id}
                        className={`log-row${entry.tone === 'error' ? ' log-row--error' : ''}`}
                      >
                        <span className="log-row__time">{formatTimeLabel(entry.time)}</span>
                        <span className="log-row__message">{entry.message}</span>
                      </div>
                    ))
                  ) : (
                    <p className="diagnostics-note">Runtime events will appear here as the pipeline moves.</p>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

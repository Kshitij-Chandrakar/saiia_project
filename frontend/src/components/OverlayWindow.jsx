import { useScreenContextStatus } from './useScreenContextStatus'
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ChevronDown,
  ChevronUp,
  Info,
  Laptop,
  LayoutDashboard,
  MessageSquare,
  Mic,
  Monitor,
  MoreVertical,
  Move,
  Plus,
  Minus,
  RotateCcw,
  Sparkles,
  Square,
  Trash2,
  User,
  X,
} from 'lucide-react'
import AnswerPanel from './AnswerPanel'
import {
  getAutoFocusedTabForAnswer,
  getPanelOverlayState,
  getPanelOwner,
  getTabForAnswerMode,
  snapshotOverlayState,
} from '../overlay_mode_state'
import { createOverlayAuthStateTracker } from '../overlay_auth_state_tracker'
import { ScreenContextChooser } from './ScreenContextControls'
import { screenContextCommandFence } from '../screen_context_events'

function formatElapsedTime(startedAt) {
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000))
  const minutes = String(Math.floor(elapsedSeconds / 60)).padStart(1, '0')
  const seconds = String(elapsedSeconds % 60).padStart(2, '0')
  return `${minutes}:${seconds}`
}

function getActivePanelQuestion(overlayState) {
  return overlayState.transcript || (['connecting', 'listening'].includes(overlayState.manualLiveState?.phase) ? 'Listening...' : 'No clear question detected yet.')
}

function getStatusSummary(overlayState) {
  const parts = []
  if (overlayState.provider) {
    parts.push(overlayState.provider)
  }
  if (overlayState.category) {
    parts.push(overlayState.category)
  }
  if (overlayState.answerRevealActive) {
    parts.push('streaming')
    return parts.join(' Â· ')
  }
  if (overlayState.totalPipelineMs != null) {
    parts.push(`${Math.round(overlayState.totalPipelineMs)} ms`)
  }
  if (!parts.length && overlayState.status) {
    parts.push(overlayState.status)
  }
  return parts.join(' · ') || 'Waiting'
}

async function triggerToolbarAction(action, payload) {
  return window.electronAPI?.triggerToolbarAction?.(action, payload)
}

function ToolbarButton({
  ariaControls,
  ariaExpanded,
  ariaHaspopup,
  active = false,
  buttonRef,
  children,
  disabled = false,
  label,
  onClick,
  onKeyDown,
  shortcut = '',
  title,
}) {
  return (
    <button
      type="button"
      ref={buttonRef}
      onClick={onClick}
      onKeyDown={onKeyDown}
      disabled={disabled}
      title={title}
      className="topbar-toolbar-button no-drag"
      data-active={active ? 'true' : 'false'}
      aria-controls={ariaControls}
      aria-expanded={ariaExpanded}
      aria-haspopup={ariaHaspopup}
    >
      <span className="topbar-toolbar-button__label">
        {children}
        {label}
      </span>
      {shortcut ? <kbd className="topbar-toolbar-kbd">{shortcut}</kbd> : null}
    </button>
  )
}

export default function OverlayWindow({ overlayState }) {
  const [activeTab, setActiveTab] = useState(null)
  const [chatOpenVersion, setChatOpenVersion] = useState(0)
  const [time, setTime] = useState(() =>
    formatElapsedTime(overlayState.sessionStartedAt || Date.now())
  )
  const [barsActive, setBarsActive] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [safeAuthState, setSafeAuthState] = useState(() => ({
    status: 'signed-out',
    email: null,
  }))
  const [analyzeMenuOpen, setAnalyzeMenuOpen] = useState(false)
  const screenContextStatus = useScreenContextStatus()
  const [screenChooserError, setScreenChooserError] = useState('')
  const menuRef = useRef(null)
  const analyzeButtonRef = useRef(null)
  const analyzeMenuRef = useRef(null)
  const lastAutoFocusAnswerKeyRef = useRef('')
  const authStateTrackerRef = useRef(null)
  const [collapsed, setCollapsed] = useState(false)
  const [modeSnapshots, setModeSnapshots] = useState(() => ({
    answer: snapshotOverlayState({ ...overlayState, answer: '', transcript: '' }),
    screen: snapshotOverlayState({ ...overlayState, answer: '', transcript: '' }),
    chat: snapshotOverlayState({ ...overlayState, answer: '', transcript: '' }),
  }))
  const [panelViewportHeight, setPanelViewportHeight] = useState(() =>
    typeof window === 'undefined' ? 520 : Math.max(260, window.innerHeight - 132)
  )
  const [panelViewportWidth, setPanelViewportWidth] = useState(() =>
    typeof window === 'undefined' ? 620 : Math.max(320, window.innerWidth - 56)
  )

  const laptopOn = Boolean(overlayState.systemAudioEnabled)
  const micOn = Boolean(overlayState.microphoneEnabled)
  const audioPipelineStatus = String(overlayState.audioPipelineStatus || 'idle')
  const recordingActive = audioPipelineStatus === 'recording'
  const transcribingActive = audioPipelineStatus === 'transcribing'
  const generatingActive = audioPipelineStatus === 'generating'
  const recordingBusy = transcribingActive || generatingActive || Boolean(overlayState.manualProcessing)
  const sourceWarningActive = Boolean(overlayState.audioSourceWarning) && !laptopOn && !micOn
  const toolbarRecordingDisabled = Boolean(
    overlayState.autoMode || overlayState.autoProcessing || overlayState.ocrProcessing || recordingBusy
  )
  const autoGenOn = Boolean(overlayState.autoMode)
  const question = getActivePanelQuestion(overlayState)
  const statusSummary = getStatusSummary(overlayState)
  const overlayOpacity = Math.min(1, Math.max(0.4, Number(overlayState.overlayOpacity) || 1))
  const toolbarTimeLabel = sourceWarningActive
    ? 'Select audio source'
    : recordingActive
    ? `Listening ${formatElapsedTime(overlayState.recordingStartedAt || Date.now())}`
    : transcribingActive
      ? 'Transcribing...'
      : generatingActive
        ? 'Generating...'
        : recordingBusy
      ? 'Processing...'
      : time
  const stopEnabled = Boolean(
    recordingActive ||
    transcribingActive ||
    generatingActive ||
    recordingBusy ||
    overlayState.autoMode ||
    overlayState.autoProcessing ||
    overlayState.ocrProcessing ||
    overlayState.screenAnswerLoading ||
    overlayState.answerRevealActive
  )

  const barColor =
    audioPipelineStatus === 'recording'
      ? '#ef4444'
      : audioPipelineStatus === 'transcribing'
        ? '#f59e0b'
        : audioPipelineStatus === 'generating'
          ? '#22c55e'
          : 'rgba(255,255,255,0.75)'

  const analyzeMenuId = 'topbar-analyze-screen-menu'

  const closeAnalyzeMenu = useCallback((restoreFocus = true) => {
    setAnalyzeMenuOpen(false)
    if (restoreFocus) {
      window.requestAnimationFrame(() => analyzeButtonRef.current?.focus())
    }
  }, [])

  const handleAnalyzeScreen = useCallback(() => {
    setActiveTab('analyzeScreen')
    setCollapsed(false)
    setMenuOpen(false)
    setScreenChooserError('')
    setAnalyzeMenuOpen(true)
  }, [])

  const handleAnalyzeMenuKeyDown = useCallback((event) => {
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(event.target.tagName) && event.key !== 'Escape') return
    const items = [...(analyzeMenuRef.current?.querySelectorAll('button:not(:disabled), input:not(:disabled), select') || [])]
    const currentIndex = items.indexOf(document.activeElement)

    if (event.key === 'Escape') {
      event.preventDefault()
      closeAnalyzeMenu(true)
      return
    }

    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const direction = event.key === 'ArrowDown' ? 1 : -1
      const nextIndex = currentIndex >= 0
        ? (currentIndex + direction + items.length) % items.length
        : 0
      items[nextIndex]?.focus()
    }
  }, [closeAnalyzeMenu])

  const handleAnalyzeMenuAction = useCallback(async (action) => {
    closeAnalyzeMenu(true)
    await triggerToolbarAction(action, {
      trigger: action === 'analyze-screen-ocr' ? 'menu_ocr' : 'menu_extension',
    })
  }, [closeAnalyzeMenu])

  if (!authStateTrackerRef.current) {
    authStateTrackerRef.current = createOverlayAuthStateTracker(setSafeAuthState)
  }

  const refreshSafeAuthState = useCallback(async () => {
    await authStateTrackerRef.current.refresh(() => window.saiia?.getAuthState?.())
  }, [])

  const clearSafeAuthState = useCallback(() => {
    authStateTrackerRef.current.clear()
  }, [])

  const handleOpenDashboard = useCallback(async () => {
    setMenuOpen(false)
    try {
      await window.saiia?.openDashboard?.()
    } catch {
      // Dashboard opening is best-effort from the overlay menu.
    }
  }, [])

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setTime(formatElapsedTime(overlayState.sessionStartedAt || Date.now()))
    }, 1000)
    return () => window.clearInterval(intervalId)
  }, [overlayState.sessionStartedAt])

  useEffect(() => {
    refreshSafeAuthState()
  }, [refreshSafeAuthState])

  useEffect(() => {
    if (overlayState.visible === false) {
      clearSafeAuthState()
    }
  }, [overlayState.visible, clearSafeAuthState])

  useEffect(() => {
    if (!menuOpen) {
      return undefined
    }
    refreshSafeAuthState()
    const intervalId = window.setInterval(refreshSafeAuthState, 1000)
    return () => window.clearInterval(intervalId)
  }, [menuOpen, refreshSafeAuthState])

  useEffect(() => {
    const owner = getPanelOwner(getTabForAnswerMode(overlayState.answerDisplayMode))
    setModeSnapshots((current) => ({
      ...current,
      [owner]: snapshotOverlayState(overlayState),
    }))

    const nextAutoFocusAnswerKey = overlayState.answer
      ? `${overlayState.answerDisplayMode}\n${overlayState.answer}`
      : ''
    const shouldAutoFocusAnswer =
      nextAutoFocusAnswerKey &&
      lastAutoFocusAnswerKeyRef.current !== nextAutoFocusAnswerKey
    lastAutoFocusAnswerKeyRef.current = nextAutoFocusAnswerKey

    if (shouldAutoFocusAnswer) {
      const nextFocusedTab = getAutoFocusedTabForAnswer({
        activeTab,
        answerDisplayMode: overlayState.answerDisplayMode,
        answer: overlayState.answer,
      })
      if (nextFocusedTab) {
        setActiveTab(nextFocusedTab)
      }
    }
  }, [overlayState, activeTab])

  useEffect(() => {
    if (!overlayState.manualLiveState?.sessionId) return
    setActiveTab('aiHelp')
    setCollapsed(false)
  }, [overlayState.manualLiveState?.sessionId])

  const handleAiHelp = async () => {
    setActiveTab('aiHelp')
    setCollapsed(false)
    setMenuOpen(false)
    setAnalyzeMenuOpen(false)
  }

  const handleChat = () => {
    setChatOpenVersion((version) => version + 1)
    setActiveTab('chat')
    setCollapsed(false)
    setMenuOpen(false)
    setAnalyzeMenuOpen(false)
  }

  const accountLabel = safeAuthState.status === 'connected'
    ? safeAuthState.email || 'Signed in'
    : ''

  const panelMode = useMemo(() => {
    if (activeTab === 'chat') {
      return 'chat'
    }
    if (activeTab === 'analyzeScreen') {
      return 'analyzeScreen'
    }
    return 'aiHelp'
  }, [activeTab])
  const panelOverlayState = getPanelOverlayState({
    activeTab,
    overlayState,
    modeSnapshots,
  })

  useEffect(() => {
    const updateViewportSize = () => {
      setPanelViewportHeight(Math.max(260, window.innerHeight - 132))
      setPanelViewportWidth(Math.max(320, window.innerWidth - 56))
    }

    updateViewportSize()
    window.addEventListener('resize', updateViewportSize)
    return () => window.removeEventListener('resize', updateViewportSize)
  }, [])

  const handleResetOverlayPosition = useCallback(async () => {
    await window.electronAPI?.resetOverlayPosition?.()
    setMenuOpen(false)
  }, [])

  const handleSetOverlayOpacity = useCallback(async (nextOpacity) => {
    await window.electronAPI?.setOverlayOpacity?.(nextOpacity)
  }, [])

  useEffect(() => {
    if (!menuOpen) {
      return undefined
    }

    const handlePointerDown = (event) => {
      if (!menuRef.current?.contains(event.target)) {
        setMenuOpen(false)
      }
    }

    window.addEventListener('pointerdown', handlePointerDown)
    return () => window.removeEventListener('pointerdown', handlePointerDown)
  }, [menuOpen])

  useEffect(() => {
    if (!analyzeMenuOpen) {
      return undefined
    }

    const frameId = window.requestAnimationFrame(() => {
      analyzeMenuRef.current?.querySelector('input:not(:disabled)')?.focus()
    })

    return () => window.cancelAnimationFrame(frameId)
  }, [analyzeMenuOpen])

  useEffect(() => {
    if (!analyzeMenuOpen) {
      return undefined
    }

    const handlePointerDown = (event) => {
      if (
        analyzeMenuRef.current?.contains(event.target) ||
        analyzeButtonRef.current?.contains(event.target)
      ) {
        return
      }
      closeAnalyzeMenu(true)
    }

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        closeAnalyzeMenu(true)
      }
    }

    window.addEventListener('pointerdown', handlePointerDown)
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('pointerdown', handlePointerDown)
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [analyzeMenuOpen, closeAnalyzeMenu])

  useEffect(() => {
    if (!window.electronAPI?.onToolbarAction) {
      return undefined
    }

    const unsubscribe = window.electronAPI.onToolbarAction((payload) => {
      if (payload?.action === 'analyze-screen') {
        setActiveTab('analyzeScreen')
        setCollapsed(false)
        setScreenChooserError('')
        setAnalyzeMenuOpen(true)
      }
    })

    return () => {
      if (unsubscribe) {
        unsubscribe()
      }
    }
  }, [])

  return (
    <div className="topbar-overlay-root">
      <div className="topbar-overlay-stack">
        <div
          className={`topbar-toolbar-shell drag-region${collapsed ? ' topbar-toolbar-shell--collapsed' : ''}`}
        >
          <div className="topbar-toolbar-brand">
            <button
              type="button"
              onClick={() => {
                if (collapsed) {
                  setCollapsed(false)
                  return
                }
                if (toolbarRecordingDisabled && !recordingActive) {
                  return
                }
                triggerToolbarAction('toggle-recording-bar')
              }}
              className="topbar-toolbar-brand__button no-drag"
              title={
                recordingActive
                  ? 'Stop Recording'
                  : transcribingActive
                    ? 'Transcribing...'
                    : generatingActive
                      ? 'Generating answer...'
                      : recordingBusy
                        ? 'Processing Recording'
                    : 'Start Recording'
              }
              aria-label={
                recordingActive
                  ? 'Stop Recording'
                  : transcribingActive
                    ? 'Transcribing...'
                    : generatingActive
                      ? 'Generating answer...'
                      : recordingBusy
                        ? 'Processing Recording'
                    : 'Start Recording'
              }
              disabled={toolbarRecordingDisabled && !recordingActive}
              style={{
                background: recordingActive
                  ? 'rgba(239, 68, 68, 0.18)'
                  : transcribingActive
                    ? 'rgba(251, 191, 36, 0.16)'
                    : generatingActive
                      ? 'rgba(34, 197, 94, 0.16)'
                    : 'transparent',
                boxShadow: recordingActive
                  ? '0 0 0 1px rgba(239, 68, 68, 0.45), 0 0 14px rgba(239, 68, 68, 0.28)'
                  : transcribingActive
                    ? '0 0 0 1px rgba(251, 191, 36, 0.35)'
                    : generatingActive
                      ? '0 0 0 1px rgba(34, 197, 94, 0.35)'
                    : 'none',
                opacity: toolbarRecordingDisabled && !recordingActive ? 0.68 : 1,
              }}
            >
              <span className="topbar-toolbar-brand__bars">
                {[0, 1, 2].map((index) => (
                  <span
                    key={index}
                    className="topbar-toolbar-brand__bar"
                    style={{
                      background: barColor,
                      boxShadow:
                        audioPipelineStatus === 'recording'
                          ? '0 0 6px rgba(239, 68, 68, 0.95)'
                          : audioPipelineStatus === 'transcribing'
                            ? '0 0 5px rgba(251, 191, 36, 0.65)'
                            : audioPipelineStatus === 'generating'
                              ? '0 0 5px rgba(34, 197, 94, 0.65)'
                              : barsActive
                                ? '0 0 5px #4ade80'
                                : 'none',
                      animationName:
                        recordingActive || transcribingActive || generatingActive || barsActive
                          ? 'topbarBarBounce'
                          : 'none',
                      animationDuration: `${0.55 + index * 0.15}s`,
                      animationTimingFunction: 'ease-in-out',
                      animationIterationCount: 'infinite',
                      animationDirection: 'alternate',
                      animationDelay: `${index * 0.12}s`,
                      height: recordingActive
                        ? `${[10, 16, 12][index]}px`
                        : transcribingActive || generatingActive || barsActive
                          ? '14px'
                          : `${[8, 13, 10][index]}px`,
                    }}
                  />
                ))}
              </span>
              {recordingActive ? <span className="topbar-toolbar-red-dot topbar-toolbar-red-dot--pulse" /> : null}
            </button>
          </div>

          {!collapsed ? (
            <>
              <div className="topbar-toolbar-divider" />

              <button
                type="button"
                onClick={() => triggerToolbarAction('toggle-system-audio')}
                className="topbar-toolbar-icon-button no-drag"
                title="System audio"
                disabled={recordingActive || recordingBusy}
                style={{
                  boxShadow: sourceWarningActive ? '0 0 0 1px rgba(239, 68, 68, 0.5)' : 'none',
                }}
              >
                <Laptop size={15} className="topbar-toolbar-icon" />
                {laptopOn ? <span className="topbar-toolbar-red-dot" /> : null}
              </button>

              <button
                type="button"
                onClick={() => triggerToolbarAction('toggle-microphone')}
                className="topbar-toolbar-icon-button no-drag"
                disabled={recordingActive || recordingBusy}
                title="Microphone"
                style={{
                  boxShadow: sourceWarningActive ? '0 0 0 1px rgba(239, 68, 68, 0.5)' : 'none',
                }}
              >
                <Mic size={15} className="topbar-toolbar-icon" />
                {micOn ? <span className="topbar-toolbar-red-dot" /> : null}
              </button>

              <div className="topbar-toolbar-divider topbar-toolbar-divider--compact" />

              <ToolbarButton
                active={activeTab === 'aiHelp'}
                label="Answer"
                onClick={handleAiHelp}
                shortcut="Ctrl Enter"
              >
                <Sparkles size={13} />
              </ToolbarButton>

              <div className="topbar-analyze-menu-shell no-drag">
                <ToolbarButton
                  active={activeTab === 'analyzeScreen'}
                  ariaControls={analyzeMenuOpen ? analyzeMenuId : undefined}
                  ariaExpanded={analyzeMenuOpen}
                  ariaHaspopup="dialog"
                  buttonRef={analyzeButtonRef}
                  label="Analyze Screen"
                  onClick={handleAnalyzeScreen}
                  shortcut="Ctrl Shift Enter"
                  title={overlayState.ocrProcessing ? 'Analyzing screen...' : 'Analyze active screen'}
                >
                  <Monitor size={13} />
                </ToolbarButton>

                {analyzeMenuOpen ? (
                  <div
                    id={analyzeMenuId}
                    ref={analyzeMenuRef}
                    className="topbar-analyze-menu no-drag"
                    role="dialog"
                    aria-label="Analyze Screen"
                    onKeyDown={handleAnalyzeMenuKeyDown}
                  >
                    <div className="topbar-analyze-menu__heading">Analyze Screen</div>
                    <ScreenContextChooser status={screenContextStatus}
                      blocked={Boolean(overlayState.recording || overlayState.autoMode || overlayState.autoProcessing)}
                      onExecute={async command => {
                        try {
                          await window.electronAPI.executeScreenContext(command)
                          closeAnalyzeMenu(true)
                        } catch { setScreenChooserError('Screen action unavailable. Refresh the chooser and try again.') }
                      }}
                      onExtension={() => handleAnalyzeMenuAction('analyze-screen-extension')}
                    />
                    {screenChooserError ? <p role="alert">{screenChooserError}</p> : null}
                  </div>
                ) : null}
              </div>

              <ToolbarButton
                active={activeTab === 'chat'}
                label="Chat"
                onClick={handleChat}
              >
                <MessageSquare size={13} />
              </ToolbarButton>

              <button
                type="button"
                onClick={() => triggerToolbarAction('stop-active-operation', screenContextStatus ? { screenExpected: screenContextCommandFence(screenContextStatus) } : undefined)}
                className="topbar-toolbar-stop-button no-drag"
                title="Stop current operation"
                aria-label="Stop current operation"
                disabled={!stopEnabled}
              >
                <Square size={10} className="topbar-toolbar-stop-button__icon" />
              </button>

              <div className="topbar-toolbar-divider topbar-toolbar-divider--compact" />

              <span className="topbar-toolbar-time">{toolbarTimeLabel}</span>

              <div className="topbar-toolbar-divider topbar-toolbar-divider--narrow" />

              <div ref={menuRef} className="topbar-toolbar-menu-shell">
                <button
                  type="button"
                  onClick={() => {
                    setAnalyzeMenuOpen(false)
                    setMenuOpen((v) => !v)
                  }}
                  className="topbar-toolbar-icon-button no-drag"
                >
                  <MoreVertical size={15} className="topbar-toolbar-icon" />
                </button>

                {menuOpen ? (
                  <div className="topbar-menu no-drag">
                    <div className="topbar-menu__row topbar-menu__row--header">
                      <User size={16} className="topbar-menu__icon" />
                      <span className="topbar-menu__header-copy">
                        <span className="topbar-menu__text">Intervu AI</span>
                        {accountLabel ? (
                          <span className="topbar-menu__account">{accountLabel}</span>
                        ) : null}
                      </span>
                    </div>

                    <button
                      type="button"
                      className="topbar-menu__row topbar-menu__row--button topbar-menu__row--bordered no-drag"
                      onClick={handleOpenDashboard}
                    >
                      <LayoutDashboard size={16} className="topbar-menu__icon" />
                      <span className="topbar-menu__text">Dashboard</span>
                    </button>

                    <div className="topbar-menu__row topbar-menu__row--bordered">
                      <span className="topbar-menu__text topbar-menu__text--grow">Zoom</span>
                      <div className="topbar-menu__zoom-actions">
                        <button
                          type="button"
                          className="topbar-menu__square-button"
                          onClick={() =>
                            triggerToolbarAction('set-font-size', {
                              value: Math.min(20, (overlayState.fontSize || 14) + 1),
                            })
                          }
                        >
                          <Plus size={13} className="topbar-menu__square-icon" />
                        </button>
                        <button
                          type="button"
                          className="topbar-menu__square-button"
                          onClick={() =>
                            triggerToolbarAction('set-font-size', {
                              value: Math.max(12, (overlayState.fontSize || 14) - 1),
                            })
                          }
                        >
                          <Minus size={13} className="topbar-menu__square-icon" />
                        </button>
                        <button
                          type="button"
                          className="topbar-menu__square-button"
                          onClick={() => triggerToolbarAction('set-font-size', { value: 14 })}
                        >
                          <RotateCcw size={13} className="topbar-menu__square-icon" />
                        </button>
                      </div>
                    </div>

                    <div className="topbar-menu__row topbar-menu__row--bordered">
                      <span className="topbar-menu__text topbar-menu__text--grow">Opacity</span>
                      <div className="topbar-menu__zoom-actions">
                        <button
                          type="button"
                          className="topbar-menu__square-button"
                          onClick={() => handleSetOverlayOpacity(overlayOpacity + 0.1)}
                          title="Increase opacity"
                        >
                          <Plus size={13} className="topbar-menu__square-icon" />
                        </button>
                        <button
                          type="button"
                          className="topbar-menu__square-button"
                          onClick={() => handleSetOverlayOpacity(overlayOpacity - 0.1)}
                          title="Decrease opacity"
                        >
                          <Minus size={13} className="topbar-menu__square-icon" />
                        </button>
                        <button
                          type="button"
                          className="topbar-menu__square-button"
                          onClick={() => handleSetOverlayOpacity(1)}
                          title="Reset opacity"
                        >
                          <RotateCcw size={13} className="topbar-menu__square-icon" />
                        </button>
                      </div>
                    </div>

                    <div className="topbar-menu__row topbar-menu__row--bordered">
                      <span className="topbar-menu__text topbar-menu__text--grow">Auto Generate</span>
                      <button
                        type="button"
                        onClick={() => triggerToolbarAction('toggle-auto-generate')}
                        className="topbar-menu__toggle"
                        style={{ background: autoGenOn ? 'rgba(255,255,255,0.85)' : 'rgba(255,255,255,0.18)' }}
                      >
                        <span
                          className="topbar-menu__toggle-knob"
                          style={{
                            left: autoGenOn ? 'calc(100% - 18px)' : '2px',
                            background: autoGenOn ? '#1a1a1c' : '#ffffff',
                          }}
                        />
                      </button>
                    </div>

                    <button
                      type="button"
                      className="topbar-menu__row topbar-menu__row--button topbar-menu__row--bordered no-drag"
                      onClick={handleResetOverlayPosition}
                    >
                      <Move size={16} className="topbar-menu__icon" />
                      <span className="topbar-menu__text topbar-menu__text--grow">
                        Reset overlay position
                      </span>
                    </button>

                    <button
                      type="button"
                      className="topbar-menu__row topbar-menu__row--button topbar-menu__row--bordered no-drag"
                      onClick={() => window.electronAPI?.toggleOverlayVisibility?.()}
                    >
                      <X size={16} className="topbar-menu__icon" />
                      <span className="topbar-menu__text topbar-menu__text--grow">Hide overlay</span>
                    </button>

                    <button
                      type="button"
                      className="topbar-menu__row topbar-menu__row--button no-drag"
                      onClick={() => triggerToolbarAction('end-session')}
                    >
                      <span className="topbar-menu__end-box" />
                      <span className="topbar-menu__text topbar-menu__text--grow">End Session</span>
                      <Info size={13} className="topbar-menu__info" />
                    </button>
                  </div>
                ) : null}
              </div>

              <button
                type="button"
                className="topbar-toolbar-icon-button"
                title="Drag overlay"
                aria-label="Drag overlay"
              >
                <Move size={14} className="topbar-toolbar-icon" />
              </button>

              <button
                type="button"
                onClick={() => {
                  setAnalyzeMenuOpen(false)
                  setCollapsed(true)
                }}
                className="topbar-toolbar-icon-button no-drag"
              >
                <ChevronUp size={15} className="topbar-toolbar-icon" />
              </button>
            </>
          ) : null}
        </div>

        {barsActive ? (
          <div className="topbar-bars-panel">
            <p className="topbar-bars-panel__text">
              {overlayState.error
                ? overlayState.error
                : `${question} `}
              <span className="topbar-bars-panel__muted">{statusSummary}</span>
            </p>

            <button type="button" className="topbar-bars-panel__icon-button no-drag" title="Delete">
              <Trash2 size={13} className="topbar-bars-panel__icon" />
            </button>
            <button type="button" className="topbar-bars-panel__icon-button no-drag" title="Collapse">
              <ChevronDown size={13} className="topbar-bars-panel__icon" />
            </button>
            <button
              type="button"
              onClick={() => setBarsActive(false)}
              className="topbar-bars-panel__icon-button no-drag"
              title="Close"
            >
              <X size={13} className="topbar-bars-panel__icon" />
            </button>
          </div>
        ) : null}

        {activeTab ? (
          <AnswerPanel
            mode={panelMode}
            overlayState={panelOverlayState}
            chatOpenVersion={chatOpenVersion}
            maxViewportHeight={panelViewportHeight}
            maxViewportWidth={panelViewportWidth}
            onCancelChat={() => setActiveTab(null)}
            onClose={() => setActiveTab(null)}
          />
        ) : null}
      </div>
    </div>
  )
}

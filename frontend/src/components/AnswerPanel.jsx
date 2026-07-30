import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  LoaderCircle,
  Maximize2,
  RotateCcw,
  Trash2,
  X,
} from 'lucide-react'
import { groupConceptualAnswer, parseConceptualAnswer } from '../answer_format.js'
import { getQuestionHistorySummary } from '../question_history.js'
import {
  extractCopyableCode,
  hasSavedScreenResult,
  hasScreenError,
  isScreenAnalysisRunning,
} from '../screen_mode_state.js'

const iconButtonStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 24,
  height: 24,
  borderRadius: 6,
  background: 'transparent',
  border: 'none',
  cursor: 'pointer',
  transition: 'background-color 0.2s',
}

const panelShellStyle = {
  fontFamily: "'Inter', sans-serif",
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
  const match = value.match(/```([^\n`]*)\s*\n?([\s\S]*?)```/)
  if (match) {
    return {
      language: String(match[1] || '').trim().toLowerCase(),
      code: cleanExtractedCode(match[2]),
    }
  }

  const openFenceMatch = value.match(/```([^\n`]*)\s*\n([\s\S]*)$/)
  if (openFenceMatch) {
    return {
      language: String(openFenceMatch[1] || '').trim().toLowerCase(),
      code: cleanExtractedCode(openFenceMatch[2]),
    }
  }

  const codeSectionMatch = value.match(
    /^Code:\s*\n([\s\S]*?)(?=^\s*(?:Complexity|Edge cases|Why it works|Explanation|Approach|Steps|Bug|Fix|Corrected Code|Trace|Final output):|\s*$)/im
  )
  if (codeSectionMatch) {
    return {
      language: value.match(/```([^\n`]*)/i)?.[1]?.trim().toLowerCase() || '',
      code: cleanExtractedCode(codeSectionMatch[1]),
    }
  }

  return { language: '', code: '' }
}

function cleanExtractedCode(text) {
  const value = String(text || '')
    .replace(/^\s*```[a-zA-Z0-9_-]*\s*/i, '')
    .replace(/\s*```\s*$/i, '')
    .replace(/\s+$/, '')

  const stopMatch = value.match(/^\s*(?:Complexity|Edge cases|Why it works|Explanation|Approach|Steps|Bug|Fix|Trace|Final output):/im)
  const code = stopMatch ? value.slice(0, stopMatch.index).replace(/\s+$/, '') : value
  return code.trim() ? code : ''
}

function parseAnswerSections(text) {
  const normalized = String(text || '').replace(/\r\n/g, '\n').trim()
  if (!normalized) {
    return []
  }

  const withoutCodeFences = normalized
    .replace(/```[^\n`]*\n?[\s\S]*?```/g, '')
    .replace(/```[^\n`]*\n[\s\S]*$/g, '')
    .trim()
  const headingPattern = /^(Approach|Steps|Code|Complexity|Edge cases|Bug|Fix|Corrected Code|Why it works|Trace|Final output):\s*(.*)$/i
  const sections = []
  let currentSection = null

  for (const rawLine of withoutCodeFences.split('\n')) {
    const line = rawLine.trimEnd()
    const headingMatch = line.match(headingPattern)
    if (headingMatch) {
      if (currentSection) {
        sections.push(currentSection)
      }
      currentSection = {
        label: headingMatch[1],
        body: String(headingMatch[2] || '').trim(),
      }
      continue
    }

    if (!currentSection) {
      currentSection = { label: '', body: line.trim() }
      continue
    }

    currentSection.body = [currentSection.body, line.trim()].filter(Boolean).join('\n')
  }

  if (currentSection) {
    sections.push(currentSection)
  }

  return sections
    .map((section) => ({
      label: section.label,
      body: String(section.body || '').trim(),
    }))
    .filter((section) => section.label || section.body)
}

function cleanScreenQuestionSummary(text) {
  const raw = String(text || '').replace(/\r\n/g, '\n').trim()
  if (!raw) {
    return 'Analyze the active window.'
  }

  const noisePattern = /\b(?:RunCode|Run Code|Submit Code|UploadCodeasFile|Upload Code as File|Test against custom input|Line:\s*\d+|Col:\s*\d+|Google Chrome|Leaderboard|Submissions|Discussions|Editorial|Constraints|Sample Input|Sample Output|Output Format|Input Format|Enter your code here|Read input from STDIN|Print output to STDOUT)\b/gi
  const cleaned = raw
    .replace(noisePattern, ' ')
    .replace(/\s+/g, ' ')
    .replace(/\s+([.,;:!?])/g, '$1')
    .trim()

  const stopMatch = cleaned.match(/\b(?:Input Format|Output Format|Sample Input|Sample Output|Constraints|def\s+\w+\s*\(|class\s+Solution\b)/i)
  const candidate = stopMatch ? cleaned.slice(0, stopMatch.index).trim() : cleaned
  const summary = candidate || cleaned || raw.replace(/\s+/g, ' ').trim()

  if (summary.length <= 260) {
    return summary
  }

  const clipped = summary.slice(0, 260)
  const sentenceEnd = Math.max(clipped.lastIndexOf('.'), clipped.lastIndexOf('?'), clipped.lastIndexOf('!'))
  if (sentenceEnd > 120) {
    return `${clipped.slice(0, sentenceEnd + 1).trim()}`
  }
  return `${clipped.replace(/\s+\S*$/, '').trim()}...`
}

function cleanInlineMarkdown(text) {
  return String(text || '')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/__(.*?)__/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\s+/g, ' ')
    .trim()
}

const CODE_KEYWORDS = {
  python: new Set([
    'and', 'as', 'assert', 'break', 'class', 'continue', 'def', 'elif', 'else', 'except',
    'False', 'finally', 'for', 'from', 'if', 'import', 'in', 'is', 'lambda', 'None',
    'not', 'or', 'pass', 'return', 'True', 'try', 'while', 'with', 'yield',
  ]),
  javascript: new Set([
    'async', 'await', 'break', 'case', 'catch', 'class', 'const', 'continue', 'default',
    'else', 'export', 'for', 'function', 'if', 'import', 'let', 'new', 'return', 'switch',
    'throw', 'try', 'var', 'while',
  ]),
  java: new Set([
    'boolean', 'break', 'case', 'catch', 'class', 'continue', 'else', 'final', 'for',
    'if', 'import', 'int', 'new', 'private', 'public', 'return', 'static', 'String',
    'switch', 'throw', 'try', 'void', 'while',
  ]),
  cpp: new Set([
    'auto', 'bool', 'break', 'case', 'class', 'const', 'continue', 'else', 'for', 'if',
    'include', 'int', 'long', 'namespace', 'return', 'std', 'string', 'using', 'vector',
    'void', 'while',
  ]),
}

function renderHighlightedCode(code, language) {
  const normalizedLanguage = String(language || '').toLowerCase()
  const keywords = CODE_KEYWORDS[normalizedLanguage] || CODE_KEYWORDS.javascript
  const value = String(code || '')
  const tokenPattern = /(#.*|\/\/.*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b\d+(?:\.\d+)?\b|\b[A-Za-z_][A-Za-z0-9_]*\b)/g
  const parts = []
  let lastIndex = 0

  for (const match of value.matchAll(tokenPattern)) {
    if (match.index > lastIndex) {
      parts.push({ text: value.slice(lastIndex, match.index), type: 'plain' })
    }
    const text = match[0]
    const type =
      text.startsWith('#') || text.startsWith('//')
        ? 'comment'
        : text.startsWith('"') || text.startsWith("'")
          ? 'string'
          : /^\d/.test(text)
            ? 'number'
            : keywords.has(text)
              ? 'keyword'
              : 'plain'
    parts.push({ text, type })
    lastIndex = match.index + text.length
  }

  if (lastIndex < value.length) {
    parts.push({ text: value.slice(lastIndex), type: 'plain' })
  }

  return parts.map((part, index) =>
    part.type === 'plain' ? (
      part.text
    ) : (
      <span key={`${part.type}-${index}`} className={`code-token code-token--${part.type}`}>
        {part.text}
      </span>
    )
  )
}

function renderSolutionText(text, keyPrefix) {
  const lines = String(text || '')
    .replace(/\r\n/g, '\n')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)

  if (!lines.length) {
    return null
  }

  return lines.map((line, index) => {
    const headingMatch = line.match(/^#{1,4}\s*(.+)$/)
    if (headingMatch) {
      return (
        <p key={`${keyPrefix}-heading-${index}`} className="topbar-screen-panel__solution-heading">
          {cleanInlineMarkdown(headingMatch[1])}
        </p>
      )
    }

    const numberedMatch = line.match(/^(\d+)\.\s*(.+)$/)
    if (numberedMatch) {
      return (
        <div key={`${keyPrefix}-number-${index}`} className="topbar-screen-panel__solution-point">
          <span className="topbar-screen-panel__solution-index">{numberedMatch[1]}</span>
          <p>{cleanInlineMarkdown(numberedMatch[2])}</p>
        </div>
      )
    }

    const bulletMatch = line.match(/^[*-]\s*(.+)$/)
    if (bulletMatch) {
      return (
        <div key={`${keyPrefix}-bullet-${index}`} className="topbar-screen-panel__solution-bullet">
          <span />
          <p>{cleanInlineMarkdown(bulletMatch[1])}</p>
        </div>
      )
    }

    return (
      <p key={`${keyPrefix}-paragraph-${index}`} className="topbar-screen-panel__solution-copy">
        {cleanInlineMarkdown(line)}
      </p>
    )
  })
}

function getPanelCopy(mode, overlayState) {
  if (mode === 'chat') {
    return {
      title: overlayState.transcript || 'No clear question detected yet.',
      body:
        overlayState.answer ||
        (overlayState.isManualGenerating
          ? 'Generating answer...'
          : 'Type your interview question here and press Enter to use the existing answer pipeline.'),
      footer: overlayState.provider
        ? `Chat · ${overlayState.provider}`
        : 'Chat · Waiting',
    }
  }

  if (mode === 'analyzeScreen') {
    return {
      title:
        overlayState.ocrText ||
        overlayState.transcript ||
        'Analyze the active window.',
      body:
        overlayState.screenAnswerText ||
        overlayState.answer ||
        (overlayState.ocrProcessing
          ? 'Analyzing question...'
          : 'Capture a visible question or coding problem from the active external window.'),
      footer:
        overlayState.totalPipelineMs != null
          ? `Analyze Screen · ${Math.round(overlayState.totalPipelineMs)} ms`
          : 'Analyze Screen · Waiting',
    }
  }

  const timestampParts = []
  if (overlayState.provider) {
    timestampParts.push(overlayState.provider)
  }
  if (overlayState.category) {
    timestampParts.push(overlayState.category)
  }
  if (overlayState.answerRevealActive) {
    timestampParts.push('streaming')
  } else
  if (overlayState.totalPipelineMs != null) {
    timestampParts.push(`${Math.round(overlayState.totalPipelineMs)} ms`)
  }

  return {
    title: overlayState.transcript || 'No clear question detected yet.',
    body:
      overlayState.answer ||
      'Your latest SAIIA answer will appear here once a question is captured or generated.',
    footer: timestampParts.length ? timestampParts.join(' · ') : 'AI Answer',
  }
}

export default function AnswerPanel({
  mode,
  overlayState,
  maxViewportHeight = 520,
  maxViewportWidth = 620,
  onCancelChat,
  onClose,
}) {
  const [size, setSize] = useState({ w: 520, h: 280 })
  const [collapsed, setCollapsed] = useState(false)
  const [chatDraft, setChatDraft] = useState('')
  const [chatEditing, setChatEditing] = useState(false)
  const [chatError, setChatError] = useState('')
  const [chatAwaitingResult, setChatAwaitingResult] = useState(false)
  const bodyRef = useRef(null)
  const chatInputRef = useRef(null)
  const resizeFrameRef = useRef(0)
  const resizeStartRef = useRef(null)

  const content = useMemo(() => getPanelCopy(mode, overlayState), [mode, overlayState])
  const historyMode = mode === 'analyzeScreen' ? 'screen' : mode === 'aiHelp' ? 'answer' : ''
  const historySummary = useMemo(
    () => getQuestionHistorySummary(overlayState.questionHistory, historyMode),
    [historyMode, overlayState.questionHistory]
  )
  const cleanedScreenQuestionSummary = useMemo(
    () => cleanScreenQuestionSummary(overlayState.ocrText || overlayState.transcript || content.title),
    [content.title, overlayState.ocrText, overlayState.transcript]
  )
  const visibleBody = content.body
  const revealInProgress = Boolean(overlayState.answerRevealActive && overlayState.answerFullAvailable)
  const structuredCodingAnswer =
    !revealInProgress && overlayState.codingAnswer && String(overlayState.codingAnswer.code || '').trim()
      ? overlayState.codingAnswer
      : null
  const fallbackScreenAnswerText =
    !overlayState.screenAnswerText && overlayState.screenAnswerGenerated
      ? String(overlayState.answer || '').trim()
      : ''
  const progressiveScreenAnswerText =
    overlayState.screenAnswerCommittedToOverlay && overlayState.answer
      ? String(overlayState.answer || '').trim()
      : ''
  const effectiveScreenAnswerText =
    overlayState.screenAnswerCommittedToOverlay
      ? progressiveScreenAnswerText || fallbackScreenAnswerText
      : overlayState.screenAnswerText || fallbackScreenAnswerText
  const screenAnswerForCode = overlayState.screenAnswerText || effectiveScreenAnswerText
  const derivedScreenCode = !overlayState.screenCodeAnswer && screenAnswerForCode
    ? extractCodeBlock(screenAnswerForCode)
    : { language: '', code: '' }
  const effectiveScreenCode = overlayState.screenCodeAnswer || derivedScreenCode.code
  const effectiveScreenCodeLanguage =
    overlayState.screenCodeLanguage ||
    derivedScreenCode.language ||
    (overlayState.screenQuestionType === 'coding' ? 'python' : '')
  const copyableScreenCode = extractCopyableCode({
    screenAnswerText: effectiveScreenAnswerText,
    screenCodeAnswer: overlayState.screenCodeAnswer,
    screenCodeLanguage: overlayState.screenCodeLanguage,
  })
  const formattedScreenAnswerSections = parseAnswerSections(effectiveScreenAnswerText).filter(
    (section) => !effectiveScreenCode || !/^(code|corrected code)$/i.test(section.label)
  )
  const showScreenAnswerMode =
    mode === 'analyzeScreen' &&
    (overlayState.screenPanelMode === 'answer' ||
      Boolean(overlayState.screenAnswerGenerated && effectiveScreenAnswerText))
  const screenQuestionCount = Number(overlayState.pipelineTimings?.questions_answered || 0)
  const screenBatchResult = screenQuestionCount > 1
  const screenHasResult = hasSavedScreenResult(overlayState)
  const screenHasError = hasScreenError(overlayState)
  const screenBusy = isScreenAnalysisRunning(overlayState)
  const minPanelHeight = mode === 'analyzeScreen' || mode === 'chat' ? 320 : 238
  const maxPanelHeight = Math.max(minPanelHeight, maxViewportHeight)
  const panelWidth = Math.max(320, maxViewportWidth)
  const panelHeight = maxPanelHeight

  useEffect(() => {
    if (mode !== 'chat') {
      setChatEditing(false)
      setChatAwaitingResult(false)
      setChatError('')
      return
    }

    setChatDraft(overlayState.transcript || '')
    setChatEditing(true)
    setChatAwaitingResult(false)
    setChatError(overlayState.manualQuestionError || '')
  }, [mode, overlayState.manualQuestionError, overlayState.transcript])

  useEffect(() => {
    if (mode !== 'chat' || !chatEditing) {
      return
    }

    const frame = window.requestAnimationFrame(() => {
      chatInputRef.current?.focus()
      const input = chatInputRef.current
      if (input && typeof input.selectionStart === 'number') {
        const cursor = input.value.length
        input.setSelectionRange(cursor, cursor)
      }
    })

    return () => window.cancelAnimationFrame(frame)
  }, [mode, chatEditing])

  useEffect(() => {
    if (mode !== 'chat' || !chatAwaitingResult || overlayState.isManualGenerating) {
      return
    }

    if (overlayState.answer) {
      setChatEditing(false)
    }
    setChatAwaitingResult(false)
  }, [mode, chatAwaitingResult, overlayState.answer, overlayState.isManualGenerating])

  useEffect(() => {
    if (revealInProgress) {
      return
    }
    if (bodyRef.current && !collapsed) {
      const scrollH = bodyRef.current.scrollHeight
      const needed = scrollH + (mode === 'chat' ? 82 : 96)
      setSize((s) => ({
        ...s,
        w: mode === 'analyzeScreen' ? Math.max(s.w, 640) : s.w,
        h: Math.min(maxPanelHeight, Math.max(minPanelHeight, needed)),
      }))
    }
  }, [
    visibleBody,
    chatDraft,
    chatEditing,
    collapsed,
    maxViewportHeight,
    mode,
    effectiveScreenAnswerText,
    effectiveScreenCode,
    maxPanelHeight,
    minPanelHeight,
    revealInProgress,
    showScreenAnswerMode,
  ])

  useEffect(() => {
    setSize((current) => ({
      w: mode === 'analyzeScreen' ? Math.max(current.w, 640) : Math.min(current.w, mode === 'chat' ? 560 : 620),
      h: Math.min(Math.max(current.h, minPanelHeight), maxPanelHeight),
    }))
  }, [maxPanelHeight, minPanelHeight, mode])

  const handleResizePointerDown = useCallback(async (event) => {
    event.preventDefault()
    event.stopPropagation()
    const handleElement = event.currentTarget
    const pointerId = event.pointerId
    const startX = event.screenX
    const startY = event.screenY

    const result = await window.electronAPI?.getOverlayBounds?.()
    const bounds = result?.bounds
    if (!bounds) {
      return
    }

    handleElement.setPointerCapture?.(pointerId)
    resizeStartRef.current = {
      x: startX,
      y: startY,
      width: bounds.width,
      height: bounds.height,
    }

    const onMove = (ev) => {
      if (!resizeStartRef.current) {
        return
      }

      ev.preventDefault()
      const start = resizeStartRef.current
      const nextSize = {
        width: start.width + ev.screenX - start.x,
        height: start.height + ev.screenY - start.y,
        minHeight: minPanelHeight + 132,
      }

      if (resizeFrameRef.current) {
        window.cancelAnimationFrame(resizeFrameRef.current)
      }
      resizeFrameRef.current = window.requestAnimationFrame(() => {
        resizeFrameRef.current = 0
        window.electronAPI?.resizeOverlayBottomRight?.(nextSize)
      })
    }

    const onUp = () => {
      resizeStartRef.current = null
      if (resizeFrameRef.current) {
        window.cancelAnimationFrame(resizeFrameRef.current)
        resizeFrameRef.current = 0
      }
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      window.removeEventListener('pointercancel', onUp)
    }

    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    window.addEventListener('pointercancel', onUp)
  }, [])

  const answerGroups = useMemo(() => {
    if (revealInProgress) {
      return []
    }
    if (structuredCodingAnswer) {
      return []
    }
    return groupConceptualAnswer(parseConceptualAnswer(visibleBody))
  }, [revealInProgress, structuredCodingAnswer, visibleBody])
  const snippet = `${visibleBody.replace(/\n/g, ' ').slice(0, 80)}${visibleBody.length > 80 ? '...' : ''}`

  const handleAnalyzeScreenAction = async () => {
    if (screenBusy) {
      return
    }
    await window.electronAPI?.triggerToolbarAction?.('analyze-screen-ocr', {
      trigger: screenHasError && !screenHasResult
        ? 'retry_analysis'
        : screenHasResult
          ? 'analyze_again'
          : 'initial_analysis',
    })
  }

  const handleKeepPreviousAnswer = async () => {
    await window.electronAPI?.triggerToolbarAction?.('keep-previous-screen-answer')
  }

  const handleUseExtension = async () => {
    await window.electronAPI?.triggerToolbarAction?.('analyze-screen-extension')
  }

  const handleManualSubmit = async () => {
    if (overlayState.isManualGenerating) {
      return
    }

    const text = chatDraft.trim()
    if (!text) {
      setChatError('Please type a question first.')
      return
    }

    setChatError('')
    setChatAwaitingResult(true)
    await window.electronAPI?.triggerToolbarAction?.('submit-manual-question', {
      text,
    })
  }

  const handleChatKeyDown = async (event) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      setChatDraft('')
      setChatError('')
      setChatEditing(false)
      setChatAwaitingResult(false)
      await window.electronAPI?.triggerToolbarAction?.('reset-manual-chat')
      onCancelChat?.()
      return
    }

    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      await handleManualSubmit()
    }
  }

  const handleRegenerateAnswer = async () => {
    await window.electronAPI?.triggerToolbarAction?.('ai-answer')
  }

  const handleDeleteAnswer = async () => {
    await window.electronAPI?.triggerToolbarAction?.('clear-answers')
  }

  const handleShowFullAnswer = async () => {
    await window.electronAPI?.triggerToolbarAction?.('show-full-answer')
  }

  const handleHistoryPrevious = async () => {
    await window.electronAPI?.triggerToolbarAction?.('history-previous', {
      mode: historyMode,
    })
  }

  const handleHistoryNext = async () => {
    await window.electronAPI?.triggerToolbarAction?.('history-next', {
      mode: historyMode,
    })
  }

  if (collapsed) {
    return (
      <div
        className="topbar-answer-collapsed"
        style={{
          width: panelWidth,
          ...panelShellStyle,
        }}
      >
        <p className="topbar-answer-collapsed__snippet">
          {snippet || 'Waiting for the latest answer...'}
        </p>

        <button
          type="button"
          onClick={() => setCollapsed(false)}
          className="topbar-answer-collapsed__show"
        >
          Show
        </button>

        <button type="button" onClick={handleDeleteAnswer} style={iconButtonStyle} title="Delete">
          <Trash2 size={13} className="topbar-answer-icon-muted" />
        </button>

        <button type="button" style={iconButtonStyle} title="Collapse">
          <ChevronDown size={13} className="topbar-answer-icon-muted" />
        </button>

        <button type="button" onClick={onClose} style={iconButtonStyle} title="Close">
          <X size={13} className="topbar-answer-icon-muted" />
        </button>
      </div>
    )
  }

  return (
    <div
      className="topbar-answer-panel"
      style={{
        width: panelWidth,
        height: panelHeight,
        maxHeight: maxPanelHeight,
        ...panelShellStyle,
      }}
    >
      <div className="topbar-answer-panel__header">
        <div className={`topbar-answer-panel__question-row${mode === 'chat' ? ' topbar-answer-panel__question-row--chat' : ''}`}>
          {mode === 'chat' && chatEditing ? null : (
            <span className="topbar-answer-panel__label">Question:</span>
          )}
          {mode === 'chat' && chatEditing ? (
            <div className="topbar-chat-panel__question-shell">
              <textarea
                ref={chatInputRef}
                className="topbar-chat-panel__textarea no-drag"
                value={chatDraft}
                onChange={(event) => {
                  setChatDraft(event.target.value)
                  if (chatError) {
                    setChatError('')
                  }
                }}
                onKeyDown={handleChatKeyDown}
                placeholder="Ask or paste a question..."
                rows={1}
                disabled={overlayState.isManualGenerating}
              />
              {chatError ? (
                <p className="topbar-chat-panel__error">{chatError}</p>
              ) : (
                <p className="topbar-chat-panel__hint">
                  Enter to submit. Shift+Enter adds a line. Esc cancels.
                </p>
              )}
            </div>
          ) : (
            <p className="topbar-answer-panel__question">
              {mode === 'analyzeScreen' ? cleanedScreenQuestionSummary : content.title}
            </p>
          )}
          {historySummary.total > 0 && mode !== 'chat' ? (
            <div
              className="topbar-answer-panel__history-controls no-drag"
              aria-label={`Question ${historySummary.position} of ${historySummary.total}`}
            >
              <button
                type="button"
                className="topbar-answer-panel__history-button"
                onClick={handleHistoryPrevious}
                disabled={!historySummary.canPrevious}
                title="Previous question"
              >
                <ChevronLeft size={13} />
              </button>
              <span className="topbar-answer-panel__history-position">
                {historySummary.position} / {historySummary.total}
              </span>
              <button
                type="button"
                className="topbar-answer-panel__history-button"
                onClick={handleHistoryNext}
                disabled={!historySummary.canNext}
                title="Next question"
              >
                <ChevronRight size={13} />
              </button>
            </div>
          ) : null}
        </div>
      </div>

      <div
        ref={bodyRef}
        className="topbar-answer-panel__body"
      >
        {mode === 'analyzeScreen' ? (
          <div className="topbar-screen-panel">
            {screenBusy && screenHasResult ? (
              <div className="topbar-chat-panel__status" style={{ marginBottom: 10 }}>
                <LoaderCircle size={13} className="topbar-screen-panel__spinner" />
                <span>Analyzing a new screen...</span>
              </div>
            ) : null}

            {overlayState.screenError ? (
              <div className="topbar-screen-panel__error-block">
                <p className="topbar-chat-panel__error">{overlayState.screenError}</p>
                <div className="topbar-screen-panel__actions">
                  <button
                    type="button"
                    className="topbar-screen-panel__button"
                    onClick={handleAnalyzeScreenAction}
                    disabled={screenBusy || overlayState.recording || overlayState.autoMode}
                  >
                    Retry Analyze Screen
                  </button>
                  {screenHasResult ? (
                    <button
                      type="button"
                      className="topbar-screen-panel__button topbar-screen-panel__button--ghost"
                      onClick={handleKeepPreviousAnswer}
                      disabled={screenBusy}
                    >
                      Keep Previous Answer
                    </button>
                  ) : null}
                </div>
              </div>
            ) : null}

            {showScreenAnswerMode ? (
              <>
                <div className="topbar-answer-panel__answer-row">
                  <span className="topbar-answer-panel__label">
                    {overlayState.screenQuestionType === 'coding' ||
                    overlayState.screenQuestionType === 'debugging' ||
                    overlayState.screenQuestionType === 'output'
                      ? 'Coding Solution:'
                      : screenBatchResult
                        ? 'Screen Answers:'
                        : 'Screen Answer:'}
                  </span>
                </div>

                {overlayState.screenAnswerLoading ? (
                  <div className="topbar-chat-panel__status">
                    <LoaderCircle size={13} className="topbar-screen-panel__spinner" />
                    <span>Regenerating screen answer...</span>
                  </div>
                ) : null}

                {effectiveScreenAnswerText ? (
                  <div className="topbar-screen-panel__answer">
                    {formattedScreenAnswerSections.length > 0 ? (
                      formattedScreenAnswerSections.map((section, index) => (
                        <div
                          key={`${section.label || 'section'}-${index}`}
                          className="topbar-screen-panel__solution-section"
                        >
                          {section.label ? (
                            <p className="topbar-screen-panel__solution-title">
                              {section.label}:
                            </p>
                          ) : null}
                          {renderSolutionText(section.body, `${section.label || 'section'}-${index}`)}
                        </div>
                      ))
                    ) : (
                      <div className="topbar-screen-panel__solution-section">
                        {renderSolutionText(
                          effectiveScreenAnswerText.replace(/```[^\n`]*\n?[\s\S]*?```/g, '').trim(),
                          'fallback-solution'
                        )}
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="topbar-screen-panel__hint">
                    Screen answer will appear here after generation.
                  </p>
                )}

                {effectiveScreenCode ? (
                  <div className="topbar-screen-panel__code-wrap">
                    <div className="topbar-screen-panel__meta">
                      <span>Code{effectiveScreenCodeLanguage ? ` (${effectiveScreenCodeLanguage})` : ''}</span>
                    </div>
                    <pre
                      className={`topbar-screen-panel__code language-${effectiveScreenCodeLanguage || 'plain'}`}
                      data-language={effectiveScreenCodeLanguage || 'plain'}
                    >
                      <code>{renderHighlightedCode(effectiveScreenCode, effectiveScreenCodeLanguage)}</code>
                    </pre>
                  </div>
                ) : null}

                <div className="topbar-screen-panel__actions">
                  {copyableScreenCode.code ? (
                    <button
                      type="button"
                      className="topbar-screen-panel__button"
                      aria-label="Copy Code"
                      onClick={() => copyToClipboard(copyableScreenCode.code)}
                    >
                      Copy Code
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="topbar-screen-panel__button topbar-screen-panel__button--ghost"
                    onClick={handleAnalyzeScreenAction}
                    disabled={screenBusy || overlayState.recording || overlayState.autoMode}
                  >
                    Analyze Screen
                  </button>
                  <button
                    type="button"
                    className="topbar-screen-panel__button topbar-screen-panel__button--ghost"
                    aria-label="Use Browser Extension"
                    onClick={handleUseExtension}
                    disabled={screenBusy}
                  >
                    Extension
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="topbar-answer-panel__answer-row">
                  <span className="topbar-answer-panel__label">Screen Answer:</span>
                </div>

                <div className="topbar-screen-panel__actions">
                  <button
                    type="button"
                    className="topbar-screen-panel__button"
                    onClick={handleAnalyzeScreenAction}
                    disabled={
                      overlayState.ocrProcessing ||
                      overlayState.screenAnswerLoading ||
                      overlayState.recording ||
                      overlayState.autoMode
                    }
                  >
                    {overlayState.ocrProcessing || overlayState.screenAnswerLoading ? (
                      <>
                        <LoaderCircle size={13} className="topbar-screen-panel__spinner" />
                        {overlayState.ocrProcessing ? 'Analyzing...' : 'Generating...'}
                      </>
                    ) : (
                      'Analyze Screen'
                    )}
                  </button>

                  <button
                    type="button"
                    className="topbar-screen-panel__button topbar-screen-panel__button--ghost"
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
        ) : (
          <>
            <div className="topbar-answer-panel__answer-row">
              <span className="topbar-answer-panel__label">Answer:</span>
            </div>

            {mode === 'chat' && overlayState.isManualGenerating ? (
              <div className="topbar-chat-panel__status">
                <LoaderCircle size={13} className="topbar-screen-panel__spinner" />
                <span>Generating answer...</span>
              </div>
            ) : null}

            {revealInProgress ? (
              <button
                type="button"
                className="topbar-screen-panel__button topbar-screen-panel__button--ghost"
                onClick={handleShowFullAnswer}
                style={{ marginBottom: 10 }}
              >
                Show full answer
              </button>
            ) : null}

            {revealInProgress ? (
              <p
                className="topbar-answer-panel__paragraph"
                style={{ whiteSpace: 'pre-wrap' }}
              >
                {visibleBody}
                <span className="topbar-answer-panel__caret" />
              </p>
            ) : null}

            {structuredCodingAnswer ? (
              <div className="topbar-answer-panel__coding-answer">
                <section>
                  <h3 className="topbar-answer-panel__section-heading">Approach</h3>
                  <p className="topbar-answer-panel__paragraph">
                    {cleanInlineMarkdown(structuredCodingAnswer.approach)}
                  </p>
                </section>
                <section>
                  <div className="topbar-answer-panel__code-heading">
                    <h3 className="topbar-answer-panel__section-heading">Code</h3>
                    <button
                      type="button"
                      className="topbar-screen-panel__button topbar-screen-panel__button--ghost"
                      onClick={() => copyToClipboard(structuredCodingAnswer.code)}
                    >
                      Copy Code
                    </button>
                  </div>
                  <pre
                    className={`topbar-screen-panel__code language-${structuredCodingAnswer.language || 'plain'}`}
                    data-language={structuredCodingAnswer.language || 'plain'}
                  >
                    <code>{renderHighlightedCode(structuredCodingAnswer.code, structuredCodingAnswer.language)}</code>
                  </pre>
                </section>
                <section>
                  <h3 className="topbar-answer-panel__section-heading">Time Complexity</h3>
                  <p className="topbar-answer-panel__paragraph">
                    {cleanInlineMarkdown(structuredCodingAnswer.time_complexity)}
                  </p>
                </section>
                <section>
                  <h3 className="topbar-answer-panel__section-heading">Space Complexity</h3>
                  <p className="topbar-answer-panel__paragraph">
                    {cleanInlineMarkdown(structuredCodingAnswer.space_complexity)}
                  </p>
                </section>
              </div>
            ) : null}

            {!revealInProgress && !structuredCodingAnswer ? answerGroups.map((group, index) => {
              const caret = index === answerGroups.length - 1 && revealInProgress

              if (group.type === 'list') {
                return (
                  <ul key={`${mode}-${index}`} className="topbar-answer-panel__list">
                    {group.items.map((item, itemIndex) => (
                      <li key={`${mode}-${index}-${itemIndex}`}>
                        {item}
                        {caret && itemIndex === group.items.length - 1 ? (
                          <span className="topbar-answer-panel__caret" />
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )
              }

              if (group.type === 'heading') {
                return (
                  <h3 key={`${mode}-${index}`} className="topbar-answer-panel__section-heading">
                    {group.text}
                    {caret ? <span className="topbar-answer-panel__caret" /> : null}
                  </h3>
                )
              }

              return (
                <p key={`${mode}-${index}`} className="topbar-answer-panel__paragraph">
                  {group.text}
                  {caret ? <span className="topbar-answer-panel__caret" /> : null}
                </p>
              )
            }) : null}
          </>
        )}
      </div>

      <div className="topbar-answer-panel__footer">
        <span className="topbar-answer-panel__footer-text">{content.footer}</span>

        <div className="topbar-answer-panel__footer-actions">
          <button
            type="button"
            onClick={handleRegenerateAnswer}
            style={iconButtonStyle}
            title="Regenerate answer"
          >
            <RotateCcw size={13} className="topbar-answer-icon-muted" />
          </button>

          <button type="button" onClick={handleDeleteAnswer} style={iconButtonStyle} title="Delete answer">
            <Trash2 size={13} className="topbar-answer-icon-muted" />
          </button>

          <button
            type="button"
            onClick={() => setCollapsed(true)}
            style={iconButtonStyle}
            title="Collapse"
          >
            <X size={13} className="topbar-answer-icon-muted" />
          </button>

          <div
            className="topbar-answer-resize-handle no-drag"
            onPointerDown={handleResizePointerDown}
            style={{ ...iconButtonStyle, marginLeft: 4 }}
            title="Resize"
          >
            <Maximize2 size={13} className="topbar-answer-icon-resize" />
          </div>
        </div>
      </div>
    </div>
  )
}

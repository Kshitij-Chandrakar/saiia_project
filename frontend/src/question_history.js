export const QUESTION_HISTORY_LIMIT = 50

function stripInternalControlMarkers(text) {
  return String(text || '')
    .replace(/\[\[\s*(category|type|mode|intent|answer_type)\s*:\s*[A-Za-z0-9_. -]{0,80}\s*\]\]/gi, '')
    .trim()
}

const EMPTY_MODE_HISTORY = Object.freeze({
  entries: Object.freeze([]),
  currentIndex: -1,
})

export function createQuestionHistoryState() {
  return {
    answer: { entries: [], currentIndex: -1 },
    screen: { entries: [], currentIndex: -1 },
  }
}

export function normalizeQuestionHistoryMode(mode) {
  if (mode === 'answer' || mode === 'manual' || mode === 'auto') {
    return 'answer'
  }
  if (mode === 'screen' || mode === 'analyzeScreen') {
    return 'screen'
  }
  return ''
}

export function createQuestionHistoryEntry({
  id,
  mode,
  requestId = '',
  question = '',
  originalQuestion = '',
  resolvedQuestion = '',
  followUpDetected = false,
  followUpConfidence = null,
  followUpResolutionStatus = '',
  followUpContextEntryIds = [],
  topic = '',
  resolutionMethod = '',
  fullAnswer = '',
  displayedAnswer = '',
  status = 'complete',
  category = '',
  provider = '',
  model = '',
  primaryProvider = '',
  primaryModel = '',
  generationMs = null,
  totalPipelineMs = null,
  metadata = {},
  createdAt = new Date().toISOString(),
  completedAt = null,
} = {}) {
  return {
    id: id || `question-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    mode: normalizeQuestionHistoryMode(mode),
    requestId: String(requestId || ''),
    question: String(question || ''),
    originalQuestion: String(originalQuestion || question || ''),
    resolvedQuestion: String(resolvedQuestion || ''),
    followUpDetected: Boolean(followUpDetected),
    followUpConfidence,
    followUpResolutionStatus: String(followUpResolutionStatus || ''),
    followUpContextEntryIds: Array.isArray(followUpContextEntryIds) ? [...followUpContextEntryIds] : [],
    topic: String(topic || ''),
    resolutionMethod: String(resolutionMethod || ''),
    fullAnswer: stripInternalControlMarkers(fullAnswer),
    displayedAnswer: stripInternalControlMarkers(displayedAnswer || fullAnswer),
    status,
    category: String(category || ''),
    provider: String(provider || ''),
    model: String(model || ''),
    primaryProvider: String(primaryProvider || ''),
    primaryModel: String(primaryModel || ''),
    generationMs,
    totalPipelineMs,
    metadata: metadata && typeof metadata === 'object' ? { ...metadata } : {},
    createdAt,
    completedAt,
  }
}

function getModeHistory(state, mode) {
  return state?.[mode] || EMPTY_MODE_HISTORY
}

function enforceHistoryLimit(entries, currentIndex, limit) {
  let nextEntries = entries
  let nextIndex = currentIndex

  while (nextEntries.length > limit) {
    const removableIndex = nextEntries.findIndex(
      (entry, index) => entry.status !== 'generating' && index !== nextIndex
    )
    const removeAt = removableIndex >= 0 ? removableIndex : 0
    nextEntries = nextEntries.filter((_, index) => index !== removeAt)
    if (removeAt < nextIndex) {
      nextIndex -= 1
    } else if (removeAt === nextIndex) {
      nextIndex = Math.min(nextIndex, nextEntries.length - 1)
    }
  }

  return { entries: nextEntries, currentIndex: nextIndex }
}

export function appendQuestionHistoryEntry(state, entry, limit = QUESTION_HISTORY_LIMIT) {
  const mode = normalizeQuestionHistoryMode(entry?.mode)
  if (!mode) {
    return state
  }

  const modeHistory = getModeHistory(state, mode)
  const nextEntry = createQuestionHistoryEntry({ ...entry, mode })
  const withoutExisting = modeHistory.entries.filter((item) => item.id !== nextEntry.id)
  const limited = enforceHistoryLimit([...withoutExisting, nextEntry], withoutExisting.length, limit)

  return {
    ...state,
    [mode]: limited,
  }
}

export function updateQuestionHistoryEntry(state, modeInput, entryId, patch, options = {}) {
  const mode = normalizeQuestionHistoryMode(modeInput)
  if (!mode || !entryId) {
    return state
  }

  const modeHistory = getModeHistory(state, mode)
  let changed = false
  const entries = modeHistory.entries.map((entry) => {
    if (entry.id !== entryId) {
      return entry
    }
    if (options.requestId && entry.requestId && entry.requestId !== String(options.requestId)) {
      return entry
    }
    changed = true
    return {
      ...entry,
      ...patch,
      fullAnswer: Object.prototype.hasOwnProperty.call(patch || {}, 'fullAnswer')
        ? stripInternalControlMarkers(patch.fullAnswer)
        : entry.fullAnswer,
      displayedAnswer: Object.prototype.hasOwnProperty.call(patch || {}, 'displayedAnswer')
        ? stripInternalControlMarkers(patch.displayedAnswer)
        : entry.displayedAnswer,
      metadata: patch?.metadata
        ? { ...(entry.metadata || {}), ...patch.metadata }
        : entry.metadata,
    }
  })

  if (!changed) {
    return state
  }

  return {
    ...state,
    [mode]: {
      ...modeHistory,
      entries,
    },
  }
}

export function selectQuestionHistoryIndex(state, modeInput, index) {
  const mode = normalizeQuestionHistoryMode(modeInput)
  if (!mode) {
    return state
  }

  const modeHistory = getModeHistory(state, mode)
  if (!modeHistory.entries.length) {
    return state
  }

  const nextIndex = Math.max(0, Math.min(modeHistory.entries.length - 1, index))
  if (nextIndex === modeHistory.currentIndex) {
    return state
  }

  return {
    ...state,
    [mode]: {
      ...modeHistory,
      currentIndex: nextIndex,
    },
  }
}

export function selectQuestionHistoryOffset(state, modeInput, offset) {
  const mode = normalizeQuestionHistoryMode(modeInput)
  if (!mode) {
    return state
  }

  const modeHistory = getModeHistory(state, mode)
  return selectQuestionHistoryIndex(state, mode, modeHistory.currentIndex + offset)
}

export function getSelectedQuestionHistoryEntry(state, modeInput) {
  const mode = normalizeQuestionHistoryMode(modeInput)
  if (!mode) {
    return null
  }
  const modeHistory = getModeHistory(state, mode)
  return modeHistory.entries[modeHistory.currentIndex] || null
}

export function getQuestionHistorySummary(state, modeInput) {
  const mode = normalizeQuestionHistoryMode(modeInput)
  const modeHistory = getModeHistory(state, mode)
  const total = modeHistory.entries.length
  const currentIndex = total ? Math.max(0, Math.min(modeHistory.currentIndex, total - 1)) : -1

  return {
    mode,
    total,
    currentIndex,
    position: currentIndex >= 0 ? currentIndex + 1 : 0,
    canPrevious: currentIndex > 0,
    canNext: currentIndex >= 0 && currentIndex < total - 1,
  }
}

export function hasSavedScreenResult(state = {}) {
  return Boolean(
    String(state.ocrText || '').trim() ||
    String(state.screenAnswerText || '').trim() ||
    state.screenAnswerGenerated ||
    state.screenAnswerDisplayedInPanel ||
    state.screenAnswerCommittedToOverlay ||
    String(state.extractedScreenQuestion || '').trim() ||
    String(state.finalExtractedScreenQuestion || '').trim()
  )
}

export function hasScreenError(state = {}) {
  return Boolean(String(state.screenError || '').trim())
}

export function isScreenAnalysisRunning(state = {}) {
  return Boolean(state.ocrProcessing || state.screenAnswerLoading)
}

export function extractCopyableCode(result = {}) {
  const structuredCode = String(
    result.screenCodeAnswer ||
      result.code ||
      result.codingAnswer?.code ||
      result.metadata?.screenCodeAnswer ||
      ''
  )
  if (structuredCode.trim()) {
    return {
      code: structuredCode.replace(/\s+$/, ''),
      language: String(result.screenCodeLanguage || result.language || result.codingAnswer?.language || '').trim(),
    }
  }

  const answerText = String(
    result.screenAnswerText ||
      result.answerText ||
      result.fullAnswer ||
      result.displayedAnswer ||
      result.answer ||
      ''
  )
  const match = answerText.match(/```([\w+-]*)\s*\n([\s\S]*?)```/)
  const code = String(match?.[2] || '').replace(/\s+$/, '').trim()
  return {
    code,
    language: String(match?.[1] || '').trim().toLowerCase(),
  }
}

export function hasCopyableCode(result = {}) {
  return Boolean(extractCopyableCode(result).code)
}

export function shouldStartInitialScreenAnalysis(state = {}) {
  return !isScreenAnalysisRunning(state) && !hasSavedScreenResult(state) && !hasScreenError(state)
}

export function getScreenAnalysisActionLabel(state = {}) {
  if (isScreenAnalysisRunning(state)) {
    return 'Analyzing...'
  }
  return 'Analyze Screen'
}

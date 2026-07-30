const QUESTION_TYPE_COMPATIBILITY = {
  coding: 'coding',
  debugging: 'debugging',
  output: 'output_prediction',
  output_prediction: 'output_prediction',
  mcq: 'mcq',
  visual: 'diagram',
  diagram: 'diagram',
  chart: 'chart',
  architecture: 'architecture',
  system_design: 'system_design',
  technical: 'technical',
  aptitude: 'aptitude',
  interview: 'general',
  general: 'general',
  none: 'unknown',
  '': 'unknown',
}

export function normalizeQuestionType(value) {
  const key = String(value || '').trim().toLowerCase()
  return QUESTION_TYPE_COMPATIBILITY[key] || 'unknown'
}

export function normalizeScreenResponse(response = {}) {
  const legacy = response && typeof response === 'object' ? response : {}
  const envelope = isUsableEnvelope(legacy.envelope)
    ? legacy.envelope
    : buildEnvelopeFromLegacy(legacy)

  return {
    legacy,
    envelope,
    questions: Array.isArray(envelope.questions) ? envelope.questions : [],
  }
}

export function getScreenQuestions(result = {}) {
  return normalizeScreenResponse(result).questions
}

export function getScreenAnswerText(result = {}) {
  const legacyAnswer = String(result?.answer || result?.screenAnswerText || result?.fullAnswer || '').trim()
  if (legacyAnswer) {
    return legacyAnswer
  }
  return getScreenQuestions(result)
    .map((item) => item?.question?.answer?.text || '')
    .filter(Boolean)
    .join('\n')
}

export function getScreenCode(result = {}) {
  const legacyCode = String(result?.code || result?.screenCodeAnswer || result?.metadata?.screenCodeAnswer || '').trim()
  if (legacyCode) {
    return legacyCode
  }
  return getScreenQuestions(result).find((item) => item?.question?.answer?.code)?.question?.answer?.code || ''
}

export function getScreenQuestionType(result = {}) {
  const legacyType = String(result?.question_type || result?.screenQuestionType || result?.metadata?.screenQuestionType || '').trim()
  if (legacyType) {
    return normalizeQuestionType(legacyType)
  }
  return getScreenQuestions(result)[0]?.question?.question_type || 'unknown'
}

export function getScreenExtractionStatus(result = {}) {
  return normalizeScreenResponse(result).envelope.status || 'failed'
}

function isUsableEnvelope(envelope) {
  return Boolean(
    envelope &&
      typeof envelope === 'object' &&
      envelope.schema_version === '1.0' &&
      envelope.mode === 'screen' &&
      Array.isArray(envelope.questions)
  )
}

function buildEnvelopeFromLegacy(legacy) {
  const ok = Boolean(legacy.ok)
  const questions = ok ? buildQuestionsFromLegacy(legacy) : []
  return {
    schema_version: '1.0',
    request_id: String(legacy.request_id || 'legacy_screen_request'),
    operation_id: String(legacy.operation_id || 'legacy_screen_operation'),
    mode: 'screen',
    source_type: 'screen_capture',
    browser: null,
    status: questions.length ? 'ready' : 'failed',
    questions,
    selected_question_id: questions.length === 1 ? questions[0].question_id : null,
    extraction: {
      complete: questions.length > 0 && !Boolean(legacy.incomplete),
      confidence: clampConfidence(legacy.confidence),
      missing_sections: [],
      warnings: Number(legacy.incomplete_question_count || 0) > 0 ? ['incomplete_questions_ignored'] : [],
      method: 'screen_vision',
    },
    timing: {
      capture_ms: nonnegativeNumber(legacy.capture_ms),
      image_prepare_ms: nonnegativeNumber(legacy.image_prepare_ms),
      screen_model_ms: nonnegativeNumber(legacy.screen_model_ms || legacy.vision_ms),
      response_parse_ms: nonnegativeNumber(legacy.response_parse_ms),
      overlay_render_ms: legacy.overlay_render_ms == null ? null : nonnegativeNumber(legacy.overlay_render_ms),
      total_ms: nonnegativeNumber(legacy.total_screen_pipeline_ms),
    },
    metrics: {
      screenshot_count: nonnegativeInteger(legacy.screenshot_count, 1),
      screen_model_request_count: nonnegativeInteger(legacy.screen_model_request_count, 1),
      automatic_fallback_count: nonnegativeInteger(legacy.automatic_fallback_count, 0),
      correction_request_count: nonnegativeInteger(legacy.correction_request_count, 0),
      generation_request_count: nonnegativeInteger(legacy.generation_request_count, 0),
    },
    error: questions.length
      ? null
      : {
          code: 'unreadable_screen',
          message: String(legacy.error || 'The question could not be read clearly.'),
          retryable: true,
          details: null,
        },
  }
}

function buildQuestionsFromLegacy(legacy) {
  const rawItems = Array.isArray(legacy.items) && legacy.items.length ? legacy.items : [legacy]
  return rawItems
    .map((item, index) => buildQuestionItem(item, index + 1))
    .filter(Boolean)
}

function buildQuestionItem(item, index) {
  const statement = String(item?.question || '').trim()
  const answerText = String(item?.answer || '').trim()
  if (!statement || !answerText) {
    return null
  }
  const questionType = normalizeQuestionType(item.question_type)
  const code = String(item.code || '').trim() || null
  const language = String(item.language || '').trim() || null
  return {
    question_id: String(item.question_id || `screen_question_${index}`),
    display_number: String(item.display_number || ''),
    question: {
      question_type: questionType,
      title: '',
      statement,
      function_description: '',
      input_format: '',
      output_format: '',
      constraints: [],
      examples: [],
      options: [],
      answer: {
        text: answerText,
        code,
        explanation: null,
      },
      visual_context: {
        diagram_present: questionType === 'diagram' || questionType === 'architecture',
        chart_present: questionType === 'chart',
        image_context_required: ['diagram', 'chart', 'architecture'].includes(questionType),
        visual_description: null,
      },
      code_context: {
        selected_language: language,
        language_source: language ? 'unknown' : null,
        starter_code: null,
        function_signature: null,
        class_name: null,
        editor_type: null,
        platform_mode: null,
        submission_mode: questionType === 'coding' && code ? 'standalone_program' : null,
      },
    },
    region: null,
  }
}

function clampConfidence(value) {
  return Math.max(0, Math.min(1, nonnegativeNumber(value)))
}

function nonnegativeNumber(value) {
  const numeric = Number(value || 0)
  return Number.isFinite(numeric) ? Math.max(0, numeric) : 0
}

function nonnegativeInteger(value, fallback) {
  const numeric = Number.parseInt(value, 10)
  return Number.isFinite(numeric) ? Math.max(0, numeric) : fallback
}

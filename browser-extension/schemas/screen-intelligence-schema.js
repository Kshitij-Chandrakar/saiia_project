import { ERROR_CODES, safeError } from '../core/errors.js'
import { LIMITS } from '../core/payload-limits.js'

export const QUESTION_TYPES = Object.freeze([
  'coding',
  'debugging',
  'output_prediction',
  'mcq',
  'diagram',
  'chart',
  'architecture',
  'system_design',
  'technical',
  'aptitude',
  'general',
  'unknown',
])

export function emptyAnswer() {
  return { text: null, code: null, explanation: null }
}

export function buildEnvelope({ operation_id, request_id, browser, question, extraction, timingMs = 0 }) {
  const scope = classifyExtensionScope({ question, extraction })
  if (!scope.supported) {
    return buildFailedEnvelope({
      operation_id,
      request_id,
      browser,
      code: ERROR_CODES.unsupportedPage,
      message: 'No coding problem was detected in the active tab. Use Analyze Screen OCR for other question types.',
      retryable: false,
      timingMs,
      extraction: { ...extraction, scope },
    })
  }
  const complete = Boolean(extraction?.complete)
  const status = extraction?.status || (complete ? 'ready' : 'incomplete')
  const questionItem = {
    question_id: 'question_1',
    display_number: '',
    question,
    region: null,
  }
  return enforceEnvelopeLimits({
    schema_version: '1.0',
    request_id,
    operation_id,
    mode: 'screen',
    source_type: 'browser_extension',
    status,
    browser,
    questions: [questionItem],
    selected_question_id: 'question_1',
    extraction: {
      complete,
      confidence: Math.max(0, Math.min(1, Number(extraction?.confidence || 0))),
      missing_sections: Array.isArray(extraction?.missing_sections) ? extraction.missing_sections : [],
      warnings: Array.isArray(extraction?.warnings) ? extraction.warnings : [],
      method: 'generic_dom',
      candidate_count: Number.isFinite(extraction?.candidate_count) ? extraction.candidate_count : null,
      selected_candidate_score: Number.isFinite(extraction?.selected_candidate_score) ? extraction.selected_candidate_score : null,
      selection_strategy: extraction?.selection_strategy || null,
      valid_option_count: Number.isFinite(extraction?.valid_option_count) ? extraction.valid_option_count : null,
      detected_option_count: Number.isFinite(extraction?.detected_option_count) ? extraction.detected_option_count : null,
      valid_mcq_group: Boolean(extraction?.valid_mcq_group),
      scope,
      diagnostics: safeDiagnostics(extraction?.diagnostics),
    },
    timing: { total_ms: Math.max(0, Number(timingMs || 0)) },
    metrics: {
      screenshot_count: 0,
      screen_model_request_count: 0,
      automatic_fallback_count: 0,
      correction_request_count: 0,
      generation_request_count: 0,
    },
    error: null,
  })
}

export function buildFailedEnvelope({ operation_id, request_id, browser = null, code, message, retryable = true, timingMs = 0, extraction = null }) {
  return {
    schema_version: '1.0',
    request_id,
    operation_id,
    mode: 'screen',
    source_type: 'browser_extension',
    status: 'failed',
    browser,
    questions: [],
    selected_question_id: null,
    extraction: {
      complete: false,
      confidence: Math.max(0, Math.min(1, Number(extraction?.confidence || 0))),
      missing_sections: [],
      warnings: Array.isArray(extraction?.warnings) ? extraction.warnings : [],
      method: 'generic_dom',
      candidate_count: Number.isFinite(extraction?.candidate_count) ? extraction.candidate_count : null,
      selected_candidate_score: Number.isFinite(extraction?.selected_candidate_score) ? extraction.selected_candidate_score : null,
      selection_strategy: extraction?.selection_strategy || null,
      valid_option_count: Number.isFinite(extraction?.valid_option_count) ? extraction.valid_option_count : null,
      detected_option_count: Number.isFinite(extraction?.detected_option_count) ? extraction.detected_option_count : null,
      valid_mcq_group: Boolean(extraction?.valid_mcq_group),
      scope: extraction?.scope || null,
      diagnostics: safeDiagnostics(extraction?.diagnostics),
    },
    timing: { total_ms: Math.max(0, Number(timingMs || 0)) },
    metrics: {
      screenshot_count: 0,
      screen_model_request_count: 0,
      automatic_fallback_count: 0,
      correction_request_count: 0,
      generation_request_count: 0,
    },
    error: safeError(code, message, null, retryable),
  }
}

export function classifyExtensionScope({ question, extraction = null }) {
  const evidence = collectCodingEvidence({ question, extraction })
  if (evidence.validMcqGroupPresent) {
    return scopeResult(false, 'mcq_option_group_detected', evidence, 0.97)
  }
  if (evidence.outputPredictionOnly) {
    return scopeResult(false, 'output_prediction_uses_ocr', evidence, 0.94)
  }
  if (evidence.debugFixInstructionPresent && evidence.relevantCodePresent) {
    return scopeResult(true, 'debugging_task_with_code_fix_intent', evidence)
  }
  if (evidence.strongCodingWorkspace) {
    return scopeResult(true, 'coding_workspace_with_code_context', evidence)
  }
  if (evidence.fullProgramTask) {
    return scopeResult(true, 'full_program_task', evidence)
  }
  if (evidence.usableCodingInstruction && evidence.hasCodingStructure) {
    return scopeResult(true, evidence.starterCodePresent || evidence.functionSignaturePresent || evidence.classNamePresent || evidence.editorPresent ? 'actionable_function_stub' : 'actionable_coding_task', evidence)
  }
  if (evidence.visualOnly) {
    return scopeResult(false, 'visual_question_uses_ocr', evidence, 0.92)
  }
  return scopeResult(false, 'no_actionable_coding_task', evidence, 0.9)
}

export function collectCodingEvidence({ question = {}, extraction = null }) {
  const codeContext = question?.code_context || {}
  const text = sanitizeScopeText([
    question?.cleaned_question,
    question?.raw_question,
    question?.statement,
    question?.function_description,
    question?.task,
    question?.description,
    question?.input_format,
    question?.output_format,
  ].filter(Boolean).join('\n')).toLowerCase()
  const starterCode = [
    codeContext?.starter_code,
    question?.starter_code,
    question?.visible_code,
    question?.editor_code,
  ].filter(Boolean).join('\n')
  const functionSignature = codeContext?.function_signature || question?.function_signature || ''
  const className = codeContext?.class_name || question?.class_name || ''
  const optionCount = Array.isArray(question?.options) ? question.options.length : 0
  const usableText = text.length >= 24
  const codingInstructionPresent = /\b(given|your task is to|you are required to|write|write code|implement|implement the solution|implement the function|implement the method|complete|complete the code|complete the solution|convert|find|calculate|compute|determine|construct|build|create|modify|remove|generate|sort|merge|reverse|rotate|return the required result|solve|solve this problem|solve this challenge|fill in|provide an implementation|process the input|produce the output|read input|read from standard input|standard input|stdin|print output|print to standard output|standard output|stdout|submit)\b/.test(text)
  const debugFixInstructionPresent = /\b(fix|debug|correct|repair|buggy|failing|broken)\b/.test(text)
  const fullProgramSignalsPresent = /\b(write a program|read input|read from standard input|standard input|stdin|print output|print to standard output|standard output|stdout)\b/.test(text) || Boolean(question?.input_format || question?.output_format)
  const starterCodePresent = Boolean(starterCode)
  const functionSignaturePresent = Boolean(functionSignature)
  const classNamePresent = Boolean(className)
  const editorPresent = Boolean(codeContext?.editor_present || codeContext?.editor_type || question?.editor_present)
  const editorTextAvailable = Boolean(codeContext?.editor_text_available || extraction?.diagnostics?.editor_text_available)
  const editorBoilerplateOnly = Boolean(codeContext?.editor_boilerplate_only || extraction?.diagnostics?.editor_boilerplate_only)
  const relevantCodePresent = starterCodePresent || functionSignaturePresent || classNamePresent || editorPresent
  const taskTextPresent = codingInstructionPresent || fullProgramSignalsPresent || Boolean(question?.function_description || question?.input_format || question?.output_format || question?.constraints?.length || question?.examples?.length || text.length >= 48)
  const strongCodingEvidence = relevantCodePresent || fullProgramSignalsPresent
  return {
    usableText,
    cleanedQuestionPresent: Boolean(question?.cleaned_question),
    statementPresent: Boolean(question?.statement),
    codingInstructionPresent,
    usableCodingInstruction: usableText && codingInstructionPresent,
    starterCodePresent,
    functionSignaturePresent,
    classNamePresent,
    editorPresent,
    editorTextAvailable,
    editorBoilerplateOnly,
    fullProgramSignalsPresent,
    strongCodingWorkspace: usableText && relevantCodePresent && taskTextPresent,
    fullProgramTask: usableText && fullProgramSignalsPresent,
    debugFixInstructionPresent,
    relevantCodePresent,
    hasCodingStructure: relevantCodePresent || fullProgramSignalsPresent || Boolean(question?.constraints?.length || question?.examples?.length || text.length >= 40),
    validMcqGroupPresent: question?.question_type === 'mcq' && optionCount >= 2 && extraction?.valid_mcq_group !== false,
    visualPresent: Boolean(question?.visual_context?.visual_present || question?.visual_context?.diagram_present || question?.visual_context?.chart_present),
    visualOnly: Boolean(question?.visual_context?.image_context_required && !strongCodingEvidence && !(usableText && codingInstructionPresent && Boolean(question?.constraints?.length || question?.examples?.length || text.length >= 40))),
    outputPredictionOnly: question?.question_type === 'output_prediction',
  }
}

function scopeResult(supported, reason, evidence, confidence = 0.92) {
  return {
    supported,
    scope: supported ? 'coding' : 'non_coding',
    reason,
    confidence,
    scope_supported: supported,
    scope_reason: reason,
    usable_text: evidence.usableText,
    coding_instruction: evidence.codingInstructionPresent,
    starter_code_present: evidence.starterCodePresent,
    function_signature_present: evidence.functionSignaturePresent,
    class_name_present: evidence.classNamePresent,
    editor_present: evidence.editorPresent,
    editor_text_available: evidence.editorTextAvailable,
    editor_boilerplate_only: evidence.editorBoilerplateOnly,
    relevant_code_present: evidence.relevantCodePresent,
    strong_coding_workspace: evidence.strongCodingWorkspace,
    full_program_signals: evidence.fullProgramSignalsPresent,
    debug_fix_instruction: evidence.debugFixInstructionPresent,
    valid_mcq_group: evidence.validMcqGroupPresent,
    visual_present: evidence.visualPresent,
    visual_context_required: evidence.visualOnly,
  }
}

function sanitizeScopeText(value) {
  return String(value ?? '')
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, LIMITS.maxTextLength)
}

export function validateEnvelope(envelope) {
  if (!envelope || typeof envelope !== 'object') {
    return { ok: false, error: 'envelope_required' }
  }
  if (JSON.stringify(envelope).includes('<html') || JSON.stringify(envelope).includes('<body')) {
    return { ok: false, error: 'raw_html_forbidden' }
  }
  if (envelope.schema_version !== '1.0' || envelope.source_type !== 'browser_extension') {
    return { ok: false, error: 'invalid_envelope_identity' }
  }
  if (envelope.metrics?.screenshot_count !== 0 || envelope.metrics?.screen_model_request_count !== 0) {
    return { ok: false, error: 'invalid_extension_metrics' }
  }
  if (envelope.questions?.some((item) => item?.question?.answer?.text || item?.question?.answer?.code)) {
    return { ok: false, error: 'extension_must_not_generate_answer' }
  }
  if (JSON.stringify(envelope).length > LIMITS.maxEnvelopeBytes) {
    return { ok: false, error: 'envelope_too_large' }
  }
  return { ok: true, error: null }
}

function safeDiagnostics(value) {
  if (!value || typeof value !== 'object') return null
  return {
    initial_candidate_count: Number.isFinite(value.initial_candidate_count) ? value.initial_candidate_count : null,
    collapsed_candidate_count: Number.isFinite(value.collapsed_candidate_count) ? value.collapsed_candidate_count : null,
    top_score: Number.isFinite(value.top_score) ? value.top_score : null,
    second_score: Number.isFinite(value.second_score) ? value.second_score : null,
    initial_top_score: Number.isFinite(value.initial_top_score) ? value.initial_top_score : null,
    initial_second_score: Number.isFinite(value.initial_second_score) ? value.initial_second_score : null,
    candidate_relationship: typeof value.candidate_relationship === 'string' ? value.candidate_relationship : null,
    shared_root_found: Boolean(value.shared_root_found),
    combined_split_layout: Boolean(value.combined_split_layout),
    independent_question_evidence: Array.isArray(value.independent_question_evidence)
      ? value.independent_question_evidence.slice(0, 8).filter((entry) => typeof entry === 'string')
      : [],
    selection_strategy: typeof value.selection_strategy === 'string' ? value.selection_strategy : null,
    final_status: typeof value.final_status === 'string' ? value.final_status : null,
    editor_candidate_count: Number.isFinite(value.editor_candidate_count) ? value.editor_candidate_count : null,
    editor_present: Boolean(value.editor_present),
    editor_type: typeof value.editor_type === 'string' ? value.editor_type : null,
    editor_code_available: Boolean(value.editor_code_available),
    editor_text_available: Boolean(value.editor_text_available),
    editor_boilerplate_only: Boolean(value.editor_boilerplate_only),
    code_extraction_method: typeof value.code_extraction_method === 'string' ? value.code_extraction_method : null,
    code_line_count: Number.isFinite(value.code_line_count) ? value.code_line_count : null,
    code_length: Number.isFinite(value.code_length) ? value.code_length : null,
    code_may_be_partial: Boolean(value.code_may_be_partial),
    code_extraction_warning: typeof value.code_extraction_warning === 'string' ? value.code_extraction_warning : null,
    editor_scope: typeof value.editor_scope === 'string' ? value.editor_scope : null,
    raw_example_candidate_count: Number.isFinite(value.raw_example_candidate_count) ? value.raw_example_candidate_count : null,
    final_example_count: Number.isFinite(value.final_example_count) ? value.final_example_count : null,
    duplicate_example_count: Number.isFinite(value.duplicate_example_count) ? value.duplicate_example_count : null,
    unknown_example_count: Number.isFinite(value.unknown_example_count) ? value.unknown_example_count : null,
    orphan_example_part_count: Number.isFinite(value.orphan_example_part_count) ? value.orphan_example_part_count : null,
    runtime_test_panel_excluded_count: Number.isFinite(value.runtime_test_panel_excluded_count) ? value.runtime_test_panel_excluded_count : null,
    constraint_candidate_count: Number.isFinite(value.constraint_candidate_count) ? value.constraint_candidate_count : null,
    final_constraint_count: Number.isFinite(value.final_constraint_count) ? value.final_constraint_count : null,
    constraints_truncated: Boolean(value.constraints_truncated),
    constraint_source: typeof value.constraint_source === 'string' ? value.constraint_source : null,
    constraint_code_like_rejected_count: Number.isFinite(value.constraint_code_like_rejected_count) ? value.constraint_code_like_rejected_count : null,
    section_boundary_stop_count: Number.isFinite(value.section_boundary_stop_count) ? value.section_boundary_stop_count : null,
    editor_section_excluded_count: Number.isFinite(value.editor_section_excluded_count) ? value.editor_section_excluded_count : null,
  }
}

function enforceEnvelopeLimits(envelope) {
  if (JSON.stringify(envelope).length <= LIMITS.maxEnvelopeBytes) {
    return envelope
  }
  envelope.extraction.warnings.push('payload_truncated')
  envelope.questions[0].question.statement = envelope.questions[0].question.statement.slice(0, LIMITS.maxTextLength)
  return envelope
}

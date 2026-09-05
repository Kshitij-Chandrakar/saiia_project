import React, { useEffect, useRef, useState } from 'react'
import { Route, Routes } from 'react-router-dom'
import {
  AuthCallbackPage,
  AuthDashboardPage,
  AuthDesktopLoginPage,
  AuthForgotPasswordPage,
  AuthLoginPage,
  AuthLogoutPage,
  AuthResumePage,
  AuthResetPasswordPage,
  AuthSignupPage,
  AuthStatusPage,
  AuthUnsubscribePage,
} from './auth/AuthScreens'
import MainDiagnosticsWindow from './components/MainDiagnosticsWindow'
import OverlayWindowView from './components/OverlayWindow'
import { readNdjsonStream, stripInternalControlMarkers } from './answer_stream'
import { isCurrentRequest } from './request_state'
import { normalizeScreenResponse } from './screen_intelligence_contract'
import {
  SCREEN_OPERATION_STATUS,
  canCommitScreenResult,
  cancelScreenOperation,
  createScreenOpaqueId,
  createScreenOperation,
  isCurrentScreenOperation,
  supersedeScreenOperation,
  transitionScreenOperation,
} from './screen_operation_state'
import {
  appendQuestionHistoryEntry,
  createQuestionHistoryEntry,
  createQuestionHistoryState,
  getSelectedQuestionHistoryEntry,
  normalizeQuestionHistoryMode,
  selectQuestionHistoryOffset,
  updateQuestionHistoryEntry,
} from './question_history'
import './styles/glass.css'

const BACKEND_URL = 'http://localhost:8000'
const OVERLAY_PRIVACY_MESSAGE =
  'Visibility during screen sharing depends on OS, meeting app, and whether the user shares full screen, window, or tab.'
const AUTO_MIC_CHUNK_MS = 4000
const AUTO_SYSTEM_CHUNK_MS = 3000
const AUTO_COOLDOWN_MS = 4000
const AUTO_BUFFER_TTL_MS = 12000
const AUTO_BUFFER_MAX_CHUNKS = 3
const AUTO_SEGMENT_GAP_MS = 1200
const AUTO_DUPLICATE_WINDOW_MS = 60000
const REFINEMENT_POLL_INTERVAL_MS = 2000
const REFINEMENT_POLL_START_DELAY_MS = 1500
const REFINEMENT_POLL_MAX_ATTEMPTS = 20
const REFINEMENT_POLL_TIMEOUT_MS = 45000
const SCREEN_CAPTURE_MAX_DIMENSION = 2200
const FOLLOWUP_CONTEXT_LIMIT = 5
const FOLLOWUP_ANSWER_EXCERPT_LIMIT = 800
const SCREEN_OCR_UNREADABLE_MESSAGE = 'The question could not be read clearly.'

function getBackendWebSocketUrl(path) {
  const base = BACKEND_URL.replace(/^http/i, 'ws')
  return `${base}${path}`
}

function downsampleToInt16Mono(float32Array, inputSampleRate, outputSampleRate = 16000) {
  if (!float32Array?.length) {
    return new Int16Array(0)
  }

  if (inputSampleRate === outputSampleRate) {
    const direct = new Int16Array(float32Array.length)
    for (let index = 0; index < float32Array.length; index += 1) {
      const sample = Math.max(-1, Math.min(1, float32Array[index]))
      direct[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff
    }
    return direct
  }

  const ratio = inputSampleRate / outputSampleRate
  const nextLength = Math.max(1, Math.round(float32Array.length / ratio))
  const result = new Int16Array(nextLength)
  let offsetResult = 0
  let offsetBuffer = 0

  while (offsetResult < result.length) {
    const nextOffsetBuffer = Math.min(
      float32Array.length,
      Math.round((offsetResult + 1) * ratio)
    )
    let accumulator = 0
    let count = 0
    for (let sampleIndex = offsetBuffer; sampleIndex < nextOffsetBuffer; sampleIndex += 1) {
      accumulator += float32Array[sampleIndex]
      count += 1
    }
    const sample = count ? accumulator / count : 0
    const normalized = Math.max(-1, Math.min(1, sample))
    result[offsetResult] = normalized < 0 ? normalized * 0x8000 : normalized * 0x7fff
    offsetResult += 1
    offsetBuffer = nextOffsetBuffer
  }

  return result
}

function getPreferredRecorderMimeType() {
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']
  return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || ''
}

function getAudioFilename(blob) {
  const type = blob.type.split(';')[0]
  const extensionByType = {
    'audio/webm': 'webm',
    'audio/wav': 'wav',
    'audio/x-wav': 'wav',
    'audio/mpeg': 'mp3',
    'audio/mp4': 'mp4',
    'audio/x-m4a': 'm4a',
    'audio/ogg': 'ogg',
  }

  const extension = extensionByType[type] || 'webm'
  return `clip.${extension}`
}

async function parseJsonResponse(response, fallbackMessage) {
  let payload = null

  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  if (!response.ok) {
    const message = payload?.detail || payload?.error || fallbackMessage
    throw new Error(message)
  }

  return payload
}

function normalizePipelineError(error, fallbackMessage) {
  const message = error?.message || fallbackMessage

  if (/selected resume is not ready for generation/i.test(message)) {
    return 'Selected resume is not ready for generation. Please finish resume setup or rebuild the index from the dashboard.'
  }
  if (/selected resume is not ready or does not contain enough context/i.test(message)) {
    return 'Selected resume is not ready or does not contain enough project context for this answer.'
  }
  if (/does not contain enough project details/i.test(message)) {
    return 'The selected resume is ready, but it does not contain enough project details to answer this accurately.'
  }

  if (/failed to fetch|networkerror|load failed/i.test(message)) {
    return 'SAIIA could not reach the backend. Please make sure the backend is running and try again.'
  }

  return message || fallbackMessage
}

function normalizeScreenCaptureError(error) {
  const message = String(error?.message || '').replace(/^Error invoking remote method '[^']+':\s*/i, '').trim()

  if (/active_window_not_identified|active question window|active window|identified|target question window/i.test(message)) {
    return {
      code: 'active_window_not_identified',
      message: 'SAIIA could not capture the question window.',
      userAction: 'Focus the browser/question window and retry.',
      retryable: true,
    }
  }

  return {
    code: 'screen_capture_failed',
    message: normalizePipelineError(error, SCREEN_OCR_UNREADABLE_MESSAGE),
    userAction: 'Retry Analyze Screen after focusing the question window.',
    retryable: true,
  }
}

async function captureDisplayFrameBlob() {
  if (!navigator.mediaDevices?.getDisplayMedia) {
    throw new Error('Could not capture screen.')
  }

  let stream = null

  try {
    stream = await navigator.mediaDevices.getDisplayMedia({
      video: {
        frameRate: 1,
      },
      audio: false,
    })

    const [track] = stream.getVideoTracks()
    if (!track) {
      throw new Error('Could not capture screen.')
    }

    const video = document.createElement('video')
    video.srcObject = stream
    video.muted = true
    video.playsInline = true

    await new Promise((resolve, reject) => {
      video.onloadedmetadata = () => resolve()
      video.onerror = () => reject(new Error('Could not capture screen.'))
    })

    await video.play()

    const width = video.videoWidth || 0
    const height = video.videoHeight || 0
    if (!width || !height) {
      throw new Error('Could not capture screen.')
    }

    const scale = Math.min(
      1,
      SCREEN_CAPTURE_MAX_DIMENSION / Math.max(width, height)
    )
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(width * scale))
    canvas.height = Math.max(1, Math.round(height * scale))

    const context = canvas.getContext('2d')
    if (!context) {
      throw new Error('Could not capture screen.')
    }

    context.drawImage(video, 0, 0, canvas.width, canvas.height)

    const blob = await new Promise((resolve) => {
      canvas.toBlob(resolve, 'image/png')
    })

    if (!blob || blob.size === 0) {
      throw new Error('Could not capture screen.')
    }

    return blob
  } finally {
    stream?.getTracks().forEach((track) => track.stop())
  }
}

function isBrowserScreenCaptureAvailable() {
  return typeof navigator !== 'undefined' && Boolean(navigator.mediaDevices?.getDisplayMedia)
}

function isLocalDevRenderer() {
  return (
    typeof window !== 'undefined' &&
    (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
  )
}

async function dataUrlToBlob(dataUrl) {
  const response = await fetch(dataUrl)
  return response.blob()
}

function normalizeListInput(value) {
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === 'string') {
          return item
        }
        if (item && typeof item === 'object') {
          return Object.values(item)
            .map((part) => String(part || '').trim())
            .filter(Boolean)
            .join(' - ')
        }
        return String(item || '')
      })
      .join('\n')
  }

  return String(value || '')
}

function buildFollowupContextEntries(historyState, modeInput) {
  const mode = normalizeQuestionHistoryMode(modeInput)
  const entries = historyState?.[mode]?.entries || []
  return entries
    .filter((entry) => entry?.status === 'complete' && (entry.resolvedQuestion || entry.originalQuestion || entry.question))
    .slice(-FOLLOWUP_CONTEXT_LIMIT)
    .reverse()
    .map((entry) => {
      const createdAt = Date.parse(entry.completedAt || entry.createdAt || '')
      const fullAnswer = String(entry.fullAnswer || entry.displayedAnswer || '')
      const codingAnswer = entry.metadata?.codingAnswer || {}
      return {
        entry_id: entry.id,
        mode,
        original_question: entry.originalQuestion || entry.question || '',
        resolved_question: entry.resolvedQuestion || '',
        answer_excerpt: fullAnswer.replace(/\s+/g, ' ').trim().slice(0, FOLLOWUP_ANSWER_EXCERPT_LIMIT),
        answer_type: entry.metadata?.answerType || entry.category || '',
        category: entry.category || '',
        topic: entry.topic || entry.metadata?.followUpTopic || '',
        programming_language: codingAnswer?.language || entry.metadata?.programmingLanguage || '',
        code_present: Boolean(codingAnswer?.code || entry.metadata?.screenCodeAnswer),
        code: String(codingAnswer?.code || entry.metadata?.screenCodeAnswer || '').slice(0, 4000),
        created_at: Number.isFinite(createdAt) ? createdAt / 1000 : Date.now() / 1000,
      }
    })
}

function validateProfile(profile) {
  const summary = String(profile?.professional_summary || profile?.resume || '').trim()
  const role = String(profile?.current_title || profile?.target_role || profile?.role || '').trim()
  const skills = limitCsv(profile?.top_skills || profile?.skills || profile?.technical_skills, 3)
  const project = limitMultiline(profile?.projects || profile?.experience, 1)
  return [summary, role, skills, project].some((field) => field.length > 0)
}

function limitCsv(value, limit) {
  return normalizeListInput(value)
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, limit)
    .join(', ')
}

function limitMultiline(value, limit) {
  return normalizeListInput(value)
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, limit)
    .join('\n')
}

function buildLiveProfileContext(profile) {
  const education = [
    String(profile?.degree || '').trim(),
    String(profile?.branch || profile?.branch_specialization || '').trim(),
    String(profile?.college || profile?.college_university || profile?.university || '').trim(),
    String(profile?.graduation_year || '').trim(),
  ]
    .filter(Boolean)
    .join(', ')

  let savedSummary = {}
  try {
    savedSummary = JSON.parse(String(profile?.live_profile_summary || '{}'))
  } catch {
    savedSummary = {}
  }

  return {
    full_name: String(savedSummary?.full_name || profile?.full_name || '').trim(),
    target_role: String(
      savedSummary?.target_role || profile?.target_role || profile?.current_title || profile?.role || ''
    ).trim(),
    education: String(savedSummary?.education || education || profile?.education || '').trim(),
    top_skills: limitCsv(savedSummary?.top_skills || profile?.top_skills || profile?.skills, 6),
    projects: limitMultiline(savedSummary?.projects || profile?.projects, 2),
    company: String(savedSummary?.company || profile?.company || '').trim(),
    live_profile_summary: String(profile?.live_profile_summary || '').trim(),
    raw_resume_text: '',
  }
}

function createEmptyPipelineTimings() {
  return {
    recording_ms: null,
    upload_ms: null,
    transcription_ms: null,
    question_detect_ms: null,
    classification_ms: null,
    profile_load_ms: null,
    rag_ms: null,
    prompt_build_ms: null,
    capture_ms: null,
    image_prepare_ms: null,
    screen_model_ms: null,
    response_parse_ms: null,
    frontend_response_parse_ms: null,
    overlay_render_ms: null,
    total_screen_pipeline_ms: null,
    original_image_width: 0,
    original_image_height: 0,
    sent_image_width: 0,
    sent_image_height: 0,
    encoded_image_bytes: 0,
    screen_capture_count: null,
    screen_model_request_count: null,
    screen_extraction_request_count: null,
    screen_generation_request_count: null,
    questions_answered: null,
    incomplete_questions_ignored: null,
    automatic_fallback_count: null,
    correction_request_count: null,
    primary_generation_ms: null,
    refinement_generation_ms: null,
    groq_generation_ms: null,
    answer_received_ms: null,
    overlay_commit_ms: null,
    bar_reset_ms: null,
    frontend_update_ms: null,
    total_pipeline_ms: null,
    stt_provider: '',
    stt_fallback_used: false,
    stt_fallback_reason: '',
    profile_context_used: null,
    profile_context_policy: '',
    retrieved_chunk_count: null,
  }
}

function createEmptyCodingRuntimeAudit() {
  return {
    request_question_excerpt: '',
    full_problem_text_present: false,
    full_problem_text_excerpt: '',
    editor_text_present: false,
    editor_text_excerpt: '',
    generation_question_excerpt: '',
    source: '',
    screen_question_type: '',
    coding_answer_mode: false,
    code_generation_mode: '',
    function_stub_detected: false,
    function_name: '',
    required_stub_preserved: null,
    standalone_solution_rejected: null,
    code_validation_passed: null,
    correction_pass_used: null,
  }
}

const SCREEN_TECHNICAL_TYPES = new Set(['coding', 'debugging', 'output'])
const SCREEN_PROFILE_SUPPRESSED_TYPES = new Set([
  'coding',
  'debugging',
  'output',
  'visual',
  'mcq',
  'architecture',
])

function isScreenTechnicalType(questionType) {
  return SCREEN_TECHNICAL_TYPES.has(String(questionType || '').trim().toLowerCase())
}

function shouldSuppressScreenProfileContext(questionType) {
  return SCREEN_PROFILE_SUPPRESSED_TYPES.has(String(questionType || '').trim().toLowerCase())
}

function mergeScreenProblemText(texts) {
  const seen = new Set()
  const ordered = []

  for (const rawText of texts) {
    const blocks = String(rawText || '')
      .split(/\n{2,}/)
      .map((block) =>
        block
          .split('\n')
          .filter((line) => {
            const trimmed = line.trim()
            return !(
              trimmed.startsWith('{') &&
              (trimmed.includes('"is_question"') ||
                trimmed.includes("'is_question'") ||
                trimmed.includes('"question_type"') ||
                trimmed.includes("'question_type'") ||
                trimmed.includes('"raw_vision_json"'))
            )
          })
          .join('\n')
          .replace(/\s*\{\s*["']is_question["']\s*:.*$/s, '')
          .trim()
      )
      .filter(Boolean)

    for (const block of blocks) {
      const key = block.toLowerCase().replace(/\s+/g, ' ').trim()
      if (!key || seen.has(key)) {
        continue
      }
      seen.add(key)
      ordered.push(block)
    }
  }

  return ordered.join('\n\n').trim()
}

function pickScreenQuestionType(types) {
  const priority = ['coding', 'debugging', 'output', 'visual', 'mcq', 'architecture', 'interview', 'general']
  const normalized = types
    .map((value) => String(value || '').trim().toLowerCase())
    .filter((value) => value && value !== 'none')

  for (const type of priority) {
    if (normalized.includes(type)) {
      return type
    }
  }

  return normalized[0] || 'none'
}

function extractCodeBlockFromAnswer(answerText) {
  const text = String(answerText || '')
  const match = text.match(/```([\w+-]*)\n([\s\S]*?)```/)
  if (!match) {
    return {
      code: '',
      language: '',
    }
  }

  return {
    language: String(match[1] || '').trim().toLowerCase(),
    code: String(match[2] || '').replace(/\s+$/, ''),
  }
}

function normalizeScreenGeneratedAnswer(result, fallbackAnswer = '') {
  return String(
    result?.finalAnswer ||
      result?.answer ||
      result?.displayedAnswer ||
      result?.generatedAnswer ||
      fallbackAnswer ||
      ''
  ).trim()
}

function detectNeedsMoreScreenContent(questionType, text, payload = {}) {
  const normalizedType = String(questionType || '').trim().toLowerCase()
  const normalizedText = String(text || '').toLowerCase()

  if (['coding', 'debugging', 'output', 'visual', 'mcq', 'architecture'].includes(normalizedType)) {
    return true
  }

  if (payload?.screen_platform_detected && payload.screen_platform_detected !== 'unknown') {
    return true
  }

  return /(example|constraints|options?|input:|output:|follow the|study the following|based on the chart)/i.test(normalizedText)
}

function buildScreenProblemContext(payload, fallbackQuestion = '') {
  const fullProblemText = mergeScreenProblemText([
    payload?.full_problem_text,
    payload?.final_merged_problem,
    payload?.cleaned_text,
    payload?.final_extracted_question,
    payload?.extracted_question,
    fallbackQuestion,
  ])

  const codeLikeBlocks = [
    payload?.editor_text,
    payload?.cleaned_text,
    payload?.raw_vision_text,
    payload?.final_merged_problem,
    payload?.final_extracted_question,
  ]
    .flatMap((value) =>
      String(value || '')
        .split(/\n{2,}/)
        .map((block) => block.trim())
        .filter(Boolean)
    )
    .filter((block) =>
      /(^|\n)\s*def\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\(|(^|\n)\s*class\s+[A-Za-z_][A-Za-z0-9_]*\b|(^|\n)\s*(?:from\s+\S+\s+import\s+.+|import\s+.+)$|(^|\n)\s*@[A-Za-z_][A-Za-z0-9_.()]*|(^|\n)\s*[A-Za-z_][A-Za-z0-9_]*\s*=\s*.+|(^|\n)\s*if\s+__name__\s*==\s*['"]__main__['"]\s*:|\bpublic\s+static\b|\bfunction\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\(|#\s*Write your logic here/im.test(block)
    )

  return {
    fullProblemText,
    editorText: mergeScreenProblemText(codeLikeBlocks),
    inputFormat: String(payload?.input_format || '').trim(),
    outputFormat: String(payload?.output_format || '').trim(),
    sampleInput: String(payload?.sample_input || '').trim(),
    sampleOutput: String(payload?.sample_output || '').trim(),
    problemTitle: String(payload?.problem_title || '').trim(),
    screenPlatformDetected: String(payload?.screen_platform_detected || '').trim(),
  }
}

function getSelectedAudioSourceLabel(audioSources) {
  const systemOn = Boolean(audioSources?.system)
  const microphoneOn = Boolean(audioSources?.microphone)

  if (systemOn && microphoneOn) {
    return 'both'
  }
  if (systemOn) {
    return 'system'
  }
  if (microphoneOn) {
    return 'microphone'
  }
  return 'none'
}

const AUTO_FILLER_PHRASES = new Set([
  'um',
  'uh',
  'hmm',
  'okay',
  'yes',
  'no',
  'thank you',
  'hello',
  'can you hear me',
  'testing',
  'one second',
  'wait',
  'yeah',
  'alright',
])

function looksLikeInterviewQuestion(text) {
  const normalized = normalizeTranscriptForDedup(text)
  return /(^|\s)(what|why|how|when|where|who|can|could|would|should|tell|explain|describe|walk)\b/.test(normalized) ||
    normalized.includes('introduce yourself') ||
    normalized.includes('tell me about yourself') ||
    normalized.includes('why should we hire you') ||
    normalized.includes('why do you want to join') ||
    normalized.includes('difference between') ||
    normalized.includes('what is') ||
    normalized.includes('how would you')
}

function getAutoRejectReason(text) {
  const normalized = normalizeTranscriptForDedup(text)
  if (!normalized) {
    return 'silence_or_no_speech'
  }
  if (AUTO_FILLER_PHRASES.has(normalized)) {
    return 'filler_phrase'
  }
  if (normalized.length < 8 && !looksLikeInterviewQuestion(text)) {
    return 'too_short'
  }
  const meaningfulWords = normalized.split(' ').filter((word) => word.length > 1)
  if (meaningfulWords.length < 3 && !looksLikeInterviewQuestion(text)) {
    return 'not_enough_meaningful_words'
  }
  return ''
}

function getSystemAudioCapabilityMessage(detail) {
  return (
    detail ||
    'System audio capture is not available yet. Use microphone or configure system audio capture.'
  )
}

function normalizeTranscriptForDedup(text) {
  return String(text || '')
    .trim()
    .toLowerCase()
    .replace(/[^\w\s]/g, ' ')
    .replace(/\s+/g, ' ')
}

function levenshteinDistance(a, b) {
  const left = String(a || '')
  const right = String(b || '')
  const matrix = Array.from({ length: left.length + 1 }, () => Array(right.length + 1).fill(0))
  for (let row = 0; row <= left.length; row += 1) {
    matrix[row][0] = row
  }
  for (let col = 0; col <= right.length; col += 1) {
    matrix[0][col] = col
  }
  for (let row = 1; row <= left.length; row += 1) {
    for (let col = 1; col <= right.length; col += 1) {
      const cost = left[row - 1] === right[col - 1] ? 0 : 1
      matrix[row][col] = Math.min(
        matrix[row - 1][col] + 1,
        matrix[row][col - 1] + 1,
        matrix[row - 1][col - 1] + cost
      )
    }
  }
  return matrix[left.length][right.length]
}

function similarityScore(a, b) {
  const left = normalizeTranscriptForDedup(a)
  const right = normalizeTranscriptForDedup(b)
  if (!left || !right) {
    return 0
  }
  if (left === right) {
    return 1
  }
  const distance = levenshteinDistance(left, right)
  return 1 - distance / Math.max(left.length, right.length, 1)
}

const TECHNICAL_CANONICAL_TERMS = [
  'Naive Bayes',
  'support vector machine',
  'support vector machines',
  'decision tree',
  'random forest',
  'gradient descent',
  'batch gradient descent',
  'mini-batch gradient descent',
  'stochastic gradient descent',
  'linear regression',
  'logistic regression',
  'K-means',
  'KNN',
  'PCA',
  'NLP',
  'LLM',
  'transformer',
  'attention mechanism',
  'overfitting',
  'underfitting',
  'bias-variance',
  'OOP',
  'object-oriented programming',
  'REST API',
  'FastAPI',
  'React.js',
  'Node.js',
  'SQL',
  'NoSQL',
]

function replaceWithReason(text, pattern, replacement, reason, corrections, options = {}) {
  const nextText = String(text || '')
  let changed = false
  let matchedValue = ''
  const updated = nextText.replace(pattern, (match) => {
    if (options.condition && !options.condition(nextText, match)) {
      return match
    }
    changed = true
    matchedValue = match
    return replacement
  })
  if (changed && updated !== nextText) {
    corrections.push({
      from: matchedValue || nextText,
      to: replacement,
      reason,
    })
  }
  return updated
}

function correctTechnicalQuestionText(text) {
  const originalText = String(text || '').trim()
  if (!originalText) {
    return {
      correctedText: '',
      corrections: [],
      confidence: 1,
      possibleSttError: false,
    }
  }

  let correctedText = originalText
  const corrections = []
  const technicalContext =
    /(explain|what is|what are|algorithm|classifier|machine learning|model|probability|classification|bayes|gradient|regression|api|programming|tree|forest)/i

  correctedText = replaceWithReason(
    correctedText,
    /\b(naf bias|naive bias|nav bias|naïve bias|naive base|nav base|naf base)\b/gi,
    'Naive Bayes',
    'contextual_naive_bayes_correction',
    corrections,
    { condition: (fullText) => technicalContext.test(fullText) }
  )
  correctedText = replaceWithReason(
    correctedText,
    /\bmini batch gradient descent\b/gi,
    'mini-batch gradient descent',
    'canonical_hyphenation',
    corrections
  )
  correctedText = replaceWithReason(
    correctedText,
    /\bbias variance\b/gi,
    'bias-variance',
    'canonical_hyphenation',
    corrections
  )
  correctedText = replaceWithReason(
    correctedText,
    /\bobject oriented programming\b/gi,
    'object-oriented programming',
    'canonical_hyphenation',
    corrections
  )
  correctedText = replaceWithReason(correctedText, /\bfast api\b/gi, 'FastAPI', 'canonical_product_name', corrections)
  correctedText = replaceWithReason(correctedText, /\breact js\b/gi, 'React.js', 'canonical_product_name', corrections)
  correctedText = replaceWithReason(correctedText, /\bnode js\b/gi, 'Node.js', 'canonical_product_name', corrections)
  correctedText = replaceWithReason(correctedText, /\brest api\b/gi, 'REST API', 'canonical_product_name', corrections)
  correctedText = replaceWithReason(correctedText, /\bnosql\b/gi, 'NoSQL', 'canonical_product_name', corrections)
  correctedText = replaceWithReason(correctedText, /\bsql\b/gi, 'SQL', 'canonical_product_name', corrections)
  correctedText = replaceWithReason(correctedText, /\bsvm\b/g, 'SVM', 'canonical_abbreviation', corrections)
  correctedText = replaceWithReason(correctedText, /\bknn\b/g, 'KNN', 'canonical_abbreviation', corrections)
  correctedText = replaceWithReason(correctedText, /\bpca\b/g, 'PCA', 'canonical_abbreviation', corrections)
  correctedText = replaceWithReason(correctedText, /\bnlp\b/g, 'NLP', 'canonical_abbreviation', corrections)
  correctedText = replaceWithReason(correctedText, /\bllm\b/g, 'LLM', 'canonical_abbreviation', corrections)
  correctedText = replaceWithReason(
    correctedText,
    /\boops\b/gi,
    'OOP',
    'concept_abbreviation',
    corrections,
    { condition: (fullText) => /(explain|what is|programming|concept|oriented)/i.test(fullText) }
  )
  correctedText = replaceWithReason(
    correctedText,
    /\bk means\b/gi,
    'K-means',
    'canonical_hyphenation',
    corrections
  )
  correctedText = replaceWithReason(
    correctedText,
    /\bnatural language processing\b/gi,
    'NLP',
    'canonical_abbreviation',
    corrections
  )
  correctedText = replaceWithReason(
    correctedText,
    /\blarge language model\b/gi,
    'LLM',
    'canonical_abbreviation',
    corrections
  )

  const words = correctedText.split(/\s+/).filter(Boolean)
  for (let size = 4; size >= 2; size -= 1) {
    for (let index = 0; index <= words.length - size; index += 1) {
      const phrase = words.slice(index, index + size).join(' ')
      const normalizedPhrase = normalizeTranscriptForDedup(phrase)
      if (!normalizedPhrase || normalizedPhrase.length < 5) {
        continue
      }
      const bestMatch = TECHNICAL_CANONICAL_TERMS.reduce(
        (best, candidate) => {
          const score = similarityScore(normalizedPhrase, candidate)
          if (score > best.score) {
            return { candidate, score }
          }
          return best
        },
        { candidate: '', score: 0 }
      )
      if (bestMatch.score >= 0.82 && normalizeTranscriptForDedup(bestMatch.candidate) !== normalizedPhrase) {
        const escapedPhrase = phrase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
        const phrasePattern = new RegExp(`\\b${escapedPhrase}\\b`, 'i')
        correctedText = replaceWithReason(
          correctedText,
          phrasePattern,
          bestMatch.candidate,
          `fuzzy_technical_match_${bestMatch.score.toFixed(2)}`,
          corrections
        )
      }
    }
  }

  const possibleSttError =
    corrections.length === 0 &&
    /(naf|nav|naive\s+bias|mini batch|support vector|gradient decent|fast api|react js|node js|oops)/i.test(originalText)

  const confidence = corrections.length ? 0.94 : possibleSttError ? 0.55 : 0.9

  return {
    correctedText: correctedText.trim(),
    corrections,
    confidence,
    possibleSttError,
  }
}

function isSimilarTranscript(a, b) {
  if (!a || !b) {
    return false
  }
  if (a === b) {
    return true
  }
  if (a.length > 18 && b.length > 18 && (a.includes(b) || b.includes(a))) {
    return true
  }

  const aTokens = new Set(a.split(' ').filter(Boolean))
  const bTokens = new Set(b.split(' ').filter(Boolean))
  if (!aTokens.size || !bTokens.size) {
    return false
  }

  let overlap = 0
  for (const token of aTokens) {
    if (bTokens.has(token)) {
      overlap += 1
    }
  }

  const similarity = overlap / Math.max(aTokens.size, bTokens.size)
  return similarity >= 0.85
}

function getSafeGenerationSource(mode, source) {
  const normalizedSource = String(source || '').trim().toLowerCase()
  if (normalizedSource === 'chat') {
    return 'chat'
  }
  if (normalizedSource === 'answer') {
    return 'answer'
  }
  if (normalizedSource === 'analyze_screen' || normalizedSource === 'screen') {
    return 'analyze_screen'
  }
  if (normalizedSource === 'auto') {
    return 'auto'
  }

  const normalizedMode = String(mode || '').trim().toLowerCase()
  if (normalizedMode === 'chat') {
    return 'chat'
  }
  if (normalizedMode === 'screen') {
    return 'analyze_screen'
  }
  if (normalizedMode === 'auto') {
    return 'auto'
  }
  if (normalizedMode === 'manual') {
    return 'answer'
  }
  return 'unknown'
}

function useElectronOverlaySync(state) {
  useEffect(() => {
    if (!window.electronAPI?.updateOverlayState) {
      return
    }

    window.electronAPI.updateOverlayState({
      ...state,
      privacyMessage: OVERLAY_PRIVACY_MESSAGE,
    })
  }, [state])
}

function OverlayWindow() {
  const [overlayState, setOverlayState] = useState({
    answer: '',
    codingAnswer: null,
    answerRevealActive: false,
    answerFullAvailable: false,
    answerDisplayMode: 'answer',
    questionHistory: createQuestionHistoryState(),
    questionHistoryNavigationCount: 0,
    error: '',
    status: 'Waiting for a question...',
    transcript: '',
    fontSize: 14,
    provider: '',
    category: '',
    generationMs: null,
    totalPipelineMs: null,
    visible: true,
    recording: false,
    manualProcessing: false,
    isManualGenerating: false,
    manualQuestionError: '',
    recordingStartedAt: null,
    audioPipelineStatus: 'idle',
    audioSourceWarning: false,
    autoMode: false,
    autoProcessing: false,
    ocrProcessing: false,
    ocrText: '',
    ocrConfidence: null,
    screenSources: [],
    screenVisionProvider: '',
    screenVisionModel: '',
    screenCaptureTarget: 'active_window',
    screenWindowTitle: '',
    screenProcessName: '',
    screenImageWidth: 0,
    screenImageHeight: 0,
    rawScreenVisionText: '',
    rawScreenVisionJson: '',
    screenCleanedText: '',
    extractedScreenQuestion: '',
    screenQuestionType: 'none',
    screenConfidence: null,
    screenCaptureMs: 0,
    screenVisionMs: 0,
    screenFallbackOcrUsed: false,
    screenScreenshotHidSaiiaWindows: false,
    screenDebugPath: '',
    screenRejectedUiNoise: false,
    screenUiNoiseRatio: 0,
    screenRejectReason: '',
    screenAnswerGenerated: false,
    screenAnswerText: '',
    screenCodeAnswer: '',
    screenCodeLanguage: '',
    screenAnswerDisplayedInPanel: false,
    screenAnswerCommittedToOverlay: false,
    screenPanelMode: 'preview',
    screenAnswerLoading: false,
    screenError: '',
    screenOperation: null,
    microphoneEnabled: false,
    systemAudioEnabled: false,
    activeAudioSource: 'none',
    systemAudioSupported: false,
    systemAudioDeviceName: '',
    systemAudioSampleRate: null,
    autoModeStatus: 'off',
    autoModeSource: 'none',
    lastAutoTranscript: '',
    lastDetectedQuestion: '',
    autoRejectedReason: '',
    cooldownRemainingMs: 0,
    screenShareProtectionEnabled: true,
    overlayOpacity: 1,
    sessionStartedAt: Date.now(),
    selectedResumeIdExists: false,
    selectedResumeName: '',
    privacyMessage: OVERLAY_PRIVACY_MESSAGE,
  })

  useEffect(() => {
    let unsubscribe = null

    async function loadInitialState() {
      if (!window.electronAPI?.getOverlayState) {
        return
      }

      const initialState = await window.electronAPI.getOverlayState()
      setOverlayState((current) => ({ ...current, ...initialState }))

      if (window.electronAPI?.onOverlayState) {
        unsubscribe = window.electronAPI.onOverlayState((nextState) => {
          setOverlayState((current) => ({ ...current, ...nextState }))
        })
      }
    }

    loadInitialState()

    return () => {
      if (unsubscribe) {
        unsubscribe()
      }
    }
  }, [])

  return <OverlayWindowView overlayState={overlayState} />
}

function MainWindow() {
  const [recording, setRecording] = useState(false)
  const [manualProcessing, setManualProcessing] = useState(false)
  const [isManualGenerating, setIsManualGenerating] = useState(false)
  const [manualQuestionError, setManualQuestionError] = useState('')
  const [autoMode, setAutoMode] = useState(false)
  const [autoProcessing, setAutoProcessing] = useState(false)
  const [answer, setAnswer] = useState('')
  const [codingAnswer, setCodingAnswer] = useState(null)
  const [fullAnswer, setFullAnswer] = useState('')
  const [answerRevealActive, setAnswerRevealActive] = useState(false)
  const [answerDisplayMode, setAnswerDisplayMode] = useState('answer')
  const [questionHistory, setQuestionHistory] = useState(() => createQuestionHistoryState())
  const [questionHistoryNavigationCount, setQuestionHistoryNavigationCount] = useState(0)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [fontSize, setFontSize] = useState(14)
  const [provider, setProvider] = useState('')
  const [primaryProvider, setPrimaryProvider] = useState('')
  const [primaryModel, setPrimaryModel] = useState('')
  const [refinementProvider, setRefinementProvider] = useState('')
  const [refinementModel, setRefinementModel] = useState('')
  const [refinementUsed, setRefinementUsed] = useState(false)
  const [refinementStatus, setRefinementStatus] = useState('')
  const [refinementMessage, setRefinementMessage] = useState('')
  const [refinementJobId, setRefinementJobId] = useState('')
  const [refinedAnswer, setRefinedAnswer] = useState('')
  const [displayedAnswerSource, setDisplayedAnswerSource] = useState('')
  const [category, setCategory] = useState('')
  const [transcript, setTranscript] = useState('')
  const [generationMs, setGenerationMs] = useState(null)
  const [totalPipelineMs, setTotalPipelineMs] = useState(null)
  const [pipelineTimings, setPipelineTimings] = useState(createEmptyPipelineTimings())
  const [codingRuntimeAudit, setCodingRuntimeAudit] = useState(createEmptyCodingRuntimeAudit())
  const [performanceMode, setPerformanceMode] = useState('standard')
  const [overlayVisible, setOverlayVisible] = useState(true)
  const [systemAudioEnabled, setSystemAudioEnabled] = useState(false)
  const [audioSources, setAudioSources] = useState({ system: false, microphone: false })
  const [audioPipelineStatus, setAudioPipelineStatus] = useState('idle')
  const [audioSourceWarning, setAudioSourceWarning] = useState(false)
  const [activeAudioSource, setActiveAudioSource] = useState('none')
  const [systemAudioSupported, setSystemAudioSupported] = useState(false)
  const [systemAudioDeviceName, setSystemAudioDeviceName] = useState('')
  const [systemAudioDefaultDeviceName, setSystemAudioDefaultDeviceName] = useState('')
  const [systemAudioInputSampleRate, setSystemAudioInputSampleRate] = useState(null)
  const [systemAudioSampleRate, setSystemAudioSampleRate] = useState(null)
  const [systemAudioRmsLevel, setSystemAudioRmsLevel] = useState(null)
  const [systemAudioPeakLevel, setSystemAudioPeakLevel] = useState(null)
  const [systemAudioChunkBytesSent, setSystemAudioChunkBytesSent] = useState(0)
  const [systemAudioDroppedSilenceChunks, setSystemAudioDroppedSilenceChunks] = useState(0)
  const [systemAudioClippingDetected, setSystemAudioClippingDetected] = useState(false)
  const [systemAudioQualityWarning, setSystemAudioQualityWarning] = useState('')
  const [systemAudioDebugWavPath, setSystemAudioDebugWavPath] = useState('')
  const [systemAudioEffectiveGain, setSystemAudioEffectiveGain] = useState(null)
  const [autoModeStatus, setAutoModeStatus] = useState('off')
  const [micStreamingState, setMicStreamingState] = useState('off')
  const [answerPipelineState, setAnswerPipelineState] = useState('idle')
  const [micStreamRestartCount, setMicStreamRestartCount] = useState(0)
  const [lastMicStreamRestartReason, setLastMicStreamRestartReason] = useState('')
  const [autoModeSource, setAutoModeSource] = useState('none')
  const [autoStartClicked, setAutoStartClicked] = useState(false)
  const [lastAutoTranscript, setLastAutoTranscript] = useState('')
  const [rawFinalTranscript, setRawFinalTranscript] = useState('')
  const [lastDetectedQuestion, setLastDetectedQuestion] = useState('')
  const [acceptedAutoQuestion, setAcceptedAutoQuestion] = useState('')
  const [displayedAutoQuestionRunId, setDisplayedAutoQuestionRunId] = useState('')
  const [currentAutoQuestionRunId, setCurrentAutoQuestionRunId] = useState('')
  const [lastGeneratedAt, setLastGeneratedAt] = useState(null)
  const [autoRejectedReason, setAutoRejectedReason] = useState('')
  const [extractedQuestionCandidate, setExtractedQuestionCandidate] = useState('')
  const [polishedQuestionCandidate, setPolishedQuestionCandidate] = useState('')
  const [correctedQuestionCandidate, setCorrectedQuestionCandidate] = useState('')
  const [technicalCorrectionsSummary, setTechnicalCorrectionsSummary] = useState('')
  const [possibleSttError, setPossibleSttError] = useState(false)
  const [questionCandidateSource, setQuestionCandidateSource] = useState('')
  const [questionDetectionInput, setQuestionDetectionInput] = useState('')
  const [questionDetectReason, setQuestionDetectReason] = useState('')
  const [isQuestionDetected, setIsQuestionDetected] = useState(false)
  const [cooldownRemainingMs, setCooldownRemainingMs] = useState(0)
  const [recentTranscriptBuffer, setRecentTranscriptBuffer] = useState('')
  const [pendingAutoQuestion, setPendingAutoQuestion] = useState('')
  const [pendingCooldownQuestion, setPendingCooldownQuestion] = useState('')
  const [pendingCooldownQuestionAgeMs, setPendingCooldownQuestionAgeMs] = useState(0)
  const [cooldownQueueReason, setCooldownQueueReason] = useState('')
  const [queuedQuestionProcessed, setQueuedQuestionProcessed] = useState(false)
  const [generationStarted, setGenerationStarted] = useState(false)
  const [generationBlockedReason, setGenerationBlockedReason] = useState('')
  const [isCooldownListening, setIsCooldownListening] = useState(false)
  const [sttProvider, setSttProvider] = useState('')
  const [sttFallbackUsed, setSttFallbackUsed] = useState(false)
  const [sttFallbackReason, setSttFallbackReason] = useState('')
  const [autoStreamingConnected, setAutoStreamingConnected] = useState(false)
  const [partialAutoTranscript, setPartialAutoTranscript] = useState('')
  const [streamingError, setStreamingError] = useState('')
  const [screenShareProtectionEnabled] = useState(true)
  const [overlayOpacity, setOverlayOpacity] = useState(1)
  const [ocrText, setOcrText] = useState('')
  const [ocrConfidence, setOcrConfidence] = useState(null)
  const [ocrProcessing, setOcrProcessing] = useState(false)
  const [screenSources, setScreenSources] = useState([])
  const [screenVisionProvider, setScreenVisionProvider] = useState('')
  const [screenVisionModel, setScreenVisionModel] = useState('')
  const [screenCaptureTarget, setScreenCaptureTarget] = useState('active_window')
  const [screenWindowTitle, setScreenWindowTitle] = useState('')
  const [screenProcessName, setScreenProcessName] = useState('')
  const [screenImageWidth, setScreenImageWidth] = useState(0)
  const [screenImageHeight, setScreenImageHeight] = useState(0)
  const [rawScreenVisionText, setRawScreenVisionText] = useState('')
  const [rawScreenVisionJson, setRawScreenVisionJson] = useState('')
  const [screenCleanedText, setScreenCleanedText] = useState('')
  const [extractedScreenQuestion, setExtractedScreenQuestion] = useState('')
  const [screenQuestionType, setScreenQuestionType] = useState('none')
  const [screenConfidence, setScreenConfidence] = useState(null)
  const [screenCaptureMs, setScreenCaptureMs] = useState(0)
  const [screenVisionMs, setScreenVisionMs] = useState(0)
  const [screenFallbackOcrUsed, setScreenFallbackOcrUsed] = useState(false)
  const [screenScreenshotHidSaiiaWindows, setScreenScreenshotHidSaiiaWindows] = useState(false)
  const [screenDebugPath, setScreenDebugPath] = useState('')
  const [screenPlatformDetected, setScreenPlatformDetected] = useState('unknown')
  const [screenCropUsed, setScreenCropUsed] = useState(false)
  const [screenCropRegion, setScreenCropRegion] = useState('')
  const [screenSourceRegion, setScreenSourceRegion] = useState('unknown')
  const [screenExtractionRetryReason, setScreenExtractionRetryReason] = useState('')
  const [screenRejectedUiNoise, setScreenRejectedUiNoise] = useState(false)
  const [screenRejectedCodeBoilerplate, setScreenRejectedCodeBoilerplate] = useState(false)
  const [screenUiNoiseRatio, setScreenUiNoiseRatio] = useState(0)
  const [screenRejectReason, setScreenRejectReason] = useState('')
  const [rawFullWindowVisionJson, setRawFullWindowVisionJson] = useState('')
  const [rawCroppedVisionJson, setRawCroppedVisionJson] = useState('')
  const [finalExtractedScreenQuestion, setFinalExtractedScreenQuestion] = useState('')
  const [screenValidProblemFound, setScreenValidProblemFound] = useState(false)
  const [groqVisionAttempted, setGroqVisionAttempted] = useState(false)
  const [groqVisionSuccess, setGroqVisionSuccess] = useState(false)
  const [groqVisionError, setGroqVisionError] = useState('')
  const [groqVisionHttpStatus, setGroqVisionHttpStatus] = useState(null)
  const [groqVisionRawResponsePreview, setGroqVisionRawResponsePreview] = useState('')
  const [groqVisionParseError, setGroqVisionParseError] = useState('')
  const [groqVisionTimeout, setGroqVisionTimeout] = useState(false)
  const [screenFallbackReason, setScreenFallbackReason] = useState('')
  const [screenAnswerGenerated, setScreenAnswerGenerated] = useState(false)
  const [screenError, setScreenError] = useState('')
  const [screenAnalyzeMode, setScreenAnalyzeMode] = useState('visible_window')
  const [screenNeedsMoreContent, setScreenNeedsMoreContent] = useState(false)
  const [screenFullCaptureEnabled, setScreenFullCaptureEnabled] = useState(false)
  const [screenFullProblemCaptureUsed, setScreenFullProblemCaptureUsed] = useState(false)
  const [screenCaptureCount, setScreenCaptureCount] = useState(1)
  const [screenScrollPositions, setScreenScrollPositions] = useState('')
  const [screenDuplicateCaptureStopped, setScreenDuplicateCaptureStopped] = useState(false)
  const [screenBottomReached, setScreenBottomReached] = useState(false)
  const [screenRestoredScrollPosition, setScreenRestoredScrollPosition] = useState(false)
  const [screenDiagramDetected, setScreenDiagramDetected] = useState(false)
  const [screenChartDetected, setScreenChartDetected] = useState(false)
  const [finalMergedProblem, setFinalMergedProblem] = useState('')
  const [screenFullProblemText, setScreenFullProblemText] = useState('')
  const [screenEditorText, setScreenEditorText] = useState('')
  const [screenForceTechnical, setScreenForceTechnical] = useState(false)
  const [screenCodingAnswerMode, setScreenCodingAnswerMode] = useState(false)
  const [screenProfileContextUsed, setScreenProfileContextUsed] = useState(true)
  const [screenAutoGenerate, setScreenAutoGenerate] = useState(false)
  const [screenAnswerText, setScreenAnswerText] = useState('')
  const [screenCodeAnswer, setScreenCodeAnswer] = useState('')
  const [screenCodeLanguage, setScreenCodeLanguage] = useState('')
  const [screenAnswerDisplayedInPanel, setScreenAnswerDisplayedInPanel] = useState(false)
  const [screenAnswerCommittedToOverlay, setScreenAnswerCommittedToOverlay] = useState(false)
  const [screenPanelMode, setScreenPanelMode] = useState('preview')
  const [screenAnswerLoading, setScreenAnswerLoading] = useState(false)
  const [screenOperation, setScreenOperation] = useState(null)
  const [eventLog, setEventLog] = useState([])
  const [lastError, setLastError] = useState('')
  const [isDiagnosticsCollapsed, setIsDiagnosticsCollapsed] = useState(false)
  const [sessionStartedAt] = useState(() => Date.now())
  const [startupSessionConfig, setStartupSessionConfig] = useState(null)
  const [recordingStartedAt, setRecordingStartedAt] = useState(null)

  const mediaRecorderRef = useRef(null)
  const streamRef = useRef(null)
  const chunksRef = useRef([])
  const autoModeRef = useRef(false)
  const autoModeRunIdRef = useRef('')
  const currentAutoQuestionRunIdRef = useRef('')
  const autoLoopTimeoutRef = useRef(null)
  const autoCooldownIntervalRef = useRef(null)
  const autoCooldownUntilRef = useRef(0)
  const recentProcessedTranscriptsRef = useRef([])
  const recentAutoTranscriptBufferRef = useRef([])
  const pendingAutoQuestionRef = useRef(null)
  const pendingCooldownQuestionRef = useRef(null)
  const autoGenerationInFlightRef = useRef(false)
  const assemblyAiFallbackWarningShownRef = useRef(false)
  const lastCheckedAutoCandidateRef = useRef('')
  const autoStreamingSocketRef = useRef(null)
  const autoStreamingClosingRef = useRef(false)
  const autoStreamingAudioContextRef = useRef(null)
  const autoStreamingSourceNodeRef = useRef(null)
  const autoStreamingProcessorRef = useRef(null)
  const refinementPollTimeoutRef = useRef(null)
  const refinementPollStartedAtRef = useRef(0)
  const refinementPollAttemptsRef = useRef(0)
  const activeRefinementJobIdRef = useRef('')
  const latestGenerationRequestIdRef = useRef(0)
  const lastLoggedStatusRef = useRef('')
  const lastLoggedErrorRef = useRef('')
  const profileCacheRef = useRef(null)
  const profileFetchMsRef = useRef(null)
  const startupSessionConfigRef = useRef(null)
  const answerRef = useRef('')
  const fullAnswerRef = useRef('')
  const questionHistoryRef = useRef(questionHistory)
  const activeGenerateAbortControllerRef = useRef(null)
  const audioSourcesRef = useRef({ system: false, microphone: false })
  const audioPipelineStatusRef = useRef('idle')
  const activeAudioSourceRef = useRef('none')
  const autoModeSourceRef = useRef('none')
  const activeAudioPipelineRequestIdRef = useRef('')
  const activeScreenOperationRef = useRef(null)
  const committedScreenOperationIdsRef = useRef(new Set())
  const sourceWarningTimeoutRef = useRef(null)
  const answerReadyResetTimeoutRef = useRef(null)
  const generatingWatchdogTimeoutRef = useRef(null)
  const systemRecordingIdRef = useRef('')
  const manualRecordingCancelledRef = useRef(false)

  const applyStartupSessionConfig = (nextConfig) => {
    startupSessionConfigRef.current = nextConfig
    setStartupSessionConfig(nextConfig)
  }

  const beginScreenOperation = (sourceType) => {
    const nextOperation = createScreenOperation({ sourceType })
    if (activeScreenOperationRef.current) {
      activeScreenOperationRef.current = supersedeScreenOperation(
        activeScreenOperationRef.current,
        nextOperation.operationId
      )
    }
    activeScreenOperationRef.current = nextOperation
    setScreenOperation(nextOperation)
    latestGenerationRequestIdRef.current = nextOperation.requestId
    return nextOperation
  }

  const updateCurrentScreenOperation = (operation, status, patch = {}) => {
    if (!isCurrentScreenOperation(activeScreenOperationRef.current, operation)) {
      return activeScreenOperationRef.current
    }
    const nextOperation = transitionScreenOperation(activeScreenOperationRef.current, status, patch)
    activeScreenOperationRef.current = nextOperation
    setScreenOperation(nextOperation)
    return nextOperation
  }

  const failCurrentScreenOperation = (operation, message) => {
    updateCurrentScreenOperation(operation, SCREEN_OPERATION_STATUS.FAILED, {
      error: message,
      isCurrent: false,
    })
  }

  const finishCurrentScreenOperation = (operation) => {
    updateCurrentScreenOperation(operation, SCREEN_OPERATION_STATUS.READY, {
      isCurrent: false,
      committed: true,
    })
  }

  const markScreenOperationCommitted = (operationId) => {
    if (!operationId) {
      return
    }
    const nextIds = new Set(committedScreenOperationIdsRef.current)
    nextIds.add(operationId)
    if (nextIds.size > 50) {
      committedScreenOperationIdsRef.current = new Set(Array.from(nextIds).slice(-50))
      return
    }
    committedScreenOperationIdsRef.current = nextIds
  }

  useEffect(() => {
    answerRef.current = answer
  }, [answer])

  useEffect(() => {
    questionHistoryRef.current = questionHistory
  }, [questionHistory])

  const setFullAnswerState = (value) => {
    fullAnswerRef.current = value
    setFullAnswer(value)
  }

  const setQuestionHistoryState = (updater) => {
    setQuestionHistory((current) => {
      const next = typeof updater === 'function' ? updater(current) : updater
      questionHistoryRef.current = next
      return next
    })
  }

  const isSelectedHistoryEntry = (mode, entryId) => {
    if (!mode || !entryId) {
      return true
    }
    const selected = getSelectedQuestionHistoryEntry(questionHistoryRef.current, mode)
    return selected?.id === entryId
  }

  const applyQuestionHistoryEntry = (entry) => {
    if (!entry) {
      return
    }
    const historyMode = normalizeQuestionHistoryMode(entry.mode)
    const visibleAnswer = entry.displayedAnswer || entry.fullAnswer || ''

    setAnswerDisplayMode(historyMode || 'answer')
    setTranscript(entry.question || '')
    setFullAnswerState(entry.fullAnswer || visibleAnswer)
    setAnswer(visibleAnswer)
    setCodingAnswer(entry.metadata?.codingAnswer || null)
    setAnswerRevealActive(entry.status === 'generating')
    setProvider(entry.provider || entry.primaryProvider || '')
    setPrimaryProvider(entry.primaryProvider || entry.provider || '')
    setPrimaryModel(entry.primaryModel || entry.model || '')
    setCategory(entry.category || '')
    setGenerationMs(entry.generationMs ?? null)
    setTotalPipelineMs(entry.totalPipelineMs ?? null)

    if (historyMode === 'screen') {
      const metadata = entry.metadata || {}
      setOcrText(entry.question || '')
      setFinalExtractedScreenQuestion(entry.question || '')
      setExtractedScreenQuestion(entry.question || '')
      setScreenQuestionType(metadata.screenQuestionType || 'none')
      setScreenFullProblemText(metadata.fullProblemText || entry.question || '')
      setScreenEditorText(metadata.editorText || '')
      setScreenAnswerText(entry.fullAnswer || visibleAnswer)
      setScreenCodeAnswer(metadata.screenCodeAnswer || '')
      setScreenCodeLanguage(metadata.screenCodeLanguage || '')
      setScreenAnswerGenerated(Boolean(entry.fullAnswer || visibleAnswer))
      setScreenAnswerDisplayedInPanel(Boolean(entry.fullAnswer || visibleAnswer))
      setScreenAnswerCommittedToOverlay(Boolean(entry.fullAnswer || visibleAnswer))
      setScreenPanelMode(entry.fullAnswer || visibleAnswer ? 'answer' : 'preview')
      setPipelineTimings(metadata.pipelineTimings || createEmptyPipelineTimings())
    }
  }

  const navigateQuestionHistory = (modeInput, offset) => {
    const mode = normalizeQuestionHistoryMode(modeInput)
    if (!mode) {
      return
    }
    let selectedEntry = null
    setQuestionHistoryState((current) => {
      const next = selectQuestionHistoryOffset(current, mode, offset)
      selectedEntry = getSelectedQuestionHistoryEntry(next, mode)
      return next
    })
    setQuestionHistoryNavigationCount((count) => count + 1)
    applyQuestionHistoryEntry(selectedEntry)
  }

  const clearProgressiveAnswer = () => {
    activeGenerateAbortControllerRef.current?.abort()
    activeGenerateAbortControllerRef.current = null
    setFullAnswerState('')
    setAnswer('')
    setCodingAnswer(null)
    setAnswerRevealActive(false)
  }

  const showFullAnswerNow = () => {
    setAnswer(fullAnswerRef.current)
    if (!answerRevealActive) {
      setAnswerRevealActive(false)
    }
  }

  const streamGenerateAnswer = async ({
    body,
    requestId,
    displayMode = 'answer',
    historyMode = '',
    historyEntryId = '',
  }) => {
    activeGenerateAbortControllerRef.current?.abort()
    const controller = new AbortController()
    activeGenerateAbortControllerRef.current = controller
    let accumulatedAnswer = ''
    let finalPayload = null
    let streamRequestId = ''
    let receivedAnyDelta = false
    let firstDeltaMs = null
    const streamStartedAt = performance.now()

    if (!historyMode || isSelectedHistoryEntry(historyMode, historyEntryId)) {
      setAnswerDisplayMode(displayMode)
      setFullAnswerState('')
      setAnswer('')
    }
    if (!historyMode || isSelectedHistoryEntry(historyMode, historyEntryId)) {
      setAnswerRevealActive(true)
    }

    try {
      const activeStartupSessionConfig = startupSessionConfigRef.current
      const selectedResumeId = String(activeStartupSessionConfig?.selectedResumeId || '').trim()
      const activeSessionId = String(activeStartupSessionConfig?.activeSessionId || '').trim()
      const requestBody = {
        ...body,
        ...(selectedResumeId ? { selected_resume_id: selectedResumeId } : {}),
        ...(activeSessionId ? { session_id: activeSessionId } : {}),
      }
      const desktopGenerateAnswer = window.saiia?.generateAnswer
      if (selectedResumeId && typeof desktopGenerateAnswer === 'function') {
        const result = await desktopGenerateAnswer(requestBody)
        if (!result?.ok) {
          throw new Error(result?.payload?.detail || 'Could not generate an answer right now.')
        }
        finalPayload = result.payload || {}
        const finalAnswer = stripInternalControlMarkers(finalPayload.answer || '')
        if (finalAnswer) {
          accumulatedAnswer = finalAnswer
          fullAnswerRef.current = finalAnswer
          setFullAnswer(finalAnswer)
          setAnswer(finalAnswer)
        }
        if (historyMode && historyEntryId) {
          setQuestionHistoryState((current) =>
            updateQuestionHistoryEntry(
              current,
              historyMode,
              historyEntryId,
              {
                displayedAnswer: finalAnswer,
                fullAnswer: finalAnswer,
                status: 'complete',
              },
              { requestId }
            )
          )
        }
        return finalPayload
      }

      const response = await fetch(`${BACKEND_URL}/generate/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
        signal: controller.signal,
      })

      if (!response.ok) {
        const fallbackResponse = await fetch(`${BACKEND_URL}/generate/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(requestBody),
        })
        return parseJsonResponse(fallbackResponse, 'Could not generate an answer right now.')
      }

      await readNdjsonStream(response, {
        signal: controller.signal,
        onEvent: (event) => {
          if (!isCurrentRequest(latestGenerationRequestIdRef.current, requestId)) {
            controller.abort()
            return
          }
          if (event.type === 'start') {
            streamRequestId = event.request_id || ''
            return
          }
          if (streamRequestId && event.request_id && event.request_id !== streamRequestId) {
            return
          }
          if (event.type === 'delta') {
            const text = stripInternalControlMarkers(event.text || '')
            if (!text) {
              return
            }
          receivedAnyDelta = true
          if (firstDeltaMs == null) {
            firstDeltaMs = Number((performance.now() - streamStartedAt).toFixed(2))
          }
          accumulatedAnswer += text
            if (historyMode && historyEntryId) {
              setQuestionHistoryState((current) =>
                updateQuestionHistoryEntry(
                  current,
                  historyMode,
                  historyEntryId,
                  {
                    displayedAnswer: accumulatedAnswer,
                    fullAnswer: accumulatedAnswer,
                    status: 'generating',
                  },
                  { requestId }
                )
              )
            }
            if (!historyMode || isSelectedHistoryEntry(historyMode, historyEntryId)) {
              fullAnswerRef.current = accumulatedAnswer
              setFullAnswer(accumulatedAnswer)
              setAnswer(accumulatedAnswer)
            }
            return
          }
          if (event.type === 'replace') {
            const replacement = stripInternalControlMarkers(event.answer || '')
            accumulatedAnswer = replacement
            if (historyMode && historyEntryId) {
              setQuestionHistoryState((current) =>
                updateQuestionHistoryEntry(
                  current,
                  historyMode,
                  historyEntryId,
                  {
                    displayedAnswer: replacement,
                    fullAnswer: replacement,
                    status: 'generating',
                  },
                  { requestId }
                )
              )
            }
            if (!historyMode || isSelectedHistoryEntry(historyMode, historyEntryId)) {
              fullAnswerRef.current = replacement
              setFullAnswer(replacement)
              setAnswer(replacement)
            }
            return
          }
          if (event.type === 'metadata') {
            finalPayload = { ...(event.metadata || {}) }
            return
          }
          if (event.type === 'error') {
            if (!receivedAnyDelta) {
              throw new Error(event.error || 'Could not generate an answer right now.')
            }
            finalPayload = {
              ...(finalPayload || {}),
              answer: accumulatedAnswer,
              error: event.error || 'stream_incomplete',
              stream_incomplete: true,
            }
          }
        },
      })
    } finally {
      if (activeGenerateAbortControllerRef.current === controller) {
        activeGenerateAbortControllerRef.current = null
      }
      if (!historyMode || isSelectedHistoryEntry(historyMode, historyEntryId)) {
        setAnswerRevealActive(false)
      }
    }

    const answer = String((finalPayload && finalPayload.answer) || accumulatedAnswer || '')
    return {
      ...(finalPayload || {}),
      answer,
      provider: finalPayload?.provider || 'openai',
      model: finalPayload?.model || '',
      fallback_used: Boolean(finalPayload?.fallback_used),
      frontend_first_delta_ms: firstDeltaMs,
    }
  }

  useEffect(() => {
    if (screenPanelMode !== 'answer' || !screenAnswerGenerated || screenAnswerText.trim()) {
      return
    }

    const fallbackAnswer = String(refinedAnswer || fullAnswerRef.current || answer || '').trim()
    if (!fallbackAnswer) {
      return
    }

    const extractedCode = extractCodeBlockFromAnswer(fallbackAnswer)
    setScreenAnswerText(fallbackAnswer)
    setScreenCodeAnswer(extractedCode.code)
    setScreenCodeLanguage(
      extractedCode.language || (screenQuestionType === 'coding' ? 'python' : '')
    )
    setScreenAnswerDisplayedInPanel(true)
    setScreenAnswerCommittedToOverlay(true)
  }, [
    answer,
    refinedAnswer,
    screenAnswerGenerated,
    screenAnswerText,
    screenPanelMode,
    screenQuestionType,
  ])

  useEffect(() => {
    return () => {
      activeGenerateAbortControllerRef.current?.abort()
    }
  }, [])

  useEffect(() => {
    audioSourcesRef.current = audioSources
  }, [audioSources])

  useEffect(() => {
    audioPipelineStatusRef.current = audioPipelineStatus
  }, [audioPipelineStatus])

  useEffect(() => {
    activeAudioSourceRef.current = activeAudioSource
  }, [activeAudioSource])

  useEffect(() => {
    autoModeSourceRef.current = autoModeSource
  }, [autoModeSource])

  useEffect(() => {
    let unsubscribe = null

    async function loadOverlayState() {
      if (!window.electronAPI?.getOverlayState) {
        return
      }

      const initialState = await window.electronAPI.getOverlayState()
      setOverlayVisible(Boolean(initialState.visible))

      if (window.electronAPI?.onOverlayState) {
        unsubscribe = window.electronAPI.onOverlayState((nextState) => {
          if (typeof nextState.visible === 'boolean') {
            setOverlayVisible(nextState.visible)
          }
          if (typeof nextState.overlayOpacity === 'number') {
            setOverlayOpacity(nextState.overlayOpacity)
          }
        })
      }
    }

    loadOverlayState()

    return () => {
      if (unsubscribe) {
        unsubscribe()
      }
    }
  }, [])

  useEffect(() => {
    return () => {
      autoModeRef.current = false
      if (autoLoopTimeoutRef.current) {
        clearTimeout(autoLoopTimeoutRef.current)
      }
      if (autoCooldownIntervalRef.current) {
        clearInterval(autoCooldownIntervalRef.current)
      }
      if (refinementPollTimeoutRef.current) {
        clearTimeout(refinementPollTimeoutRef.current)
      }
      if (mediaRecorderRef.current?.state && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop()
      }
      if (sourceWarningTimeoutRef.current) {
        clearTimeout(sourceWarningTimeoutRef.current)
      }
      if (answerReadyResetTimeoutRef.current) {
        clearTimeout(answerReadyResetTimeoutRef.current)
      }
      if (generatingWatchdogTimeoutRef.current) {
        clearTimeout(generatingWatchdogTimeoutRef.current)
      }
      if (autoStreamingSocketRef.current) {
        autoStreamingSocketRef.current.close()
        autoStreamingSocketRef.current = null
      }
      if (autoStreamingProcessorRef.current) {
        autoStreamingProcessorRef.current.disconnect()
        autoStreamingProcessorRef.current = null
      }
      if (autoStreamingSourceNodeRef.current) {
        autoStreamingSourceNodeRef.current.disconnect()
        autoStreamingSourceNodeRef.current = null
      }
      if (autoStreamingAudioContextRef.current) {
        autoStreamingAudioContextRef.current.close().catch(() => {})
        autoStreamingAudioContextRef.current = null
      }
      streamRef.current?.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
  }, [])

  useElectronOverlaySync({
    answer,
    codingAnswer,
    answerRevealActive,
    answerFullAvailable: Boolean(fullAnswer),
    answerDisplayMode,
    questionHistory,
    questionHistoryNavigationCount,
    error,
    status: status || (answer ? 'Latest answer ready.' : 'Waiting for a question...'),
    transcript,
    fontSize,
    provider,
    category,
    generationMs,
    totalPipelineMs,
    performanceMode,
    recording,
    manualProcessing,
    isManualGenerating,
    manualQuestionError,
    recordingStartedAt,
    audioPipelineStatus,
    audioSourceWarning,
    autoMode,
    autoProcessing,
    ocrProcessing,
    ocrText,
    ocrConfidence,
    screenSources,
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
    screenVisionMs,
    screenFallbackOcrUsed,
    screenScreenshotHidSaiiaWindows,
    screenDebugPath,
    screenRejectedUiNoise,
    screenUiNoiseRatio,
    screenRejectReason,
    screenAnswerGenerated,
    screenAnswerText,
    screenCodeAnswer,
    screenCodeLanguage,
    screenAnswerDisplayedInPanel,
    screenAnswerCommittedToOverlay,
    screenPanelMode,
    screenAnswerLoading,
    screenError,
    screenOperation,
    microphoneEnabled: audioSources.microphone,
    systemAudioEnabled,
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
    autoModeStatus,
    micStreamingState,
    answerPipelineState,
    micStreamRestartCount,
    lastMicStreamRestartReason,
    autoModeSource,
    autoStartClicked,
    lastAutoTranscript,
    rawFinalTranscript,
    lastDetectedQuestion,
    acceptedAutoQuestion,
    displayedAutoQuestionRunId,
    currentAutoQuestionRunId,
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
    sttProvider,
    sttFallbackUsed,
    sttFallbackReason,
    screenShareProtectionEnabled,
    overlayOpacity,
    sessionStartedAt,
    selectedResumeIdExists: Boolean(String(startupSessionConfig?.selectedResumeId || '').trim()),
    selectedResumeName: String(startupSessionConfig?.selectedResumeName || '').trim(),
  })

  const clearAutoLoop = () => {
    if (autoLoopTimeoutRef.current) {
      clearTimeout(autoLoopTimeoutRef.current)
      autoLoopTimeoutRef.current = null
    }
    if (autoCooldownIntervalRef.current) {
      clearInterval(autoCooldownIntervalRef.current)
      autoCooldownIntervalRef.current = null
    }
  }

  const isContinuousMicAutoActive = () =>
    Boolean(autoModeRef.current && autoModeSourceRef.current === 'microphone' && autoStreamingSocketRef.current)

  const keepMicAutoListeningVisual = () => {
    if (!isContinuousMicAutoActive()) {
      return
    }
    setMicStreamingState('listening')
    setActiveAudioSource('microphone')
    setAudioPipelineStatus('recording')
  }

  const createAutoQuestionRunId = (runId) =>
    `${runId}-${Date.now()}-${Math.random().toString(16).slice(2)}`

  const isAutoQuestionRunActive = (runId, questionRunId) =>
    Boolean(
      autoModeRef.current &&
      runId &&
      questionRunId &&
      autoModeRunIdRef.current === runId &&
      currentAutoQuestionRunIdRef.current === questionRunId
    )

  const beginAutoQuestionRun = (runId, questionRunId) => {
    if (!autoModeRef.current || autoModeRunIdRef.current !== runId) {
      return false
    }
    currentAutoQuestionRunIdRef.current = questionRunId
    setCurrentAutoQuestionRunId(questionRunId)
    return true
  }

  const clearCurrentAutoQuestionRun = (questionRunId = '') => {
    if (!questionRunId || currentAutoQuestionRunIdRef.current === questionRunId) {
      currentAutoQuestionRunIdRef.current = ''
      setCurrentAutoQuestionRunId('')
    }
  }

  const clearTransientStreamingCloseError = () => {
    if (/no close frame received or sent/i.test(String(streamingError || ''))) {
      setStreamingError('')
    }
    if (/no close frame received or sent/i.test(String(lastError || ''))) {
      setLastError('')
      lastLoggedErrorRef.current = ''
    }
  }

  const stopAutoStreamingBridge = (sendTerminate = true) => {
    autoStreamingClosingRef.current = true
    const socket = autoStreamingSocketRef.current
    autoStreamingSocketRef.current = null

    if (socket) {
      try {
        if (sendTerminate && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: 'terminate' }))
        }
      } catch {
        // Ignore websocket termination send failures during shutdown.
      }
      try {
        socket.close()
      } catch {
        // Ignore socket close failures during shutdown.
      }
    }

    if (autoStreamingProcessorRef.current) {
      autoStreamingProcessorRef.current.disconnect()
      autoStreamingProcessorRef.current.onaudioprocess = null
      autoStreamingProcessorRef.current = null
    }
    if (autoStreamingSourceNodeRef.current) {
      autoStreamingSourceNodeRef.current.disconnect()
      autoStreamingSourceNodeRef.current = null
    }
    if (autoStreamingAudioContextRef.current) {
      autoStreamingAudioContextRef.current.close().catch(() => {})
      autoStreamingAudioContextRef.current = null
    }

    setAutoStreamingConnected(false)
    setPartialAutoTranscript('')
    if (autoModeSourceRef.current === 'microphone') {
      setMicStreamingState('off')
      setAnswerPipelineState('idle')
    }
  }

  const scheduleAudioPipelineIdleReset = () => {
    if (answerReadyResetTimeoutRef.current) {
      clearTimeout(answerReadyResetTimeoutRef.current)
    }

    answerReadyResetTimeoutRef.current = window.setTimeout(() => {
      setAudioPipelineStatus('idle')
      answerReadyResetTimeoutRef.current = null
    }, 450)
  }

  const clearAudioPipelineIdleReset = () => {
    if (answerReadyResetTimeoutRef.current) {
      clearTimeout(answerReadyResetTimeoutRef.current)
      answerReadyResetTimeoutRef.current = null
    }
  }

  const finishAnswerPipeline = ({ requestId, resetStatusMessage = false } = {}) => {
    if (requestId && activeAudioPipelineRequestIdRef.current && activeAudioPipelineRequestIdRef.current !== requestId) {
      return
    }
    clearAudioPipelineIdleReset()
    if (generatingWatchdogTimeoutRef.current) {
      clearTimeout(generatingWatchdogTimeoutRef.current)
      generatingWatchdogTimeoutRef.current = null
    }
    activeAudioPipelineRequestIdRef.current = ''
    if (isContinuousMicAutoActive()) {
      keepMicAutoListeningVisual()
    } else {
      setAudioPipelineStatus('idle')
    }
    if (autoModeRef.current && autoModeSourceRef.current !== 'none' && autoStreamingSocketRef.current) {
      setActiveAudioSource(autoModeSourceRef.current)
    } else {
      setActiveAudioSource('none')
    }
    setRecording(false)
    setManualProcessing(false)
    if (resetStatusMessage && !answer) {
      setStatus('Waiting for a question...')
    }
  }

  const markAudioPipelineError = ({ requestId } = {}) => {
    if (requestId && activeAudioPipelineRequestIdRef.current && activeAudioPipelineRequestIdRef.current !== requestId) {
      return
    }
    if (generatingWatchdogTimeoutRef.current) {
      clearTimeout(generatingWatchdogTimeoutRef.current)
      generatingWatchdogTimeoutRef.current = null
    }
    activeAudioPipelineRequestIdRef.current = ''
    if (isContinuousMicAutoActive()) {
      keepMicAutoListeningVisual()
    } else {
      setAudioPipelineStatus('idle')
    }
    if (autoModeRef.current && autoModeSourceRef.current !== 'none' && autoStreamingSocketRef.current) {
      setActiveAudioSource(autoModeSourceRef.current)
    } else {
      setActiveAudioSource('none')
    }
    setRecording(false)
    setManualProcessing(false)
  }

  const fetchSystemAudioDevices = async () => {
    const response = await fetch(`${BACKEND_URL}/api/audio/system/devices`)
    const payload = await parseJsonResponse(
      response,
      'Could not load system audio devices.'
    )
    const devices = Array.isArray(payload?.devices) ? payload.devices : []
    const supported = Boolean(payload?.supported) && devices.length > 0
    setSystemAudioSupported(supported)
    const defaultDeviceName = String(payload?.default_device_name || devices[0]?.name || '').trim()
    setSystemAudioDefaultDeviceName(defaultDeviceName)
    setSystemAudioDeviceName(defaultDeviceName)
    return {
      supported,
      devices,
      defaultDeviceName,
    }
  }

  const startAutoCooldown = (runId) => {
    autoCooldownUntilRef.current = Date.now() + AUTO_COOLDOWN_MS
    setAutoModeStatus('cooldown')
    setAnswerPipelineState('cooldown')
    setIsCooldownListening(true)
    setStatus('Cooldown, still listening...')
    setCooldownRemainingMs(AUTO_COOLDOWN_MS)
    if (autoCooldownIntervalRef.current) {
      clearInterval(autoCooldownIntervalRef.current)
    }
    autoCooldownIntervalRef.current = window.setInterval(() => {
      if (autoModeRunIdRef.current !== runId) {
        clearInterval(autoCooldownIntervalRef.current)
        autoCooldownIntervalRef.current = null
        return
      }
      const remaining = Math.max(0, autoCooldownUntilRef.current - Date.now())
      setCooldownRemainingMs(remaining)
    if (pendingCooldownQuestionRef.current?.timestamp) {
        setPendingCooldownQuestionAgeMs(Date.now() - pendingCooldownQuestionRef.current.timestamp)
      }
      if (remaining <= 0) {
        clearInterval(autoCooldownIntervalRef.current)
        autoCooldownIntervalRef.current = null
        setIsCooldownListening(false)
        setAnswerPipelineState('idle')
        void flushPendingCooldownQuestion(runId, autoModeSourceRef.current || 'microphone')
      }
    }, 250)
  }

  const resetAutoTranscriptBuffer = () => {
    recentAutoTranscriptBufferRef.current = []
    setRecentTranscriptBuffer('')
  }

  const pushAutoTranscriptBuffer = (text) => {
    const nextText = String(text || '').trim()
    const now = Date.now()
    recentAutoTranscriptBufferRef.current = recentAutoTranscriptBufferRef.current
      .filter((entry) => now - entry.timestamp <= AUTO_BUFFER_TTL_MS)
      .slice(-AUTO_BUFFER_MAX_CHUNKS + 1)

    if (nextText) {
      const lastEntry = recentAutoTranscriptBufferRef.current[recentAutoTranscriptBufferRef.current.length - 1]
      if (!lastEntry || !isSimilarTranscript(normalizeTranscriptForDedup(lastEntry.text), normalizeTranscriptForDedup(nextText))) {
        recentAutoTranscriptBufferRef.current.push({ text: nextText, timestamp: now })
      }
    }

    const combined = recentAutoTranscriptBufferRef.current
      .map((entry) => entry.text)
      .filter(Boolean)
      .join(' ')
      .replace(/\s+/g, ' ')
      .trim()

    setRecentTranscriptBuffer(combined)
    return combined
  }

  const clearPendingAutoQuestion = () => {
    pendingAutoQuestionRef.current = null
    setPendingAutoQuestion('')
  }

  const clearPendingCooldownQuestion = () => {
    pendingCooldownQuestionRef.current = null
    setPendingCooldownQuestion('')
    setPendingCooldownQuestionAgeMs(0)
    setCooldownQueueReason('')
  }

  const setPendingAutoQuestionState = (payload) => {
    pendingAutoQuestionRef.current = payload
    setPendingAutoQuestion(payload?.text || '')
  }

  const setPendingCooldownQuestionState = (payload, reason = 'queued_during_cooldown') => {
    const queuedAt = Date.now()
    pendingCooldownQuestionRef.current = {
      ...payload,
      timestamp: queuedAt,
      reason,
    }
    setPendingCooldownQuestion(payload?.text || '')
    setPendingCooldownQuestionAgeMs(0)
    setCooldownQueueReason(reason)
    setQueuedQuestionProcessed(false)
  }

  const flashAudioSourceWarning = (message = 'Select microphone, system audio, or both before recording.') => {
    if (sourceWarningTimeoutRef.current) {
      clearTimeout(sourceWarningTimeoutRef.current)
    }

    setAudioSourceWarning(true)
    setError('')
    setStatus(message)
    sourceWarningTimeoutRef.current = window.setTimeout(() => {
      setAudioSourceWarning(false)
      sourceWarningTimeoutRef.current = null
    }, 1800)
  }

  const clearAudioSourceWarning = () => {
    if (sourceWarningTimeoutRef.current) {
      clearTimeout(sourceWarningTimeoutRef.current)
      sourceWarningTimeoutRef.current = null
    }
    setAudioSourceWarning(false)
  }

  const stopActiveStream = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    mediaRecorderRef.current = null
    chunksRef.current = []
  }

  const resetAnswerMeta = () => {
    setProvider('')
    setPrimaryProvider('')
    setPrimaryModel('')
    setRefinementProvider('')
    setRefinementModel('')
    setRefinementUsed(false)
    setRefinementStatus('')
    setRefinementMessage('')
    setRefinementJobId('')
    setRefinedAnswer('')
    setDisplayedAnswerSource('')
    setDisplayedAutoQuestionRunId('')
    setCurrentAutoQuestionRunId('')
    currentAutoQuestionRunIdRef.current = ''
    activeRefinementJobIdRef.current = ''
    refinementPollStartedAtRef.current = 0
    refinementPollAttemptsRef.current = 0
    setCategory('')
    setGenerationMs(null)
    setTotalPipelineMs(null)
    setPipelineTimings(createEmptyPipelineTimings())
    setCodingRuntimeAudit(createEmptyCodingRuntimeAudit())
  }

  const resetScreenOcrState = () => {
    setOcrText('')
    setOcrConfidence(null)
    setScreenSources([])
    setScreenVisionProvider('')
    setScreenVisionModel('')
    setScreenCaptureTarget('active_window')
    setScreenWindowTitle('')
    setScreenProcessName('')
    setScreenImageWidth(0)
    setScreenImageHeight(0)
    setRawScreenVisionText('')
    setRawScreenVisionJson('')
    setScreenCleanedText('')
    setExtractedScreenQuestion('')
    setScreenQuestionType('none')
    setScreenConfidence(null)
    setScreenCaptureMs(0)
    setScreenVisionMs(0)
    setScreenFallbackOcrUsed(false)
    setScreenScreenshotHidSaiiaWindows(false)
    setScreenDebugPath('')
    setScreenPlatformDetected('unknown')
    setScreenCropUsed(false)
    setScreenCropRegion('')
    setScreenSourceRegion('unknown')
    setScreenExtractionRetryReason('')
    setScreenRejectedUiNoise(false)
    setScreenRejectedCodeBoilerplate(false)
    setScreenUiNoiseRatio(0)
    setScreenRejectReason('')
    setRawFullWindowVisionJson('')
    setRawCroppedVisionJson('')
    setFinalExtractedScreenQuestion('')
    setScreenValidProblemFound(false)
    setGroqVisionAttempted(false)
    setGroqVisionSuccess(false)
    setGroqVisionError('')
    setGroqVisionHttpStatus(null)
    setGroqVisionRawResponsePreview('')
    setGroqVisionParseError('')
    setGroqVisionTimeout(false)
    setScreenFallbackReason('')
    setScreenAnswerGenerated(false)
    setScreenError('')
    setScreenAnalyzeMode('visible_window')
    setScreenNeedsMoreContent(false)
    setScreenFullCaptureEnabled(false)
    setScreenFullProblemCaptureUsed(false)
    setScreenCaptureCount(1)
    setScreenScrollPositions('')
    setScreenDuplicateCaptureStopped(false)
    setScreenBottomReached(false)
    setScreenRestoredScrollPosition(false)
    setScreenDiagramDetected(false)
    setScreenChartDetected(false)
    setFinalMergedProblem('')
    setScreenFullProblemText('')
    setScreenEditorText('')
    setScreenForceTechnical(false)
    setScreenCodingAnswerMode(false)
    setScreenProfileContextUsed(true)
    setScreenAutoGenerate(false)
    setScreenAnswerText('')
    setScreenCodeAnswer('')
    setScreenCodeLanguage('')
    setScreenAnswerDisplayedInPanel(false)
    setScreenAnswerCommittedToOverlay(false)
    setScreenPanelMode('preview')
    setScreenAnswerLoading(false)
  }

  const clearTranscriptState = () => {
    setTranscript('')
    resetScreenOcrState()
    setManualQuestionError('')
    setError('')
    setStatus('Transcript cleared.')
  }

  const clearAnswerState = () => {
    clearProgressiveAnswer()
    resetAnswerMeta()
    setManualQuestionError('')
    setError('')
    setStatus('Answers cleared.')
  }

  const resetAutoInterviewState = () => {
    clearAutoLoop()
    clearPendingAutoQuestion()
    clearPendingCooldownQuestion()
    autoModeRef.current = false
    autoModeRunIdRef.current = ''
    currentAutoQuestionRunIdRef.current = ''
    autoCooldownUntilRef.current = 0
    recentProcessedTranscriptsRef.current = []
    recentAutoTranscriptBufferRef.current = []
    autoGenerationInFlightRef.current = false
    assemblyAiFallbackWarningShownRef.current = false
    lastCheckedAutoCandidateRef.current = ''
    autoStreamingClosingRef.current = false
    autoModeSourceRef.current = 'none'
    audioSourcesRef.current = { system: false, microphone: false }
    audioPipelineStatusRef.current = 'idle'
    activeAudioSourceRef.current = 'none'
    activeAudioPipelineRequestIdRef.current = ''
    chunksRef.current = []
    manualRecordingCancelledRef.current = false
    setAutoMode(false)
    setAutoProcessing(false)
    setAutoModeStatus('off')
    setMicStreamingState('off')
    setAnswerPipelineState('idle')
    setMicStreamRestartCount(0)
    setLastMicStreamRestartReason('')
    setAutoModeSource('none')
    setAutoStartClicked(false)
    setLastAutoTranscript('')
    setRawFinalTranscript('')
    setLastDetectedQuestion('')
    setAcceptedAutoQuestion('')
    setDisplayedAutoQuestionRunId('')
    setCurrentAutoQuestionRunId('')
    setLastGeneratedAt(null)
    setAutoRejectedReason('')
    setExtractedQuestionCandidate('')
    setPolishedQuestionCandidate('')
    setCorrectedQuestionCandidate('')
    setTechnicalCorrectionsSummary('')
    setPossibleSttError(false)
    setQuestionCandidateSource('')
    setQuestionDetectionInput('')
    setQuestionDetectReason('')
    setIsQuestionDetected(false)
    setCooldownRemainingMs(0)
    setRecentTranscriptBuffer('')
    setCooldownQueueReason('')
    setQueuedQuestionProcessed(false)
    setGenerationStarted(false)
    setGenerationBlockedReason('')
    setIsCooldownListening(false)
    setSttProvider('')
    setSttFallbackUsed(false)
    setSttFallbackReason('')
    setAutoStreamingConnected(false)
    setPartialAutoTranscript('')
    setStreamingError('')
    setAudioSources({ system: false, microphone: false })
    setAudioPipelineStatus('idle')
    setActiveAudioSource('none')
  }

  const loadProfileForLiveAnswer = async ({ force = false } = {}) => {
    if (!force && profileCacheRef.current) {
      return {
        profile: profileCacheRef.current,
        profileFetchMs: profileFetchMsRef.current ?? 0,
        fromCache: true,
      }
    }

    const profileFetchStarted = performance.now()
    const profileResponse = await fetch(`${BACKEND_URL}/api/profile`)
    const profile = await parseJsonResponse(profileResponse, 'Could not load profile.')
    const profileFetchMs = Number((performance.now() - profileFetchStarted).toFixed(2))
    profileCacheRef.current = profile
    profileFetchMsRef.current = profileFetchMs
    return {
      profile,
      profileFetchMs,
      fromCache: false,
    }
  }

  useEffect(() => {
    loadProfileForLiveAnswer().catch(() => {})
  }, [])

  useEffect(() => {
    fetchSystemAudioDevices().catch(() => {
      setSystemAudioSupported(false)
      setSystemAudioDeviceName('')
    })
  }, [])

  useEffect(() => {
    const handleStorage = (event) => {
      if (event.key !== 'saiiaProfileUpdatedAt') {
        return
      }

      profileCacheRef.current = null
      profileFetchMsRef.current = null
      appendEventLog('Saved profile updated. New live answers will use the latest profile.', 'info')
    }

    window.addEventListener('storage', handleStorage)
    return () => {
      window.removeEventListener('storage', handleStorage)
    }
  }, [])

  const appendEventLog = (message, tone = 'info') => {
    const nextMessage = String(message || '').trim()
    if (!nextMessage) {
      return
    }

    setEventLog((current) => {
      const nextEntry = {
        id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        message: nextMessage,
        tone,
        time: Date.now(),
      }
      return [nextEntry, ...current].slice(0, 10)
    })
  }

  const logAutoModeDebug = (message, details = null, tone = 'info') => {
    const nextDetails = details && typeof details === 'object' ? details : null
    if (nextDetails) {
      console.log(`[AutoMode] ${message}`, nextDetails)
      appendEventLog(
        `${message}: ${Object.entries(nextDetails)
          .map(([key, value]) => `${key}=${String(value)}`)
          .join(', ')}`,
        tone
      )
      return
    }

    console.log(`[AutoMode] ${message}`)
    appendEventLog(message, tone)
  }

  useEffect(() => {
    if (!status || status === lastLoggedStatusRef.current) {
      return
    }
    lastLoggedStatusRef.current = status
    appendEventLog(status, 'info')
  }, [status])

  useEffect(() => {
    if (!error || error === lastLoggedErrorRef.current) {
      return
    }
    lastLoggedErrorRef.current = error
    setLastError(error)
    appendEventLog(error, 'error')
  }, [error])

  useEffect(() => {
    if (!refinementJobId || refinementStatus !== 'pending') {
      if (refinementPollTimeoutRef.current) {
        clearTimeout(refinementPollTimeoutRef.current)
        refinementPollTimeoutRef.current = null
      }
      refinementPollStartedAtRef.current = 0
      refinementPollAttemptsRef.current = 0
      return undefined
    }

    let cancelled = false
    const trackedJobId = refinementJobId
    activeRefinementJobIdRef.current = trackedJobId

    if (!refinementPollStartedAtRef.current) {
      refinementPollStartedAtRef.current = Date.now()
      refinementPollAttemptsRef.current = 0
    }

    const pollRefinement = async () => {
      const elapsedMs = Date.now() - refinementPollStartedAtRef.current
      if (
        refinementPollAttemptsRef.current >= REFINEMENT_POLL_MAX_ATTEMPTS ||
        elapsedMs >= REFINEMENT_POLL_TIMEOUT_MS
      ) {
        setRefinementStatus('failed')
        setRefinementMessage('Groq refinement timed out. Primary Groq answer kept.')
        setRefinementJobId('')
        return
      }

      refinementPollAttemptsRef.current += 1

      try {
        const response = await fetch(`${BACKEND_URL}/generate/refinement/${trackedJobId}`)
        const payload = await parseJsonResponse(
          response,
          'Could not fetch Groq refinement status.'
        )

        if (cancelled || activeRefinementJobIdRef.current !== trackedJobId) {
          return
        }

        setRefinementProvider(payload.refinement_provider || 'groq')
        setRefinementStatus(payload.refinement_status || 'pending')

        if (payload.refinement_status === 'completed' && payload.refined_answer?.trim()) {
          setRefinedAnswer(payload.refined_answer)
          setRefinementMessage('Groq refined answer available.')
          activeRefinementJobIdRef.current = ''
          setRefinementJobId('')
          return
        }

        if (payload.refinement_status === 'failed') {
          setRefinementMessage(payload.error || 'Groq refinement failed. Primary Groq answer kept.')
          activeRefinementJobIdRef.current = ''
          setRefinementJobId('')
          return
        }

        refinementPollTimeoutRef.current = window.setTimeout(
          pollRefinement,
          REFINEMENT_POLL_INTERVAL_MS
        )
      } catch (err) {
        console.error('Refinement polling error', err)
        if (cancelled || activeRefinementJobIdRef.current !== trackedJobId) {
          return
        }
        setRefinementStatus('failed')
        setRefinementMessage('Groq refinement failed. Primary Groq answer kept.')
        activeRefinementJobIdRef.current = ''
        setRefinementJobId('')
      }
    }

    refinementPollTimeoutRef.current = window.setTimeout(
      pollRefinement,
      REFINEMENT_POLL_START_DELAY_MS
    )

    return () => {
      cancelled = true
      if (refinementPollTimeoutRef.current) {
        clearTimeout(refinementPollTimeoutRef.current)
        refinementPollTimeoutRef.current = null
      }
      if (activeRefinementJobIdRef.current === trackedJobId) {
        activeRefinementJobIdRef.current = ''
      }
    }
  }, [refinementJobId, refinementStatus])

  const transcribeAudioBlob = async (blob, mode) => {
    if (!blob || blob.size === 0) {
      if (mode === 'manual') {
        setAudioPipelineStatus('error')
        scheduleAudioPipelineIdleReset()
      }
      throw new Error('The recording is empty. Please record a short question and try again.')
    }

    setStatus(mode === 'auto' ? 'Processing detected speech...' : 'Transcribing...')
    setError('')
    if (mode === 'manual') {
      setAudioPipelineStatus('transcribing')
    }

    const form = new FormData()
    form.append('file', blob, getAudioFilename(blob))
    form.append('mode', mode)

    const transcriptionStarted = performance.now()
    const transcribeResponse = await fetch(`${BACKEND_URL}/transcribe/`, {
      method: 'POST',
      body: form,
    })
    const transcribePayload = await parseJsonResponse(
      transcribeResponse,
      'Could not transcribe the recording.'
    )
    const text = transcribePayload.text || ''
    const noSpeech = Boolean(transcribePayload.no_speech) || !text.trim()
    const nextSttProvider = String(transcribePayload.transcription_provider || '').trim()
    const nextFallbackUsed = Boolean(transcribePayload.fallback_used)
    const nextFallbackReason = String(transcribePayload.fallback_reason || '').trim()
    setSttProvider(nextSttProvider)
    setSttFallbackUsed(nextFallbackUsed)
    setSttFallbackReason(nextFallbackReason)

    if (
      nextFallbackUsed &&
      /assemblyai/i.test(nextFallbackReason) &&
      !assemblyAiFallbackWarningShownRef.current
    ) {
      assemblyAiFallbackWarningShownRef.current = true
      appendEventLog('AssemblyAI STT failed, using local Whisper fallback.', 'info')
    }

    if (noSpeech) {
      if (mode === 'manual') {
        setAudioPipelineStatus('idle')
      }
      setStatus('Waiting for a question...')
      if (mode === 'manual') {
        setTranscript('')
      }
      console.info('SAIIA transcript skipped', {
        mode,
        transcription_provider: transcribePayload.transcription_provider,
        transcription_model: transcribePayload.transcription_model,
        no_speech: true,
        reason: transcribePayload.reason || 'silence_or_no_speech',
      })
      return {
        text: '',
        uploadMs: transcribePayload.upload_ms ?? null,
        transcriptionMs:
          transcribePayload.transcription_ms ??
          Number((performance.now() - transcriptionStarted).toFixed(2)),
        noSpeech: true,
        sttProvider: nextSttProvider,
        fallbackUsed: nextFallbackUsed,
        fallbackReason: nextFallbackReason,
      }
    }

    const transcriptionMs =
      transcribePayload.transcription_ms ??
      Number((performance.now() - transcriptionStarted).toFixed(2))
    setTranscript(text)
    console.info('SAIIA transcript', {
      text,
      upload_ms: transcribePayload.upload_ms,
      transcription_ms: transcriptionMs,
      mode,
      transcription_provider: transcribePayload.transcription_provider,
      transcription_model: transcribePayload.transcription_model,
      fallback_used: transcribePayload.fallback_used,
      no_speech: false,
    })

    return {
      text,
      uploadMs: transcribePayload.upload_ms ?? null,
      transcriptionMs,
      noSpeech: false,
      sttProvider: nextSttProvider,
      fallbackUsed: nextFallbackUsed,
      fallbackReason: nextFallbackReason,
    }
  }

  const startSystemAudioRecording = async () => {
    const response = await fetch(`${BACKEND_URL}/api/audio/system/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
    const payload = await parseJsonResponse(
      response,
      'System audio recording failed to start.'
    )
    systemRecordingIdRef.current = payload.recording_id || ''
    setSystemAudioSupported(true)
    setSystemAudioDeviceName(String(payload.device_name || '').trim())
    return payload
  }

  const stopSystemAudioRecording = async ({ recordingId = systemRecordingIdRef.current, applyResult = true } = {}) => {
    const response = await fetch(`${BACKEND_URL}/api/audio/system/stop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ recording_id: recordingId || null }),
    })
    const payload = await parseJsonResponse(
      response,
      'Could not stop system audio recording.'
    )
    if (systemRecordingIdRef.current === recordingId) {
      systemRecordingIdRef.current = ''
    }
    if (applyResult) {
      setSystemAudioSupported(true)
      setSystemAudioDeviceName(String(payload.device_name || '').trim())
    }
    const text = String(payload.transcript || '').trim()
    const noSpeech = Boolean(payload.no_speech) || !text

    if (noSpeech) {
      if (applyResult) {
        setAudioPipelineStatus('idle')
        setTranscript('')
        setStatus('No question detected.')
      }
      return {
        text: '',
        uploadMs: null,
        transcriptionMs: payload.transcription_ms ?? null,
        noSpeech: true,
      }
    }

    if (applyResult) {
      setTranscript(text)
    }
    return {
      text,
      uploadMs: null,
      transcriptionMs: payload.transcription_ms ?? null,
      noSpeech: false,
    }
  }

  const stopSystemAudioRecordingForLogout = () => {
    const recordingId = systemRecordingIdRef.current
    if (!recordingId) {
      return
    }
    systemRecordingIdRef.current = ''
    stopSystemAudioRecording({ recordingId, applyResult: false }).catch(() => {})
  }

  const classifyAndGenerate = async ({
    text,
    displayQuestion = null,
    fullProblemText = '',
    editorText = '',
    inputFormat = '',
    outputFormat = '',
    sampleInput = '',
    sampleOutput = '',
    problemTitle = '',
    screenPlatformDetected = '',
    recordingMs = null,
    uploadMs = null,
    transcriptionMs,
    questionDetectMs = null,
    pipelineStarted,
    mode,
    pipelineToken = null,
    autoQuestionRunId = '',
    onCommittedQuestion = null,
    source = '',
    screenQuestionType = 'none',
    forceTechnical = false,
    suppressProfileContext = false,
  }) => {
    const requestId = Date.now() + Math.random()
    latestGenerationRequestIdRef.current = requestId
    const displayMode = mode === 'screen' ? 'screen' : mode === 'chat' ? 'chat' : 'answer'
    const historyMode = normalizeQuestionHistoryMode(displayMode)
    const requestSource = getSafeGenerationSource(mode, source)
    const historyEntryId = historyMode
      ? `qh-${Date.now()}-${Math.random().toString(16).slice(2)}`
      : ''
    const continuousMicAuto = mode === 'auto' && isContinuousMicAutoActive()
    const trackAudioPipeline =
      (mode === 'manual' || mode === 'auto') &&
      (
        activeAudioSourceRef.current !== 'none' ||
        recording ||
        manualProcessing ||
        audioPipelineStatusRef.current === 'recording' ||
        audioPipelineStatusRef.current === 'transcribing' ||
        audioPipelineStatusRef.current === 'generating'
      )

    if (trackAudioPipeline) {
      activeAudioPipelineRequestIdRef.current = String(requestId)
      if (continuousMicAuto) {
        keepMicAutoListeningVisual()
      } else {
        setAudioPipelineStatus('generating')
      }
      if (generatingWatchdogTimeoutRef.current) {
        clearTimeout(generatingWatchdogTimeoutRef.current)
      }
      generatingWatchdogTimeoutRef.current = window.setTimeout(() => {
        if (
          activeAudioPipelineRequestIdRef.current === String(requestId) &&
          audioPipelineStatusRef.current === 'generating' &&
          answerRef.current
        ) {
          console.warn('Pipeline status auto-reset after completed answer.')
          finishAnswerPipeline({ requestId: String(requestId) })
        }
      }, 30000)
    }

    try {
      if (refinementJobId) {
      activeRefinementJobIdRef.current = ''
      if (refinementPollTimeoutRef.current) {
        clearTimeout(refinementPollTimeoutRef.current)
        refinementPollTimeoutRef.current = null
      }
      setRefinementMessage('Previous refinement superseded by a newer question.')
      setRefinementJobId('')
      setRefinedAnswer('')
    }

    const effectiveScreenQuestionType = String(screenQuestionType || 'none').trim().toLowerCase()

    if (trackAudioPipeline) {
      setStatus('Classifying question...')
      setAnswerPipelineState('classifying')
      if (mode === 'auto' && autoQuestionRunId) {
        logAutoModeDebug(`starting classify for autoQuestionRunId=${autoQuestionRunId}`, {
          question: text,
        })
      }
    } else if (mode === 'screen') {
      setStatus(forceTechnical ? 'Preparing technical screen answer...' : 'Classifying screen text...')
    } else {
      setStatus('Question detected. Generating answer...')
    }

    let nextCategory = 'general'
    let classificationMs = 0

    if (forceTechnical) {
      nextCategory = 'technical'
      classificationMs = 0
    } else {
      const classificationStarted = performance.now()
      const classifyResponse = await fetch(`${BACKEND_URL}/classify/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      const classifyPayload = await parseJsonResponse(
        classifyResponse,
        'Could not classify the question.'
      )
      nextCategory = classifyPayload.category
      classificationMs =
        classifyPayload.classification_ms ??
        Number((performance.now() - classificationStarted).toFixed(2))
    }
    if (!isCurrentRequest(latestGenerationRequestIdRef.current, requestId)) {
      return
    }

    if (trackAudioPipeline) {
      setStatus('Generating answer...')
      setAnswerPipelineState('generating')
      if (mode === 'auto' && autoQuestionRunId) {
        logAutoModeDebug(`starting generate for autoQuestionRunId=${autoQuestionRunId}`, {
          question: text,
        })
      }
    } else if (mode === 'screen') {
      setStatus('Generating answer from screen text...')
    }

    let profile = {}
    let profileFetchMs = 0
    let fromCache = true

    if (!suppressProfileContext) {
      const loadedProfile = await loadProfileForLiveAnswer()
      profile = loadedProfile.profile
      profileFetchMs = loadedProfile.profileFetchMs
      fromCache = loadedProfile.fromCache

      if (!validateProfile(profile)) {
        const refreshed = await loadProfileForLiveAnswer({ force: true })
        profile = refreshed.profile
        profileFetchMs = refreshed.profileFetchMs
        fromCache = false
        if (!validateProfile(profile)) {
          throw new Error('Please complete your profile before generating interview answers.')
        }
      }
    }

    const liveProfile = suppressProfileContext ? {} : buildLiveProfileContext(profile)

    const committedQuestionBeforeStream = String(displayQuestion || text || '').trim()
    const followupContext = historyMode
      ? buildFollowupContextEntries(questionHistoryRef.current, historyMode)
      : []
    const activeStartupSessionConfig = startupSessionConfigRef.current
    const activeSessionId = String(activeStartupSessionConfig?.activeSessionId || '').trim()
    const selectedResumeId = String(activeStartupSessionConfig?.selectedResumeId || '').trim()
    const selectedResumeName = String(activeStartupSessionConfig?.selectedResumeName || '').trim()
    const targetRole = String(
      activeStartupSessionConfig?.targetRole || activeStartupSessionConfig?.role || ''
    ).trim()
    const companyName = String(
      activeStartupSessionConfig?.companyName || activeStartupSessionConfig?.company || ''
    ).trim()
    const jobDescription = String(
      activeStartupSessionConfig?.jobDescription || activeStartupSessionConfig?.jobContext || ''
    ).trim()
    const generateRequestBody = {
      request_id: String(requestId),
      question: text,
      original_question: committedQuestionBeforeStream || text,
      followup_mode: historyMode,
      followup_context: followupContext,
      full_problem_text: fullProblemText || text,
      editor_text: editorText || '',
      input_format: inputFormat || '',
      output_format: outputFormat || '',
      sample_input: sampleInput || '',
      sample_output: sampleOutput || '',
      problem_title: problemTitle || '',
      screen_platform_detected: screenPlatformDetected || '',
      category: nextCategory,
      profile: selectedResumeId ? {} : liveProfile,
      source: requestSource,
      screen_question_type: effectiveScreenQuestionType,
      force_technical: forceTechnical,
      profile_context_used: !suppressProfileContext,
      recording_ms: recordingMs,
      upload_ms: uploadMs,
      transcription_ms: transcriptionMs,
      classification_ms: classificationMs,
      profile_fetch_ms: profileFetchMs,
      session_id: activeSessionId || undefined,
      selected_resume_id: selectedResumeId || undefined,
      target_role: targetRole || undefined,
      company_name: companyName || undefined,
      job_description: jobDescription || undefined,
    }
    const selectedResumeDiagnostics = {
      activeSessionIdExists: Boolean(activeSessionId),
      selectedResumeIdExists: Boolean(selectedResumeId),
      generationRequestIncludesSessionId: Boolean(generateRequestBody.session_id),
      generationRequestIncludesSelectedResumeId: Boolean(generateRequestBody.selected_resume_id),
      jobContextIncluded: Boolean(companyName || jobDescription),
      targetRoleIncluded: Boolean(targetRole),
    }
    console.info('Intervu AI selected resume generation diagnostics', selectedResumeDiagnostics)
    if (committedQuestionBeforeStream) {
      setTranscript(committedQuestionBeforeStream)
    }
    if (historyMode && historyEntryId) {
      setQuestionHistoryState((current) =>
        appendQuestionHistoryEntry(
          current,
          createQuestionHistoryEntry({
            id: historyEntryId,
            mode: historyMode,
            requestId,
            question: committedQuestionBeforeStream,
            originalQuestion: committedQuestionBeforeStream,
            status: 'generating',
            category: nextCategory,
            provider: 'openai',
            primaryProvider: 'openai',
            metadata: {
              source,
              safeSource: requestSource,
              screenQuestionType: effectiveScreenQuestionType,
              fullProblemText,
              editorText,
            },
          })
        )
      )
      setQuestionHistoryNavigationCount((count) => count + 1)
    }
    setCategory(nextCategory)
    setProvider('openai')
    setPrimaryProvider('openai')
    setPrimaryModel('')
    setCodingAnswer(null)
    setGenerationMs(null)
    setTotalPipelineMs(null)
    setStatus('Streaming answer...')
    const generatePayload = await streamGenerateAnswer({
      body: generateRequestBody,
      requestId,
      displayMode,
      historyMode,
      historyEntryId,
    })

    if (!generatePayload.answer || !generatePayload.answer.trim()) {
      throw new Error('Generation finished without a usable answer. Please try again.')
    }
    const resolvedCategory =
      String(generatePayload.generate_category || nextCategory).trim().toLowerCase() || nextCategory

    if (!isCurrentRequest(latestGenerationRequestIdRef.current, requestId)) {
      return
    }
    if (pipelineToken && autoModeRunIdRef.current !== pipelineToken) {
      return
    }
    if (autoQuestionRunId && !isAutoQuestionRunActive(pipelineToken, autoQuestionRunId)) {
      return
    }

    const answerReceivedMs = Number((performance.now() - pipelineStarted).toFixed(2))
    const overlayCommitStarted = performance.now()
    const committedQuestion = String(displayQuestion || text || '').trim()
    if (committedQuestion && committedQuestion !== committedQuestionBeforeStream) {
      setTranscript(committedQuestion)
    }
    const overlayCommitMs = Number((performance.now() - overlayCommitStarted).toFixed(2))
    let barResetMs = null
    const baseTotalPipelineMs = Number((performance.now() - pipelineStarted).toFixed(2))
    if (trackAudioPipeline) {
      finishAnswerPipeline({ requestId: String(requestId) })
      barResetMs = Number((performance.now() - pipelineStarted).toFixed(2))
    }

    const frontendUpdateMs = Number((performance.now() - overlayCommitStarted).toFixed(2))
    const nextTotalPipelineMs = Number((answerReceivedMs + frontendUpdateMs).toFixed(2))
    const nextPipelineTimings = {
      recording_ms: recordingMs,
      upload_ms: uploadMs,
      transcription_ms: transcriptionMs,
      question_detect_ms: questionDetectMs,
      classification_ms: classificationMs,
      profile_load_ms: fromCache ? 0 : profileFetchMs,
      rag_ms: generatePayload.rag_ms ?? null,
      prompt_build_ms: generatePayload.prompt_build_ms ?? null,
      primary_generation_ms:
        generatePayload.primary_generation_ms ??
        generatePayload.groq_generation_ms ??
        generatePayload.generation_ms ??
        null,
      refinement_generation_ms: generatePayload.refinement_generation_ms ?? null,
      groq_generation_ms: generatePayload.groq_generation_ms ?? generatePayload.generation_ms ?? null,
      answer_received_ms: answerReceivedMs,
      time_to_first_visible_text_ms:
        generatePayload.time_to_first_visible_text_ms ??
        generatePayload.frontend_first_delta_ms ??
        null,
      overlay_commit_ms: overlayCommitMs,
      bar_reset_ms: barResetMs,
      frontend_update_ms: frontendUpdateMs,
      total_pipeline_ms: nextTotalPipelineMs,
      stt_provider: sttProvider,
      stt_fallback_used: sttFallbackUsed,
      stt_fallback_reason: sttFallbackReason,
      profile_context_used: generatePayload.profile_context_used ?? !suppressProfileContext,
      profile_context_policy: generatePayload.profile_context_policy || '',
      retrieved_chunk_count: generatePayload.retrieved_chunk_count ?? null,
      resume_context_source: generatePayload.resume_context_source || 'none',
      selected_resume_id_used: generatePayload.selected_resume_id_used ?? false,
      selected_resume_chunk_count: generatePayload.selected_resume_chunk_count ?? 0,
      selected_resume_candidate_name_available:
        generatePayload.selected_resume_candidate_name_available ?? false,
      selected_resume_candidate_name_source: generatePayload.selected_resume_candidate_name_source || 'none',
      project_context_chunks_found: generatePayload.project_context_chunks_found ?? 0,
      project_context_source: generatePayload.project_context_source || 'none',
      selected_resume_strict_mode: generatePayload.selected_resume_strict_mode ?? false,
      selected_resume_context_used_in_prompt: generatePayload.selected_resume_context_used_in_prompt ?? false,
      generic_fallback_blocked: generatePayload.generic_fallback_blocked ?? false,
      generic_project_fallback_blocked: generatePayload.generic_project_fallback_blocked ?? false,
      profile_fallback_blocked: generatePayload.profile_fallback_blocked ?? false,
      profile_context_suppressed_by_selected_resume:
        generatePayload.profile_context_suppressed_by_selected_resume ?? false,
      final_context_priority: generatePayload.final_context_priority || 'none',
      job_context_included: generatePayload.job_context_included ?? Boolean(companyName || jobDescription),
      target_role_included: generatePayload.target_role_included ?? Boolean(targetRole),
      project_intent_detected: generatePayload.project_intent_detected ?? false,
      selected_resume_id_exists: selectedResumeDiagnostics.selectedResumeIdExists,
      selected_resume_name: selectedResumeName,
      active_session_id_exists: selectedResumeDiagnostics.activeSessionIdExists,
      generation_request_includes_session_id:
        selectedResumeDiagnostics.generationRequestIncludesSessionId,
      generation_request_includes_selected_resume_id:
        selectedResumeDiagnostics.generationRequestIncludesSelectedResumeId,
      generation_request_includes_job_context: selectedResumeDiagnostics.jobContextIncluded,
      generation_request_includes_target_role: selectedResumeDiagnostics.targetRoleIncluded,
    }
    const visibleHistoryEntry = !historyMode || isSelectedHistoryEntry(historyMode, historyEntryId)

    if (historyMode && historyEntryId) {
      setQuestionHistoryState((current) =>
        updateQuestionHistoryEntry(
          current,
          historyMode,
          historyEntryId,
          {
            question: committedQuestion || committedQuestionBeforeStream,
            fullAnswer: generatePayload.answer,
            displayedAnswer: generatePayload.answer,
            originalQuestion: generatePayload.original_question || committedQuestion || committedQuestionBeforeStream,
            resolvedQuestion: generatePayload.resolved_question || '',
            followUpDetected: Boolean(generatePayload.follow_up_detected),
            followUpConfidence: generatePayload.follow_up_confidence ?? null,
            followUpResolutionStatus: generatePayload.follow_up_resolution_status || '',
            followUpContextEntryIds: generatePayload.follow_up_context_entry_ids || [],
            topic: generatePayload.follow_up_topic || '',
            resolutionMethod: generatePayload.follow_up_resolution_method || '',
            status: 'complete',
            category: resolvedCategory,
            provider: generatePayload.provider || '',
            model: generatePayload.model || '',
            primaryProvider: generatePayload.primary_provider || '',
            primaryModel: generatePayload.primary_model || '',
            generationMs: generatePayload.generation_ms ?? null,
            totalPipelineMs: nextTotalPipelineMs,
            completedAt: new Date().toISOString(),
            metadata: {
              source,
              screenQuestionType: effectiveScreenQuestionType,
              fullProblemText,
              editorText,
              pipelineTimings: nextPipelineTimings,
              selectedResumeName,
              selectedResumeIdExists: Boolean(selectedResumeId),
              answerType: generatePayload.answer_type || '',
              codingAnswer: generatePayload.coding_answer || null,
              programmingLanguage: generatePayload.resolved_language || generatePayload.coding_answer?.language || '',
              followUpTopic: generatePayload.follow_up_topic || '',
              followUpResolutionMs: generatePayload.follow_up_resolution_ms ?? null,
              screenCodeAnswer: mode === 'screen' ? extractCodeBlockFromAnswer(generatePayload.answer).code : '',
              screenCodeLanguage:
                mode === 'screen'
                  ? extractCodeBlockFromAnswer(generatePayload.answer).language ||
                    (effectiveScreenQuestionType === 'coding' ? 'python' : '')
                  : '',
            },
          },
          { requestId }
        )
      )
    }

    if (visibleHistoryEntry) {
      if (mode !== 'screen' && mode !== 'chat') {
        setAnswerDisplayMode('answer')
      }
      setFullAnswerState(generatePayload.answer)
      setAnswer(generatePayload.answer)
      setCodingAnswer(generatePayload.coding_answer || null)
      setProvider(generatePayload.provider || '')
      setPrimaryProvider(generatePayload.primary_provider || '')
      setPrimaryModel(generatePayload.primary_model || '')
      setRefinementProvider(generatePayload.refinement_provider || '')
      setRefinementModel(generatePayload.refinement_model || '')
      setRefinementUsed(Boolean(generatePayload.refinement_used))
      setRefinementStatus(generatePayload.refinement_status || '')
      setRefinementJobId(generatePayload.refinement_job_id || '')
      setRefinedAnswer('')
      activeRefinementJobIdRef.current = generatePayload.refinement_job_id || ''
      setDisplayedAnswerSource(
        generatePayload.refinement_used
          ? 'groq refined'
          : generatePayload.provider === 'groq'
            ? 'groq'
            : generatePayload.provider || ''
      )
      refinementPollStartedAtRef.current = generatePayload.refinement_job_id ? Date.now() : 0
      refinementPollAttemptsRef.current = 0
      if (generatePayload.refinement_status === 'pending') {
        setRefinementMessage('Groq refinement pending...')
      } else if (generatePayload.refinement_status === 'completed') {
        setRefinementMessage('Groq refinement completed.')
      } else if (generatePayload.refinement_status === 'disabled') {
        setRefinementMessage('Refinement disabled.')
      } else if (generatePayload.refinement_status === 'unsupported_provider') {
        setRefinementMessage('Refinement provider unsupported. Primary Groq answer kept.')
      } else if (generatePayload.refinement_status === 'timeout') {
        setRefinementMessage('Groq refinement timed out. Primary Groq answer kept.')
      } else if (generatePayload.refinement_status === 'failed') {
        setRefinementMessage('Groq refinement failed. Primary Groq answer kept.')
      } else {
        setRefinementMessage('')
      }
      setCategory(resolvedCategory)
      setGenerationMs(generatePayload.generation_ms ?? null)
      setPipelineTimings(nextPipelineTimings)
      setCodingRuntimeAudit(generatePayload.coding_runtime_audit || createEmptyCodingRuntimeAudit())
      setPerformanceMode(generatePayload.performance_mode || 'standard')
      setTotalPipelineMs(nextTotalPipelineMs)
    }
    setStatus('Latest answer ready.')
    setAnswerPipelineState(Date.now() < autoCooldownUntilRef.current ? 'cooldown' : 'idle')
    if (typeof onCommittedQuestion === 'function') {
      onCommittedQuestion({
        question: committedQuestion,
        category: resolvedCategory,
      })
    }
    setGenerationStarted(false)
    setGenerationBlockedReason('')

    console.info('SAIIA answer pipeline', {
      mode,
      recording_ms: recordingMs,
      upload_ms: uploadMs,
      transcription_ms: transcriptionMs,
      question_detect_ms: questionDetectMs,
      classification_ms: classificationMs,
      profile_fetch_ms: fromCache ? 0 : profileFetchMs,
      rag_ms: generatePayload.rag_ms,
      prompt_build_ms: generatePayload.prompt_build_ms,
      primary_generation_ms:
        generatePayload.primary_generation_ms ??
        generatePayload.groq_generation_ms ??
        generatePayload.generation_ms,
      refinement_generation_ms: generatePayload.refinement_generation_ms ?? null,
      groq_generation_ms: generatePayload.groq_generation_ms ?? generatePayload.generation_ms,
      answer_received_ms: answerReceivedMs,
      time_to_first_visible_text_ms:
        generatePayload.time_to_first_visible_text_ms ??
        generatePayload.frontend_first_delta_ms ??
        null,
      overlay_commit_ms: overlayCommitMs,
      bar_reset_ms: barResetMs,
      frontend_update_ms: frontendUpdateMs,
      generation_ms: generatePayload.generation_ms,
      total_pipeline_ms: nextTotalPipelineMs,
      provider: generatePayload.provider,
      primary_provider: generatePayload.primary_provider,
      primary_model: generatePayload.primary_model,
      refinement_provider: generatePayload.refinement_provider,
      refinement_model: generatePayload.refinement_model,
      refinement_used: generatePayload.refinement_used,
      refinement_status: generatePayload.refinement_status,
      model: generatePayload.model,
      fallback_used: generatePayload.fallback_used,
      retrieval_used: generatePayload.retrieval_used,
      retrieved_chunk_count: generatePayload.retrieved_chunk_count,
      resume_context_source: generatePayload.resume_context_source,
      selected_resume_id_used: generatePayload.selected_resume_id_used,
      selected_resume_chunk_count: generatePayload.selected_resume_chunk_count,
      selected_resume_candidate_name_available:
        generatePayload.selected_resume_candidate_name_available,
      selected_resume_candidate_name_source: generatePayload.selected_resume_candidate_name_source,
      selected_resume_strict_mode: generatePayload.selected_resume_strict_mode,
      selected_resume_context_used_in_prompt: generatePayload.selected_resume_context_used_in_prompt,
      generic_fallback_blocked: generatePayload.generic_fallback_blocked,
      profile_fallback_blocked: generatePayload.profile_fallback_blocked,
      profile_context_suppressed_by_selected_resume:
        generatePayload.profile_context_suppressed_by_selected_resume,
      final_context_priority: generatePayload.final_context_priority,
      selected_resume_id_exists: selectedResumeDiagnostics.selectedResumeIdExists,
      generation_request_includes_selected_resume_id:
        selectedResumeDiagnostics.generationRequestIncludesSelectedResumeId,
      coding_runtime_audit: generatePayload.coding_runtime_audit,
    })
    return {
      answer: generatePayload.answer,
      category: resolvedCategory,
      provider: generatePayload.provider || '',
      primaryProvider: generatePayload.primary_provider || '',
      primaryModel: generatePayload.primary_model || '',
      refinementStatus: generatePayload.refinement_status || '',
      profileContextUsed: generatePayload.profile_context_used ?? !suppressProfileContext,
      resumeContextSource: generatePayload.resume_context_source || 'none',
      selectedResumeIdUsed: Boolean(generatePayload.selected_resume_id_used),
      selectedResumeChunkCount: generatePayload.selected_resume_chunk_count ?? 0,
    }
    } catch (err) {
      setGenerationStarted(false)
      setGenerationBlockedReason(err?.message || 'generation_failed')
      setAnswerPipelineState('idle')
      if (trackAudioPipeline) {
        markAudioPipelineError({ requestId: String(requestId) })
      }
      throw err
    }
  }

  const processManualBlob = async (blob) => {
    const pipelineStarted = performance.now()
    const recordingMs = recordingStartedAt
      ? Number((Date.now() - recordingStartedAt).toFixed(2))
      : null
    const { text, uploadMs, transcriptionMs, noSpeech } = await transcribeAudioBlob(blob, 'manual')
    if (noSpeech) {
      return
    }
    await classifyAndGenerate({
      text,
      displayQuestion: text,
      recordingMs,
      uploadMs,
      transcriptionMs,
      pipelineStarted,
      mode: 'manual',
    })
  }

  const shouldSkipRecentTranscript = (normalizedText) => {
    const now = Date.now()
    recentProcessedTranscriptsRef.current = recentProcessedTranscriptsRef.current.filter(
      (entry) => now - entry.timestamp < AUTO_DUPLICATE_WINDOW_MS
    )

    const duplicateEntry = recentProcessedTranscriptsRef.current.find((entry) =>
      isSimilarTranscript(entry.text, normalizedText)
    )
    if (duplicateEntry) {
      return 'recent_duplicate_question'
    }

    return ''
  }

  const recordAutoSegment = (stream, runId) =>
    new Promise((resolve, reject) => {
      const mimeType = getPreferredRecorderMimeType()
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream)

      mediaRecorderRef.current = recorder
      chunksRef.current = []

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data)
        }
      }

      recorder.onerror = (event) => {
        logAutoModeDebug('mic recorder error', { runId }, 'error')
        reject(event.error || new Error('Auto Mode recorder error.'))
      }

      recorder.onstop = () => {
        const type = recorder.mimeType || chunksRef.current[0]?.type || 'audio/webm'
        const blob = new Blob(chunksRef.current, { type })
        mediaRecorderRef.current = null
        chunksRef.current = []
        logAutoModeDebug('mic chunk captured', {
          runId,
          size: blob.size,
          type: blob.type || 'audio/webm',
        })
        if (!blob.size) {
          reject(new Error('Auto Mode produced an empty microphone recording.'))
          return
        }
        resolve(blob)
      }

      logAutoModeDebug('mic chunk capture starting', { runId, duration_ms: AUTO_MIC_CHUNK_MS })
      recorder.start()
      setRecording(true)
      setAudioPipelineStatus('recording')
      setActiveAudioSource('microphone')
      setAutoModeStatus('capturing')
      setRecordingStartedAt(Date.now())

      window.setTimeout(() => {
        if (autoModeRunIdRef.current !== runId) {
          logAutoModeDebug('mic chunk cancelled before stop', { runId })
          if (recorder.state !== 'inactive') {
            recorder.stop()
          }
          return
        }
        if (recorder.state !== 'inactive') {
          recorder.stop()
        }
      }, AUTO_MIC_CHUNK_MS)
    })

  const handleOverlayToggle = async () => {
    if (!window.electronAPI?.toggleOverlayVisibility) {
      return
    }

    const nextState = await window.electronAPI.toggleOverlayVisibility()
    if (typeof nextState?.visible === 'boolean') {
      setOverlayVisible(nextState.visible)
    }
  }

  const captureSystemAutoChunk = async (runId) => {
    logAutoModeDebug('calling /api/audio/system/capture-chunk', {
      runId,
      duration_ms: AUTO_SYSTEM_CHUNK_MS,
    })
    setAutoModeStatus('capturing')
    setAudioPipelineStatus('recording')
    setActiveAudioSource('system')
    const response = await fetch(`${BACKEND_URL}/api/audio/system/capture-chunk`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ duration_ms: AUTO_SYSTEM_CHUNK_MS }),
    })
    const payload = await parseJsonResponse(
      response,
      'System audio Auto Mode could not capture audio.'
    )
    if (autoModeRunIdRef.current !== runId) {
      return null
    }
    setSystemAudioDeviceName(String(payload.device_name || '').trim())
    setAudioPipelineStatus('transcribing')
    return {
      text: String(payload.transcript || ''),
      recordingMs: payload.recording_ms ?? AUTO_SYSTEM_CHUNK_MS,
      uploadMs: null,
      transcriptionMs: payload.transcription_ms ?? null,
      noSpeech: Boolean(payload.no_speech) || !String(payload.transcript || '').trim(),
      reason: payload.reason || '',
      sttProvider: String(payload.provider || '').trim(),
      fallbackUsed: false,
      fallbackReason: '',
    }
  }

  const queuePendingAutoQuestion = (payload, reason) => {
    const normalizedText = String(payload?.normalizedQuestion || '').trim()
    if (!normalizedText) {
      return
    }

    if (reason === 'cooldown_active') {
      const duplicateReason = shouldSkipRecentTranscript(normalizedText)
      if (duplicateReason) {
        setAutoRejectedReason(duplicateReason)
        return
      }
      if (
        pendingCooldownQuestionRef.current?.normalizedQuestion &&
        isSimilarTranscript(pendingCooldownQuestionRef.current.normalizedQuestion, normalizedText)
      ) {
        return
      }
      setPendingCooldownQuestionState(payload, 'queued_during_cooldown')
      setAutoModeStatus('cooldown')
      setStatus('Cooldown, still listening...')
      logAutoModeDebug('cooldown question queued', {
        reason,
        question: payload.text,
      })
      return
    }

    if (
      pendingAutoQuestionRef.current?.normalizedQuestion &&
      isSimilarTranscript(pendingAutoQuestionRef.current.normalizedQuestion, normalizedText)
    ) {
      return
    }

    if (pendingAutoQuestionRef.current && autoGenerationInFlightRef.current) {
      logAutoModeDebug('pending auto question kept', {
        reason: 'generation_in_progress_lock',
        current: pendingAutoQuestionRef.current.text,
      })
      return
    }

    if (pendingAutoQuestionRef.current && Date.now() < autoCooldownUntilRef.current) {
      logAutoModeDebug('pending auto question kept', {
        reason: 'cooldown_lock',
        current: pendingAutoQuestionRef.current.text,
      })
      return
    }

    setPendingAutoQuestionState(payload)
    setAutoModeStatus('pending')
    setStatus('Pending question queued.')
    logAutoModeDebug('pending auto question queued', {
      reason,
      question: payload.text,
    })
  }

  const flushPendingCooldownQuestion = async (runId, sourceMode) => {
    const pending = pendingCooldownQuestionRef.current
    if (!pending || autoModeRunIdRef.current !== runId || autoGenerationInFlightRef.current) {
      return
    }
    if (Date.now() < autoCooldownUntilRef.current) {
      return
    }

    const duplicateReason = shouldSkipRecentTranscript(pending.normalizedQuestion)
    if (duplicateReason) {
      logAutoModeDebug('queued cooldown question rejected', { reason: duplicateReason })
      clearPendingCooldownQuestion()
      setAutoRejectedReason(duplicateReason)
      return
    }

    const nextPayload = {
      ...pending,
      questionRunId: createAutoQuestionRunId(runId),
      pipelineStarted: performance.now(),
    }
    clearPendingCooldownQuestion()
    setQueuedQuestionProcessed(true)
    await processAutoQuestion(runId, sourceMode, nextPayload)
  }

  const detectCorrectedAutoQuestion = async (baseTranscript) => {
    const initialDetection = await detectAutoQuestion(baseTranscript)
    const candidateText = String(initialDetection.extracted_candidate || '').trim()
    const polishedCandidate = String(initialDetection.polished_candidate || candidateText || baseTranscript).trim()
    const correction = correctTechnicalQuestionText(polishedCandidate || candidateText || baseTranscript)
    const correctedCandidate = String(correction.correctedText || polishedCandidate || candidateText || baseTranscript).trim()
    const correctionSummary = correction.corrections
      .map((entry) => `${entry.from} -> ${entry.to}`)
      .join(' | ')

    let finalDetection = initialDetection
    if (correctedCandidate && normalizeTranscriptForDedup(correctedCandidate) !== normalizeTranscriptForDedup(polishedCandidate)) {
      finalDetection = await detectAutoQuestion(correctedCandidate)
    }

    return {
      initialDetection,
      finalDetection,
      candidateText,
      polishedCandidate,
      correctedCandidate,
      correctionSummary,
      possibleSttError: correction.possibleSttError,
      correctionConfidence: correction.confidence,
    }
  }

  const handleAutoTranscriptFinal = async ({
    runId,
    sourceMode,
    text,
    transcriptionMs = null,
    sttProviderName = '',
    fallbackUsed = false,
    fallbackReason = '',
    pipelineStarted = performance.now(),
  }) => {
    if (!autoModeRef.current || autoModeRunIdRef.current !== runId) {
      return
    }

    const normalizedText = String(text || '').trim()
    setRawFinalTranscript(normalizedText)
    setLastAutoTranscript(normalizedText)
    pushAutoTranscriptBuffer(normalizedText)
    const effectiveTranscript = normalizedText

    if (sttProviderName) {
      setSttProvider(sttProviderName)
    }
    setSttFallbackUsed(Boolean(fallbackUsed))
    setSttFallbackReason(String(fallbackReason || '').trim())

    if (!effectiveTranscript) {
      setAutoRejectedReason('silence_or_no_speech')
      setQuestionDetectReason('silence_or_no_speech')
      setIsQuestionDetected(false)
      setAnswerPipelineState('idle')
      if (sourceMode === 'microphone') {
        keepMicAutoListeningVisual()
      }
      setStatus(Date.now() < autoCooldownUntilRef.current ? 'Cooldown, still listening...' : 'Listening...')
      setAutoModeStatus(Date.now() < autoCooldownUntilRef.current ? 'cooldown' : 'listening')
      return
    }

    const fillerReason = getAutoRejectReason(effectiveTranscript)
    if (fillerReason) {
      setAutoRejectedReason(fillerReason)
      setQuestionDetectReason(fillerReason)
      setIsQuestionDetected(false)
      setAnswerPipelineState('idle')
      if (sourceMode === 'microphone') {
        keepMicAutoListeningVisual()
      }
      setStatus(Date.now() < autoCooldownUntilRef.current ? 'Cooldown, still listening...' : 'Listening...')
      setAutoModeStatus(Date.now() < autoCooldownUntilRef.current ? 'cooldown' : 'listening')
      return
    }

    if (normalizedText.length <= 8) {
      setAutoRejectedReason('candidate_too_short')
      setQuestionDetectReason('candidate_too_short')
      setIsQuestionDetected(false)
      setAnswerPipelineState('idle')
      if (sourceMode === 'microphone') {
        keepMicAutoListeningVisual()
      }
      return
    }

    setAutoModeStatus('detecting')
    setAnswerPipelineState('detecting')
    setStatus('Question detected')
    const detectionResult = await detectCorrectedAutoQuestion(normalizedText)
    if (!autoModeRef.current || autoModeRunIdRef.current !== runId) {
      return
    }

    const {
      finalDetection,
      candidateText,
      polishedCandidate,
      correctedCandidate,
      correctionSummary,
      possibleSttError: detectedPossibleSttError,
    } = detectionResult
    const detectionInput = String(
      finalDetection.normalized_question || correctedCandidate || polishedCandidate || candidateText || normalizedText
    ).trim()
    setExtractedQuestionCandidate(candidateText)
    setPolishedQuestionCandidate(polishedCandidate)
    setCorrectedQuestionCandidate(correctedCandidate)
    setTechnicalCorrectionsSummary(correctionSummary)
    setPossibleSttError(Boolean(detectedPossibleSttError))
    setQuestionCandidateSource(String(finalDetection.candidate_source || 'none'))
    setQuestionDetectionInput(detectionInput)
    setQuestionDetectReason(String(finalDetection.reason || ''))
    setIsQuestionDetected(Boolean(finalDetection.is_question))

    const normalizedCheckedCandidate = normalizeTranscriptForDedup(detectionInput)
    if (
      normalizedCheckedCandidate &&
      normalizedCheckedCandidate.length > 8 &&
      lastCheckedAutoCandidateRef.current === normalizedCheckedCandidate
    ) {
      setAutoRejectedReason('duplicate_candidate_check')
      setAnswerPipelineState('idle')
      if (sourceMode === 'microphone') {
        keepMicAutoListeningVisual()
      }
      return
    }
    if (normalizedCheckedCandidate.length > 8) {
      lastCheckedAutoCandidateRef.current = normalizedCheckedCandidate
    }

    const normalizedQuestion = normalizeTranscriptForDedup(
      finalDetection.normalized_question || finalDetection.normalized_text || detectionInput || effectiveTranscript
    )
    const skipReason = shouldSkipRecentTranscript(normalizedQuestion)

    setPipelineTimings((current) => ({
      ...current,
      question_detect_ms: finalDetection.questionDetectMs,
      transcription_ms: transcriptionMs,
      stt_provider: sttProviderName || current.stt_provider,
      stt_fallback_used: Boolean(fallbackUsed),
      stt_fallback_reason: String(fallbackReason || ''),
    }))

    if (!finalDetection.is_question) {
      setAutoRejectedReason(finalDetection.reason || 'not_a_question')
      setAnswerPipelineState('idle')
      if (sourceMode === 'microphone') {
        keepMicAutoListeningVisual()
      }
      setStatus(Date.now() < autoCooldownUntilRef.current ? 'Cooldown, still listening...' : 'Listening...')
      setAutoModeStatus(Date.now() < autoCooldownUntilRef.current ? 'cooldown' : 'listening')
      return
    }

    if (skipReason) {
      setAutoRejectedReason(skipReason)
      setAnswerPipelineState('idle')
      if (sourceMode === 'microphone') {
        keepMicAutoListeningVisual()
      }
      setStatus(Date.now() < autoCooldownUntilRef.current ? 'Cooldown, still listening...' : 'Listening...')
      setAutoModeStatus(Date.now() < autoCooldownUntilRef.current ? 'cooldown' : 'listening')
      return
    }

    const questionText = String(
      finalDetection.normalized_question || correctedCandidate || polishedCandidate || candidateText || effectiveTranscript
    ).trim()
    const acceptedQuestion = questionText
    setAutoRejectedReason('')
    setError('')
    setAcceptedAutoQuestion(acceptedQuestion)
    setLastDetectedQuestion(acceptedQuestion)
    const questionRunId = createAutoQuestionRunId(runId)

    const autoQuestionPayload = {
      text: acceptedQuestion,
      displayQuestion: acceptedQuestion,
      normalizedQuestion,
      recordingMs: null,
      uploadMs: null,
      transcriptionMs,
      questionDetectMs: finalDetection.questionDetectMs,
      pipelineStarted: performance.now(),
      questionRunId,
    }

    if (autoGenerationInFlightRef.current) {
      setGenerationBlockedReason('generation_in_progress')
      queuePendingAutoQuestion(autoQuestionPayload, 'generation_in_progress')
      return
    }

    if (Date.now() < autoCooldownUntilRef.current) {
      setGenerationBlockedReason('cooldown_active')
      queuePendingAutoQuestion(autoQuestionPayload, 'cooldown_active')
      return
    }

    setGenerationBlockedReason('')
    logAutoModeDebug('question accepted', {
      autoQuestionRunId: questionRunId,
      question: acceptedQuestion,
      source: sourceMode,
    })
    setAutoModeStatus('question_detected')
    setStatus('Question detected')
    await processAutoQuestion(runId, sourceMode, autoQuestionPayload)
  }

  const processAutoQuestion = async (runId, sourceMode, payload) => {
    if (!payload?.text || autoModeRunIdRef.current !== runId || autoGenerationInFlightRef.current) {
      const blockedReason = !payload?.text
        ? 'missing_payload_text'
        : autoModeRunIdRef.current !== runId
          ? 'stale_auto_run'
          : 'generation_already_in_flight'
      setGenerationBlockedReason(blockedReason)
      logAutoModeDebug('discarded stale question run', {
        reason: blockedReason,
        autoQuestionRunId: payload?.questionRunId || 'n/a',
      })
      return
    }
    if (!beginAutoQuestionRun(runId, payload.questionRunId)) {
      setGenerationBlockedReason('question_run_not_active')
      logAutoModeDebug('discarded stale question run', {
        reason: 'question_run_not_active',
        autoQuestionRunId: payload.questionRunId || 'n/a',
      })
      return
    }

    autoGenerationInFlightRef.current = true
    setAutoRejectedReason('')
    setAutoModeStatus('generating')
    setAnswerPipelineState('classifying')
    if (sourceMode === 'microphone' && isContinuousMicAutoActive()) {
      keepMicAutoListeningVisual()
    } else {
      setAudioPipelineStatus('generating')
      setActiveAudioSource(sourceMode)
    }
    setGenerationStarted(true)
    setGenerationBlockedReason('')
    setPendingAutoQuestion(payload.text)
    logAutoModeDebug('starting classify for autoQuestionRunId=' + payload.questionRunId, {
      question: payload.text,
      source: sourceMode,
    })

    try {
      await classifyAndGenerate({
        text: payload.text,
        displayQuestion: payload.displayQuestion || payload.text,
        recordingMs: payload.recordingMs ?? null,
        uploadMs: payload.uploadMs ?? null,
        transcriptionMs: payload.transcriptionMs ?? null,
        questionDetectMs: payload.questionDetectMs ?? null,
        pipelineStarted: payload.pipelineStarted ?? performance.now(),
        mode: 'auto',
        pipelineToken: runId,
        autoQuestionRunId: payload.questionRunId,
        onCommittedQuestion: ({ question }) => {
          if (!isAutoQuestionRunActive(runId, payload.questionRunId)) {
            return
          }
          setLastDetectedQuestion(question)
          setDisplayedAutoQuestionRunId(payload.questionRunId)
          if (pendingAutoQuestionRef.current?.questionRunId === payload.questionRunId) {
            clearPendingAutoQuestion()
          }
          resetAutoTranscriptBuffer()
          clearTransientStreamingCloseError()
        },
      })
      logAutoModeDebug('starting generate for autoQuestionRunId=' + payload.questionRunId, {
        question: payload.text,
      })

      if (!isAutoQuestionRunActive(runId, payload.questionRunId)) {
        logAutoModeDebug('discarded stale question run', {
          reason: 'became_inactive_after_generate',
          autoQuestionRunId: payload.questionRunId,
        })
        return
      }

      recentProcessedTranscriptsRef.current.push({
        text: payload.normalizedQuestion,
        timestamp: Date.now(),
      })
      setLastGeneratedAt(Date.now())
      setGenerationStarted(false)
      setGenerationBlockedReason('')
      logAutoModeDebug('answer generated for auto question', {
        runId,
        source: sourceMode,
        question: payload.text,
      })
      logAutoModeDebug('generate completed for autoQuestionRunId=' + payload.questionRunId, {
        question: payload.text,
      })
      startAutoCooldown(runId)
    } finally {
      autoGenerationInFlightRef.current = false
      clearCurrentAutoQuestionRun(payload.questionRunId)
    }
  }

  const flushPendingAutoQuestion = async (runId, sourceMode) => {
    const pending = pendingAutoQuestionRef.current
    if (!pending || autoModeRunIdRef.current !== runId || autoGenerationInFlightRef.current) {
      return
    }
    if (Date.now() < autoCooldownUntilRef.current) {
      return
    }

    const duplicateReason = shouldSkipRecentTranscript(pending.normalizedQuestion)
    if (duplicateReason) {
      logAutoModeDebug('pending auto question rejected', { reason: duplicateReason })
      clearPendingAutoQuestion()
      setAutoRejectedReason(duplicateReason)
      return
    }

    clearPendingAutoQuestion()
    await processAutoQuestion(runId, sourceMode, pending)
  }

  const detectAutoQuestion = async (text) => {
    const started = performance.now()
    const detectResponse = await fetch(`${BACKEND_URL}/api/question-detect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        transcript: text,
        combined_transcript: recentAutoTranscriptBufferRef.current
          .map((entry) => entry.text)
          .filter(Boolean)
          .join(' ')
          .trim(),
      }),
    })
    const detectPayload = await parseJsonResponse(
      detectResponse,
      'Could not detect whether the transcript is a question.'
    )
    return {
      ...detectPayload,
      questionDetectMs: Number((performance.now() - started).toFixed(2)),
    }
  }

  const startAutoStreamingMic = async (runId, stream) => {
    setStreamingError('')
    clearTransientStreamingCloseError()
    setPartialAutoTranscript('')
    autoStreamingClosingRef.current = false
    setMicStreamingState('connecting')
    setAnswerPipelineState('idle')
    setMicStreamRestartCount(0)
    setLastMicStreamRestartReason('')

    const socket = new WebSocket(getBackendWebSocketUrl('/ws/auto-stt'))
    socket.binaryType = 'arraybuffer'
    autoStreamingSocketRef.current = socket

    const audioContext = new window.AudioContext()
    autoStreamingAudioContextRef.current = audioContext
    const sourceNode = audioContext.createMediaStreamSource(stream)
    autoStreamingSourceNodeRef.current = sourceNode
    const processor = audioContext.createScriptProcessor(4096, 1, 1)
    autoStreamingProcessorRef.current = processor

    processor.onaudioprocess = (event) => {
      if (
        !autoModeRef.current ||
        autoModeRunIdRef.current !== runId ||
        socket.readyState !== WebSocket.OPEN
      ) {
        return
      }
      const inputChannel = event.inputBuffer.getChannelData(0)
      const pcm16 = downsampleToInt16Mono(
        inputChannel,
        audioContext.sampleRate,
        16000
      )
      if (pcm16.length) {
        socket.send(pcm16.buffer)
      }
    }

    sourceNode.connect(processor)
    processor.connect(audioContext.destination)

    const activateAutoStreamingFallback = () => {
      if (!autoModeRef.current || autoModeRunIdRef.current !== runId) {
        return
      }
      if (autoStreamingSocketRef.current) {
        return
      }
      setSttProvider('whisper_local')
      setSttFallbackUsed(true)
      setSttFallbackReason('assemblyai_streaming_failed')
      setStreamingError('AssemblyAI streaming failed, using local Whisper fallback.')
      appendEventLog('AssemblyAI streaming failed, using local Whisper fallback.', 'info')
      logAutoModeDebug('auto streaming fallback activated', { runId, provider: 'whisper_local' })
      scheduleNextAutoCycle(runId, 'microphone', 100)
    }

    socket.onopen = () => {
      if (autoModeRunIdRef.current !== runId) {
        return
      }
      setAutoStreamingConnected(true)
      setAutoModeStatus('listening')
      setStatus('Listening...')
      setMicStreamingState('listening')
      keepMicAutoListeningVisual()
      logAutoModeDebug('assemblyai streaming websocket connected', { runId })
    }

    socket.onmessage = async (event) => {
      if (!autoModeRef.current || autoModeRunIdRef.current !== runId) {
        return
      }

      let payload = null
      try {
        payload = JSON.parse(String(event.data || '{}'))
      } catch {
        return
      }

      const eventName = String(payload.event || '').toLowerCase()
      if (eventName === 'begin') {
        setAutoStreamingConnected(true)
        setSttProvider('assemblyai_streaming')
        setStreamingError('')
        setError('')
        clearTransientStreamingCloseError()
        setMicStreamingState('listening')
        keepMicAutoListeningVisual()
        return
      }

      if (eventName === 'turn') {
        const transcriptText = String(payload.transcript || '').trim()
        if (!transcriptText) {
          return
        }

        if (payload.end_of_turn) {
          setPartialAutoTranscript('')
          await handleAutoTranscriptFinal({
            runId,
            sourceMode: 'microphone',
            text: transcriptText,
            transcriptionMs: null,
            sttProviderName: 'assemblyai_streaming',
            fallbackUsed: false,
            fallbackReason: '',
            pipelineStarted: performance.now(),
          })
          return
        }

        setPartialAutoTranscript(transcriptText)
        setAutoModeStatus('listening')
        keepMicAutoListeningVisual()
        setStatus(Date.now() < autoCooldownUntilRef.current ? 'Cooldown, still listening...' : 'Listening...')
        return
      }

      if (eventName === 'termination') {
        setAutoStreamingConnected(false)
        setMicStreamingState(autoModeRef.current ? 'stopped' : 'off')
        logAutoModeDebug('assemblyai streaming session terminated', { runId })
        return
      }

      if (eventName === 'error') {
        const message = String(payload.message || 'AssemblyAI streaming error.')
        if (
          autoStreamingClosingRef.current ||
          !autoModeRef.current ||
          /no close frame received or sent/i.test(message)
        ) {
          setStreamingError('')
          return
        }
        setStreamingError(message)
        setAutoStreamingConnected(false)
        setMicStreamingState('error')
        setLastMicStreamRestartReason('assemblyai_streaming_error')
        stopAutoStreamingBridge(false)
        logAutoModeDebug('assemblyai streaming error', { runId, message }, 'error')
        activateAutoStreamingFallback()
      }
    }

    socket.onerror = () => {
      if (autoModeRunIdRef.current !== runId) {
        return
      }
      if (autoStreamingClosingRef.current || !autoModeRef.current) {
        return
      }
      setStreamingError('AssemblyAI streaming connection failed.')
      setAutoStreamingConnected(false)
      setMicStreamingState('error')
      setLastMicStreamRestartReason('websocket_error')
      stopAutoStreamingBridge(false)
      logAutoModeDebug('assemblyai streaming websocket error', { runId }, 'error')
      activateAutoStreamingFallback()
    }

    socket.onclose = () => {
      if (autoModeRunIdRef.current !== runId || autoStreamingClosingRef.current || !autoModeRef.current) {
        return
      }
      setAutoStreamingConnected(false)
      setMicStreamingState(autoModeRef.current ? 'stopped' : 'off')
      logAutoModeDebug('assemblyai streaming websocket closed', { runId })
      stopAutoStreamingBridge(false)
      activateAutoStreamingFallback()
    }
  }

  const startAutoStreamingSystem = async (runId) => {
    setStreamingError('')
    clearTransientStreamingCloseError()
    setPartialAutoTranscript('')
    setSystemAudioSampleRate(null)
    autoStreamingClosingRef.current = false

    const socket = new WebSocket(getBackendWebSocketUrl('/ws/system-auto-stt'))
    socket.binaryType = 'arraybuffer'
    autoStreamingSocketRef.current = socket

    const stopSystemStreaming = (message) => {
      if (
        autoStreamingClosingRef.current ||
        !autoModeRef.current ||
        /no close frame received or sent/i.test(String(message || ''))
      ) {
        setStreamingError('')
        return
      }
      setStreamingError(message)
      setAutoStreamingConnected(false)
      stopAutoStreamingBridge(false)
      setAutoModeStatus('error')
      setError(message)
      setStatus('Auto Mode stopped.')
      autoModeRef.current = false
      autoModeRunIdRef.current = ''
      setAutoMode(false)
      setAutoProcessing(false)
    }

    socket.onopen = () => {
      if (autoModeRunIdRef.current !== runId) {
        return
      }
      setAutoStreamingConnected(true)
      setAutoModeStatus('listening')
      setStatus('Listening...')
      setSttProvider('assemblyai_streaming')
      setActiveAudioSource('system')
      logAutoModeDebug('system assemblyai streaming websocket connected', { runId })
    }

    socket.onmessage = async (event) => {
      if (!autoModeRef.current || autoModeRunIdRef.current !== runId) {
        return
      }

      let payload = null
      try {
        payload = JSON.parse(String(event.data || '{}'))
      } catch {
        return
      }

      const eventName = String(payload.event || '').toLowerCase()
      if (eventName === 'system_stream_ready') {
        setAutoStreamingConnected(true)
        setStreamingError('')
        setError('')
        clearTransientStreamingCloseError()
        setSystemAudioDeviceName(String(payload.device_name || '').trim())
        setSystemAudioInputSampleRate(payload.input_sample_rate ?? null)
        setSystemAudioSampleRate(payload.sample_rate ?? null)
        setSttProvider('assemblyai_streaming')
        setActiveAudioSource('system')
        return
      }

      if (eventName === 'quality') {
        setSystemAudioDeviceName(String(payload.selected_device_name || payload.device_name || systemAudioDeviceName || '').trim())
        setSystemAudioInputSampleRate(payload.input_sample_rate ?? null)
        setSystemAudioSampleRate(payload.target_sample_rate ?? payload.sample_rate ?? null)
        setSystemAudioRmsLevel(payload.rms_level ?? null)
        setSystemAudioPeakLevel(payload.peak_level ?? null)
        setSystemAudioChunkBytesSent(payload.bytes_sent_per_second ?? payload.chunk_bytes_sent ?? 0)
        setSystemAudioDroppedSilenceChunks(payload.dropped_silence_chunks ?? 0)
        setSystemAudioClippingDetected(Boolean(payload.clipping_detected))
        setSystemAudioQualityWarning(String(payload.warning || '').trim())
        setSystemAudioDebugWavPath(String(payload.debug_wav_path || '').trim())
        setSystemAudioEffectiveGain(payload.effective_gain ?? null)
        if (payload.warning) {
          appendEventLog(String(payload.warning), 'info')
        }
        return
      }

      if (eventName === 'begin') {
        setAutoStreamingConnected(true)
        setStreamingError('')
        setError('')
        clearTransientStreamingCloseError()
        setSttProvider('assemblyai_streaming')
        setActiveAudioSource('system')
        return
      }

      if (eventName === 'turn') {
        const transcriptText = String(payload.transcript || '').trim()
        if (!transcriptText) {
          return
        }

        if (payload.end_of_turn) {
          setPartialAutoTranscript('')
          await handleAutoTranscriptFinal({
            runId,
            sourceMode: 'system',
            text: transcriptText,
            transcriptionMs: null,
            sttProviderName: 'assemblyai_streaming',
            fallbackUsed: false,
            fallbackReason: '',
            pipelineStarted: performance.now(),
          })
          return
        }

        setPartialAutoTranscript(transcriptText)
        setAutoModeStatus('listening')
        setActiveAudioSource('system')
        setStatus(Date.now() < autoCooldownUntilRef.current ? 'Cooldown, still listening...' : 'Listening...')
        return
      }

      if (eventName === 'termination') {
        setAutoStreamingConnected(false)
        logAutoModeDebug('system assemblyai streaming session terminated', { runId })
        return
      }

      if (eventName === 'error') {
        const message = String(payload.message || 'System audio streaming failed.')
        if (
          autoStreamingClosingRef.current ||
          !autoModeRef.current ||
          /no close frame received or sent/i.test(message)
        ) {
          setStreamingError('')
          return
        }
        logAutoModeDebug('system assemblyai streaming error', { runId, message }, 'error')
        stopSystemStreaming(message)
      }
    }

    socket.onerror = () => {
      if (autoModeRunIdRef.current !== runId) {
        return
      }
      if (autoStreamingClosingRef.current || !autoModeRef.current) {
        return
      }
      logAutoModeDebug('system assemblyai streaming websocket error', { runId }, 'error')
      stopSystemStreaming('System audio streaming failed.')
    }

    socket.onclose = () => {
      if (autoModeRunIdRef.current !== runId || autoStreamingClosingRef.current || !autoModeRef.current) {
        return
      }
      setAutoStreamingConnected(false)
      logAutoModeDebug('system assemblyai streaming websocket closed', { runId })
    }
  }

  const runAutoModeCycle = async (runId, sourceMode) => {
    if (!autoModeRef.current || autoModeRunIdRef.current !== runId) {
      return
    }

    setAutoRejectedReason('')
    if (Date.now() >= autoCooldownUntilRef.current) {
      setCooldownRemainingMs(0)
      setIsCooldownListening(false)
    }
    setAutoModeStatus(Date.now() < autoCooldownUntilRef.current ? 'cooldown' : 'listening')
    setAudioPipelineStatus('idle')
    setActiveAudioSource('none')
    setStatus(Date.now() < autoCooldownUntilRef.current ? 'Cooldown, still listening...' : 'Listening...')

    try {
      setAutoProcessing(true)
      let captureResult = null
      const pipelineStarted = performance.now()

      logAutoModeDebug('auto cycle starting', {
        runId,
        source: sourceMode,
        status: autoModeStatus || 'off',
      })

      if (sourceMode === 'microphone') {
        if (!streamRef.current) {
          throw new Error('Could not access the microphone. Please check microphone permissions and try again.')
        }
        const blob = await recordAutoSegment(streamRef.current, runId)
        if (autoModeRunIdRef.current !== runId) {
          logAutoModeDebug('mic chunk ignored after stale run id', { runId })
          return
        }
        setRecording(false)
        setRecordingStartedAt(null)
        setAudioPipelineStatus('transcribing')
        setAutoModeStatus('transcribing')
        logAutoModeDebug('sending chunk to /transcribe', {
          runId,
          size: blob.size,
          mode: 'auto_fallback',
        })
        captureResult = await transcribeAudioBlob(blob, 'auto_fallback')
        captureResult = {
          ...captureResult,
          recordingMs: AUTO_MIC_CHUNK_MS,
        }
      } else if (sourceMode === 'system') {
        captureResult = await captureSystemAutoChunk(runId)
      } else {
        throw new Error(`Auto Mode source is invalid: ${sourceMode || 'none'}`)
      }

      if (!captureResult || autoModeRunIdRef.current !== runId) {
        logAutoModeDebug('auto capture result unavailable', { runId, source: sourceMode })
        return
      }

      const text = String(captureResult.text || '').trim()
      if (captureResult.sttProvider) {
        setSttProvider(captureResult.sttProvider)
      }
      setSttFallbackUsed(Boolean(captureResult.fallbackUsed))
      setSttFallbackReason(String(captureResult.fallbackReason || '').trim())
      logAutoModeDebug('transcript received', {
        runId,
        source: sourceMode,
        text: text || '(empty)',
        no_speech: captureResult.noSpeech ? 'true' : 'false',
      })
      setLastAutoTranscript(text)
      const combinedTranscript = pushAutoTranscriptBuffer(text)

      if (captureResult.noSpeech || !text) {
        logAutoModeDebug('auto chunk rejected', {
          runId,
          reason: captureResult.reason || 'silence_or_no_speech',
        })
        setAutoRejectedReason(captureResult.reason || 'silence_or_no_speech')
        setAudioPipelineStatus('idle')
        setActiveAudioSource('none')
        setAutoModeStatus(Date.now() < autoCooldownUntilRef.current ? 'cooldown' : 'listening')
        setStatus(Date.now() < autoCooldownUntilRef.current ? 'Cooldown, still listening...' : 'Listening...')
        await flushPendingAutoQuestion(runId, sourceMode)
        return
      }

      const fillerReason = getAutoRejectReason(combinedTranscript || text)
      if (fillerReason) {
        logAutoModeDebug('auto chunk rejected', { runId, reason: fillerReason })
        setAutoRejectedReason(fillerReason)
        setAudioPipelineStatus('idle')
        setActiveAudioSource('none')
        setAutoModeStatus(Date.now() < autoCooldownUntilRef.current ? 'cooldown' : 'listening')
        setStatus(Date.now() < autoCooldownUntilRef.current ? 'Cooldown, still listening...' : 'Listening...')
        await flushPendingAutoQuestion(runId, sourceMode)
        return
      }

      setAutoModeStatus('detecting')
      const detectionInput = text || combinedTranscript
      const detectionResult = await detectCorrectedAutoQuestion(detectionInput)
      if (autoModeRunIdRef.current !== runId) {
        logAutoModeDebug('question detection ignored after stale run id', { runId })
        return
      }
      const {
        finalDetection,
        candidateText,
        polishedCandidate,
        correctedCandidate,
        correctionSummary,
        possibleSttError: detectedPossibleSttError,
      } = detectionResult
      const finalDetectionInput = String(
        finalDetection.normalized_question || correctedCandidate || polishedCandidate || candidateText || detectionInput
      ).trim()
      setExtractedQuestionCandidate(candidateText)
      setPolishedQuestionCandidate(polishedCandidate)
      setCorrectedQuestionCandidate(correctedCandidate)
      setTechnicalCorrectionsSummary(correctionSummary)
      setPossibleSttError(Boolean(detectedPossibleSttError))
      setQuestionCandidateSource(String(finalDetection.candidate_source || 'none'))
      setQuestionDetectionInput(finalDetectionInput)
      setQuestionDetectReason(String(finalDetection.reason || ''))
      setIsQuestionDetected(Boolean(finalDetection.is_question))
      const normalizedQuestion = normalizeTranscriptForDedup(
        finalDetection.normalized_question || finalDetection.normalized_text || finalDetectionInput
      )
      const skipReason = shouldSkipRecentTranscript(normalizedQuestion)

      setPipelineTimings((current) => ({
        ...current,
        question_detect_ms: finalDetection.questionDetectMs,
      }))

      if (!finalDetection.is_question) {
        logAutoModeDebug('auto chunk rejected', {
          runId,
          reason: finalDetection.reason || 'not_a_question',
        })
        setAutoRejectedReason(finalDetection.reason || 'not_a_question')
        setAudioPipelineStatus('idle')
        setActiveAudioSource('none')
        setAutoModeStatus(Date.now() < autoCooldownUntilRef.current ? 'cooldown' : 'listening')
        setStatus(Date.now() < autoCooldownUntilRef.current ? 'Cooldown, still listening...' : 'Listening...')
        await flushPendingAutoQuestion(runId, sourceMode)
        return
      }

      if (skipReason) {
        logAutoModeDebug('auto chunk rejected', { runId, reason: skipReason })
        setAutoRejectedReason(skipReason)
        setAudioPipelineStatus('idle')
        setActiveAudioSource('none')
        setAutoModeStatus(Date.now() < autoCooldownUntilRef.current ? 'cooldown' : 'listening')
        setStatus(Date.now() < autoCooldownUntilRef.current ? 'Cooldown, still listening...' : 'Listening...')
        await flushPendingAutoQuestion(runId, sourceMode)
        return
      }

      const questionText = String(finalDetectionInput || text).trim()
      const acceptedQuestion = questionText
      setAutoRejectedReason('')
      setError('')
      setAcceptedAutoQuestion(acceptedQuestion)
      setLastDetectedQuestion(acceptedQuestion)
      const questionRunId = createAutoQuestionRunId(runId)
      const autoQuestionPayload = {
        text: acceptedQuestion,
        displayQuestion: acceptedQuestion,
        normalizedQuestion,
        recordingMs: captureResult.recordingMs ?? null,
        uploadMs: captureResult.uploadMs ?? null,
        transcriptionMs: captureResult.transcriptionMs ?? null,
        questionDetectMs: finalDetection.questionDetectMs,
        pipelineStarted: performance.now(),
        questionRunId,
      }
      if (autoGenerationInFlightRef.current) {
        setGenerationBlockedReason('generation_in_progress')
        queuePendingAutoQuestion(autoQuestionPayload, 'generation_in_progress')
        return
      }

      if (Date.now() < autoCooldownUntilRef.current) {
        setGenerationBlockedReason('cooldown_active')
        queuePendingAutoQuestion(autoQuestionPayload, 'cooldown_active')
        return
      }

      setGenerationBlockedReason('')
      logAutoModeDebug('question accepted', {
        autoQuestionRunId: questionRunId,
        question: acceptedQuestion,
        source: sourceMode,
      })
      setAutoModeStatus('question_detected')
      setStatus('Question detected')
      await processAutoQuestion(runId, sourceMode, autoQuestionPayload)
      await flushPendingAutoQuestion(runId, sourceMode)
    } catch (err) {
      if (autoModeRunIdRef.current !== runId) {
        return
      }
      console.error('Auto Mode pipeline error', err)
      logAutoModeDebug(
        'auto cycle failed',
        { runId, source: sourceMode, error: err?.message || 'unknown_error' },
        'error'
      )
      clearProgressiveAnswer()
      resetAnswerMeta()
      setAutoModeStatus('error')
      setAudioPipelineStatus('idle')
      setActiveAudioSource('none')
      setError(normalizePipelineError(err, 'Auto Mode could not process the latest segment.'))
      setStatus('Auto Mode stopped.')
      autoModeRef.current = false
      setAutoMode(false)
    } finally {
      if (autoModeRunIdRef.current === runId) {
        setRecording(false)
        setAutoProcessing(false)
        setRecordingStartedAt(null)
        await flushPendingAutoQuestion(runId, sourceMode)
      }
    }
  }

  const scheduleNextAutoCycle = (runId, sourceMode, delayMs = AUTO_SEGMENT_GAP_MS) => {
    clearAutoLoop()
    if (!autoModeRef.current || autoModeRunIdRef.current !== runId) {
      return
    }
    autoLoopTimeoutRef.current = window.setTimeout(async () => {
      if (!autoModeRef.current || autoModeRunIdRef.current !== runId) {
        return
      }
      await runAutoModeCycle(runId, sourceMode)
      if (!autoModeRef.current || autoModeRunIdRef.current !== runId) {
        return
      }
      const remainingCooldown = Math.max(0, autoCooldownUntilRef.current - Date.now())
      scheduleNextAutoCycle(
        runId,
        sourceMode,
        remainingCooldown > 0 ? Math.min(remainingCooldown, 800) : AUTO_SEGMENT_GAP_MS
      )
    }, delayMs)
  }

  const startAutoMode = async () => {
    const sourceMode = getSelectedAudioSourceLabel(audioSourcesRef.current)
    setAutoStartClicked(true)
    logAutoModeDebug('auto start clicked', {
      selected_audio_sources: sourceMode,
      microphone: audioSourcesRef.current.microphone ? 'true' : 'false',
      system: audioSourcesRef.current.system ? 'true' : 'false',
      chosen_source: sourceMode,
      auto_mode_status: autoModeStatus || 'off',
    })
    if (sourceMode === 'none') {
      setError('')
      setStatus('Select microphone or system audio before starting Auto Mode.')
      logAutoModeDebug('auto start blocked', { reason: 'no_source_selected' }, 'error')
      return
    }
    if (sourceMode === 'both') {
      setError('')
      setStatus('Both-source Auto Mode is not implemented yet. Select microphone or system audio only.')
      logAutoModeDebug('auto start blocked', { reason: 'both_source_not_supported' }, 'error')
      return
    }

    setError('')
    clearProgressiveAnswer()
    resetAnswerMeta()
    setTranscript('')
    setAutoRejectedReason('')
    setLastAutoTranscript('')
    setRawFinalTranscript('')
    setLastDetectedQuestion('')
    setAcceptedAutoQuestion('')
    setDisplayedAutoQuestionRunId('')
    setCurrentAutoQuestionRunId('')
    setMicStreamingState(sourceMode === 'microphone' ? 'connecting' : 'off')
    setAnswerPipelineState('idle')
    setMicStreamRestartCount(0)
    setLastMicStreamRestartReason('')
    setCooldownRemainingMs(0)
    resetAutoTranscriptBuffer()
    clearPendingAutoQuestion()
    clearPendingCooldownQuestion()
    setIsCooldownListening(false)
    setQueuedQuestionProcessed(false)
    setGenerationStarted(false)
    setGenerationBlockedReason('')
    setExtractedQuestionCandidate('')
    setPolishedQuestionCandidate('')
    setCorrectedQuestionCandidate('')
    setTechnicalCorrectionsSummary('')
    setPossibleSttError(false)
    setQuestionCandidateSource('')
    setQuestionDetectionInput('')
    setQuestionDetectReason('')
    setIsQuestionDetected(false)
    lastCheckedAutoCandidateRef.current = ''
    setSystemAudioRmsLevel(null)
    setSystemAudioPeakLevel(null)
    setSystemAudioChunkBytesSent(0)
    setSystemAudioDroppedSilenceChunks(0)
    setSystemAudioClippingDetected(false)
    setSystemAudioQualityWarning('')
    setSystemAudioDebugWavPath('')
    setSystemAudioInputSampleRate(null)
    setSystemAudioEffectiveGain(null)
    setSttProvider('')
    setSttFallbackUsed(false)
    setSttFallbackReason('')
    setAutoStreamingConnected(false)
    setPartialAutoTranscript('')
    setStreamingError('')
    setSystemAudioSampleRate(null)
    assemblyAiFallbackWarningShownRef.current = false
    setAutoModeSource(sourceMode)
    autoModeSourceRef.current = sourceMode
    setAutoModeStatus('listening')
    setStatus(sourceMode === 'microphone' ? 'Preparing microphone...' : 'Preparing system audio...')

    try {
      if (sourceMode === 'microphone') {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        manualRecordingCancelledRef.current = false
        streamRef.current = stream
      } else {
        const capability = await fetchSystemAudioDevices()
        if (!capability.supported) {
          throw new Error('System audio capture is not available yet. Use microphone or configure system audio capture.')
        }
      }
      const runId = `${Date.now()}-${Math.random().toString(16).slice(2)}`
      autoModeRef.current = true
      autoModeRunIdRef.current = runId
      clearCurrentAutoQuestionRun()
      autoCooldownUntilRef.current = 0
      recentProcessedTranscriptsRef.current = []
      autoGenerationInFlightRef.current = false
      setAutoMode(true)
      setAutoProcessing(false)
      setStatus('Listening...')
      if (sourceMode === 'microphone') {
        await startAutoStreamingMic(runId, streamRef.current)
      } else {
        await startAutoStreamingSystem(runId)
      }
    } catch (err) {
      console.error('Auto Mode start error', err)
      logAutoModeDebug(
        'auto start failed',
        { source: sourceMode, error: err?.message || 'unknown_error' },
        'error'
      )
      autoModeRef.current = false
      autoModeRunIdRef.current = ''
      setAutoMode(false)
      setAutoModeStatus('error')
      setAudioPipelineStatus('idle')
      setActiveAudioSource('none')
      setError(normalizePipelineError(err, 'Could not start Auto Mode.'))
      setStatus(sourceMode === 'microphone' ? 'Microphone unavailable.' : 'System audio unavailable.')
    }
  }

  const stopAutoMode = () => {
    logAutoModeDebug('auto mode stopping', {
      runId: autoModeRunIdRef.current || 'none',
      source: autoModeSourceRef.current || 'none',
    })
    autoModeRef.current = false
    autoModeRunIdRef.current = ''
    clearCurrentAutoQuestionRun()
    setAutoMode(false)
    setAutoProcessing(false)
    setManualProcessing(false)
    autoGenerationInFlightRef.current = false
    stopAutoStreamingBridge()
    setAutoModeStatus('off')
    setAutoModeSource('none')
    autoModeSourceRef.current = 'none'
    setCooldownRemainingMs(0)
    setIsCooldownListening(false)
    setAcceptedAutoQuestion('')
    clearPendingAutoQuestion()
    clearPendingCooldownQuestion()
    setQueuedQuestionProcessed(false)
    setGenerationStarted(false)
    setGenerationBlockedReason('')
    resetAutoTranscriptBuffer()
    setRawFinalTranscript('')
    setDisplayedAutoQuestionRunId('')
    setExtractedQuestionCandidate('')
    setPolishedQuestionCandidate('')
    setCorrectedQuestionCandidate('')
    setTechnicalCorrectionsSummary('')
    setPossibleSttError(false)
    setQuestionCandidateSource('')
    setQuestionDetectionInput('')
    setQuestionDetectReason('')
    setIsQuestionDetected(false)
    lastCheckedAutoCandidateRef.current = ''
    setStreamingError('')
    setSystemAudioSampleRate(null)
    setSystemAudioRmsLevel(null)
    setSystemAudioPeakLevel(null)
    setSystemAudioChunkBytesSent(0)
    setSystemAudioDroppedSilenceChunks(0)
    setSystemAudioClippingDetected(false)
    setSystemAudioQualityWarning('')
    setSystemAudioDebugWavPath('')
    clearAutoLoop()

    if (mediaRecorderRef.current?.state && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    } else {
      stopActiveStream()
    }

    setRecording(false)
    setRecordingStartedAt(null)
    setAudioPipelineStatus('idle')
    setActiveAudioSource('none')
    setMicStreamingState('off')
    setAnswerPipelineState('idle')
    setStatus('Auto Mode stopped.')
  }

  const stopActiveOperation = () => {
    latestGenerationRequestIdRef.current = createScreenOpaqueId('stopped_request')
    activeGenerateAbortControllerRef.current?.abort()
    activeGenerateAbortControllerRef.current = null
    if (activeScreenOperationRef.current?.isCurrent) {
      activeScreenOperationRef.current = cancelScreenOperation(activeScreenOperationRef.current)
      setScreenOperation(activeScreenOperationRef.current)
    }

    if (autoModeRef.current || autoMode) {
      stopAutoMode()
    } else if (mediaRecorderRef.current?.state && mediaRecorderRef.current.state !== 'inactive') {
      manualRecordingCancelledRef.current = true
      mediaRecorderRef.current.stop()
    } else {
      stopActiveStream()
    }

    if (generatingWatchdogTimeoutRef.current) {
      clearTimeout(generatingWatchdogTimeoutRef.current)
      generatingWatchdogTimeoutRef.current = null
    }
    if (answerReadyResetTimeoutRef.current) {
      clearTimeout(answerReadyResetTimeoutRef.current)
      answerReadyResetTimeoutRef.current = null
    }
    if (refinementPollTimeoutRef.current) {
      clearTimeout(refinementPollTimeoutRef.current)
      refinementPollTimeoutRef.current = null
    }

    setManualProcessing(false)
    setIsManualGenerating(false)
    setAutoProcessing(false)
    setRecording(false)
    setRecordingStartedAt(null)
    setAudioPipelineStatus('idle')
    setActiveAudioSource('none')
    setAnswerPipelineState('idle')
    setAnswerRevealActive(false)
    setScreenAnswerLoading(false)
    setOcrProcessing(false)
    setStatus('Stopped.')
  }

  const resetRuntimeForDesktopLogout = () => {
    stopSystemAudioRecordingForLogout()
    stopActiveOperation()
    clearTranscriptState()
    clearAnswerState()
    resetAutoInterviewState()
    resetScreenOcrState()
    setQuestionHistoryState(() => createQuestionHistoryState())
    setQuestionHistoryNavigationCount(0)
    setEventLog([])
    applyStartupSessionConfig(null)
    profileCacheRef.current = null
    profileFetchMsRef.current = null
    setStatus('Signed out. Log in to start a new desktop session.')
  }

  const applyRefinedAnswer = () => {
    if (refinementStatus !== 'completed' || !refinedAnswer) {
      return
    }

    setFullAnswerState(refinedAnswer)
    setAnswer(refinedAnswer)
    setAnswerRevealActive(false)
    setDisplayedAnswerSource('groq refined')
    setRefinementMessage('Groq refined answer applied to overlay.')
  }

  const requestActiveWindowAnalysis = async ({
    blob,
    windowTitle = '',
    processName = '',
    captureMs = 0,
    hidSaiiaWindows = false,
  }) => {
    const form = new FormData()
    form.append('file', blob, 'active-window.png')
    form.append('window_title', windowTitle)
    form.append('process_name', processName)
    form.append('capture_ms', String(captureMs || 0))
    form.append('hid_saiia_windows', hidSaiiaWindows ? 'true' : 'false')

    setStatus('Extracting question...')
    const response = await fetch(`${BACKEND_URL}/api/screen/analyze-active-window`, {
      method: 'POST',
      body: form,
    })
    return parseJsonResponse(
      response,
      'Screen analysis failed. Please try again.'
    )
  }

  const requestActiveWindowAnswer = async ({
    blob,
    windowTitle = '',
    processName = '',
    captureMs = 0,
    hidSaiiaWindows = false,
    operation = null,
  }) => {
    const form = new FormData()
    form.append('file', blob, 'active-window.png')
    form.append('window_title', windowTitle)
    form.append('process_name', processName)
    form.append('capture_ms', String(captureMs || 0))
    form.append('hid_saiia_windows', hidSaiiaWindows ? 'true' : 'false')
    if (operation) {
      form.append('operation_id', operation.operationId)
      form.append('request_id', operation.requestId)
      form.append('source_type', operation.sourceType)
    }

    setStatus('Analyzing question...')
    const uploadStarted = performance.now()
    const response = await fetch(`${BACKEND_URL}/api/screen/analyze-active-window-answer`, {
      method: 'POST',
      body: form,
    })
    const uploadMs = Number((performance.now() - uploadStarted).toFixed(2))
    const parseStarted = performance.now()
    const payload = await parseJsonResponse(
      response,
      SCREEN_OCR_UNREADABLE_MESSAGE
    )
    return {
      ...payload,
      upload_ms: payload.upload_ms ?? uploadMs,
      frontend_response_parse_ms: Number((performance.now() - parseStarted).toFixed(2)),
    }
  }

  const requestExtensionUnavailable = async (operation) => {
    const form = new FormData()
    form.append('operation_id', operation.operationId)
    form.append('request_id', operation.requestId)
    const response = await fetch(`${BACKEND_URL}/api/screen/extension-unavailable`, {
      method: 'POST',
      body: form,
    })
    return parseJsonResponse(response, 'Browser extension connection is not available yet.')
  }

  const applyScreenAnalysisPayload = (payload, overrides = {}) => {
    const mergedPayload = { ...payload, ...overrides }
    const contextPayload = buildScreenProblemContext(
      mergedPayload,
      mergedPayload.final_extracted_question || mergedPayload.extracted_question || ''
    )
    setScreenVisionProvider(mergedPayload.vision_provider || '')
    setScreenVisionModel(mergedPayload.vision_model || '')
    setScreenCaptureTarget(mergedPayload.capture_target || 'active_window')
    setScreenWindowTitle(mergedPayload.window_title || '')
    setScreenProcessName(mergedPayload.process_name || '')
    setScreenImageWidth(Number(mergedPayload.image_width || 0))
    setScreenImageHeight(Number(mergedPayload.image_height || 0))
    setRawScreenVisionText(mergedPayload.raw_vision_text || '')
    setRawScreenVisionJson(mergedPayload.raw_vision_json || '')
    setScreenCleanedText(mergedPayload.cleaned_text || '')
    setExtractedScreenQuestion(mergedPayload.extracted_question || '')
    setScreenQuestionType(mergedPayload.question_type || 'none')
    setScreenConfidence(Number(mergedPayload.confidence || 0))
    setScreenCaptureMs(Number(mergedPayload.capture_ms || 0))
    setScreenVisionMs(Number(mergedPayload.vision_ms || 0))
    setScreenFallbackOcrUsed(Boolean(mergedPayload.fallback_ocr_used))
    setScreenScreenshotHidSaiiaWindows(Boolean(mergedPayload.screenshot_hid_saiia_windows))
    setScreenDebugPath(mergedPayload.screenshot_debug_path || '')
    setScreenPlatformDetected(mergedPayload.screen_platform_detected || 'unknown')
    setScreenCropUsed(Boolean(mergedPayload.crop_used))
    setScreenCropRegion(mergedPayload.crop_region || '')
    setScreenSourceRegion(mergedPayload.source_region || 'unknown')
    setScreenExtractionRetryReason(mergedPayload.extraction_retry_reason || '')
    setScreenRejectedUiNoise(Boolean(mergedPayload.rejected_ui_noise))
    setScreenRejectedCodeBoilerplate(Boolean(mergedPayload.rejected_code_boilerplate))
    setScreenUiNoiseRatio(Number(mergedPayload.ui_noise_ratio || 0))
    setScreenRejectReason(mergedPayload.reason || '')
    setRawFullWindowVisionJson(mergedPayload.raw_full_window_vision_json || '')
    setRawCroppedVisionJson(mergedPayload.raw_cropped_vision_json || '')
    setFinalExtractedScreenQuestion(mergedPayload.final_extracted_question || mergedPayload.extracted_question || '')
    setScreenValidProblemFound(Boolean(mergedPayload.valid_problem_found))
    setGroqVisionAttempted(Boolean(mergedPayload.groq_vision_attempted))
    setGroqVisionSuccess(Boolean(mergedPayload.groq_vision_success))
    setGroqVisionError(mergedPayload.groq_vision_error || '')
    setGroqVisionHttpStatus(
      mergedPayload.groq_vision_http_status == null ? null : Number(mergedPayload.groq_vision_http_status)
    )
    setGroqVisionRawResponsePreview(mergedPayload.groq_vision_raw_response_preview || '')
    setGroqVisionParseError(mergedPayload.groq_vision_parse_error || '')
    setGroqVisionTimeout(Boolean(mergedPayload.groq_vision_timeout))
    setScreenFallbackReason(mergedPayload.fallback_reason || '')
    setScreenAnswerGenerated(false)
    setScreenError(mergedPayload.error || '')
    setOcrConfidence(mergedPayload.confidence ?? null)
    setScreenAnalyzeMode(mergedPayload.analyze_mode || 'visible_window')
    setScreenNeedsMoreContent(Boolean(mergedPayload.needs_more_screen_content))
    setScreenFullCaptureEnabled(Boolean(mergedPayload.full_capture_enabled))
    setScreenFullProblemCaptureUsed(Boolean(mergedPayload.full_problem_capture_used))
    setScreenCaptureCount(Number(mergedPayload.capture_count || 1))
    setScreenScrollPositions(mergedPayload.scroll_positions || '')
    setScreenDuplicateCaptureStopped(Boolean(mergedPayload.duplicate_capture_stopped))
    setScreenBottomReached(Boolean(mergedPayload.bottom_reached))
    setScreenRestoredScrollPosition(Boolean(mergedPayload.restored_scroll_position))
    setScreenDiagramDetected(Boolean(mergedPayload.diagram_detected))
    setScreenChartDetected(Boolean(mergedPayload.chart_detected))
    setFinalMergedProblem(mergedPayload.final_merged_problem || '')
    setScreenFullProblemText(contextPayload.fullProblemText || '')
    setScreenEditorText(contextPayload.editorText || '')
    setScreenForceTechnical(isScreenTechnicalType(mergedPayload.question_type || 'none'))
    setScreenCodingAnswerMode(String(mergedPayload.question_type || '').trim().toLowerCase() === 'coding')
    setScreenProfileContextUsed(!shouldSuppressScreenProfileContext(mergedPayload.question_type || 'none'))
    setScreenPanelMode('preview')
    setScreenAnswerLoading(false)

    const finalQuestion = String(mergedPayload.final_extracted_question || mergedPayload.extracted_question || '').trim()

    if (!mergedPayload.is_question || !finalQuestion) {
      setOcrText(finalQuestion)
      setError('')
      setLastError(mergedPayload.error || 'Screen text found, but no clear question/problem detected.')
      appendEventLog(mergedPayload.error || 'Screen text found, but no clear question/problem detected.', 'error')
      setStatus('Screen text found, but no clear question/problem detected.')
      return {
        ok: false,
        payload: mergedPayload,
        fullProblemText: contextPayload.fullProblemText,
        editorText: contextPayload.editorText,
        inputFormat: contextPayload.inputFormat,
        outputFormat: contextPayload.outputFormat,
        sampleInput: contextPayload.sampleInput,
        sampleOutput: contextPayload.sampleOutput,
        problemTitle: contextPayload.problemTitle,
        screenPlatformDetected: contextPayload.screenPlatformDetected,
      }
    }

    const questionText = finalQuestion
    setLastError('')
    setOcrText(questionText)
    setTranscript(questionText)
    setStatus('Screen question detected.')
    return {
      ok: true,
      payload: mergedPayload,
      questionText,
      questionType: mergedPayload.question_type || 'none',
      fullProblemText: contextPayload.fullProblemText,
      editorText: contextPayload.editorText,
      inputFormat: contextPayload.inputFormat,
      outputFormat: contextPayload.outputFormat,
      sampleInput: contextPayload.sampleInput,
      sampleOutput: contextPayload.sampleOutput,
      problemTitle: contextPayload.problemTitle,
      screenPlatformDetected: contextPayload.screenPlatformDetected,
    }
  }

  const analyzeActiveWindowBlob = async ({
    blob,
    windowTitle = '',
    processName = '',
    captureMs = 0,
    hidSaiiaWindows = false,
    commitState = true,
    overrides = {},
  }) => {
    const payload = await requestActiveWindowAnalysis({
      blob,
      windowTitle,
      processName,
      captureMs,
      hidSaiiaWindows,
    })

    if (!commitState) {
      const mergedPayload = { ...payload, ...overrides }
      const contextPayload = buildScreenProblemContext(
        mergedPayload,
        mergedPayload.final_extracted_question || mergedPayload.extracted_question || ''
      )
      const finalQuestion = String(mergedPayload.final_extracted_question || mergedPayload.extracted_question || '').trim()
      return {
        ok: Boolean(mergedPayload.is_question && finalQuestion),
        payload: mergedPayload,
        questionText: finalQuestion,
        questionType: mergedPayload.question_type || 'none',
        fullProblemText: contextPayload.fullProblemText,
        editorText: contextPayload.editorText,
        inputFormat: contextPayload.inputFormat,
        outputFormat: contextPayload.outputFormat,
        sampleInput: contextPayload.sampleInput,
        sampleOutput: contextPayload.sampleOutput,
        problemTitle: contextPayload.problemTitle,
        screenPlatformDetected: contextPayload.screenPlatformDetected,
      }
    }

    return applyScreenAnalysisPayload(payload, overrides)
  }

  const commitDirectScreenAnswer = (payload, { operation, pipelineStarted }) => {
    if (!isCurrentScreenOperation(activeScreenOperationRef.current, operation)) {
      return
    }

    const questionText = String(payload.question || '').trim()
    const generatedAnswer = String(payload.answer || '').trim()
    if (!payload.ok || !questionText || !generatedAnswer) {
      throw new Error(payload.error || SCREEN_OCR_UNREADABLE_MESSAGE)
    }

    const questionType = String(payload.question_type || 'none').trim().toLowerCase()
    const resultMode = String(payload.result_mode || 'single').trim().toLowerCase() === 'batch' ? 'batch' : 'single'
    const normalizedScreenResult = normalizeScreenResponse(payload)
    const screenEnvelope = normalizedScreenResult.envelope
    const responseOperationId = String(payload.operation_id || screenEnvelope.operation_id || '').trim()
    const responseRequestId = String(payload.request_id || screenEnvelope.request_id || '').trim()
    const responseSourceType = String(payload.source_type || screenEnvelope.source_type || '').trim()
    const responseStatus = String(screenEnvelope.status || '').trim()
    if (!canCommitScreenResult({
      responseOperationId,
      responseRequestId,
      responseSourceType,
      responseStatus,
      currentOperation: activeScreenOperationRef.current,
      committedOperationIds: committedScreenOperationIdsRef.current,
      hasUsableResult: Boolean(payload.ok && questionText && generatedAnswer),
    })) {
      return
    }
    markScreenOperationCommitted(operation.operationId)
    const screenAnswerItems = Array.isArray(payload.items) ? payload.items : []
    const questionCount = Number(payload.question_count || screenAnswerItems.length || 1)
    const incompleteQuestionCount = Number(payload.incomplete_question_count || 0)
    const extractedCode = extractCodeBlockFromAnswer(generatedAnswer)
    const payloadCode = String(payload.code || '').trim()
    const payloadLanguage = String(payload.language || '').trim().toLowerCase()
    const screenCode = payloadCode || extractedCode.code
    const screenCodeLanguage = payloadLanguage || extractedCode.language || (questionType === 'coding' ? 'python' : '')
    const answerReceivedMs = Number((performance.now() - pipelineStarted).toFixed(2))
    const screenModelMs = Number(payload.screen_model_ms || payload.vision_ms || payload.vision_latency_ms || 0)
    const generationMs = null
    const overlayRenderStarted = performance.now()
    const preCommitTotalMs = Number((performance.now() - pipelineStarted).toFixed(2))
    const nextCategory = isScreenTechnicalType(questionType) ? 'technical' : questionType === 'mcq' ? 'technical' : 'general'
    const historyEntryId = `qh-${Date.now()}-${Math.random().toString(16).slice(2)}`
    const nextPipelineTimings = {
      ...createEmptyPipelineTimings(),
      capture_ms: Number(payload.capture_ms || 0),
      image_prepare_ms: Number(payload.image_prepare_ms || 0),
      upload_ms: Number(payload.upload_ms || 0),
      screen_model_ms: screenModelMs,
      response_parse_ms: Number(payload.response_parse_ms || 0),
      frontend_response_parse_ms: Number(payload.frontend_response_parse_ms || 0),
      vision_ms: Number(payload.vision_ms || 0),
      primary_generation_ms: null,
      generation_ms: null,
      answer_received_ms: answerReceivedMs,
      overlay_commit_ms: 0,
      provider: payload.vision_provider || '',
      primary_provider: payload.vision_provider || '',
      primary_model: payload.vision_model || '',
      model: payload.vision_model || '',
      profile_context_policy: 'FORBIDDEN',
      profile_context_used: false,
      retrieved_chunk_count: 0,
      original_image_width: Number(payload.original_image_width || 0),
      original_image_height: Number(payload.original_image_height || 0),
      sent_image_width: Number(payload.image_width || 0),
      sent_image_height: Number(payload.image_height || 0),
      encoded_image_bytes: Number(payload.encoded_image_bytes || 0),
      screen_capture_count: Number(payload.screenshot_count || 1),
      screen_model_request_count: Number(payload.screen_model_request_count || 1),
      screen_extraction_request_count: Number(payload.extraction_request_count || 1),
      screen_generation_request_count: Number(payload.generation_request_count || 0),
      questions_answered: questionCount,
      incomplete_questions_ignored: incompleteQuestionCount,
      automatic_fallback_count: Number(payload.automatic_fallback_count || 0),
      correction_request_count: Number(payload.correction_request_count || 0),
    }

    setQuestionHistoryState((current) =>
      appendQuestionHistoryEntry(
        current,
        createQuestionHistoryEntry({
          id: historyEntryId,
          mode: 'screen',
          requestId: operation.requestId,
          question: questionText,
          originalQuestion: questionText,
          fullAnswer: generatedAnswer,
          displayedAnswer: generatedAnswer,
          status: 'complete',
          category: nextCategory,
          provider: payload.vision_provider || '',
          primaryProvider: payload.vision_provider || '',
          primaryModel: payload.vision_model || '',
          generationMs,
          totalPipelineMs: preCommitTotalMs,
          completedAt: new Date().toISOString(),
          metadata: {
            source: 'screen',
            operationId: operation.operationId,
            requestId: operation.requestId,
            screenQuestionType: questionType,
            resultMode,
            screenAnswerItems,
            screenEnvelope,
            sourceType: screenEnvelope.source_type,
            questionCount,
            incompleteQuestionCount,
            fullProblemText: questionText,
            editorText: '',
            pipelineTimings: nextPipelineTimings,
            answerType: questionType,
            screenCodeAnswer: screenCode,
            screenCodeLanguage,
          },
        })
      )
    )
    setQuestionHistoryNavigationCount((count) => count + 1)

    setAnswerDisplayMode('screen')
    setTranscript(questionText)
    setOcrText(questionText)
    setFinalExtractedScreenQuestion(questionText)
    setExtractedScreenQuestion(questionText)
    setScreenCleanedText(questionText)
    setScreenQuestionType(questionType)
    setScreenConfidence(Number(payload.confidence || 0))
    setOcrConfidence(payload.confidence ?? null)
    setScreenVisionProvider(payload.vision_provider || '')
    setScreenVisionModel(payload.vision_model || '')
    setScreenCaptureTarget(payload.capture_target || 'active_external_window')
    setScreenWindowTitle(payload.window_title || '')
    setScreenProcessName(payload.process_name || '')
    setScreenImageWidth(Number(payload.image_width || 0))
    setScreenImageHeight(Number(payload.image_height || 0))
    setScreenCaptureMs(Number(payload.capture_ms || 0))
    setScreenVisionMs(Number(payload.vision_ms || 0))
    setRawScreenVisionText(payload.raw_vision_text || '')
    setScreenFallbackOcrUsed(Boolean(payload.fallback_used))
    setScreenScreenshotHidSaiiaWindows(Boolean(payload.screenshot_hid_saiia_windows))
    setScreenCaptureCount(Number(payload.screenshot_count || 1))
    setScreenFullCaptureEnabled(false)
    setScreenFullProblemCaptureUsed(false)
    setScreenDuplicateCaptureStopped(false)
    setScreenBottomReached(false)
    setScreenRestoredScrollPosition(false)
    setScreenScrollPositions('')
    setScreenPlatformDetected('unknown')
    setScreenCropUsed(false)
    setScreenCropRegion('')
    setScreenSourceRegion('main_content')
    setScreenExtractionRetryReason('')
    setScreenRejectedUiNoise(false)
    setScreenRejectedCodeBoilerplate(false)
    setScreenUiNoiseRatio(0)
    setScreenRejectReason(payload.reason || '')
    setFinalMergedProblem(questionText)
    setScreenFullProblemText(questionText)
    setScreenEditorText('')
    setScreenValidProblemFound(true)
    setScreenNeedsMoreContent(false)
    setScreenDiagramDetected(questionType === 'architecture' || questionType === 'visual')
    setScreenChartDetected(questionType === 'visual')
    setGroqVisionAttempted(false)
    setGroqVisionSuccess(false)
    setGroqVisionError('')
    setGroqVisionHttpStatus(null)
    setGroqVisionRawResponsePreview('')
    setGroqVisionParseError('')
    setGroqVisionTimeout(false)
    setScreenFallbackReason('')
    setScreenForceTechnical(isScreenTechnicalType(questionType))
    setScreenCodingAnswerMode(questionType === 'coding')
    setScreenProfileContextUsed(false)
    setScreenAutoGenerate(false)
    setScreenAnswerText(generatedAnswer)
    setScreenCodeAnswer(screenCode)
    setScreenCodeLanguage(screenCodeLanguage)
    setScreenAnswerGenerated(true)
    setScreenAnswerDisplayedInPanel(true)
    setScreenAnswerCommittedToOverlay(true)
    setScreenAnswerLoading(false)
    setScreenPanelMode('answer')
    setScreenError('')

    setFullAnswerState(generatedAnswer)
    setAnswer(generatedAnswer)
    setCodingAnswer(null)
    setProvider(payload.vision_provider || '')
    setPrimaryProvider(payload.vision_provider || '')
    setPrimaryModel(payload.vision_model || '')
    setDisplayedAnswerSource(payload.vision_provider || 'screen')
    setCategory(nextCategory)
    setGenerationMs(generationMs)
    const overlayRenderMs = Number((performance.now() - overlayRenderStarted).toFixed(2))
    const totalMs = Number((performance.now() - pipelineStarted).toFixed(2))
    const finalPipelineTimings = {
      ...nextPipelineTimings,
      overlay_render_ms: overlayRenderMs,
      overlay_commit_ms: overlayRenderMs,
      frontend_update_ms: overlayRenderMs,
      total_screen_pipeline_ms: totalMs,
      total_pipeline_ms: totalMs,
    }
    setTotalPipelineMs(totalMs)
    setPipelineTimings(finalPipelineTimings)
    setStatus(questionCount > 1 ? 'Answers ready' : 'Answer ready')
    finishCurrentScreenOperation(operation)
  }

  const handleElectronScreenSourceCapture = async (sourceId) => {
    if (!window.saiia?.captureScreen) {
      throw new Error('Screen capture is not supported in this Electron session.')
    }

    const operation = beginScreenOperation('screen_capture')
    const pipelineStarted = performance.now()
    setError('')
    setOcrProcessing(true)
    setScreenError('')
    setStatus('Capturing selected window...')

    try {
      updateCurrentScreenOperation(operation, SCREEN_OPERATION_STATUS.CAPTURING)
      const payload = await window.saiia.captureScreen(sourceId)
      if (!payload?.imageDataUrl) {
        throw new Error('Could not capture screen.')
      }

      const blob = await dataUrlToBlob(payload.imageDataUrl)
      setScreenSources([])
      if (!isCurrentScreenOperation(activeScreenOperationRef.current, operation)) {
        return
      }
      updateCurrentScreenOperation(operation, SCREEN_OPERATION_STATUS.PROCESSING)
      const answerPayload = await requestActiveWindowAnswer({
        blob,
        windowTitle: payload.name || '',
        processName: '',
        captureMs: 0,
        hidSaiiaWindows: false,
        operation,
      })
      if (!isCurrentScreenOperation(activeScreenOperationRef.current, operation)) {
        return
      }
      commitDirectScreenAnswer(answerPayload, { operation, pipelineStarted })
    } catch (err) {
      console.error('Electron screen capture error', err)
      if (!isCurrentScreenOperation(activeScreenOperationRef.current, operation)) {
        return
      }
      const message = normalizePipelineError(err, SCREEN_OCR_UNREADABLE_MESSAGE)
      const safeMessage = /could not capture|active window|target question window|identified|unsupported|backend|available in this Electron/i.test(message)
        ? message
        : SCREEN_OCR_UNREADABLE_MESSAGE
      setError(safeMessage)
      setScreenError(safeMessage)
      setStatus('Screen analysis failed.')
      failCurrentScreenOperation(operation, safeMessage)
    } finally {
      if (activeScreenOperationRef.current?.operationId === operation.operationId) {
        setOcrProcessing(false)
      }
    }
  }

  const handleScreenCapture = async () => {
    if (recording || autoMode || autoProcessing || ocrProcessing) {
      return
    }

    const operation = beginScreenOperation('screen_capture')
    const pipelineStarted = performance.now()
    setError('')
    setOcrProcessing(true)
    setScreenError('')
    setStatus('Capturing active external window...')

    try {
      if (window.saiia?.captureActiveWindow) {
        updateCurrentScreenOperation(operation, SCREEN_OPERATION_STATUS.CAPTURING)
        const capturePayload = await window.saiia.captureActiveWindow()

        if (!capturePayload?.imageDataUrl) {
          throw new Error('Could not capture the active window.')
        }
        if (!isCurrentScreenOperation(activeScreenOperationRef.current, operation)) {
          return
        }

        setScreenSources([])
        const blob = await dataUrlToBlob(capturePayload.imageDataUrl)
        if (!isCurrentScreenOperation(activeScreenOperationRef.current, operation)) {
          return
        }
        updateCurrentScreenOperation(operation, SCREEN_OPERATION_STATUS.PROCESSING)
        const payload = await requestActiveWindowAnswer({
          blob,
          windowTitle: capturePayload.windowTitle || capturePayload.name || '',
          processName: capturePayload.processName || '',
          captureMs: capturePayload.captureMs || 0,
          hidSaiiaWindows: Boolean(capturePayload.hidSaiiaWindows),
          operation,
        })
        if (!isCurrentScreenOperation(activeScreenOperationRef.current, operation)) {
          return
        }
        commitDirectScreenAnswer(payload, { operation, pipelineStarted })
        return
      }

      throw new Error(
        'Active-window screen analysis is available in the Electron desktop app.'
      )
    } catch (err) {
      console.error('Screen analysis error', err)
      if (!isCurrentScreenOperation(activeScreenOperationRef.current, operation)) {
        return
      }
      const captureError = normalizeScreenCaptureError(err)
      const safeMessage = `${captureError.message} ${captureError.userAction}`
      setAnswerDisplayMode('screen')
      setScreenPanelMode('preview')
      setError(safeMessage)
      setScreenError(safeMessage)
      setStatus(captureError.retryable ? 'Needs attention' : 'Screen analysis failed.')
      failCurrentScreenOperation(operation, safeMessage)
      appendEventLog(
        'Could not identify active window. Waiting for retry.',
        'error'
      )
    } finally {
      if (activeScreenOperationRef.current?.operationId === operation.operationId) {
        setOcrProcessing(false)
      }
    }
  }

  const handleManualQuestionSubmit = async (nextText) => {
    const text = String(nextText || '').trim()
    if (!text) {
      setManualQuestionError('Please type a question first.')
      setError('')
      setStatus('Waiting for a typed question.')
      return
    }

    if (
      recording ||
      autoMode ||
      autoProcessing ||
      ocrProcessing ||
      manualProcessing ||
      isManualGenerating
    ) {
      return
    }

    setManualQuestionError('')
    setError('')
    setAnswerDisplayMode('chat')
    clearProgressiveAnswer()
    resetAnswerMeta()
    setTranscript(text)
    setIsManualGenerating(true)

    try {
      await classifyAndGenerate({
        text,
        displayQuestion: text,
        recordingMs: null,
        uploadMs: null,
        transcriptionMs: null,
        pipelineStarted: performance.now(),
        mode: 'chat',
        source: 'chat',
      })
    } catch (err) {
      console.error('Manual chat generation error', err)
      const message = normalizePipelineError(err, 'Could not generate an answer right now.')
      clearProgressiveAnswer()
      resetAnswerMeta()
      setManualQuestionError(message)
      setError(message)
      setStatus('Request failed.')
    } finally {
      setIsManualGenerating(false)
    }
  }

  const handleGenerateFromProvidedScreenText = async (nextText, options = {}) => {
    const text = String(nextText || '').trim()
    if (!text) {
      setError('')
      setScreenAnswerGenerated(false)
      setStatus('No readable question found on screen.')
      return
    }

    const questionType = String(options.questionType || screenQuestionType || 'none').trim().toLowerCase()
    const fullProblemText = String(options.fullProblemText || screenFullProblemText || text).trim()
    const editorText = String(options.editorText || screenEditorText || '').trim()
    const inputFormat = String(options.inputFormat || '').trim()
    const outputFormat = String(options.outputFormat || '').trim()
    const sampleInput = String(options.sampleInput || '').trim()
    const sampleOutput = String(options.sampleOutput || '').trim()
    const problemTitle = String(options.problemTitle || '').trim()
    const screenPlatformForGenerate = String(options.screenPlatformDetected || screenPlatformDetected || '').trim()
    const forceTechnical = isScreenTechnicalType(questionType)
    const suppressProfileContext = shouldSuppressScreenProfileContext(questionType)
    const keepAnswerMode = options.keepAnswerMode === true || screenPanelMode === 'answer'
    const hasPreviousScreenResult = Boolean(
      screenAnswerGenerated ||
      screenAnswerCommittedToOverlay ||
      String(screenAnswerText || '').trim()
    )

    setError('')
    setScreenError('')
    setAnswerDisplayMode('screen')
    clearProgressiveAnswer()
    resetAnswerMeta()
    setManualQuestionError('')
    setTranscript(text)
    setScreenAnswerGenerated(false)
    setScreenForceTechnical(forceTechnical)
    setScreenCodingAnswerMode(questionType === 'coding')
    setScreenProfileContextUsed(!suppressProfileContext)
    setScreenAutoGenerate(Boolean(options.autoGenerate))
    if (!hasPreviousScreenResult) {
      setScreenAnswerText('')
      setScreenCodeAnswer('')
      setScreenCodeLanguage('')
      setScreenAnswerDisplayedInPanel(false)
    }
    setScreenAnswerCommittedToOverlay(false)
    setScreenAnswerLoading(true)
    setScreenPanelMode(hasPreviousScreenResult || keepAnswerMode ? 'answer' : 'preview')

    try {
      const result = await classifyAndGenerate({
        text,
        displayQuestion: text,
        fullProblemText,
        editorText,
        inputFormat,
        outputFormat,
        sampleInput,
        sampleOutput,
        problemTitle,
        screenPlatformDetected: screenPlatformForGenerate,
        recordingMs: null,
        uploadMs: null,
        transcriptionMs: null,
        pipelineStarted: performance.now(),
        mode: 'screen',
        source: 'screen',
        screenQuestionType: questionType,
        forceTechnical,
        suppressProfileContext,
      })
      const generatedAnswer = normalizeScreenGeneratedAnswer(
        result,
        String(refinedAnswer || fullAnswerRef.current || answerRef.current || answer || '').trim()
      )
      const extractedCode = extractCodeBlockFromAnswer(generatedAnswer)
      setScreenAnswerText(generatedAnswer)
      setScreenCodeAnswer(extractedCode.code)
      setScreenCodeLanguage(extractedCode.language || (questionType === 'coding' ? 'python' : ''))
      setScreenAnswerGenerated(true)
      setScreenAnswerDisplayedInPanel(Boolean(generatedAnswer))
      setScreenAnswerCommittedToOverlay(Boolean(generatedAnswer))
      setScreenPanelMode('answer')
    } catch (err) {
      console.error('Screen text generation error', err)
      if (!hasPreviousScreenResult) {
        clearProgressiveAnswer()
        resetAnswerMeta()
      }
      setError(
        normalizePipelineError(
          err,
          'Could not generate an answer from the captured screen text.'
        )
      )
      setScreenError(
        normalizePipelineError(
          err,
          'Could not generate an answer from the captured screen text.'
        )
      )
      setStatus('Request failed.')
      setScreenPanelMode(hasPreviousScreenResult || keepAnswerMode ? 'answer' : 'preview')
    } finally {
      setScreenAnswerLoading(false)
    }
  }

  const handleAnswerFromLatestContext = async () => {
    const latestScreenQuestion = ocrText.trim()
    const latestQuestion = (latestScreenQuestion || transcript).trim()

    if (!latestQuestion) {
      clearProgressiveAnswer()
      resetAnswerMeta()
      setError('No clear question detected yet.')
      setStatus('Waiting for a clear question.')
      return
    }

    setError('')
    setAnswerDisplayMode('answer')
    clearProgressiveAnswer()
    resetAnswerMeta()
    setManualQuestionError('')
    setTranscript(latestQuestion)

    try {
      if (latestScreenQuestion) {
        await handleGenerateFromProvidedScreenText(latestScreenQuestion, {
          questionType: screenQuestionType,
        })
        return
      }

      await classifyAndGenerate({
        text: latestQuestion,
        displayQuestion: latestQuestion,
        recordingMs: null,
        uploadMs: null,
        transcriptionMs: null,
        pipelineStarted: performance.now(),
        mode: 'manual',
      })
    } catch (err) {
      console.error('Toolbar answer generation error', err)
      clearProgressiveAnswer()
      resetAnswerMeta()
      setError(normalizePipelineError(err, 'Could not generate an answer right now.'))
      setStatus('Request failed.')
    }
  }

  const handleRecordToggle = async () => {
    const currentAudioSources = audioSourcesRef.current
    const currentAudioPipelineStatus = audioPipelineStatusRef.current
    const sourceMode = getSelectedAudioSourceLabel(currentAudioSources)

    if (autoMode || autoProcessing || ocrProcessing) {
      return
    }

    if (currentAudioPipelineStatus !== 'idle' && currentAudioPipelineStatus !== 'recording') {
      setStatus('Please wait...')
      return
    }

    if (!recording) {
      clearAudioPipelineIdleReset()
      clearAudioSourceWarning()

      if (sourceMode === 'none') {
        flashAudioSourceWarning()
        return
      }

      if (currentAudioSources.system && currentAudioSources.microphone) {
        setAudioPipelineStatus('error')
        setError('Both-source recording is not implemented yet. Use microphone or system audio separately.')
        setStatus('Both-source recording is not implemented yet.')
        scheduleAudioPipelineIdleReset()
        return
      }

      if (currentAudioSources.system && !currentAudioSources.microphone) {
        setError('')
        clearProgressiveAnswer()
        resetAnswerMeta()
        resetScreenOcrState()
        setManualQuestionError('')
        setTranscript('')
        setStatus('Starting system audio capture...')

        try {
          const deviceInfo = await startSystemAudioRecording()
          setRecording(true)
          setAudioPipelineStatus('recording')
          setRecordingStartedAt(Date.now())
          setActiveAudioSource('system')
          setStatus(
            deviceInfo?.device_name
              ? `Recording system audio from ${deviceInfo.device_name}...`
              : 'Recording system audio...'
          )
        } catch (err) {
          console.error('System audio start error', err)
          setRecording(false)
          setAudioPipelineStatus('error')
          setActiveAudioSource('none')
          setError(normalizePipelineError(err, getSystemAudioCapabilityMessage(err?.message)))
          setStatus('System audio capture unavailable.')
          scheduleAudioPipelineIdleReset()
        }
        return
      }

      setError('')
      setStatus('Preparing microphone...')
      clearProgressiveAnswer()
      resetAnswerMeta()
      resetScreenOcrState()
      setManualQuestionError('')
      setTranscript('')

      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        const mimeType = getPreferredRecorderMimeType()
        const recorder = mimeType
          ? new MediaRecorder(stream, { mimeType })
          : new MediaRecorder(stream)

        streamRef.current = stream
        mediaRecorderRef.current = recorder
        chunksRef.current = []

        recorder.ondataavailable = (event) => {
          if (event.data.size > 0) {
            chunksRef.current.push(event.data)
          }
        }

        recorder.onstop = async () => {
          if (manualRecordingCancelledRef.current) {
            manualRecordingCancelledRef.current = false
            chunksRef.current = []
            stopActiveStream()
            setRecording(false)
            setManualProcessing(false)
            setRecordingStartedAt(null)
            setActiveAudioSource('none')
            setAudioPipelineStatus('idle')
            setStatus('Stopped.')
            return
          }
          try {
            const type = recorder.mimeType || chunksRef.current[0]?.type || 'audio/webm'
            const blob = new Blob(chunksRef.current, { type })
            await processManualBlob(blob)
          } catch (err) {
            console.error('AI pipeline error', err)
            clearProgressiveAnswer()
            resetAnswerMeta()
            setAudioPipelineStatus('error')
            setError(normalizePipelineError(err, 'Could not process the recording.'))
            setStatus('Request failed.')
            scheduleAudioPipelineIdleReset()
          } finally {
            stopActiveStream()
            setRecording(false)
            setManualProcessing(false)
            setRecordingStartedAt(null)
            setActiveAudioSource('none')
          }
        }

        recorder.start()
        setRecording(true)
        setAudioPipelineStatus('recording')
        setActiveAudioSource('microphone')
        setRecordingStartedAt(Date.now())
        setStatus('Recording...')
      } catch (err) {
        console.error('Microphone error', err)
        setAudioPipelineStatus('error')
        setActiveAudioSource('none')
        setError('Could not access the microphone. Please check microphone permissions and try again.')
        setStatus('Microphone unavailable.')
        setManualProcessing(false)
        setRecordingStartedAt(null)
        scheduleAudioPipelineIdleReset()
      }
      return
    }

    setStatus('Stopping...')
    setManualProcessing(true)
    setAudioPipelineStatus('transcribing')

    if (sourceMode === 'system') {
      try {
        const pipelineStarted = performance.now()
        const recordingMs = recordingStartedAt
          ? Number((Date.now() - recordingStartedAt).toFixed(2))
          : null
        const { text, uploadMs, transcriptionMs, noSpeech } = await stopSystemAudioRecording()
        setRecording(false)
        setManualProcessing(false)
        setRecordingStartedAt(null)
        if (noSpeech) {
          setActiveAudioSource('none')
          return
        }
        await classifyAndGenerate({
          text,
          recordingMs,
          uploadMs,
          transcriptionMs,
          pipelineStarted,
          mode: 'manual',
        })
      } catch (err) {
        console.error('System audio stop error', err)
        clearProgressiveAnswer()
        resetAnswerMeta()
        setAudioPipelineStatus('error')
        setError(normalizePipelineError(err, 'Could not process the system audio recording.'))
        setStatus('Request failed.')
        scheduleAudioPipelineIdleReset()
      } finally {
        setRecording(false)
        setManualProcessing(false)
        setRecordingStartedAt(null)
        setActiveAudioSource('none')
      }
      return
    }

    mediaRecorderRef.current?.stop()
  }

  useEffect(() => {
    if (!window.electronAPI?.onToolbarAction) {
      return undefined
    }

    const unsubscribe = window.electronAPI.onToolbarAction(async (payload) => {
      const action = payload?.action
      const nextValue = payload?.payload?.value

      try {
        if (action === 'toggle-microphone') {
          if (recording || manualProcessing || autoMode || autoProcessing) {
            setStatus('Please wait...')
            return
          }
          clearAudioSourceWarning()
          setAudioSources((current) => ({ ...current, microphone: !current.microphone }))
          return
        }

        if (action === 'toggle-recording-bar') {
          if (autoMode) {
            stopAutoMode()
            return
          }
          await handleRecordToggle()
          return
        }

        if (action === 'toggle-system-audio') {
          if (recording || manualProcessing || autoMode || autoProcessing) {
            setStatus('Please wait...')
            return
          }
          clearAudioSourceWarning()
          const nextSystem = !audioSourcesRef.current.system
          if (nextSystem) {
            try {
              await fetchSystemAudioDevices()
            } catch (err) {
              setSystemAudioSupported(false)
              setSystemAudioDeviceName('')
              setError(normalizePipelineError(err, getSystemAudioCapabilityMessage(err?.message)))
              setStatus('System audio capability check failed.')
            }
          }
          setSystemAudioEnabled(nextSystem)
          setAudioSources((current) => ({ ...current, system: nextSystem }))
          return
        }

        if (action === 'toggle-auto-generate') {
          if (autoMode) {
            stopAutoMode()
          } else {
            await startAutoMode()
          }
          return
        }

        if (action === 'ai-answer') {
          await handleAnswerFromLatestContext()
          return
        }

        if (action === 'submit-manual-question') {
          await handleManualQuestionSubmit(payload?.payload?.text ?? payload?.text ?? '')
          return
        }

        if (action === 'reset-manual-chat') {
          setManualQuestionError('')
          return
        }

        if (action === 'analyze-screen') {
          await handleScreenCapture()
          return
        }

        if (action === 'analyze-screen-ocr') {
          await handleScreenCapture()
          return
        }

        if (action === 'analyze-screen-extension') {
          const message = 'Browser extension connection is not available yet.'
          const operation = beginScreenOperation('browser_extension')
          setAnswerDisplayMode('screen')
          setError('')
          setScreenError('')
          setOcrProcessing(false)
          setScreenAnswerLoading(false)
          setStatus('Checking browser extension...')
          try {
            const payload = await requestExtensionUnavailable(operation)
            if (!isCurrentScreenOperation(activeScreenOperationRef.current, operation)) {
              return
            }
            const nextMessage = String(payload.error || payload.envelope?.error?.message || message).trim() || message
            setScreenError(nextMessage)
            setStatus(nextMessage)
            failCurrentScreenOperation(operation, nextMessage)
          } catch (err) {
            if (!isCurrentScreenOperation(activeScreenOperationRef.current, operation)) {
              return
            }
            const nextMessage = normalizePipelineError(err, message)
            setScreenError(nextMessage)
            setStatus(nextMessage)
            failCurrentScreenOperation(operation, nextMessage)
          }
          return
        }

        if (action === 'capture-screen-source') {
          const sourceId = payload?.payload?.sourceId ?? payload?.sourceId ?? ''
          if (sourceId) {
            await handleElectronScreenSourceCapture(sourceId)
          }
          return
        }

        if (action === 'clear-screen-text') {
          resetScreenOcrState()
          setStatus('Screen text cleared.')
          return
        }

        if (action === 'set-font-size' && typeof nextValue === 'number') {
          setFontSize(Math.max(12, Math.min(20, nextValue)))
          return
        }

        if (action === 'clear-transcript') {
          clearTranscriptState()
          return
        }

        if (action === 'clear-answers') {
          clearAnswerState()
          return
        }

        if (action === 'show-full-answer') {
          showFullAnswerNow()
          return
        }

        if (action === 'stop-active-operation') {
          stopActiveOperation()
          return
        }

        if (action === 'history-previous') {
          navigateQuestionHistory(payload?.payload?.mode ?? payload?.mode ?? answerDisplayMode, -1)
          return
        }

        if (action === 'history-next') {
          navigateQuestionHistory(payload?.payload?.mode ?? payload?.mode ?? answerDisplayMode, 1)
          return
        }

        if (action === 'end-session') {
          if (autoMode) {
            stopAutoMode()
          } else if (recording) {
            mediaRecorderRef.current?.stop()
          }
          setManualProcessing(false)
          setRecordingStartedAt(null)
          setAudioPipelineStatus('idle')
          setActiveAudioSource('none')
          clearTranscriptState()
          clearAnswerState()
          clearAudioSourceWarning()
          setStatus('Session ended. Ready for a new question.')
        }
      } catch (err) {
        console.error('Toolbar action error', err)
        setAudioPipelineStatus('error')
        setError(normalizePipelineError(err, 'Toolbar action failed.'))
        setStatus('Request failed.')
        scheduleAudioPipelineIdleReset()
      }
    })

    return () => {
      if (unsubscribe) {
        unsubscribe()
      }
    }
  }, [
    autoMode,
    autoProcessing,
    audioPipelineStatus,
    audioSources,
    isManualGenerating,
    manualProcessing,
    ocrProcessing,
    ocrText,
    recording,
    transcript,
  ])

  return (
    <MainDiagnosticsWindow
      isCollapsed={isDiagnosticsCollapsed}
      setIsCollapsed={setIsDiagnosticsCollapsed}
      fontSize={fontSize}
      setFontSize={setFontSize}
      overlayVisible={overlayVisible}
      handleOverlayToggle={handleOverlayToggle}
      recording={recording}
      manualProcessing={manualProcessing}
      audioPipelineStatus={audioPipelineStatus}
      selectedAudioSource={getSelectedAudioSourceLabel(audioSources)}
      activeAudioSource={activeAudioSource}
      systemAudioSupported={systemAudioSupported}
      systemAudioDeviceName={systemAudioDeviceName}
      systemAudioDefaultDeviceName={systemAudioDefaultDeviceName}
      systemAudioInputSampleRate={systemAudioInputSampleRate}
      systemAudioSampleRate={systemAudioSampleRate}
      systemAudioRmsLevel={systemAudioRmsLevel}
      systemAudioPeakLevel={systemAudioPeakLevel}
      systemAudioChunkBytesSent={systemAudioChunkBytesSent}
      systemAudioDroppedSilenceChunks={systemAudioDroppedSilenceChunks}
      systemAudioClippingDetected={systemAudioClippingDetected}
      systemAudioQualityWarning={systemAudioQualityWarning}
      systemAudioDebugWavPath={systemAudioDebugWavPath}
      systemAudioEffectiveGain={systemAudioEffectiveGain}
      systemAudioEnabled={audioSources.system}
      microphoneEnabled={audioSources.microphone}
      autoMode={autoMode}
      autoModeStatus={autoModeStatus}
      autoModeSource={autoModeSource}
      autoStartClicked={autoStartClicked}
      lastAutoTranscript={lastAutoTranscript}
      rawFinalTranscript={rawFinalTranscript}
      lastDetectedQuestion={lastDetectedQuestion}
      acceptedAutoQuestion={acceptedAutoQuestion}
      autoRejectedReason={autoRejectedReason}
      extractedQuestionCandidate={extractedQuestionCandidate}
      polishedQuestionCandidate={polishedQuestionCandidate}
      correctedQuestionCandidate={correctedQuestionCandidate}
      technicalCorrectionsSummary={technicalCorrectionsSummary}
      possibleSttError={possibleSttError}
      questionCandidateSource={questionCandidateSource}
      questionDetectionInput={questionDetectionInput}
      questionDetectReason={questionDetectReason}
      isQuestionDetected={isQuestionDetected}
      cooldownRemainingMs={cooldownRemainingMs}
      recentTranscriptBuffer={recentTranscriptBuffer}
      pendingAutoQuestion={pendingAutoQuestion}
      pendingCooldownQuestion={pendingCooldownQuestion}
      pendingCooldownQuestionAgeMs={pendingCooldownQuestionAgeMs}
      cooldownQueueReason={cooldownQueueReason}
      queuedQuestionProcessed={queuedQuestionProcessed}
      generationStarted={generationStarted}
      generationBlockedReason={generationBlockedReason}
      micStreamingState={micStreamingState}
      answerPipelineState={answerPipelineState}
      micStreamRestartCount={micStreamRestartCount}
      lastMicStreamRestartReason={lastMicStreamRestartReason}
      isCooldownListening={isCooldownListening}
      autoStreamingConnected={autoStreamingConnected}
      partialAutoTranscript={partialAutoTranscript}
      streamingError={streamingError}
      autoProcessing={autoProcessing}
      ocrProcessing={ocrProcessing}
      handleRecordToggle={handleRecordToggle}
      startAutoMode={startAutoMode}
      stopAutoMode={stopAutoMode}
      handleScreenCapture={handleScreenCapture}
      status={status}
      error={error}
      lastError={lastError}
      transcript={transcript}
      category={category}
      provider={provider}
      primaryProvider={primaryProvider}
      primaryModel={primaryModel}
      refinementProvider={refinementProvider}
      refinementModel={refinementModel}
      refinementUsed={refinementUsed}
      refinementStatus={refinementStatus}
      refinementMessage={refinementMessage}
      displayedAnswerSource={displayedAnswerSource}
      displayedAutoQuestionRunId={displayedAutoQuestionRunId}
      currentAutoQuestionRunId={currentAutoQuestionRunId}
      generationMs={generationMs}
      totalPipelineMs={totalPipelineMs}
      pipelineTimings={pipelineTimings}
      codingRuntimeAudit={codingRuntimeAudit}
      sttProvider={sttProvider}
      sttFallbackUsed={sttFallbackUsed}
      sttFallbackReason={sttFallbackReason}
      performanceMode={performanceMode}
      answer={answer}
      profileSetupUrl={`${BACKEND_URL}/profile-setup`}
      ocrText={ocrText}
      ocrConfidence={ocrConfidence}
      screenVisionProvider={screenVisionProvider}
      screenVisionModel={screenVisionModel}
      screenCaptureTarget={screenCaptureTarget}
      screenWindowTitle={screenWindowTitle}
      screenProcessName={screenProcessName}
      screenImageWidth={screenImageWidth}
      screenImageHeight={screenImageHeight}
      rawScreenVisionText={rawScreenVisionText}
      rawScreenVisionJson={rawScreenVisionJson}
      screenCleanedText={screenCleanedText}
      extractedScreenQuestion={extractedScreenQuestion}
      screenQuestionType={screenQuestionType}
      screenConfidence={screenConfidence}
      screenCaptureMs={screenCaptureMs}
      screenVisionMs={screenVisionMs}
      screenFallbackOcrUsed={screenFallbackOcrUsed}
      screenScreenshotHidSaiiaWindows={screenScreenshotHidSaiiaWindows}
      screenDebugPath={screenDebugPath}
      screenPlatformDetected={screenPlatformDetected}
      screenCropUsed={screenCropUsed}
      screenCropRegion={screenCropRegion}
      screenSourceRegion={screenSourceRegion}
      screenExtractionRetryReason={screenExtractionRetryReason}
      screenRejectedUiNoise={screenRejectedUiNoise}
      screenRejectedCodeBoilerplate={screenRejectedCodeBoilerplate}
      screenUiNoiseRatio={screenUiNoiseRatio}
      screenRejectReason={screenRejectReason}
      rawFullWindowVisionJson={rawFullWindowVisionJson}
      rawCroppedVisionJson={rawCroppedVisionJson}
      finalExtractedScreenQuestion={finalExtractedScreenQuestion}
      screenValidProblemFound={screenValidProblemFound}
      groqVisionAttempted={groqVisionAttempted}
      groqVisionSuccess={groqVisionSuccess}
      groqVisionError={groqVisionError}
      groqVisionHttpStatus={groqVisionHttpStatus}
      groqVisionRawResponsePreview={groqVisionRawResponsePreview}
      groqVisionParseError={groqVisionParseError}
      groqVisionTimeout={groqVisionTimeout}
      screenFallbackReason={screenFallbackReason}
      screenAnswerGenerated={screenAnswerGenerated}
      screenError={screenError}
      screenAnalyzeMode={screenAnalyzeMode}
      screenNeedsMoreContent={screenNeedsMoreContent}
      screenFullCaptureEnabled={screenFullCaptureEnabled}
      screenFullProblemCaptureUsed={screenFullProblemCaptureUsed}
      screenCaptureCount={screenCaptureCount}
      screenScrollPositions={screenScrollPositions}
      screenDuplicateCaptureStopped={screenDuplicateCaptureStopped}
      screenBottomReached={screenBottomReached}
      screenRestoredScrollPosition={screenRestoredScrollPosition}
      screenDiagramDetected={screenDiagramDetected}
      screenChartDetected={screenChartDetected}
      finalMergedProblem={finalMergedProblem}
      screenForceTechnical={screenForceTechnical}
      screenCodingAnswerMode={screenCodingAnswerMode}
      screenProfileContextUsed={screenProfileContextUsed}
      screenAutoGenerate={screenAutoGenerate}
      screenAnswerText={screenAnswerText}
      screenCodeAnswer={screenCodeAnswer}
      screenCodeLanguage={screenCodeLanguage}
      screenAnswerDisplayedInPanel={screenAnswerDisplayedInPanel}
      screenAnswerCommittedToOverlay={screenAnswerCommittedToOverlay}
      screenPanelMode={screenPanelMode}
      screenAnswerLoading={screenAnswerLoading}
      resetScreenOcrState={resetScreenOcrState}
      eventLog={eventLog}
      refinedAnswer={refinedAnswer}
      applyRefinedAnswer={applyRefinedAnswer}
      onDesktopSignedOut={resetRuntimeForDesktopLogout}
      onStartupSessionConfigChange={applyStartupSessionConfig}
    />
  )
}

function ProfileSetupForm() {
  const [resume, setResume] = useState('')
  const [role, setRole] = useState('')
  const [company, setCompany] = useState('')
  const [skills, setSkills] = useState('')
  const [experience, setExperience] = useState('')

  const handleSubmit = (event) => {
    event.preventDefault()
    const profile = { resume, role, company, skills, experience }
    localStorage.setItem('candidateProfile', JSON.stringify(profile))
    window.history.back()
  }

  return (
    <div className="profile-shell">
      <div className="profile-panel glass-panel glass-panel--strong">
        <div className="drag-titlebar">
          <div className="drag-titlebar__meta">
            <h2 className="window-title">Profile Setup</h2>
            <p className="window-subtitle">Save the candidate profile that grounds every answer.</p>
          </div>
        </div>

        <form className="profile-form" onSubmit={handleSubmit}>
          <label>
            Resume Text
            <textarea
              required
              value={resume}
              onChange={(event) => setResume(event.target.value)}
              placeholder="Paste your resume here"
            />
          </label>

          <label>
            Target Role
            <input
              required
              type="text"
              value={role}
              onChange={(event) => setRole(event.target.value)}
              placeholder="e.g. Site Reliability Engineer"
            />
          </label>

          <label>
            Company Name
            <input
              required
              type="text"
              value={company}
              onChange={(event) => setCompany(event.target.value)}
              placeholder="e.g. Cogent Labs"
            />
          </label>

          <label>
            Skills
            <textarea
              required
              value={skills}
              onChange={(event) => setSkills(event.target.value)}
              placeholder="e.g. Python, FastAPI, React, MongoDB"
            />
          </label>

          <label>
            Experience / Projects
            <textarea
              required
              value={experience}
              onChange={(event) => setExperience(event.target.value)}
              placeholder="Summarize your experience and key projects"
            />
          </label>

          <div className="form-actions">
            <button className="icon-pill" type="submit">
              Save & Return
            </button>
            <button
              className="icon-pill"
              type="button"
              onClick={() => window.history.back()}
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function App() {
  const params = new URLSearchParams(window.location.search)
  const isOverlayView = params.get('view') === 'overlay'

  if (isOverlayView) {
    return <OverlayWindow />
  }

  return (
    <Routes>
      <Route path="/auth/signup" element={<AuthSignupPage backendUrl={BACKEND_URL} />} />
      <Route path="/auth/login" element={<AuthLoginPage backendUrl={BACKEND_URL} />} />
      <Route path="/auth/desktop-login" element={<AuthDesktopLoginPage backendUrl={BACKEND_URL} />} />
      <Route path="/auth/forgot-password" element={<AuthForgotPasswordPage />} />
      <Route path="/auth/reset-password" element={<AuthResetPasswordPage />} />
      <Route path="/auth/callback" element={<AuthCallbackPage backendUrl={BACKEND_URL} />} />
      <Route path="/auth/status" element={<AuthStatusPage backendUrl={BACKEND_URL} />} />
      <Route path="/unsubscribe" element={<AuthUnsubscribePage backendUrl={BACKEND_URL} />} />
      <Route path="/auth/dashboard" element={<AuthDashboardPage backendUrl={BACKEND_URL} />} />
      <Route path="/auth/resume" element={<AuthResumePage backendUrl={BACKEND_URL} />} />
      <Route path="/auth/logout" element={<AuthLogoutPage />} />
      <Route path="/" element={<MainWindow />} />
      <Route path="/profile-setup" element={<ProfileSetupForm />} />
    </Routes>
  )
}

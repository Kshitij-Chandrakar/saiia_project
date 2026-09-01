const DEFAULT_BACKEND_URL = 'http://localhost:8000'


async function parseJsonResponse(response, fallbackMessage) {
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof payload.detail === 'string' ? payload.detail.trim() : ''
    throw new Error(detail || fallbackMessage)
  }
  return payload
}


function projectCloudResume(record) {
  if (!record || typeof record !== 'object') {
    return null
  }
  return {
    id: record.id,
    original_filename: record.original_filename,
    file_size: record.file_size,
    status: record.status,
    is_active: Boolean(record.is_active),
    extraction_attempt: Number(record.extraction_attempt || 0),
    parser_provider: record.parser_provider || null,
    parser_status: record.parser_status || null,
    extraction_status: record.extraction_status || null,
    index_status: record.index_status || null,
    review_required: Boolean(record.review_required),
    confirmed_at: record.confirmed_at || null,
    active_chunk_generation: record.active_chunk_generation || null,
    failure_code: record.failure_code || null,
    failure_message: record.failure_message || null,
    updated_at: record.updated_at || null,
  }
}

function projectInterviewSession(record) {
  if (!record || typeof record !== 'object') {
    return null
  }
  const id = typeof record.id === 'string' ? record.id.trim() : ''
  if (!id) {
    return null
  }
  return {
    id,
    status: record.status || '',
    started_at: record.started_at || null,
    ended_at: record.ended_at || null,
    selected_resume_id: record.selected_resume_id || null,
    job_context_id: record.job_context_id || null,
    title: record.title || null,
    target_role: record.target_role || null,
    company_name: record.company_name || null,
    job_description_preview: record.job_description_preview || null,
  }
}

function projectInterviewTranscriptEntry(record) {
  if (!record || typeof record !== 'object') {
    return null
  }
  const id = typeof record.id === 'string' ? record.id.trim() : ''
  const sessionId = typeof record.session_id === 'string' ? record.session_id.trim() : ''
  if (!id || !sessionId) {
    return null
  }
  const turnIndex = Number(record.turn_index)
  if (!Number.isInteger(turnIndex) || turnIndex < 1) {
    return null
  }
  return {
    id,
    session_id: sessionId,
    turn_index: turnIndex,
    source: record.source || null,
    question_text: record.question_text || '',
    answer_text: record.answer_text || '',
    category: record.category || null,
    provider: record.provider || null,
    model: record.model || null,
    generation_ms: Number.isInteger(record.generation_ms) ? record.generation_ms : null,
    created_at: record.created_at || null,
  }
}

function projectInterviewSessionNotes(record) {
  if (!record || typeof record !== 'object') {
    return null
  }
  const id = typeof record.id === 'string' ? record.id.trim() : ''
  const sessionId = typeof record.session_id === 'string' ? record.session_id.trim() : ''
  if (!id || !sessionId) {
    return null
  }
  const toStringList = (value) => (
    Array.isArray(value)
      ? value.map((item) => String(item || '').trim()).filter(Boolean)
      : []
  )
  return {
    id,
    session_id: sessionId,
    status: record.status || '',
    notes_markdown: record.notes_markdown || '',
    summary: record.summary || null,
    strengths: toStringList(record.strengths),
    improvement_areas: toStringList(record.improvement_areas),
    technical_topics: toStringList(record.technical_topics),
    key_questions: toStringList(record.key_questions),
    suggested_followups: toStringList(record.suggested_followups),
    provider: record.provider || null,
    model: record.model || null,
    generation_ms: Number.isInteger(record.generation_ms) ? record.generation_ms : null,
    transcript_entry_count: Number.isInteger(record.transcript_entry_count) ? record.transcript_entry_count : 0,
    generated_at: record.generated_at || null,
  }
}

function decodeHtmlCodePoint(value, radix) {
  const codePoint = Number.parseInt(value, radix)
  return Number.isFinite(codePoint) && codePoint >= 0 && codePoint <= 0x10ffff
    ? String.fromCodePoint(codePoint)
    : ''
}

function normalizeReadableAskAIText(value) {
  let text = String(value || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  text = text
    .replace(/\\r\\n/g, '\n')
    .replace(/\\n/g, '\n')
    .replace(/\\r/g, '\n')
    .replace(/&#x([0-9a-f]+);/gi, (_, hex) => decodeHtmlCodePoint(hex, 16))
    .replace(/&#(\d+);/g, (_, code) => decodeHtmlCodePoint(code, 10))
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/g, "'")
  text = text.replace(/\\([\\`*_{}\[\]()#+\-.!>])/g, '$1')
  text = text
    .split('\n')
    .map((line) => line
      .replace(/^\s{0,3}#{1,6}\s*/, '')
      .replace(/^\s*[-*+]\s+/, '- ')
      .replace(/^\s*(\d+)\\?\.\s+/, '$1. '))
    .join('\n')
  return text
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/__(.*?)__/g, '$1')
    .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1$2')
    .trim()
}

function projectInterviewAskAIMessage(record) {
  if (!record || typeof record !== 'object') {
    return null
  }
  const id = typeof record.id === 'string' ? record.id.trim() : ''
  const sessionId = typeof record.session_id === 'string' ? record.session_id.trim() : ''
  const role = typeof record.role === 'string' ? record.role.trim() : ''
  const turnIndex = Number(record.turn_index)
  if (!id || !sessionId || !['user', 'assistant'].includes(role) || !Number.isInteger(turnIndex) || turnIndex < 1) {
    return null
  }
  return {
    id,
    session_id: sessionId,
    role,
    message_text: normalizeReadableAskAIText(record.message_text),
    turn_index: turnIndex,
    provider: record.provider || null,
    model: record.model || null,
    generation_ms: Number.isInteger(record.generation_ms) ? record.generation_ms : null,
    created_at: record.created_at || null,
  }
}

function getSafeDownloadFilename(response, fallback) {
  const contentDisposition = String(
    response?.headers?.get?.('content-disposition')
    || response?.headers?.get?.('Content-Disposition')
    || '',
  ).trim()
  const match = contentDisposition.match(/filename="([^"]+)"/i)
  const filename = match?.[1] ? String(match[1]).trim() : ''
  return filename || fallback
}


function requireAccessToken(accessToken) {
  const token = String(accessToken || '').trim()
  if (!token) {
    throw new Error('A Supabase access token is required.')
  }
  return token
}


export async function fetchCurrentUser(accessToken, options = {}) {
  const token = requireAccessToken(accessToken)

  const {
    backendUrl = DEFAULT_BACKEND_URL,
    fetchImpl = fetch,
  } = options

  const response = await fetchImpl(`${backendUrl}/api/auth/me`, {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  const payload = await parseJsonResponse(response, 'Unable to verify the current user.')

  return {
    user_id: payload.user_id,
    email: payload.email || null,
    role: payload.role || null,
  }
}


export async function bootstrapProfile(accessToken, options = {}) {
  const token = requireAccessToken(accessToken)

  const {
    backendUrl = DEFAULT_BACKEND_URL,
    fetchImpl = fetch,
  } = options

  const response = await fetchImpl(`${backendUrl}/api/auth/profile/bootstrap`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  const payload = await parseJsonResponse(response, 'Unable to bootstrap the profile.')

  return {
    user_id: payload.user_id,
    profile_exists: Boolean(payload.profile_exists),
    profile_created: Boolean(payload.profile_created),
    settings_exists: Boolean(payload.settings_exists),
    settings_created: Boolean(payload.settings_created),
    next_step: payload.next_step || 'profile_setup',
  }
}


export async function createDesktopHandoff(accessToken, refreshToken, state, options = {}) {
  const token = requireAccessToken(accessToken)
  const {
    backendUrl = DEFAULT_BACKEND_URL,
    fetchImpl = fetch,
  } = options

  const payload = await parseJsonResponse(
    await fetchImpl(`${backendUrl}/api/auth/desktop-handoff`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        state,
        refresh_token: refreshToken,
      }),
    }),
    'Unable to prepare desktop login.',
  )
  return {
    handoff_code: payload.handoff_code,
    expires_in: payload.expires_in,
  }
}


export async function uploadCloudResume(accessToken, file, options = {}) {
  const token = requireAccessToken(accessToken)
  const {
    backendUrl = DEFAULT_BACKEND_URL,
    fetchImpl = fetch,
    signal,
  } = options
  const formData = new FormData()
  formData.append('file', file)

  return parseJsonResponse(
    await fetchImpl(`${backendUrl}/api/resumes`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
      },
      body: formData,
      signal,
    }),
    'Unable to upload the resume.',
  ).then(projectCloudResume)
}


export async function fetchCurrentCloudResume(accessToken, options = {}) {
  const token = requireAccessToken(accessToken)
  const {
    backendUrl = DEFAULT_BACKEND_URL,
    fetchImpl = fetch,
    signal,
  } = options

  const payload = await parseJsonResponse(
    await fetchImpl(`${backendUrl}/api/resumes/current`, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${token}`,
      },
      signal,
    }),
    'Unable to load the current resume.',
  )
  return {
    ready: Boolean(payload.ready),
    resume: projectCloudResume(payload.resume),
  }
}


export async function fetchReviewCandidate(accessToken, options = {}) {
  const token = requireAccessToken(accessToken)
  const {
    backendUrl = DEFAULT_BACKEND_URL,
    fetchImpl = fetch,
    signal,
  } = options

  const payload = await parseJsonResponse(
    await fetchImpl(`${backendUrl}/api/resumes/review-candidate`, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${token}`,
      },
      signal,
    }),
    'Unable to load the resume review candidate.',
  )
  return {
    has_candidate: Boolean(payload.has_candidate),
    resume: projectCloudResume(payload.resume),
  }
}


export async function fetchCloudResumeStatus(accessToken, resumeId, options = {}) {
  const token = requireAccessToken(accessToken)
  const {
    backendUrl = DEFAULT_BACKEND_URL,
    fetchImpl = fetch,
    signal,
  } = options

  return parseJsonResponse(
    await fetchImpl(`${backendUrl}/api/resumes/${encodeURIComponent(resumeId)}/status`, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${token}`,
      },
      signal,
    }),
    'Unable to load the resume status.',
  ).then(projectCloudResume)
}


export async function extractCloudResume(accessToken, resumeId, options = {}) {
  const token = requireAccessToken(accessToken)
  const {
    backendUrl = DEFAULT_BACKEND_URL,
    fetchImpl = fetch,
    signal,
  } = options

  return parseJsonResponse(
    await fetchImpl(`${backendUrl}/api/resumes/${encodeURIComponent(resumeId)}/extract`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
      },
      signal,
    }),
    'Unable to extract the resume.',
  )
}


export async function confirmCloudResume(accessToken, resumeId, extractionAttempt, profile, options = {}) {
  const token = requireAccessToken(accessToken)
  const {
    backendUrl = DEFAULT_BACKEND_URL,
    fetchImpl = fetch,
    signal,
  } = options

  return parseJsonResponse(
    await fetchImpl(`${backendUrl}/api/resumes/${encodeURIComponent(resumeId)}/confirm`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        extraction_attempt: extractionAttempt,
        profile,
      }),
      signal,
    }),
    'Unable to confirm the resume profile.',
  )
}


export async function deleteCloudResume(accessToken, resumeId, options = {}) {
  const token = requireAccessToken(accessToken)
  const {
    backendUrl = DEFAULT_BACKEND_URL,
    fetchImpl = fetch,
    signal,
  } = options

  return parseJsonResponse(
    await fetchImpl(`${backendUrl}/api/resumes/${encodeURIComponent(resumeId)}`, {
      method: 'DELETE',
      headers: {
        Authorization: `Bearer ${token}`,
      },
      signal,
    }),
    'Unable to delete the resume.',
  )
}


export async function rebuildCloudResumeIndex(accessToken, resumeId, options = {}) {
  const token = requireAccessToken(accessToken)
  const {
    backendUrl = DEFAULT_BACKEND_URL,
    fetchImpl = fetch,
    signal,
  } = options

  return parseJsonResponse(
    await fetchImpl(`${backendUrl}/api/resumes/${encodeURIComponent(resumeId)}/rebuild-index`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
      },
      signal,
    }),
    'Unable to rebuild the resume index.',
  )
}


export async function fetchInterviewSessions(accessToken, options = {}) {
  const token = requireAccessToken(accessToken)
  const {
    backendUrl = DEFAULT_BACKEND_URL,
    fetchImpl = fetch,
    signal,
    limit = 20,
    page = 1,
  } = options

  const payload = await parseJsonResponse(
    await fetchImpl(
      `${backendUrl}/api/interview-sessions?limit=${encodeURIComponent(String(limit))}&page=${encodeURIComponent(String(page))}`,
      {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${token}`,
        },
        signal,
      },
    ),
    'Unable to load interview sessions.',
  )

  return {
    items: Array.isArray(payload.items) ? payload.items.map(projectInterviewSession).filter(Boolean) : [],
    limit: Number.isInteger(payload.limit) ? payload.limit : Number(limit) || 20,
    page: Number.isInteger(payload.page) ? payload.page : Number(page) || 1,
  }
}


export async function fetchInterviewTranscriptEntries(accessToken, sessionId, options = {}) {
  const token = requireAccessToken(accessToken)
  const {
    backendUrl = DEFAULT_BACKEND_URL,
    fetchImpl = fetch,
    signal,
    limit = 100,
    page = 1,
  } = options

  const payload = await parseJsonResponse(
    await fetchImpl(
      `${backendUrl}/api/interview-sessions/${encodeURIComponent(sessionId)}/transcript-entries?limit=${encodeURIComponent(String(limit))}&page=${encodeURIComponent(String(page))}`,
      {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${token}`,
        },
        signal,
      },
    ),
    'Unable to load the interview transcript.',
  )

  return {
    items: Array.isArray(payload.items) ? payload.items.map(projectInterviewTranscriptEntry).filter(Boolean) : [],
    limit: Number.isInteger(payload.limit) ? payload.limit : Number(limit) || 100,
    page: Number.isInteger(payload.page) ? payload.page : Number(page) || 1,
  }
}


export async function downloadInterviewTranscript(accessToken, sessionId, format, options = {}) {
  const token = requireAccessToken(accessToken)
  const normalizedFormat = String(format || '').trim().toLowerCase()
  if (!['txt', 'md'].includes(normalizedFormat)) {
    throw new Error('Transcript download format must be txt or md.')
  }
  const {
    backendUrl = DEFAULT_BACKEND_URL,
    fetchImpl = fetch,
    signal,
  } = options

  const response = await fetchImpl(
    `${backendUrl}/api/interview-sessions/${encodeURIComponent(sessionId)}/transcript/download?format=${encodeURIComponent(normalizedFormat)}`,
    {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${token}`,
      },
      signal,
    },
  )
  if (!response.ok) {
    let payload = {}
    try {
      payload = await response.json()
    } catch {
      payload = {}
    }
    const detail = typeof payload.detail === 'string' ? payload.detail.trim() : ''
    throw new Error(detail || 'Unable to download the interview transcript.')
  }

  return {
    filename: getSafeDownloadFilename(response, `interview-session-transcript.${normalizedFormat}`),
    content: await response.text(),
    format: normalizedFormat,
  }
}


export async function fetchInterviewSessionNotes(accessToken, sessionId, options = {}) {
  const token = requireAccessToken(accessToken)
  const {
    backendUrl = DEFAULT_BACKEND_URL,
    fetchImpl = fetch,
    signal,
  } = options

  const payload = await parseJsonResponse(
    await fetchImpl(`${backendUrl}/api/interview-sessions/${encodeURIComponent(sessionId)}/notes`, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${token}`,
      },
      signal,
    }),
    'Unable to load AI notes.',
  )

  return projectInterviewSessionNotes(payload)
}


export async function generateInterviewSessionNotes(accessToken, sessionId, options = {}) {
  const token = requireAccessToken(accessToken)
  const {
    backendUrl = DEFAULT_BACKEND_URL,
    fetchImpl = fetch,
    signal,
    forceRegenerate = false,
  } = options

  const payload = await parseJsonResponse(
    await fetchImpl(`${backendUrl}/api/interview-sessions/${encodeURIComponent(sessionId)}/notes/generate`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ force_regenerate: Boolean(forceRegenerate) }),
      signal,
    }),
    'Unable to generate AI notes.',
  )

  return projectInterviewSessionNotes(payload)
}


export async function fetchInterviewAskAIMessages(accessToken, sessionId, options = {}) {
  const token = requireAccessToken(accessToken)
  const {
    backendUrl = DEFAULT_BACKEND_URL,
    fetchImpl = fetch,
    signal,
    limit = 50,
    page = 1,
  } = options

  const payload = await parseJsonResponse(
    await fetchImpl(
      `${backendUrl}/api/interview-sessions/${encodeURIComponent(sessionId)}/ask-ai/messages?limit=${encodeURIComponent(String(limit))}&page=${encodeURIComponent(String(page))}`,
      {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${token}`,
        },
        signal,
      },
    ),
    'Unable to load Ask AI messages.',
  )

  return {
    items: Array.isArray(payload.items) ? payload.items.map(projectInterviewAskAIMessage).filter(Boolean) : [],
    limit: Number.isInteger(payload.limit) ? payload.limit : Number(limit) || 50,
    page: Number.isInteger(payload.page) ? payload.page : Number(page) || 1,
    has_more: Boolean(payload.has_more),
    next_page: Number.isInteger(payload.next_page) ? payload.next_page : null,
  }
}


export async function askInterviewSessionAI(accessToken, sessionId, question, options = {}) {
  const token = requireAccessToken(accessToken)
  const {
    backendUrl = DEFAULT_BACKEND_URL,
    fetchImpl = fetch,
    signal,
    requestId = null,
    includeNotes = true,
  } = options

  const payload = await parseJsonResponse(
    await fetchImpl(`${backendUrl}/api/interview-sessions/${encodeURIComponent(sessionId)}/ask-ai`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        question,
        request_id: requestId,
        include_notes: Boolean(includeNotes),
      }),
      signal,
    }),
    'Unable to ask AI about this session.',
  )

  return {
    user_message: projectInterviewAskAIMessage(payload.user_message),
    assistant_message: projectInterviewAskAIMessage(payload.assistant_message),
    answer_text: normalizeReadableAskAIText(payload.answer_text),
    provider: payload.provider || null,
    model: payload.model || null,
    generation_ms: Number.isInteger(payload.generation_ms) ? payload.generation_ms : null,
    context_used: {
      transcript_entry_count: Number(payload.context_used?.transcript_entry_count || 0),
      notes_used: Boolean(payload.context_used?.notes_used),
      recent_message_count: Number(payload.context_used?.recent_message_count || 0),
    },
  }
}

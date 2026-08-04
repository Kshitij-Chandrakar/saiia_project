const DEFAULT_BACKEND_URL = 'http://localhost:8000'


async function parseJsonResponse(response, fallbackMessage) {
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.detail || fallbackMessage)
  }
  return payload
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


export async function uploadCloudResume(accessToken, file, options = {}) {
  const token = requireAccessToken(accessToken)
  const {
    backendUrl = DEFAULT_BACKEND_URL,
    fetchImpl = fetch,
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
    }),
    'Unable to upload the resume.',
  )
}


export async function fetchCurrentCloudResume(accessToken, options = {}) {
  const token = requireAccessToken(accessToken)
  const {
    backendUrl = DEFAULT_BACKEND_URL,
    fetchImpl = fetch,
  } = options

  return parseJsonResponse(
    await fetchImpl(`${backendUrl}/api/resumes/current`, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${token}`,
      },
    }),
    'Unable to load the current resume.',
  )
}


export async function fetchReviewCandidate(accessToken, options = {}) {
  const token = requireAccessToken(accessToken)
  const {
    backendUrl = DEFAULT_BACKEND_URL,
    fetchImpl = fetch,
  } = options

  return parseJsonResponse(
    await fetchImpl(`${backendUrl}/api/resumes/review-candidate`, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${token}`,
      },
    }),
    'Unable to load the resume review candidate.',
  )
}


export async function fetchCloudResumeStatus(accessToken, resumeId, options = {}) {
  const token = requireAccessToken(accessToken)
  const {
    backendUrl = DEFAULT_BACKEND_URL,
    fetchImpl = fetch,
  } = options

  return parseJsonResponse(
    await fetchImpl(`${backendUrl}/api/resumes/${encodeURIComponent(resumeId)}/status`, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${token}`,
      },
    }),
    'Unable to load the resume status.',
  )
}


export async function extractCloudResume(accessToken, resumeId, options = {}) {
  const token = requireAccessToken(accessToken)
  const {
    backendUrl = DEFAULT_BACKEND_URL,
    fetchImpl = fetch,
  } = options

  return parseJsonResponse(
    await fetchImpl(`${backendUrl}/api/resumes/${encodeURIComponent(resumeId)}/extract`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
      },
    }),
    'Unable to extract the resume.',
  )
}


export async function confirmCloudResume(accessToken, resumeId, extractionAttempt, profile, options = {}) {
  const token = requireAccessToken(accessToken)
  const {
    backendUrl = DEFAULT_BACKEND_URL,
    fetchImpl = fetch,
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
    }),
    'Unable to confirm the resume profile.',
  )
}

const DEFAULT_BACKEND_URL = 'http://localhost:8000'


export async function fetchCurrentUser(accessToken, options = {}) {
  const token = String(accessToken || '').trim()
  if (!token) {
    throw new Error('A Supabase access token is required.')
  }

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

  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.detail || 'Unable to verify the current user.')
  }

  return {
    user_id: payload.user_id,
    email: payload.email || null,
    role: payload.role || null,
  }
}


export async function bootstrapProfile(accessToken, options = {}) {
  const token = String(accessToken || '').trim()
  if (!token) {
    throw new Error('A Supabase access token is required.')
  }

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

  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.detail || 'Unable to bootstrap the profile.')
  }

  return {
    user_id: payload.user_id,
    profile_exists: Boolean(payload.profile_exists),
    profile_created: Boolean(payload.profile_created),
    settings_exists: Boolean(payload.settings_exists),
    settings_created: Boolean(payload.settings_created),
    next_step: payload.next_step || 'profile_setup',
  }
}

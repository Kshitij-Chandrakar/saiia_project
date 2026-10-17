import { supabase } from './supabaseClient'
import { fetchCloudResumeList, fetchCurrentCloudResume, fetchInterviewSessions, uploadCloudResume } from './authApi'

// Credentials stay inside the existing auth/data layer, never in component state.
async function token() {
  const result = await supabase?.auth.getSession()
  if (result?.error || !result?.data?.session?.access_token) throw Error('Sign in again to continue.')
  return result.data.session.access_token
}
export async function onboardingRequest(backendUrl, path = '', body, method = 'GET', signal) {
  const access = await token()
  const response = await fetch(`${backendUrl}/api/onboarding${path}`, { method, signal,
    headers: { Authorization: `Bearer ${access}`, 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
  if (!response.ok) throw Error('Onboarding is unavailable. Please retry. Account setup or the onboarding migration may not be ready.')
  return response.json()
}
export async function onboardingResources(backendUrl, signal) {
  const access = await token(), options = { backendUrl, signal }
  const results = await Promise.allSettled([fetchCurrentCloudResume(access, options), fetchCloudResumeList(access, options),
    fetchInterviewSessions(access, options), cloudResource(backendUrl, '/api/job-contexts', undefined, undefined, signal)])
  return { resume: results[0].value?.resume || results[1].value?.[0] || null,
    resumes: results[1].value || [], sessions: results[2].value?.items || [], jobs: results[3].value?.items || [],
    failed: results.some(r => r.status === 'rejected') }
}
export async function cloudResource(backendUrl, path, body, key, signal) {
  const access = await token()
  const response = await fetch(backendUrl + path, { method: body ? 'POST' : 'GET', signal,
    headers: { Authorization: `Bearer ${access}`, 'Content-Type': 'application/json', ...(key ? { 'Idempotency-Key': key } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}) })
  if (!response.ok) throw Error('Unable to save. Your previous data has been kept. Please retry.')
  return response.json()
}
export async function onboardingUpload(backendUrl, file) {
  return uploadCloudResume(await token(), file, { backendUrl })
}

export async function onboardingExtractJob(backendUrl, file) {
  const access = await token(), body = new FormData()
  body.append('file', file); body.append('provider_processing_consent', 'true')
  const response = await fetch(backendUrl + '/api/job-contexts/extract', { method: 'POST', body,
    headers: { Authorization: `Bearer ${access}` } })
  if (!response.ok) throw Error('Document extraction unavailable. Please retry.')
  return response.json()
}

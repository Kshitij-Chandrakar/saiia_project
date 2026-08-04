import assert from 'node:assert/strict'
import test from 'node:test'

import {
  bootstrapProfile,
  confirmCloudResume,
  extractCloudResume,
  fetchCloudResumeStatus,
  fetchCurrentCloudResume,
  fetchCurrentUser,
  fetchReviewCandidate,
  uploadCloudResume,
} from './authApi.js'
import { getSupabaseAuthConfig, hasSupabaseAuthConfig } from './supabaseClient.js'


test('Supabase auth config reports missing frontend-safe env', () => {
  assert.equal(hasSupabaseAuthConfig({}), false)
})


test('Supabase auth config accepts only URL and anon key', () => {
  const config = getSupabaseAuthConfig({
    VITE_SUPABASE_URL: ' https://project-ref.supabase.co ',
    VITE_SUPABASE_ANON_KEY: ' anon-key ',
    UNUSED_PRIVATE_VALUE: 'must-not-be-read',
  })

  assert.equal(hasSupabaseAuthConfig({
    VITE_SUPABASE_URL: config.url,
    VITE_SUPABASE_ANON_KEY: config.anonKey,
  }), true)
  assert.deepEqual(config, {
    url: 'https://project-ref.supabase.co',
    anonKey: 'anon-key',
  })
})


test('fetchCurrentUser requires a token', async () => {
  await assert.rejects(
    () => fetchCurrentUser(''),
    /access token is required/,
  )
})


test('fetchCurrentUser sends bearer token and returns safe fields', async () => {
  const rawToken = 'unit-test-access-token'
  const calls = []
  const user = await fetchCurrentUser(rawToken, {
    backendUrl: 'http://localhost:8000',
    fetchImpl: async (url, init) => {
      calls.push({ url, init })
      return {
        ok: true,
        json: async () => ({
          user_id: '00000000-0000-4000-8000-000000000001',
          email: 'user@example.com',
          role: 'authenticated',
          access_token: rawToken,
          claims: { sub: 'ignored' },
        }),
      }
    },
  })

  assert.equal(calls[0].url, 'http://localhost:8000/api/auth/me')
  assert.equal(calls[0].init.headers.Authorization, `Bearer ${rawToken}`)
  assert.deepEqual(user, {
    user_id: '00000000-0000-4000-8000-000000000001',
    email: 'user@example.com',
    role: 'authenticated',
  })
  assert.equal('access_token' in user, false)
  assert.equal('claims' in user, false)
})


test('bootstrapProfile posts bearer token and returns safe status', async () => {
  const rawToken = 'unit-test-access-token'
  const calls = []
  const result = await bootstrapProfile(rawToken, {
    backendUrl: 'http://localhost:8000',
    fetchImpl: async (url, init) => {
      calls.push({ url, init })
      return {
        ok: true,
        json: async () => ({
          user_id: '00000000-0000-4000-8000-000000000001',
          profile_exists: true,
          profile_created: true,
          settings_exists: true,
          settings_created: false,
          next_step: 'profile_setup',
          access_token: rawToken,
          private_server_value: 'ignored',
        }),
      }
    },
  })

  assert.equal(calls[0].url, 'http://localhost:8000/api/auth/profile/bootstrap')
  assert.equal(calls[0].init.method, 'POST')
  assert.equal(calls[0].init.headers.Authorization, `Bearer ${rawToken}`)
  assert.deepEqual(result, {
    user_id: '00000000-0000-4000-8000-000000000001',
    profile_exists: true,
    profile_created: true,
    settings_exists: true,
    settings_created: false,
    next_step: 'profile_setup',
  })
  assert.equal('access_token' in result, false)
  assert.equal('private_server_value' in result, false)
})


test('cloud resume helpers call authenticated backend routes', async () => {
  const rawToken = 'unit-test-access-token'
  const calls = []
  const fetchImpl = async (url, init) => {
    calls.push({ url, init })
    if (url.endsWith('/api/resumes/current')) {
      return { ok: true, json: async () => ({ ready: false, resume: null }) }
    }
    if (url.endsWith('/api/resumes/review-candidate')) {
      return { ok: true, json: async () => ({ has_candidate: false, resume: null }) }
    }
    if (url.endsWith('/status')) {
      return { ok: true, json: async () => ({ id: 'resume-id', status: 'uploaded' }) }
    }
    if (url.endsWith('/extract')) {
      return {
        ok: true,
        json: async () => ({
          resume_id: 'resume-id',
          status: 'needs_review',
          extraction_attempt: 1,
          profile: { full_name: 'Test User' },
        }),
      }
    }
    if (url.endsWith('/confirm')) {
      return {
        ok: true,
        json: async () => ({
          resume_id: 'resume-id',
          status: 'needs_review',
          extraction_attempt: 1,
          confirmed_profile_saved: true,
        }),
      }
    }
    return { ok: true, json: async () => ({ id: 'resume-id', status: 'uploaded' }) }
  }

  await uploadCloudResume(rawToken, new Blob(['resume'], { type: 'text/plain' }), { fetchImpl })
  await fetchCurrentCloudResume(rawToken, { fetchImpl })
  await fetchReviewCandidate(rawToken, { fetchImpl })
  await fetchCloudResumeStatus(rawToken, 'resume-id', { fetchImpl })
  await extractCloudResume(rawToken, 'resume-id', { fetchImpl })
  await confirmCloudResume(rawToken, 'resume-id', 1, { full_name: 'Edited User' }, { fetchImpl })

  assert.deepEqual(calls.map((call) => [call.init.method, call.url]), [
    ['POST', 'http://localhost:8000/api/resumes'],
    ['GET', 'http://localhost:8000/api/resumes/current'],
    ['GET', 'http://localhost:8000/api/resumes/review-candidate'],
    ['GET', 'http://localhost:8000/api/resumes/resume-id/status'],
    ['POST', 'http://localhost:8000/api/resumes/resume-id/extract'],
    ['POST', 'http://localhost:8000/api/resumes/resume-id/confirm'],
  ])
  assert.equal(calls.every((call) => call.init.headers.Authorization === `Bearer ${rawToken}`), true)
  assert.equal(calls[5].init.headers['Content-Type'], 'application/json')
  assert.deepEqual(JSON.parse(calls[5].init.body), {
    extraction_attempt: 1,
    profile: { full_name: 'Edited User' },
  })
})

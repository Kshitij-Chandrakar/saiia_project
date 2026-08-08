import assert from 'node:assert/strict'
import test from 'node:test'

import {
  bootstrapProfile,
  confirmCloudResume,
  deleteCloudResume,
  extractCloudResume,
  fetchCloudResumeStatus,
  fetchCurrentCloudResume,
  fetchCurrentUser,
  fetchReviewCandidate,
  rebuildCloudResumeIndex,
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
  const controller = new AbortController()
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
    if (url.endsWith('/rebuild-index')) {
      return {
        ok: true,
        json: async () => ({
          resume_id: 'resume-id',
          status: 'ready',
          index_status: 'indexed',
          active_chunk_generation: 'new-generation',
          chunk_count: 2,
          message: 'Resume index rebuilt.',
        }),
      }
    }
    if (init.method === 'DELETE') {
      return {
        ok: true,
        json: async () => ({
          resume_id: 'resume-id',
          status: 'deleted',
          is_active: false,
          ready: false,
          message: 'Resume deleted.',
        }),
      }
    }
    return {
      ok: true,
      json: async () => ({
        id: 'resume-id',
        storage_path: 'private/storage/path',
        original_filename: 'resume.txt',
        file_size: 6,
        status: 'uploaded',
          is_active: false,
          extraction_attempt: 0,
          parser_provider: 'pending',
          parser_status: 'pending',
          extraction_status: 'pending',
          index_status: 'not_indexed',
          failure_message: 'private diagnostic',
        }),
      }
  }

  const uploaded = await uploadCloudResume(rawToken, new Blob(['resume'], { type: 'text/plain' }), {
    fetchImpl,
    signal: controller.signal,
  })
  await fetchCurrentCloudResume(rawToken, { fetchImpl, signal: controller.signal })
  await fetchReviewCandidate(rawToken, { fetchImpl, signal: controller.signal })
  await fetchCloudResumeStatus(rawToken, 'resume-id', { fetchImpl, signal: controller.signal })
  await extractCloudResume(rawToken, 'resume-id', { fetchImpl, signal: controller.signal })
  await confirmCloudResume(rawToken, 'resume-id', 1, { full_name: 'Edited User' }, {
    fetchImpl,
    signal: controller.signal,
  })
  await rebuildCloudResumeIndex(rawToken, 'resume-id', { fetchImpl, signal: controller.signal })
  await deleteCloudResume(rawToken, 'resume-id', { fetchImpl, signal: controller.signal })

  assert.deepEqual(calls.map((call) => [call.init.method, call.url]), [
    ['POST', 'http://localhost:8000/api/resumes'],
    ['GET', 'http://localhost:8000/api/resumes/current'],
    ['GET', 'http://localhost:8000/api/resumes/review-candidate'],
    ['GET', 'http://localhost:8000/api/resumes/resume-id/status'],
    ['POST', 'http://localhost:8000/api/resumes/resume-id/extract'],
    ['POST', 'http://localhost:8000/api/resumes/resume-id/confirm'],
    ['POST', 'http://localhost:8000/api/resumes/resume-id/rebuild-index'],
    ['DELETE', 'http://localhost:8000/api/resumes/resume-id'],
  ])
  assert.equal(calls.every((call) => call.init.headers.Authorization === `Bearer ${rawToken}`), true)
  assert.equal(calls.every((call) => call.init.signal === controller.signal), true)
  assert.equal('Content-Type' in calls[0].init.headers, false)
  assert.equal(calls[5].init.headers['Content-Type'], 'application/json')
  assert.equal('Content-Type' in calls[6].init.headers, false)
  assert.equal('Content-Type' in calls[7].init.headers, false)
  assert.deepEqual(JSON.parse(calls[5].init.body), {
    extraction_attempt: 1,
    profile: { full_name: 'Edited User' },
  })
  assert.deepEqual(uploaded, {
    id: 'resume-id',
    original_filename: 'resume.txt',
    file_size: 6,
    status: 'uploaded',
    is_active: false,
    extraction_attempt: 0,
    parser_provider: 'pending',
    parser_status: 'pending',
    extraction_status: 'pending',
    index_status: 'not_indexed',
    review_required: false,
    confirmed_at: null,
    active_chunk_generation: null,
    failure_code: null,
    failure_message: 'private diagnostic',
    updated_at: null,
  })
  assert.equal('storage_path' in uploaded, false)
})


test('cloud resume helpers use safe fallback for validation-array detail', async () => {
  await assert.rejects(
    () => uploadCloudResume('unit-test-access-token', new Blob(['resume'], { type: 'text/plain' }), {
      fetchImpl: async () => ({
        ok: false,
        json: async () => ({
          detail: [{ msg: 'validation error should not render as object' }],
        }),
      }),
    }),
    /Unable to upload the resume\./,
  )
})


test('cloud resume helpers surface string detail and fallback empty errors', async () => {
  await assert.rejects(
    () => fetchReviewCandidate('unit-test-access-token', {
      fetchImpl: async () => ({
        ok: false,
        json: async () => ({ detail: 'Review candidate unavailable.' }),
      }),
    }),
    /Review candidate unavailable\./,
  )

  await assert.rejects(
    () => extractCloudResume('unit-test-access-token', 'resume-id', {
      fetchImpl: async () => ({
        ok: false,
        json: async () => ({}),
      }),
    }),
    /Unable to extract the resume\./,
  )
})

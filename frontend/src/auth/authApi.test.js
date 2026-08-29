import assert from 'node:assert/strict'
import test from 'node:test'

import {
  bootstrapProfile,
  confirmCloudResume,
  createDesktopHandoff,
  deleteCloudResume,
  downloadInterviewTranscript,
  extractCloudResume,
  fetchInterviewTranscriptEntries,
  fetchInterviewSessions,
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


test('createDesktopHandoff posts authenticated state and refresh token to backend only', async () => {
  const rawToken = 'unit-test-access-token'
  const calls = []
  const handoff = await createDesktopHandoff(rawToken, 'unit-test-refresh-token', 'desktop-state-123456', {
    backendUrl: 'http://localhost:8000',
    fetchImpl: async (url, init) => {
      calls.push({ url, init })
      return {
        ok: true,
        json: async () => ({
          handoff_code: 'one-time-handoff-code',
          expires_in: 300,
          access_token: 'must-not-leak',
        }),
      }
    },
  })

  assert.equal(calls[0].url, 'http://localhost:8000/api/auth/desktop-handoff')
  assert.equal(calls[0].init.method, 'POST')
  assert.equal(calls[0].init.headers.Authorization, `Bearer ${rawToken}`)
  assert.equal(calls[0].init.headers['Content-Type'], 'application/json')
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    state: 'desktop-state-123456',
    refresh_token: 'unit-test-refresh-token',
  })
  assert.deepEqual(handoff, {
    handoff_code: 'one-time-handoff-code',
    expires_in: 300,
  })
  assert.equal('access_token' in handoff, false)
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


test('fetchInterviewSessions drops records without a valid string id and keeps preview text', async () => {
  const result = await fetchInterviewSessions('unit-test-access-token', {
    backendUrl: 'http://localhost:8000',
    fetchImpl: async () => ({
      ok: true,
      json: async () => ({
        items: [
          null,
          {},
          { id: '' },
          { id: 42 },
          {
            id: ' session-1 ',
            status: 'ended',
            started_at: '2026-08-28T00:00:00Z',
            ended_at: '2026-08-28T00:05:00Z',
            title: 'Design interview',
            target_role: 'Frontend Engineer',
            company_name: 'Acme',
            job_description_preview: 'AI engineer',
          },
        ],
        limit: 20,
        page: 1,
      }),
    }),
  })

  assert.deepEqual(result, {
    items: [
      {
        id: 'session-1',
        status: 'ended',
        started_at: '2026-08-28T00:00:00Z',
        ended_at: '2026-08-28T00:05:00Z',
        selected_resume_id: null,
        job_context_id: null,
        title: 'Design interview',
        target_role: 'Frontend Engineer',
        company_name: 'Acme',
        job_description_preview: 'AI engineer',
      },
    ],
    limit: 20,
    page: 1,
  })
})


test('fetchInterviewTranscriptEntries keeps only valid transcript records', async () => {
  const result = await fetchInterviewTranscriptEntries('unit-test-access-token', 'session-1', {
    backendUrl: 'http://localhost:8000',
    fetchImpl: async (url, init) => {
      assert.equal(url, 'http://localhost:8000/api/interview-sessions/session-1/transcript-entries?limit=100&page=1')
      assert.equal(init.method, 'GET')
      assert.equal(init.headers.Authorization, 'Bearer unit-test-access-token')
      return {
        ok: true,
        json: async () => ({
          items: [
            null,
            {},
            { id: 'missing-session', turn_index: 1 },
            { id: 'bad-turn', session_id: 'session-1', turn_index: 0 },
            {
              id: 'entry-1',
              session_id: 'session-1',
              turn_index: 1,
              source: 'chat',
              question_text: 'What is FastAPI authentication?',
              answer_text: 'It uses dependency-based auth checks.',
              category: 'technical',
              provider: 'openai',
              model: 'gpt-test',
              generation_ms: 123,
              created_at: '2026-08-29T10:30:00Z',
            },
          ],
          limit: 100,
          page: 1,
        }),
      }
    },
  })

  assert.deepEqual(result, {
    items: [
      {
        id: 'entry-1',
        session_id: 'session-1',
        turn_index: 1,
        source: 'chat',
        question_text: 'What is FastAPI authentication?',
        answer_text: 'It uses dependency-based auth checks.',
        category: 'technical',
        provider: 'openai',
        model: 'gpt-test',
        generation_ms: 123,
        created_at: '2026-08-29T10:30:00Z',
      },
    ],
    limit: 100,
    page: 1,
  })
})


test('downloadInterviewTranscript uses authenticated download route and safe filename', async () => {
  const result = await downloadInterviewTranscript('unit-test-access-token', 'session-1', 'md', {
    backendUrl: 'http://localhost:8000',
    fetchImpl: async (url, init) => {
      assert.equal(url, 'http://localhost:8000/api/interview-sessions/session-1/transcript/download?format=md')
      assert.equal(init.method, 'GET')
      assert.equal(init.headers.Authorization, 'Bearer unit-test-access-token')
      return {
        ok: true,
        headers: {
          get(name) {
            return name.toLowerCase() === 'content-disposition'
              ? 'attachment; filename="interview-session-transcript.md"'
              : null
          },
        },
        text: async () => '# Interview Transcript\n',
      }
    },
  })

  assert.deepEqual(result, {
    filename: 'interview-session-transcript.md',
    content: '# Interview Transcript\n',
    format: 'md',
  })
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

import assert from 'node:assert/strict'
import test from 'node:test'

import { bootstrapProfile, fetchCurrentUser } from './authApi.js'
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

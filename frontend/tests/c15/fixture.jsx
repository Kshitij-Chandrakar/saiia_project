import React from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import WebsiteSettings, { PrivacyStatus } from '../../src/auth/WebsiteSettings'
import PrivacyExport from '../../src/auth/PrivacyExport'
let listener
const user = { id: '10000000-0000-4000-8000-000000000001', email: 'candidate@example.invalid', app_metadata: { providers: location.search.includes('google') ? ['google'] : ['email'] } }
const session = { user, access_token: 'synthetic-ui-only' }
const client = { auth: {
  storageKey: 'sb-synthetic-auth-token',
  mfa: {
    listFactors: async () => ({ data: { totp: location.search.includes('factor') ? [{ id: 'synthetic-factor', status: 'verified' }] : [] } }),
    challengeAndVerify: async ({ code }) => ({ error: code === '123456' ? null : new Error('synthetic code rejected') }),
  },
  getSession: async () => ({ data: { session } }),
  onAuthStateChange(callback) { listener = callback; return { data: { subscription: { unsubscribe() {} } } } },
  signInWithPassword: async () => location.search.includes('wrong-password') ? { data: {}, error: new Error('synthetic rejected') } : ({ data: { session: location.search.includes('wrong-account') ? { ...session, user: { id: 'other' } } : session } }),
  signOut: async () => { sessionStorage.setItem('synthetic-provider-logout', 'called'); listener?.('SIGNED_OUT', null); return {} },
} }
window.switchSyntheticAccount = () => listener('SIGNED_IN', { user: { id: 'other' } })
createRoot(document.getElementById('root')).render(<BrowserRouter><Routes>
  <Route path="/auth/export-fixture" element={<main style={{ maxWidth: 850, margin: '24px auto', padding: 16 }}><h1>Privacy controls · synthetic local preview</h1><PrivacyExport user={user} client={client} enabled={!location.search.includes('disabled')} /></main>} />
  <Route path="/auth/privacy-status" element={<PrivacyStatus />} />
  <Route path="*" element={<WebsiteSettings user={user} client={client} enabled={!location.search.includes('disabled')} />} />
</Routes></BrowserRouter>)

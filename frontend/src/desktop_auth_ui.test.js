import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { getDesktopAuthViewModel } from './desktop_auth_ui.js'

const diagnosticsSource = readFileSync(new URL('./components/MainDiagnosticsWindow.jsx', import.meta.url), 'utf8')
const preloadSource = readFileSync(new URL('../electron/preload.cjs', import.meta.url), 'utf8')

function desktopAuthStatusSource() {
  const start = diagnosticsSource.indexOf('function DesktopAuthStatus()')
  const end = diagnosticsSource.indexOf('function getReadableErrorAction', start)
  assert.ok(start >= 0)
  assert.ok(end > start)
  return diagnosticsSource.slice(start, end)
}

test('desktop auth signed-out state renders login action', () => {
  const model = getDesktopAuthViewModel({ status: 'signed-out' })

  assert.equal(model.label, 'Signed out')
  assert.equal(model.showLogin, true)
  assert.equal(model.showLogout, false)
  assert.match(model.detail, /Local desktop tools remain available/)
})

test('desktop auth connected state renders safe email and logout action', () => {
  const model = getDesktopAuthViewModel({
    status: 'connected',
    user_id: 'user-1',
    email: 'candidate@example.com',
    access_token: 'must-not-render',
    refresh_token: 'must-not-render',
  })

  assert.equal(model.label, 'Connected')
  assert.equal(model.email, 'candidate@example.com')
  assert.equal(model.user_id, 'user-1')
  assert.equal(model.showLogin, false)
  assert.equal(model.showLogout, true)
  assert.equal(JSON.stringify(model).includes('must-not-render'), false)
})

test('desktop auth token-expired state does not show stale user', () => {
  const model = getDesktopAuthViewModel({
    status: 'token-expired',
    user_id: 'stale-user',
    email: 'stale@example.com',
  })

  assert.equal(model.label, 'Session expired')
  assert.equal(model.user_id, null)
  assert.equal(model.email, null)
  assert.equal(model.showLogin, true)
})

test('desktop auth signing-in state keeps login action disabled', () => {
  const model = getDesktopAuthViewModel({ status: 'signing-in' })

  assert.equal(model.label, 'Signing in')
  assert.equal(model.showLogin, true)
  assert.equal(model.loginDisabled, true)
})

test('desktop auth recoverable cloud states keep local desktop available', () => {
  for (const status of ['offline', 'backend-unavailable']) {
    const model = getDesktopAuthViewModel({ status })

    assert.match(model.detail, /Cloud temporarily unavailable/)
    assert.match(model.detail, /Local desktop tools remain available/)
    assert.equal(model.showRefresh, true)
    assert.equal(model.showLogout, true)
  }
})

test('desktop auth UI uses only safe preload auth methods', () => {
  const source = desktopAuthStatusSource()

  assert.match(source, /saiiaApi\?\.getAuthState/)
  assert.match(source, /saiiaApi\?\.startAuthLogin/)
  assert.match(source, /saiiaApi\?\.logoutAuth/)
  assert.match(source, /saiiaApi\?\.refreshCloudStartupContext/)
  assert.match(source, /runAuthAction\('login', saiiaApi\?\.startAuthLogin\)/)
  assert.match(source, /runAuthAction\('logout', saiiaApi\?\.logoutAuth\)/)
  assert.doesNotMatch(source, /supabase/i)
  assert.doesNotMatch(source, /fetch\(/)
  assert.doesNotMatch(source, /access_token|refresh_token|service_role|Authorization/)
})

test('desktop auth preload remains narrow and exposes no generic cloud fetch', () => {
  assert.match(preloadSource, /getAuthState: \(\) => ipcRenderer\.invoke\('auth:get-state'\)/)
  assert.match(preloadSource, /startAuthLogin: \(\) => ipcRenderer\.invoke\('auth:start-login'\)/)
  assert.match(preloadSource, /logoutAuth: \(\) => ipcRenderer\.invoke\('auth:logout'\)/)
  assert.match(preloadSource, /refreshCloudStartupContext: \(\) => ipcRenderer\.invoke\('cloud:refresh-startup-context'\)/)
  assert.doesNotMatch(preloadSource, /access_token|refresh_token|service_role|Authorization/)
  assert.doesNotMatch(preloadSource, /fetch:/)
})

test('desktop auth wiring leaves local no-auth controls available', () => {
  assert.match(diagnosticsSource, /<DesktopAuthStatus \/>/)
  assert.match(diagnosticsSource, /Setup Profile/)
  assert.match(diagnosticsSource, /Start Recording \(Fallback\)/)
  assert.match(diagnosticsSource, /Analyze Active Window/)
})

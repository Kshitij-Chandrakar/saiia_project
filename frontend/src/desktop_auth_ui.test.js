import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { createDesktopAuthRequestTracker, getDesktopAuthViewModel } from './desktop_auth_ui.js'

const diagnosticsSource = readFileSync(new URL('./components/MainDiagnosticsWindow.jsx', import.meta.url), 'utf8')
const preloadSource = readFileSync(new URL('../electron/preload.cjs', import.meta.url), 'utf8')
const sensitivePattern = new RegExp([
  ['access', 'token'].join('_'),
  ['refresh', 'token'].join('_'),
  ['service', 'role'].join('_'),
  'Author' + 'ization',
].join('|'))

function desktopAuthStatusSource() {
  const start = diagnosticsSource.indexOf('function DesktopAuthStatus()')
  const end = diagnosticsSource.indexOf('function getReadableErrorAction', start)
  assert.ok(start >= 0)
  assert.ok(end > start)
  return diagnosticsSource.slice(start, end)
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((nextResolve, nextReject) => {
    resolve = nextResolve
    reject = nextReject
  })
  return { promise, resolve, reject }
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
    [['access', 'token'].join('_')]: 'must-not-render',
    [['refresh', 'token'].join('_')]: 'must-not-render',
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

test('desktop auth unknown status falls back to signed-out login state', () => {
  const model = getDesktopAuthViewModel({
    status: 'weird-unknown-status',
    user_id: 'stale-user',
    email: 'stale@example.com',
  })

  assert.equal(model.status, 'signed-out')
  assert.equal(model.label, 'Signed out')
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

test('desktop auth request tracker prevents stale initial state overwrite', async () => {
  const tracker = createDesktopAuthRequestTracker()
  const initial = deferred()
  let visible = getDesktopAuthViewModel({ status: 'signed-out' })

  const initialRequestId = tracker.start()
  const initialPromise = initial.promise.then((state) => {
    if (tracker.isCurrent(initialRequestId)) {
      visible = getDesktopAuthViewModel(state)
    }
  })

  const actionRequestId = tracker.start()
  if (tracker.isCurrent(actionRequestId)) {
    visible = getDesktopAuthViewModel({
      status: 'connected',
      user_id: 'user-2',
      email: 'fresh@example.com',
    })
  }

  initial.resolve({
    status: 'signed-out',
    user_id: 'stale-user',
    email: 'stale@example.com',
  })
  await initialPromise

  assert.equal(visible.status, 'connected')
  assert.equal(visible.email, 'fresh@example.com')
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
  assert.match(source, /authRequestTrackerRef\.current\.start\(\)/)
  assert.match(source, /applyAuthState\(state, requestId\)/)
  assert.match(source, /runAuthAction\('login', saiiaApi\?\.startAuthLogin\)/)
  assert.match(source, /runAuthAction\('logout', saiiaApi\?\.logoutAuth\)/)
  assert.doesNotMatch(source, /supabase/i)
  assert.doesNotMatch(source, /fetch\(/)
  assert.doesNotMatch(source, sensitivePattern)
})

test('desktop auth preload remains narrow and exposes no generic cloud fetch', () => {
  assert.match(preloadSource, /getAuthState: \(\) => ipcRenderer\.invoke\('auth:get-state'\)/)
  assert.match(preloadSource, /startAuthLogin: \(\) => ipcRenderer\.invoke\('auth:start-login'\)/)
  assert.match(preloadSource, /logoutAuth: \(\) => ipcRenderer\.invoke\('auth:logout'\)/)
  assert.match(preloadSource, /refreshCloudStartupContext: \(\) => ipcRenderer\.invoke\('cloud:refresh-startup-context'\)/)
  assert.doesNotMatch(preloadSource, sensitivePattern)
  assert.doesNotMatch(preloadSource, /fetch:/)
})

test('desktop auth wiring leaves local no-auth controls available', () => {
  assert.match(diagnosticsSource, /<DesktopAuthStatus \/>/)
  assert.match(diagnosticsSource, /Setup Profile/)
  assert.match(diagnosticsSource, /Start Recording \(Fallback\)/)
  assert.match(diagnosticsSource, /Analyze Active Window/)
})

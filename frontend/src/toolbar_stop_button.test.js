import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createOverlayAuthStateTracker } from './overlay_auth_state_tracker.js'

function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

test('floating toolbar places Stop between Chat and timer', () => {
  const source = readFileSync(new URL('./components/OverlayWindow.jsx', import.meta.url), 'utf8')

  const chatIndex = source.indexOf('label="Chat"')
  const stopIndex = source.indexOf("triggerToolbarAction('stop-active-operation')")
  const timerIndex = source.indexOf('topbar-toolbar-time')

  assert.ok(chatIndex > 0)
  assert.ok(stopIndex > chatIndex)
  assert.ok(timerIndex > stopIndex)
})

test('stop button uses the red circular toolbar class and icon', () => {
  const source = readFileSync(new URL('./components/OverlayWindow.jsx', import.meta.url), 'utf8')
  const styles = readFileSync(new URL('./styles/glass.css', import.meta.url), 'utf8')

  assert.match(source, /className="topbar-toolbar-stop-button no-drag"/)
  assert.match(source, /<Square size=\{10\}/)
  assert.match(styles, /\.topbar-toolbar-stop-button\s*\{[\s\S]*border-radius:\s*999px/)
  assert.match(styles, /\.topbar-toolbar-stop-button\s*\{[\s\S]*rgba\(239, 68, 68/)
})

test('stop action is non-destructive and separate from end session', () => {
  const source = readFileSync(new URL('./App.jsx', import.meta.url), 'utf8')
  const stopBranchIndex = source.indexOf("action === 'stop-active-operation'")
  const endBranchIndex = source.indexOf("action === 'end-session'")
  const stopFunctionStart = source.indexOf('const stopActiveOperation = () => {')
  const stopFunctionEnd = source.indexOf('const resetRuntimeForDesktopLogout = () => {')
  const stopFunction = source.slice(stopFunctionStart, stopFunctionEnd)

  assert.ok(stopBranchIndex > 0)
  assert.ok(endBranchIndex > stopBranchIndex)
  assert.match(stopFunction, /activeGenerateAbortControllerRef\.current\?\.abort\(\)/)
  assert.doesNotMatch(stopFunction, /clearAnswerState\(\)/)
  assert.doesNotMatch(stopFunction, /clearTranscriptState\(\)/)
})

test('runtime dropdown dashboard uses safe desktop opener and shows safe account email', () => {
  const source = readFileSync(new URL('./components/OverlayWindow.jsx', import.meta.url), 'utf8')
  const styles = readFileSync(new URL('./styles/glass.css', import.meta.url), 'utf8')

  assert.match(source, /window\.saiia\?\.openDashboard\?\.\(\)/)
  assert.match(source, /onClick=\{handleOpenDashboard\}/)
  assert.doesNotMatch(source, /onClick=\{\(\) => window\.electronAPI\?\.openMainPanel/)
  assert.match(source, /window\.saiia\?\.getAuthState\?\.\(\)/)
  assert.match(source, /safeAuthState\.status === 'connected'/)
  assert.match(source, /safeAuthState\.email \|\| 'Signed in'/)
  assert.match(source, /topbar-menu__account/)
  assert.match(styles, /\.topbar-menu__account\s*\{[\s\S]*text-overflow:\s*ellipsis/)
})

test('runtime dropdown auth state ignores stale responses after logout', async () => {
  const appliedStates = []
  const tracker = createOverlayAuthStateTracker((state) => {
    appliedStates.push(state)
  })
  const signedInRequest = deferred()
  const signedOutRequest = deferred()

  const signedInRefresh = tracker.refresh(() => signedInRequest.promise)
  const signedOutRefresh = tracker.refresh(() => signedOutRequest.promise)

  signedOutRequest.resolve({ status: 'signed-out', email: null })
  assert.equal(await signedOutRefresh, true)
  assert.deepEqual(appliedStates.at(-1), { status: 'signed-out', email: null })

  signedInRequest.resolve({ status: 'connected', email: 'old-user@example.com' })
  assert.equal(await signedInRefresh, false)
  assert.deepEqual(appliedStates.at(-1), { status: 'signed-out', email: null })

  const pendingBeforeLogout = deferred()
  const pendingRefresh = tracker.refresh(() => pendingBeforeLogout.promise)
  tracker.clear()
  assert.deepEqual(appliedStates.at(-1), { status: 'signed-out', email: null })

  pendingBeforeLogout.resolve({ status: 'connected', email: 'late-user@example.com' })
  assert.equal(await pendingRefresh, false)
  assert.deepEqual(appliedStates.at(-1), { status: 'signed-out', email: null })
})

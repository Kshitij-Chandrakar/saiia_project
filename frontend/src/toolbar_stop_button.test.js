import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

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
  const stopFunctionEnd = source.indexOf('const applyRefinedAnswer = () => {')
  const stopFunction = source.slice(stopFunctionStart, stopFunctionEnd)

  assert.ok(stopBranchIndex > 0)
  assert.ok(endBranchIndex > stopBranchIndex)
  assert.match(stopFunction, /activeGenerateAbortControllerRef\.current\?\.abort\(\)/)
  assert.doesNotMatch(stopFunction, /clearAnswerState\(\)/)
  assert.doesNotMatch(stopFunction, /clearTranscriptState\(\)/)
})

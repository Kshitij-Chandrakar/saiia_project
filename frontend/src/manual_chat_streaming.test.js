import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const appSource = readFileSync(new URL('./App.jsx', import.meta.url), 'utf8')
const mainSource = readFileSync(new URL('../electron/main.cjs', import.meta.url), 'utf8')
const preloadSource = readFileSync(new URL('../electron/preload.cjs', import.meta.url), 'utf8')

test('selected-resume Chat uses the scoped desktop stream with buffered rollback', () => {
  assert.match(appSource, /window\.saiia\?\.startAnswerStream/)
  assert.match(appSource, /window\.saiia\?\.cancelAnswerStream/)
  assert.match(appSource, /desktopAnswerStreamHandlersRef\.current\.set/)
  assert.match(appSource, /publishAnswer\(accumulatedAnswer\)/)
  assert.match(appSource, /stream_incomplete/)
  assert.match(appSource, /pipelineStarted/)
  assert.match(appSource, /started\?\.reason === 'stream-unavailable'/)
  assert.match(appSource, /applyBufferedAnswer/)
})

test('desktop answer streaming stays on narrow validated IPC channels', () => {
  assert.match(preloadSource, /startAnswerStream: \(body\) => ipcRenderer\.invoke\('generate:answer:stream:start', body\)/)
  assert.match(preloadSource, /cancelAnswerStream: \(streamId\) => ipcRenderer\.invoke\('generate:answer:stream:cancel', streamId\)/)
  assert.match(preloadSource, /onAnswerStreamEvent: \(requestId, fn\) =>/)
  assert.match(mainSource, /ipcMain\.handle\('generate:answer:stream:start'/)
  assert.match(mainSource, /ipcMain\.handle\('generate:answer:stream:cancel'/)
  assert.match(mainSource, /generate:answer:stream:event/)
  assert.match(mainSource, /validateAuthIpc\(event\)/)
  assert.doesNotMatch(preloadSource, /fetch\s*:/)
})

test('desktop stream metadata excludes raw prompt and resume payload fields', () => {
  assert.match(mainSource, /SAFE_STREAM_METADATA_EXCLUSIONS/)
  assert.match(mainSource, /raw_prompt/)
  assert.match(mainSource, /raw_resume_text/)
  assert.match(mainSource, /resume_chunks/)
  assert.match(mainSource, /transcript_payload/)
  assert.match(mainSource, /coding_runtime_audit/)
})

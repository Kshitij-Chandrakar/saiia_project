import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('..', import.meta.url))
const runtimeDirs = ['core', 'extractors', 'schemas', 'popup', 'options']

function files(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) {
      return files(full)
    }
    return full
  })
}

test('extension code does not use eval, new Function, cookies, history, storage extraction, or arbitrary remote fetch', () => {
  const combined = [
    ...runtimeDirs.flatMap((dir) => files(join(root, dir))),
    join(root, 'service-worker.js'),
    join(root, 'content-script.js'),
    join(root, 'manifest.json'),
  ]
    .filter((file) => /\.(js|json|html)$/.test(file))
    .map((file) => readFileSync(file, 'utf8'))
    .join('\n')
  assert.doesNotMatch(combined, /\beval\s*\(/)
  assert.doesNotMatch(combined, /new\s+Function/)
  assert.doesNotMatch(combined, /chrome\.cookies|chrome\.history/)
  assert.doesNotMatch(combined, /localStorage|sessionStorage/)
  assert.doesNotMatch(combined, /\bfetch\s*\(/)
  assert.doesNotMatch(combined, /document\.documentElement\.outerHTML|document\.body\.innerHTML/)
})

test('popup renders extraction previews with textContent, not innerHTML', () => {
  const popup = readFileSync(new URL('../popup/popup.js', import.meta.url), 'utf8')
  assert.match(popup, /textContent/)
  assert.match(popup, /Array\.isArray\(question\?\.constraints\)/)
  assert.doesNotMatch(popup, /innerHTML/)
})

test('content script is guarded against duplicate listener injection', () => {
  const contentScript = readFileSync(new URL('../content-script.js', import.meta.url), 'utf8')
  assert.match(contentScript, /__SAIIA_C095_CONTENT_SCRIPT_READY__/)
  assert.match(contentScript, /return/)
})

test('core extractor has no platform-hostname branching', () => {
  const extractor = [
    readFileSync(new URL('../extractors/generic-extractor.js', import.meta.url), 'utf8'),
    readFileSync(new URL('../content-script.js', import.meta.url), 'utf8'),
  ].join('\n')
  assert.doesNotMatch(extractor, /hostname|hackerrank|leetcode|codechef|codeforces|geeksforgeeks|location\.href/i)
})

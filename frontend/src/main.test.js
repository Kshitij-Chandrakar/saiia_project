import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const source = readFileSync(new URL('./main.jsx', import.meta.url), 'utf8')
const appSource = readFileSync(new URL('./App.jsx', import.meta.url), 'utf8')

test('website router preserves the default admin error boundary and recognizes admin paths case-insensitively', () => {
  assert.match(source, /pathname\.toLowerCase\(\)\.startsWith\('\/auth\/admin\/'\)/)
  assert.match(source, /path: '\/auth\/admin\/\*',[\s\S]*element: <App \/>/)
  assert.match(source, /path: '\*',[\s\S]*errorElement: <WebsiteRenderFailure \/>/)
})

test('toolbar action subscription keeps one listener while using the latest handler', () => {
  assert.match(appSource, /const toolbarHandlerRef = useRef\(null\)/)
  assert.match(appSource, /toolbarHandlerRef\.current = async \(payload\) =>/)
  assert.match(appSource, /return window\.electronAPI\.onToolbarAction\(payload => toolbarHandlerRef\.current\?\.\(payload\)\)\s*\n {2}}, \[\]\)/)
})

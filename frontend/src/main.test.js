import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const source = readFileSync(new URL('./main.jsx', import.meta.url), 'utf8')
const appSource = readFileSync(new URL('./App.jsx', import.meta.url), 'utf8')

test('website router preserves the default admin error boundary and recognizes admin paths case-insensitively', () => {
  assert.match(source, /pathname\.toLowerCase\(\)\.startsWith\('\/auth\/admin\/'\)/)
  assert.match(source, /path: '\/auth\/admin\/subscriptions',[\s\S]*element: <SubscriptionAdmin backendUrl=\{BACKEND_URL\} \/>/)
  assert.match(source, /path: '\/auth\/admin\/billing',[\s\S]*element: <BillingAdmin backendUrl=\{BACKEND_URL\} \/>/)
  assert.match(source, /path: '\*',[\s\S]*errorElement: <WebsiteRenderFailure \/>/)
  assert.match(source, /onCaughtError\(error, info\) \{ if \(isAdminPath\(\)\) console\.error\(error, info\) \}/)
  assert.match(source, /const reportRouterError = \(error, \{ location \} = \{\}\) => \{[\s\S]*location\?\.pathname\.toLowerCase\(\)\.startsWith\('\/auth\/admin\/'\)/)
  assert.match(source, /<RouterProvider router=\{websiteRouter\} onError=\{reportRouterError\} \/>/)
})

test('toolbar action subscription keeps one listener while using the latest handler', () => {
  assert.match(appSource, /const toolbarHandlerRef = useRef\(null\)/)
  assert.match(appSource, /useLayoutEffect\(\(\) => \{\s*toolbarHandlerRef\.current = async \(payload\) =>/)
  assert.match(appSource, /return window\.electronAPI\.onToolbarAction\(payload => toolbarHandlerRef\.current\?\.\(payload\)\)\s*\n {2}}, \[\]\)/)
})

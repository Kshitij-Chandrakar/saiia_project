import test from 'node:test'
import assert from 'node:assert/strict'
import { containsPrototypeHostPermissions, getOriginFromUrl, isRestrictedUrl, OPTIONAL_ORIGINS, requestPrototypeHostPermissions } from '../core/permissions.js'

test('restricted pages are rejected', () => {
  for (const url of ['chrome://settings', 'edge://extensions', 'chrome-extension://abc/page.html', 'edge-extension://abc/page.html', 'devtools://x', 'view-source:https://example.test', 'file:///tmp/a.html']) {
    assert.equal(isRestrictedUrl(url), true)
  }
  assert.equal(isRestrictedUrl('https://example.test/problem'), false)
})

test('safe origin strips path, query, and fragment', () => {
  assert.equal(getOriginFromUrl('https://example.test/path?token=secret#frag'), 'https://example.test/*')
})

test('prototype host permission request uses optional http and https origins', async () => {
  const calls = []
  const chromeApi = {
    permissions: {
      request: async (payload) => {
        calls.push(payload)
        return true
      },
      contains: async (payload) => {
        calls.push(payload)
        return true
      },
    },
  }
  assert.equal(await requestPrototypeHostPermissions(chromeApi), true)
  assert.deepEqual(calls[0].origins, OPTIONAL_ORIGINS)
  assert.equal(await containsPrototypeHostPermissions(chromeApi), true)
})

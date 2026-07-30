import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const manifest = JSON.parse(readFileSync(new URL('../manifest.json', import.meta.url), 'utf8'))

test('manifest is MV3 with service worker and no static broad content scripts', () => {
  assert.equal(manifest.manifest_version, 3)
  assert.equal(manifest.background.service_worker, 'service-worker.js')
  assert.equal(manifest.background.type, 'module')
  assert.equal(manifest.background.persistent, undefined)
  assert.equal(manifest.content_scripts, undefined)
  assert.equal(manifest.update_url, undefined)
})

test('manifest permissions are minimal and optional host permissions are explicit', () => {
  assert.deepEqual(manifest.permissions.sort(), ['scripting', 'storage'])
  assert.deepEqual(manifest.optional_host_permissions.sort(), ['http://*/*', 'https://*/*'])
  for (const forbidden of ['cookies', 'history', 'bookmarks', 'downloads', 'webRequest', 'declarativeNetRequest', 'clipboardRead', 'browsingData', 'topSites', 'debugger', 'management', 'tabs']) {
    assert.ok(!manifest.permissions.includes(forbidden), `forbidden permission present: ${forbidden}`)
  }
})

test('extension pages use packaged scripts only', () => {
  const text = readFileSync(new URL('../manifest.json', import.meta.url), 'utf8')
  const scripts = [
    manifest.background.service_worker,
    manifest.action.default_popup,
    manifest.options_page,
  ].join('\n')
  assert.doesNotMatch(scripts, /https?:\/\//)
  assert.doesNotMatch(text, /cdn|eval|new Function/)
})

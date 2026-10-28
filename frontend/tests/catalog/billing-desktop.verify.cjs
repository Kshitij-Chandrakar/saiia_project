const assert = require('node:assert/strict')
const { DesktopAuthSessionManager, AUTH_STATUSES } = require('../../electron/desktop_auth_session.cjs')
const native = JSON.parse(process.env.BILLING_BROWSER_NATIVE)
const manager = new DesktopAuthSessionManager({backendUrl:native.url})
manager.session = {access_token:native.token}
manager.user = {user_id:native.account}
manager.status = AUTH_STATUSES.CONNECTED
;(async () => {
  const result = await manager.getSubscription()
  assert.equal(result.ok,true)
  assert.equal(result.plan.name,'Plus')
  assert.equal(result.checkout_ready,true)
  assert.equal(JSON.stringify(result).includes(native.token),false)
  manager._clearCloudCache()
  assert.equal(manager.pendingClipboardSave,null)
  process.stdout.write('Desktop account refresh verified\n')
})().catch(() => { process.stderr.write('Desktop account refresh failed\n'); process.exitCode=1 })

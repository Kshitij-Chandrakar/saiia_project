import test from 'node:test'
import assert from 'node:assert/strict'
import { signOutWebsite, createWebsiteSessionLoss, validWebsiteSessionLoss, clearCompletedWebsiteLogout, isIntentionalWebsiteLogout, watchWebsiteLogoutIntent } from './websiteSessionLoss.js'

const storage = new Map()
globalThis.window = { localStorage:{ getItem:key => storage.get(key) || null, setItem:(key,value) => storage.set(key,value), removeItem:key => storage.delete(key) } }

test('only provider expiry is classified; unknown loss is neutral and ordinary visitors have no notice', () => {
  storage.clear()
  assert.equal(createWebsiteSessionLoss(false), null)
  assert.equal(createWebsiteSessionLoss(true).reason, 'signed_out')
  assert.equal(createWebsiteSessionLoss(false, {code:'session_expired'}).reason, 'expired')
  for (const error of [{status:401},{status:403},{status:500},{code:'network_error'},{code:'request_timeout'},{code:'inactivity'}]) {
    assert.equal(createWebsiteSessionLoss(true,error),null)
  }
  assert.equal(createWebsiteSessionLoss(true,{code:'refresh_token_not_found'}).reason,'signed_out')
})

test('logout intent precedes provider sign-out, clears on failure and never contains sensitive data', async () => {
  storage.clear()
  const result = await signOutWebsite({ auth:{ signOut:async () => {
    assert.equal(isIntentionalWebsiteLogout(),true)
    assert.equal(createWebsiteSessionLoss(true),null)
    assert.deepEqual(Object.keys(JSON.parse([...storage.values()][0])).sort(),['at','id','phase'])
    return {error:null}
  } } })
  assert.equal(result.error,null)
  clearCompletedWebsiteLogout(); assert.equal(isIntentionalWebsiteLogout(),false)
  await signOutWebsite({auth:{signOut:async()=>({error:{message:'synthetic failure'}})}})
  assert.equal(isIntentionalWebsiteLogout(),false)
  await assert.rejects(signOutWebsite({auth:{signOut:async()=>{throw new Error('synthetic failure')}}}))
  assert.equal(isIntentionalWebsiteLogout(),false)
})

test('stale intents do not suppress new losses and unknown navigation reasons are rejected', () => {
  storage.set('intervucopilot.website-logout-intent',JSON.stringify({id:'stale',phase:'pending',at:Date.now()-120001}))
  assert.equal(isIntentionalWebsiteLogout(),false)
  assert.equal(createWebsiteSessionLoss(true).reason,'signed_out')
  assert.deepEqual(validWebsiteSessionLoss({id:'one-notice',reason:'expired',token:'must-not-be-copied'}),{id:'one-notice',reason:'expired'})
  assert.equal(validWebsiteSessionLoss({id:'one-notice',reason:'inactivity'}),null)
  assert.equal(validWebsiteSessionLoss({id:'<invalid>',reason:'expired'}),null)
})

test('unavailable cross-tab channels never block logout or guard mounting', async () => {
  storage.clear()
  window.BroadcastChannel = class { constructor() { throw new Error('Channel unavailable') } }
  try {
    watchWebsiteLogoutIntent()()
    assert.equal((await signOutWebsite({auth:{signOut:async()=>({error:null})}})).error,null)
    clearCompletedWebsiteLogout()
  } finally { delete window.BroadcastChannel }
})

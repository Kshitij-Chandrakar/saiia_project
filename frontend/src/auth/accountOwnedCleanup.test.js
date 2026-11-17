import assert from 'node:assert/strict'
import test from 'node:test'
import { clearAccountOwnedState } from './accountOwnedCleanup.js'

function storage(entries) {
  const map = new Map(Object.entries(entries))
  return { getItem: key => map.get(key) ?? null, removeItem: key => map.delete(key), map }
}
test('clears only attributable account data; preserves other accounts and legacy verifier', () => {
  const local = storage({ candidateProfile: JSON.stringify({ user_id: 'A', summary: 'private' }), 'sb-test-auth-token': JSON.stringify({ user: { id: 'B' } }), 'sb-test-auth-token-code-verifier': 'unowned', 'unrelated.preference': 'dark' })
  const session = storage({ 'billing.operation.A': 'old', 'billing.operation.B': 'other', 'intervucopilot.privacy-receipt': 'scoped-status' })
  const result = clearAccountOwnedState('A', 'a@example.invalid', 'sb-test-auth-token', local, session)
  assert.equal(local.getItem('candidateProfile'), null)
  assert.equal(JSON.parse(local.getItem('sb-test-auth-token')).user.id, 'B')
  assert.equal(session.getItem('billing.operation.B'), 'other')
  assert.equal(session.getItem('intervucopilot.privacy-receipt'), 'scoped-status')
  assert.equal(local.getItem('unrelated.preference'), 'dark')
  assert.deepEqual(result.preservedUnknown, ['legacy-pkce'])
})
test('owned Auth JSON is removed; untagged legacy content is preserved', () => {
  const local = storage({ candidateProfile: JSON.stringify({ summary: 'legacy shared profile' }), 'sb-test-auth-token': JSON.stringify({ user: { id: 'A' } }) })
  const result = clearAccountOwnedState('A', '', 'sb-test-auth-token', local, storage({}))
  assert.equal(local.getItem('sb-test-auth-token'), null)
  assert.notEqual(local.getItem('candidateProfile'), null)
  assert.ok(result.preservedUnknown.includes('profile'))
})
test('storage failures never turn unknown data into authority to wipe', () => {
  const denied = { getItem() { throw Error('unavailable') }, removeItem() { throw Error('unavailable') } }
  assert.doesNotThrow(() => clearAccountOwnedState('A', '', 'sb-test-auth-token', denied, denied))
})


test('throwing browser storage accessors return incomplete cleanup instead of throwing', () => {
  const descriptors = ['localStorage', 'sessionStorage'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)])
  try {
    for (const [key] of descriptors) Object.defineProperty(globalThis, key, { configurable: true, get() { throw Error('denied') } })
    const result = clearAccountOwnedState('A', '', 'sb-test-auth-token')
    assert.ok(result.preservedUnknown.includes('local-storage'))
    assert.ok(result.preservedUnknown.includes('session-storage'))
    assert.deepEqual(result.removed, [])
  } finally {
    for (const [key, descriptor] of descriptors) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor)
      else delete globalThis[key]
    }
  }
})

import test from 'node:test'
import assert from 'node:assert/strict'
import { customerError, customerWebsiteError } from './customerErrors.js'

test('unknown backend/provider messages never become customer copy', () => {
  for (const error of [new Error('private database details'), { status: 503, detail: 'private', message: 'private' }, null]) {
    assert.equal(customerError(error, 'Please try again.'), 'Please try again.')
  }
})

test('recognized codes and HTTP semantics have fixed safe customer wording', () => {
  assert.equal(customerError({ code: 'invalid_credentials', message: 'private' }), 'Invalid email or password.')
  assert.match(customerError({ code: 'weak_password', message: 'private' }), /stronger password/)
  assert.match(customerError({ status: 401 }), /sign in again/i)
  assert.match(customerError({ status: 403 }), /account/)
  assert.match(customerError({ status: 429 }), /Too many attempts/)
})

test('website normalization does not change Electron presentation', () => {
  const previous = globalThis.window
  try {
    globalThis.window = { electronAPI: {} }
    assert.equal(customerWebsiteError(new Error('desktop detail'), 'safe'), 'desktop detail')
    globalThis.window = {}
    assert.equal(customerWebsiteError(new Error('private'), 'safe'), 'safe')
  } finally { globalThis.window = previous }
})

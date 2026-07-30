import test from 'node:test'
import assert from 'node:assert/strict'

import { isCurrentRequest } from './request_state.js'

test('only the newest request may commit its question, answer, and category', () => {
  const latestRequestId = 'request-2'

  assert.equal(isCurrentRequest(latestRequestId, 'request-1'), false)
  assert.equal(isCurrentRequest(latestRequestId, 'request-2'), true)
})

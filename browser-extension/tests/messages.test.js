import test from 'node:test'
import assert from 'node:assert/strict'
import { createMessage, MESSAGE_TYPES, validateMessage } from '../core/messages.js'

test('valid status message passes', () => {
  assert.equal(validateMessage(createMessage(MESSAGE_TYPES.getStatus)).ok, true)
})

test('invalid message type, missing protocol, bad IDs, and oversized messages fail', () => {
  assert.equal(validateMessage({ protocol_version: '1.0', type: 'NOPE', message_id: 'm1' }).ok, false)
  assert.equal(validateMessage({ type: MESSAGE_TYPES.getStatus, message_id: 'm1' }).error, 'invalid_protocol_version')
  const malformed = createMessage(MESSAGE_TYPES.testActiveTab, { operation_id: 'bad', request_id: 'bad' })
  assert.equal(validateMessage(malformed, { requireOperationIds: true }).ok, false)
  const huge = createMessage(MESSAGE_TYPES.getStatus, { payload: 'x'.repeat(40000) })
  assert.equal(validateMessage(huge).error, 'payload_too_large')
})

test('unknown commands fail safely', () => {
  assert.equal(validateMessage({ protocol_version: '1.0', type: 'UNKNOWN_COMMAND', message_id: 'm1' }).error, 'invalid_message')
})

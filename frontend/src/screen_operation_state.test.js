import test from 'node:test'
import assert from 'node:assert/strict'

import {
  SCREEN_OPERATION_STATUS,
  canCommitScreenResult,
  canCreateScreenHistory,
  cancelScreenOperation,
  createScreenOperation,
  isCurrentScreenOperation,
  supersedeScreenOperation,
  transitionScreenOperation,
} from './screen_operation_state.js'

function screenOperation(overrides = {}) {
  return createScreenOperation({
    sourceType: 'screen_capture',
    operationId: 'op_1',
    requestId: 'req_1',
    startedAt: 1,
    ...overrides,
  })
}

test('screen operation owns source, operation id, and request id', () => {
  const operation = screenOperation()

  assert.equal(operation.sourceType, 'screen_capture')
  assert.equal(operation.operationId, 'op_1')
  assert.equal(operation.requestId, 'req_1')
  assert.equal(operation.status, SCREEN_OPERATION_STATUS.CREATED)
  assert.equal(operation.isCurrent, true)
  assert.equal(operation.committed, false)
})

test('commit gate accepts only the current matching ready result once', () => {
  const operation = screenOperation()

  assert.equal(
    canCommitScreenResult({
      responseOperationId: 'op_1',
      responseRequestId: 'req_1',
      responseSourceType: 'screen_capture',
      responseStatus: 'ready',
      currentOperation: operation,
    }),
    true
  )
  assert.equal(
    canCreateScreenHistory({
      responseOperationId: 'op_1',
      responseRequestId: 'req_1',
      responseSourceType: 'screen_capture',
      responseStatus: 'ready',
      currentOperation: operation,
      committedOperationIds: new Set(['op_1']),
    }),
    false
  )
})

test('commit gate rejects stale, wrong-source, failed, empty, cancelled, and superseded results', () => {
  const operation = screenOperation()

  const cases = [
    { responseOperationId: 'op_old', responseRequestId: 'req_1', responseSourceType: 'screen_capture', responseStatus: 'ready' },
    { responseOperationId: 'op_1', responseRequestId: 'req_old', responseSourceType: 'screen_capture', responseStatus: 'ready' },
    { responseOperationId: 'op_1', responseRequestId: 'req_1', responseSourceType: 'browser_extension', responseStatus: 'ready' },
    { responseOperationId: 'op_1', responseRequestId: 'req_1', responseSourceType: 'screen_capture', responseStatus: 'failed' },
    { responseOperationId: 'op_1', responseRequestId: 'req_1', responseSourceType: 'screen_capture', responseStatus: 'ready', hasUsableResult: false },
  ]

  for (const item of cases) {
    assert.equal(canCommitScreenResult({ currentOperation: operation, ...item }), false)
  }

  assert.equal(
    canCommitScreenResult({
      responseOperationId: 'op_1',
      responseRequestId: 'req_1',
      responseSourceType: 'screen_capture',
      responseStatus: 'ready',
      currentOperation: cancelScreenOperation(operation),
    }),
    false
  )
  assert.equal(
    canCommitScreenResult({
      responseOperationId: 'op_1',
      responseRequestId: 'req_1',
      responseSourceType: 'screen_capture',
      responseStatus: 'ready',
      currentOperation: supersedeScreenOperation(operation, 'op_2'),
    }),
    false
  )
})

test('extension unavailable remains a failed browser-extension operation with no OCR commit', () => {
  const operation = createScreenOperation({
    sourceType: 'browser_extension',
    operationId: 'op_extension',
    requestId: 'req_extension',
    startedAt: 1,
  })
  const failed = transitionScreenOperation(operation, SCREEN_OPERATION_STATUS.FAILED, {
    error: 'Browser extension connection is not available yet.',
    isCurrent: false,
  })

  assert.equal(failed.sourceType, 'browser_extension')
  assert.equal(failed.status, SCREEN_OPERATION_STATUS.FAILED)
  assert.equal(failed.isCurrent, false)
  assert.equal(
    canCommitScreenResult({
      responseOperationId: 'op_extension',
      responseRequestId: 'req_extension',
      responseSourceType: 'browser_extension',
      responseStatus: 'failed',
      currentOperation: failed,
    }),
    false
  )
})

test('operation currentness changes after cancel and supersede', () => {
  const operation = screenOperation()
  assert.equal(isCurrentScreenOperation(operation, operation), true)
  assert.equal(isCurrentScreenOperation(cancelScreenOperation(operation), operation), false)
  assert.equal(isCurrentScreenOperation(supersedeScreenOperation(operation, 'op_2'), operation), false)
})

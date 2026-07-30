export const SCREEN_OPERATION_STATUS = Object.freeze({
  IDLE: 'idle',
  CREATED: 'created',
  CAPTURING: 'capturing',
  EXTRACTING: 'extracting',
  PROCESSING: 'processing',
  READY: 'ready',
  FAILED: 'failed',
  CANCELLED: 'cancelled',
  SUPERSEDED: 'superseded',
})

const FINAL_STATUSES = new Set([
  SCREEN_OPERATION_STATUS.READY,
  SCREEN_OPERATION_STATUS.FAILED,
  SCREEN_OPERATION_STATUS.CANCELLED,
  SCREEN_OPERATION_STATUS.SUPERSEDED,
])

export function createScreenOperation({
  sourceType,
  operationId = createScreenOpaqueId('screen_operation'),
  requestId = createScreenOpaqueId('screen_request'),
  startedAt = nowMs(),
} = {}) {
  return {
    operationId,
    requestId,
    sourceType,
    status: SCREEN_OPERATION_STATUS.CREATED,
    startedAt,
    completedAt: null,
    error: null,
    isCurrent: true,
    isCancelled: false,
    isSuperseded: false,
    committed: false,
    supersededByOperationId: '',
    cancellationReason: '',
  }
}

export function supersedeScreenOperation(operation, supersededByOperationId) {
  if (!operation || FINAL_STATUSES.has(operation.status)) {
    return operation
  }
  return {
    ...operation,
    status: SCREEN_OPERATION_STATUS.SUPERSEDED,
    completedAt: nowMs(),
    isCurrent: false,
    isSuperseded: true,
    supersededByOperationId: String(supersededByOperationId || ''),
  }
}

export function transitionScreenOperation(operation, status, patch = {}) {
  if (!operation) {
    return operation
  }
  if (FINAL_STATUSES.has(operation.status) && operation.status !== status) {
    return operation
  }
  const isFinal = FINAL_STATUSES.has(status)
  return {
    ...operation,
    ...patch,
    status,
    completedAt: isFinal ? patch.completedAt ?? nowMs() : operation.completedAt,
    isCancelled: status === SCREEN_OPERATION_STATUS.CANCELLED || Boolean(patch.isCancelled),
    isSuperseded: status === SCREEN_OPERATION_STATUS.SUPERSEDED || Boolean(patch.isSuperseded),
  }
}

export function cancelScreenOperation(operation, reason = 'operation_cancelled') {
  if (!operation) {
    return operation
  }
  if (operation.status === SCREEN_OPERATION_STATUS.CANCELLED) {
    return operation
  }
  return transitionScreenOperation(operation, SCREEN_OPERATION_STATUS.CANCELLED, {
    error: reason,
    isCurrent: false,
    cancellationReason: reason,
  })
}

export function isCurrentScreenOperation(currentOperation, operation) {
  return Boolean(
    currentOperation &&
      operation &&
      currentOperation.operationId === operation.operationId &&
      currentOperation.requestId === operation.requestId &&
      currentOperation.isCurrent &&
      !currentOperation.isCancelled &&
      !currentOperation.isSuperseded
  )
}

export function canCommitScreenResult({
  responseOperationId,
  responseRequestId,
  responseSourceType,
  responseStatus,
  currentOperation,
  committedOperationIds = new Set(),
  hasUsableResult = true,
} = {}) {
  return Boolean(
    currentOperation &&
      currentOperation.isCurrent &&
      !currentOperation.isCancelled &&
      !currentOperation.isSuperseded &&
      !committedOperationIds.has(currentOperation.operationId) &&
      currentOperation.operationId === responseOperationId &&
      currentOperation.requestId === responseRequestId &&
      currentOperation.sourceType === responseSourceType &&
      responseStatus === 'ready' &&
      hasUsableResult
  )
}

export function canCreateScreenHistory(options = {}) {
  return canCommitScreenResult(options)
}

export function createScreenOpaqueId(prefix = 'screen_id') {
  const uuid = globalThis.crypto?.randomUUID?.()
  if (uuid) {
    return `${prefix}_${uuid}`
  }
  const bytes = new Uint8Array(16)
  globalThis.crypto?.getRandomValues?.(bytes)
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
  return `${prefix}_${hex || Math.random().toString(16).slice(2)}`
}

function nowMs() {
  return globalThis.performance?.now?.() ?? Date.now()
}

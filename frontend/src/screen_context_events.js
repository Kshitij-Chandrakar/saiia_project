// Validate against a fresh main snapshot before displaying an asynchronously delivered result.
export function screenContextCommandFence(status) {
  return { runtimeSessionId: status.runtimeSessionId, generation: status.generation, threadId: status.threadId,
    revision: status.revision, requestId: status.identity?.requestId ?? null }
}

export function isCurrentScreenDelivery(delivery, current) {
  const identity = delivery?.identity
  return Boolean(identity && current && Number.isSafeInteger(delivery.revision) && delivery.revision <= current.revision &&
    identity.runtimeSessionId === current.runtimeSessionId && identity.generation === current.generation &&
    identity.accountGeneration === current.accountGeneration && identity.cloudSessionId === current.cloudSessionId &&
    identity.threadId === current.threadId && delivery.revision === identity.baseRevision + 1)
}

export function isCurrentScreenContextEvent(event, current) {
  return Boolean(event && current && event.sequence === current.sequence &&
    event.generation === current.generation && event.threadId === current.threadId &&
    event.runtimeSessionId === current.runtimeSessionId && event.accountGeneration === current.accountGeneration &&
    event.cloudSessionId === current.cloudSessionId && event.revision === current.revision &&
    ((!event.identity && !current.identity) || (event.identity && current.identity &&
      Object.keys(current.identity).every(key => event.identity[key] === current.identity[key]))))
}

export function screenContextDisplayPayload(result) {
  const first = result.items[0]
  return { ok: true, answer: result.answer, question: result.items.map(item => item.question).join('\n\n'),
    items: result.items, question_count: result.items.length, result_mode: result.items.length > 1 ? 'batch' : 'single',
    question_type: first.question_type, code: first.code, language: first.language,
    operation_id: result.identity.operationId, request_id: result.identity.requestId, source_type: 'screen_capture',
    contextIdentity: result.identity, screen_model_request_count: 1, generation_request_count: 0 }
}

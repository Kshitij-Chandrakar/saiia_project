const { createHash, randomUUID } = require('node:crypto')

const DEFAULT_LIMITS = Object.freeze({
  maxImages: 6,
  maxImageBytes: 10 * 1024 * 1024, // Existing backend screen-upload ceiling.
  maxPixels: 2200 * 2200, // Existing Electron capture maximum dimension.
  // ponytail: bound retained payload, not V8 heap; measure before increasing.
  maxRetainedBytes: 64 * 1024 * 1024,
})

function reject(code) {
  const error = new Error(code)
  error.code = code
  throw error
}

function id(value) {
  if (typeof value !== 'string' || !value.trim() || value.length > 160) reject('invalid_identity')
  return value
}

function createScreenContextController({ inspectImage, limits = {}, onBoundary = () => {} } = {}) {
  const budget = Object.freeze({ ...DEFAULT_LIMITS, ...limits })
  if (Object.keys(limits).some(key => !Object.hasOwn(DEFAULT_LIMITS, key)) ||
      Object.values(budget).some(value => !Number.isSafeInteger(value) || value <= 0)) reject('invalid_limits')
  let generation = 0
  let session = null
  let contextKind = 'question'
  let threadId = null
  let revision = 0
  let evidence = []
  let answers = []
  let images = new Map()
  let pending = null
  let retry = null
  let status = 'disposed'
  let errorCode = null
  let priorItems = []
  let clarifications = []
  let deliveries = []

  const payloadBytes = (items) => JSON.stringify(items).length * 2
  const retainedBytes = () => [...images.values()].reduce((sum, image) => sum + image.dataBase64.length * 2, 0) +
    [...evidence, ...answers, ...priorItems, ...clarifications, ...deliveries].reduce((sum, item) => sum + payloadBytes(item), 0) +
    (pending?.clarificationResponse ? payloadBytes(pending.clarificationResponse) : retry?.clarificationResponse ? payloadBytes(retry.clarificationResponse) : 0)

  function metadata() {
    return Object.freeze({
      runtimeSessionId: session?.runtimeSessionId ?? null,
      accountGeneration: session?.accountGeneration ?? null,
      cloudSessionId: session?.cloudSessionId ?? null,
      generation, threadId, contextKind, revision, status, errorCode,
      evidenceCount: evidence.length, answerCount: answers.length,
      acceptedImageCount: new Set(evidence.map(item => item.imageHash)).size,
      retainedImageCount: images.size, retainedBytes: retainedBytes(),
      pendingTurnId: pending?.token.turnId ?? null,
      priorItems: priorItems.map(item => ({ ...item })),
      sourceTurns: evidence.map((item, index) => ({ turnId: item.turnId, number: index + 1 })),
      retryAvailable: Boolean(retry), limits: budget,
    })
  }

  function invalidate() {
    if (!session && status === 'disposed') return metadata()
    generation += 1 // Fence callbacks before releasing their inputs.
    session = null
    threadId = null
    contextKind = 'question'
    revision = 0
    pending = retry = null
    evidence = []
    answers = []
    images = new Map()
    priorItems = []; clarifications = []; deliveries = []
    status = 'disposed'
    errorCode = null
    onBoundary(metadata())
    return metadata()
  }

  function adoptSession({ runtimeSessionId, accountGeneration = null, cloudSessionId = null }) {
    id(runtimeSessionId)
    if (accountGeneration !== null && (!Number.isSafeInteger(accountGeneration) || accountGeneration < 0)) reject('invalid_identity')
    if (cloudSessionId !== null) id(cloudSessionId)
    if (session?.runtimeSessionId === runtimeSessionId && session.accountGeneration === accountGeneration &&
        session.cloudSessionId === cloudSessionId) return metadata()
    invalidate()
    session = Object.freeze({ runtimeSessionId, accountGeneration, cloudSessionId })
    status = 'empty'
    onBoundary(metadata())
    return metadata()
  }

  function pruneImages() {
    const used = new Set(evidence.map(item => item.imageHash))
    if (pending?.imageHash) used.add(pending.imageHash)
    if (retry?.imageHash) used.add(retry.imageHash)
    for (const hash of images.keys()) if (!used.has(hash)) images.delete(hash)
  }

  function tokenFor(turnId, operationId, requestId) {
    return Object.freeze({ ...session, generation, threadId, baseRevision: revision,
      turnId, operationId, requestId })
  }

  function current(token) {
    if (!session || !pending || !token || Object.keys(pending.token).some(key => token[key] !== pending.token[key]) ||
        token.generation !== generation || token.threadId !== threadId || token.baseRevision !== revision) reject('stale_attempt')
    return pending
  }

  function begin({ action, targetQuestionId = null, replacesTurnIds = [], operationId = randomUUID(), requestId = randomUUID() }) {
    if (!session) reject('no_runtime_session')
    if (!['new', 'reference', 'continue'].includes(action)) reject('invalid_action')
    id(operationId)
    id(requestId)
    validateSelection(targetQuestionId, replacesTurnIds)
    if (action !== 'continue' && (targetQuestionId || replacesTurnIds.length)) reject('invalid_selection')
    if (action === 'continue') {
      if (pending) reject('operation_busy')
      if (!evidence.length) reject('no_accepted_context')
      if (evidence.length >= 32) reject('turn_count_limit')
    } else {
      contextKind = action === 'reference' ? 'reference' : 'question'
      threadId = randomUUID()
      revision = 0
      evidence = []
      answers = []
      images = new Map()
      priorItems = []; clarifications = []; deliveries = []
    }
    retry = null
    pending = { token: tokenFor(randomUUID(), operationId, requestId), imageHash: null, snapshot: null,
      action, targetQuestionId, replacesTurnIds: [...replacesTurnIds], clarificationResponse: null }
    pruneImages()
    status = 'capturing'
    errorCode = null
    return pending.token
  }

  function registerImage(token, buffer) {
    const attempt = current(token)
    if (attempt.imageHash || attempt.snapshot) reject('candidate_already_registered')
    if (!Buffer.isBuffer(buffer) || !buffer.length || buffer.length > budget.maxImageBytes) reject('invalid_image_size')
    const hash = createHash('sha256').update(buffer).digest('hex')
    if (!images.has(hash)) {
      if (images.size >= budget.maxImages) reject('image_count_limit')
      const encodedBytes = Math.ceil(buffer.length / 3) * 4 * 2
      if (retainedBytes() + encodedBytes > budget.maxRetainedBytes) reject('memory_limit')
      let size
      try { size = inspectImage?.(buffer) } catch { reject('invalid_image') }
      if (!size || !Number.isSafeInteger(size.width) || !Number.isSafeInteger(size.height) ||
          size.width <= 0 || size.height <= 0 || size.width * size.height > budget.maxPixels) reject('invalid_image')
      // Immutable image strings make request snapshots immutable too. No Buffer escapes.
      images.set(hash, Object.freeze({ imageHash: hash, byteLength: buffer.length,
        width: size.width, height: size.height, dataBase64: buffer.toString('base64') }))
    }
    attempt.imageHash = hash
    status = 'captured'
    return metadata()
  }

  function prepareRequest(token) {
    const attempt = current(token)
    if (!attempt.imageHash) reject('no_candidate_image')
    if (!attempt.snapshot) {
      attempt.snapshot = Object.freeze({
        evidence: Object.freeze([...evidence]), answers: Object.freeze([...answers]), clarifications: Object.freeze([...clarifications]),
        images: Object.freeze([...images.values()]), currentImageHash: attempt.imageHash,
      })
    }
    status = 'processing'
    return Object.freeze({ identity: attempt.token, input: attempt.snapshot, action: attempt.action, contextKind,
      priorItems: Object.freeze(priorItems.map(item => Object.freeze({ ...item }))),
      targetQuestionId: attempt.targetQuestionId, replacesTurnIds: Object.freeze([...attempt.replacesTurnIds]),
      clarificationResponse: attempt.clarificationResponse })
  }

  function validateSelection(target, turns) {
    if (target !== null && !priorItems.some(item => item.questionId === target)) reject('invalid_selection')
    if (!Array.isArray(turns) || turns.length > 32 || new Set(turns).size !== turns.length ||
        turns.some(turn => !evidence.some(item => item.turnId === turn))) reject('invalid_selection')
  }

  function commit(token, result, withAnswer, items = [], provenance = null, delivery = null) {
    const attempt = current(token)
    if (!attempt.imageHash || !attempt.snapshot || result?.validated !== true ||
        Object.keys(result).some(key => !['validated', 'evidence', 'answer'].includes(key)) ||
        !result.evidence || Object.keys(result.evidence).some(key => !['text', 'complete'].includes(key)) ||
        typeof result.evidence.text !== 'string' || !result.evidence.text.trim() ||
        Array.from(result.evidence.text).length > 24000 ||
        typeof result.evidence.complete !== 'boolean' ||
        result.evidence.complete !== withAnswer ||
        (withAnswer && (typeof result.answer !== 'string' || !result.answer.trim() || Array.from(result.answer).length > 24000)) ||
        (!withAnswer && Object.hasOwn(result, 'answer'))) reject('invalid_result')
    if (provenance !== null && (typeof provenance !== 'object' || Array.isArray(provenance) || Object.keys(provenance).length !== 2 ||
        Object.keys(provenance).some(key => !['imageHashes', 'replacesTurnIds'].includes(key)) ||
        JSON.stringify(provenance.replacesTurnIds) !== JSON.stringify(attempt.replacesTurnIds))) reject('invalid_result')
    const hashes = provenance === null ? [attempt.imageHash] : provenance.imageHashes
    if (!Array.isArray(hashes) || !hashes.includes(attempt.imageHash) || new Set(hashes).size !== hashes.length ||
        hashes.some(hash => !attempt.snapshot.images.some(image => image.imageHash === hash))) reject('invalid_result')
    const nextEvidence = Object.freeze({ ...result.evidence, imageHash: attempt.imageHash, turnId: token.turnId,
      kind: attempt.action === 'reference' ? 'reference' : 'question', imageHashes: Object.freeze([...hashes]),
      replacesTurnIds: Object.freeze([...attempt.replacesTurnIds]) })
    const nextAnswer = withAnswer ? Object.freeze({ text: result.answer, turnId: token.turnId }) : null
    const nextItems = [...priorItems]
    if (!Array.isArray(items) || items.length > 20 || (!withAnswer && items.length)) reject('invalid_result')
    for (const item of items) {
      if (!item || Object.keys(item).some(key => !['questionId', 'turnId', 'index'].includes(key)) ||
          !Number.isInteger(item.index) || item.index < 1 || item.index > 20 ||
          item.questionId !== `${item.turnId}:${item.index}` ||
          (item.turnId !== token.turnId && !priorItems.some(old => old.questionId === item.questionId))) reject('invalid_result')
      if (!nextItems.some(old => old.questionId === item.questionId)) nextItems.push(Object.freeze({ ...item }))
    }
    if (nextItems.length > 20) reject('item_count_limit')
    if (delivery !== null && (!withAnswer || !delivery || typeof delivery !== 'object' ||
        delivery.answer !== result.answer || !Array.isArray(delivery.items) || !delivery.items.length || delivery.items.length > 20)) reject('invalid_result')
    const nextDelivery = delivery === null ? null : Object.freeze({ identity: token, revision: revision + 1,
      answer: delivery.answer, items: Object.freeze(delivery.items.map(item => Object.freeze({ ...item }))) })
    if (nextDelivery && (!withAnswer || nextDelivery.answer !== result.answer || deliveries.length >= 32)) reject('invalid_result')
    const extraBytes = payloadBytes(nextEvidence) + (nextAnswer ? payloadBytes(nextAnswer) : 0) + payloadBytes(nextItems) +
      (nextDelivery ? payloadBytes(nextDelivery) : 0) +
      (attempt.clarificationResponse ? payloadBytes(attempt.clarificationResponse) : 0) + 4
    if (retainedBytes() + extraBytes > budget.maxRetainedBytes) reject('memory_limit')
    evidence.push(nextEvidence)
    if (nextAnswer) answers.push(nextAnswer)
    priorItems = nextItems
    if (attempt.clarificationResponse) clarifications.push(attempt.clarificationResponse)
    if (nextDelivery) deliveries.push(nextDelivery)
    // Deliberate append-only log: exactly one source record and revision per accepted turn.
    revision += 1
    pending = retry = null
    status = withAnswer ? 'answered' : 'collecting'
    errorCode = null
    return metadata()
  }

  function fail(token, { retryable = false } = {}) {
    const attempt = current(token)
    if (retryable && attempt.imageHash) {
      prepareRequest(token)
      retry = attempt
    } else retry = null
    pending = null
    pruneImages()
    status = 'failed'
    errorCode = 'attempt_failed'
    return metadata()
  }

  function cancel(token) {
    current(token)
    pending = retry = null
    pruneImages()
    status = 'cancelled'
    errorCode = 'attempt_cancelled'
    return metadata()
  }

  function retryTurn() {
    const requestId = randomUUID()
    if (pending) reject('operation_busy')
    if (!retry || !session || retry.token.generation !== generation || retry.token.baseRevision !== revision ||
        retry.token.threadId !== threadId) reject('retry_unavailable')
    pending = { ...retry, token: tokenFor(retry.token.turnId, retry.token.operationId, requestId) }
    retry = null
    status = 'processing'
    errorCode = null
    return pending.token
  }

  function cancelRetry() {
    retry = null
    pruneImages()
    return metadata()
  }

  function acknowledge(identity) {
    const index = deliveries.findIndex(item => item.identity.requestId === identity?.requestId &&
      Object.keys(item.identity).length === Object.keys(identity).length && Object.keys(item.identity).every(key => item.identity[key] === identity[key]))
    if (index < 0) return false
    deliveries.splice(index, 1)
    return true
  }

  function resolveClarification({ requestId, targetQuestionId = null, replacesTurnIds = [], text = '' }) {
    if (!retry || retry.token.requestId !== requestId) reject('stale_clarification')
    validateSelection(targetQuestionId, replacesTurnIds)
    if (typeof text !== 'string' || Array.from(text).length > 2000 || (!text.trim() && !targetQuestionId && !replacesTurnIds.length)) reject('invalid_clarification')
    const reply = Object.freeze({ requestId: retry.token.requestId, threadId: retry.token.threadId,
      turnId: retry.token.turnId, text: text.trim() || 'Use the explicitly selected question and replacement sources.' })
    if (retainedBytes() + payloadBytes(reply) > budget.maxRetainedBytes) reject('memory_limit')
    const token = retryTurn()
    pending.targetQuestionId = targetQuestionId || pending.targetQuestionId
    pending.replacesTurnIds = [...new Set([...pending.replacesTurnIds, ...replacesTurnIds])]
    pending.clarificationResponse = reply
    return token
  }

  return Object.freeze({ adoptSession, begin, registerImage, prepareRequest,
    commitEvidence: (token, result, provenance) => commit(token, result, false, [], provenance),
    commitAnswer: (token, result, items, provenance, delivery) => commit(token, result, true, items, provenance, delivery),
    deliveries: () => [...deliveries], acknowledge,
    fail, cancel, retryTurn, resolveClarification, cancelRetry, invalidate, dispose: invalidate, metadata })
}

module.exports = { createScreenContextController, DEFAULT_LIMITS }

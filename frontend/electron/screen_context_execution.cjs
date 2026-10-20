const { randomUUID } = require('node:crypto')

const MAX_IMAGES_BYTES = 24 * 1024 * 1024
const MAX_BODY_BYTES = 25 * 1024 * 1024
const safeId = value => typeof value === 'string' && /^[A-Za-z0-9_.:-]{1,164}$/.test(value)
const fail = (code, fieldPath = null) => { throw Object.assign(new Error(code), { code, fieldPath }) }
const exact = (value, keys) => value && typeof value === 'object' && !Array.isArray(value) &&
  Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key))
const bounded = (value, max, nonempty = false) => typeof value === 'string' && Array.from(value).length <= max && (!nonempty || value.trim())

function awaitAttempt(promise, signal, discard = () => {}) {
  return new Promise((resolve, reject) => {
    const aborted = () => reject(Object.assign(new Error('attempt_cancelled'), { code: 'attempt_cancelled' }))
    signal.addEventListener('abort', aborted, { once: true })
    if (signal.aborted) aborted()
    Promise.resolve(promise).then(value => {
      signal.removeEventListener('abort', aborted)
      if (signal.aborted) { try { discard(value) } catch {} return }
      resolve(value)
    }, error => { signal.removeEventListener('abort', aborted); reject(error) })
  })
}

function validateCommand(value, resolution = false) {
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      Object.keys(value).some(key => !(resolution ? ['requestId', 'text', 'targetQuestionId', 'replacesTurnIds', 'expected'] : ['action', 'targetQuestionId', 'replacesTurnIds', 'commandId', 'expected']).includes(key)) ||
      (!resolution && !['new', 'reference', 'continue'].includes(value.action)) ||
      (value.targetQuestionId != null && !safeId(value.targetQuestionId)) ||
      (value.replacesTurnIds !== undefined && (!Array.isArray(value.replacesTurnIds) || value.replacesTurnIds.length > 32 || value.replacesTurnIds.some(id => !safeId(id)))) ||
      (resolution && (!safeId(value.requestId) || !bounded(value.text ?? '', 2000)))) fail('invalid_command')
  if (value.commandId !== undefined && !safeId(value.commandId)) fail('invalid_command')
  return value
}

function multipart(snapshot) {
  const { input, identity, ...sidecars } = snapshot
  const prior = new Set(input.evidence.map(item => item.imageHash))
  const context = { contractVersion: '1', sourceType: 'screen_capture', identity, ...sidecars,
    input: { evidence: input.evidence, answers: input.answers, clarifications: input.clarifications ?? [], currentImageHash: input.currentImageHash,
      images: input.images.map((image, index) => ({ imageHash: image.imageHash, part: `image_${index}`,
        role: image.imageHash === input.currentImageHash ? (prior.has(image.imageHash) ? 'prior_current' : 'current') : 'prior' })) } }
  const json = Buffer.from(JSON.stringify(context))
  if (json.length > 256 * 1024 || input.images.reduce((sum, image) => sum + image.byteLength, 0) > MAX_IMAGES_BYTES) fail('upload_limit')
  const boundary = `saiia-${randomUUID()}`
  const parts = [Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="context"\r\n\r\n`), json, Buffer.from('\r\n')]
  input.images.forEach((image, index) => {
    parts.push(Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="image_${index}"; filename="screen.png"\r\nContent-Type: image/png\r\n\r\n`),
      Buffer.from(image.dataBase64, 'base64'), Buffer.from('\r\n'))
  })
  parts.push(Buffer.from(`--${boundary}--\r\n`))
  if (parts.reduce((sum, part) => sum + part.length, 0) > MAX_BODY_BYTES) fail('upload_limit')
  return { body: Buffer.concat(parts), contentType: `multipart/form-data; boundary=${boundary}`, context }
}

function validateResponse(response, snapshot) {
  const keys = ['contractVersion', 'identity', 'outcome', 'committable', 'controllerResult', 'evidenceDelta', 'answer', 'items', 'missingDetails', 'conflicts', 'clarification', 'errorCode', 'metrics']
  if (!exact(response, keys) || response.contractVersion !== '1') fail('invalid_response', '<envelope>')
  if (!exact(response.identity, Object.keys(snapshot.identity)) ||
      Object.keys(snapshot.identity).some(key => response.identity[key] !== snapshot.identity[key])) fail('invalid_response', 'identity')
  if (!['answered', 'reference_accepted', 'needs_more_content', 'needs_clarification', 'failed'].includes(response.outcome) ||
      !bounded(response.answer, 24000) || !Array.isArray(response.items) || response.items.length > 20 ||
      ![response.missingDetails, response.conflicts].every(list => Array.isArray(list) && list.length <= 20 && list.every(text => bounded(text, 1000, true))) ||
      !(response.clarification === null || bounded(response.clarification, 1000, true)) ||
      ![null, 'provider_unavailable', 'provider_error', 'provider_timeout', 'provider_rate_limited', 'provider_configuration', 'provider_refused', 'incomplete_output', 'invalid_output', 'output_limit'].includes(response.errorCode)) fail('invalid_response', '<outcome_fields>')
  const metrics = response.metrics
  if (!exact(metrics, ['logicalScreenCalls', 'httpAttempts', 'sdkMaxRetries', 'imagesSupplied', 'newCaptureCount']) ||
      ![0, 1].includes(metrics.logicalScreenCalls) || ![0, 1].includes(metrics.httpAttempts) || metrics.sdkMaxRetries !== 0 ||
      metrics.imagesSupplied !== snapshot.input.images.length || metrics.newCaptureCount !== 1) fail('invalid_response', 'metrics')
  const answered = response.outcome === 'answered'
  const reference = response.outcome === 'reference_accepted'
  if ((reference && snapshot.action !== 'reference') || (snapshot.action === 'reference' && ['answered', 'needs_more_content'].includes(response.outcome))) fail('invalid_response', 'outcome')
  const collecting = response.outcome === 'needs_more_content' || reference
  if (response.committable !== (answered || collecting)) fail('invalid_response', 'committable')
  if (answered || collecting) {
    const delta = response.evidenceDelta
    const result = response.controllerResult
    const hashes = snapshot.input.images.map(image => image.imageHash)
    if (!exact(delta, ['text', 'complete', 'imageHashes', 'replacesTurnIds'])) fail('invalid_response', 'evidenceDelta')
    if (!bounded(delta.text, 24000, true)) fail('invalid_response', 'evidenceDelta.text')
    if (delta.complete !== answered) fail('invalid_response', 'evidenceDelta.complete')
    if (!Array.isArray(delta.imageHashes) || !delta.imageHashes.includes(snapshot.input.currentImageHash) ||
        new Set(delta.imageHashes).size !== delta.imageHashes.length || delta.imageHashes.some(hash => !hashes.includes(hash))) fail('invalid_response', 'evidenceDelta.imageHashes')
    if (JSON.stringify(delta.replacesTurnIds) !== JSON.stringify(snapshot.replacesTurnIds)) fail('invalid_response', 'evidenceDelta.replacesTurnIds')
    if (!exact(result, answered ? ['validated', 'evidence', 'answer'] : ['validated', 'evidence'])) fail('invalid_response', 'controllerResult')
    if (result.validated !== true) fail('invalid_response', 'controllerResult.validated')
    if (!exact(result.evidence, ['text', 'complete']) || result.evidence.text !== delta.text || result.evidence.complete !== delta.complete) fail('invalid_response', 'controllerResult.evidence')
    if (answered && result.answer !== response.answer) fail('invalid_response', 'controllerResult.answer')
    if (response.conflicts.length || response.clarification !== null || response.errorCode !== null ||
        (answered ? (!response.answer.trim() || !response.items.length || response.missingDetails.length) : (response.answer || response.items.length || (reference ? response.missingDetails.length : !response.missingDetails.length)))) fail('invalid_response', '<commit_payload>')
  } else if (response.controllerResult !== null || response.evidenceDelta !== null || response.answer || response.items.length ||
      response.missingDetails.length || (response.outcome === 'needs_clarification' ? !response.clarification : (response.clarification !== null || response.conflicts.length))) fail('invalid_response', '<noncommittable_payload>')
  const target = snapshot.targetQuestionId || (snapshot.contextKind !== 'reference' && snapshot.priorItems.length === 1 ? snapshot.priorItems[0].questionId : null)
  if (answered && snapshot.action === 'continue' && target && response.items.length !== 1) fail('invalid_response', 'items')
  for (const [index, item] of response.items.entries()) {
    if (!exact(item, ['index', 'display_number', 'question', 'question_type', 'answer', 'language', 'code', 'question_id']) ||
        item.index !== index + 1 || !bounded(item.display_number, 32) || !bounded(item.question, 8000, true) ||
        !bounded(item.answer, 24000, true) || !bounded(item.language, 64) || !bounded(item.code, 24000) ||
        !['coding', 'mcq', 'visual', 'debugging', 'output', 'interview', 'architecture', 'general'].includes(item.question_type) ||
        (item.question_type === 'coding' && (!item.language.trim() || !item.code.trim())) ||
        item.question_id !== (target || `${snapshot.identity.turnId}:${item.index}`)) fail('invalid_response', 'items.[]')
  }
  return response
}

function createScreenContextExecution({ controller, capture, authorize, backendUrl, publish, fetchImpl = fetch, diagnose = () => {}, developmentDiagnostics = false }) {
  const destination = new URL('/api/screen/analyze-context', backendUrl)
  if (!['http:', 'https:'].includes(destination.protocol) || destination.username || destination.password) fail('invalid_backend')
  let active = null
  let lastIdentity = null
  let sequence = 0
  let detail = {}
  let captureQueue = Promise.resolve()
  let clarificationRequestId = null
  const commands = new Map()
  const status = () => ({ ...controller.metadata(), identity: lastIdentity, sequence, ...detail, deliveries: controller.deliveries(),
    clarificationRequestId })
  function emit(extra = {}) {
    sequence += 1
    try { publish({ ...status(), ...extra }) }
    catch { try { diagnose({ stage: 'delivery', code: 'notification_failed' }) } catch {} }
  }
  function checkExpected(expected) {
    if (expected === undefined) return // Internal callers; current renderer supplies its observed fence.
    const current = status()
    if (!exact(expected, ['runtimeSessionId', 'generation', 'threadId', 'revision', 'requestId']) ||
        ['runtimeSessionId', 'generation', 'threadId', 'revision'].some(key => expected[key] !== current[key]) ||
        expected.requestId !== (current.identity?.requestId ?? null)) fail('stale_command')
  }
  function boundary() {
    if (active) { clearTimeout(active.timer); active.abort.abort() }
    active = null; lastIdentity = null; detail = {}; clarificationRequestId = null; commands.clear(); emit()
  }
  function current(attempt) {
    const meta = controller.metadata()
    return active === attempt && !attempt.abort.signal.aborted && meta.generation === attempt.token.generation &&
      meta.threadId === attempt.token.threadId && meta.pendingTurnId === attempt.token.turnId && meta.revision === attempt.token.baseRevision
  }
  async function run(attempt, needsCapture) {
    let stage = needsCapture ? 'capture' : 'prepare_request'
    const diagnostic = fields => {
      // Temporary diagnostics: only application-owned codes/booleans and opaque attempt ID.
      try { diagnose({ requestId: attempt.token.requestId, stage, ...fields }) } catch { /* Diagnostics cannot affect ownership. */ }
    }
    try {
      if (needsCapture) {
        const queued = captureQueue.then(async () => {
          if (!current(attempt)) fail('stale_attempt')
          return capture({ signal: attempt.abort.signal, isCurrent: () => current(attempt),
            canRestore: () => { const meta = controller.metadata(); return meta.runtimeSessionId === attempt.token.runtimeSessionId && meta.generation === attempt.token.generation } })
        })
        captureQueue = queued.catch(() => {})
        const captured = await queued
        if (!current(attempt)) { diagnostic({ event: 'discarded', ownershipMatch: false }); return }
        if (typeof captured?.imageDataUrl !== 'string' || !/^data:image\/(png|jpeg|webp|bmp);base64,/.test(captured.imageDataUrl)) fail('capture_failed')
        controller.registerImage(attempt.token, Buffer.from(captured.imageDataUrl.split(',')[1], 'base64'))
      }
      stage = 'prepare_request'
      const snapshot = controller.prepareRequest(attempt.token)
      const upload = multipart(snapshot)
      diagnostic({ event: 'prepared', runtimeContract: 'screen-context-provenance-v1', intent: snapshot.action, contextKind: snapshot.contextKind,
        retry: !needsCapture, revision: snapshot.identity.baseRevision, images: snapshot.input.images.length,
        evidence: snapshot.input.evidence.length, answers: snapshot.input.answers.length,
        items: snapshot.priorItems.length, replacements: snapshot.replacesTurnIds.length,
        currentImageRegistered: snapshot.input.images.some(image => image.imageHash === snapshot.input.currentImageHash) })
      if (!current(attempt)) return
      detail = { phase: 'processing' }; emit()
      if (!current(attempt)) return
      stage = 'authorize'
      const auth = await awaitAttempt(authorize(attempt.token), attempt.abort.signal)
      if (!current(attempt)) return
      if (!auth.isCurrent()) fail('auth_required')
      if (!current(attempt)) return
      stage = 'transport'
      const response = await awaitAttempt(fetchImpl(destination, { method: 'POST', redirect: 'error', signal: attempt.abort.signal,
        headers: { 'Content-Type': upload.contentType, ...(developmentDiagnostics ? { 'X-SAIIA-Screen-Diagnostics': '1' } : {}),
          ...(auth.authorization ? { Authorization: auth.authorization } : {}) }, body: upload.body }), attempt.abort.signal,
        late => { void late.body?.cancel().catch(() => {}) })
      if (!current(attempt)) { diagnostic({ event: 'discarded', ownershipMatch: false }); return }
      if (!auth.isCurrent()) fail('auth_required')
      if (!current(attempt)) return
      if (!response.ok) fail(response.status === 401 || response.status === 403 ? 'auth_required' : response.status === 413 ? 'upload_limit' : response.status === 504 ? 'request_timeout' : response.status === 429 ? 'request_busy' : 'request_failed')
      // Bound parsing independently of Content-Length; no backend error bodies are broadcast.
      stage = 'response_parse'
      const reader = response.body.getReader(); const chunks = []; let size = 0
      try {
        while (true) {
          const { done, value } = await awaitAttempt(reader.read(), attempt.abort.signal); if (done) break
          size += value.byteLength; if (size > 1024 * 1024) fail('invalid_response')
          chunks.push(Buffer.from(value))
        }
      } finally { await reader.cancel().catch(() => {}) }
      const parsed = JSON.parse(Buffer.concat(chunks).toString('utf8'))
      stage = 'response_validate'
      diagnostic({ event: 'response', outcome: ['answered', 'reference_accepted', 'needs_more_content', 'needs_clarification', 'failed'].includes(parsed?.outcome) ? parsed.outcome : 'unknown',
        identityMatch: Boolean(exact(parsed?.identity, Object.keys(snapshot.identity)) && Object.keys(snapshot.identity).every(key => parsed.identity[key] === snapshot.identity[key])) })
      const result = validateResponse(parsed, snapshot)
      if (!current(attempt)) { diagnostic({ event: 'discarded', ownershipMatch: false }); return }
      if (!auth.isCurrent()) fail('auth_required')
      if (!current(attempt)) return
      stage = result.committable ? 'controller_commit' : 'backend_outcome'
      const provenance = result.evidenceDelta && { imageHashes: result.evidenceDelta.imageHashes, replacesTurnIds: result.evidenceDelta.replacesTurnIds }
      if (result.outcome === 'answered') {
        const items = result.items.map(item => snapshot.priorItems.find(prior => prior.questionId === item.question_id) ||
          { questionId: item.question_id, turnId: attempt.token.turnId, index: item.index })
        controller.commitAnswer(attempt.token, result.controllerResult, items, provenance, { answer: result.answer, items: result.items })
      } else if (['needs_more_content', 'reference_accepted'].includes(result.outcome)) controller.commitEvidence(attempt.token, result.controllerResult, provenance)
      else controller.fail(attempt.token, { retryable: true })
      if (result.outcome === 'needs_clarification') clarificationRequestId = attempt.token.requestId
      detail = { phase: result.outcome, missingDetails: result.missingDetails, conflicts: result.conflicts,
        clarification: result.clarification, errorCode: result.errorCode }
      active = null
      emit(result.outcome === 'answered' ? { result: { answer: result.answer, items: result.items, identity: result.identity } } : {})
      diagnostic({ event: 'outcome', outcome: result.outcome, errorCode: result.errorCode,
        ownershipMatch: true, revisionAdvanced: controller.metadata().revision === attempt.token.baseRevision + 1 })
    } catch (error) {
      if (!current(attempt)) { diagnostic({ event: 'discarded', ownershipMatch: false }); return }
      const safeCode = ['invalid_response', 'invalid_result', 'memory_limit', 'item_count_limit', 'stale_attempt', 'upload_limit', 'auth_required',
        'capture_failed', 'invalid_image_size', 'invalid_image', 'image_count_limit', 'request_failed', 'active_window_not_identified', 'request_timeout', 'request_busy'].includes(error.code) ? error.code : 'unclassified_error'
      diagnostic({ event: 'rejected', ownershipMatch: true, code: safeCode,
        captureRejectionReason: stage === 'capture' && ['active_window_ambiguous', 'no_valid_target', 'no_external_desktop_source',
          'no_recent_external_target_or_desktop_source'].includes(error.reason) ? error.reason : null,
        fieldPath: error.fieldPath ?? null,
        commitRejectionReason: stage === 'controller_commit' ? safeCode : null })
      controller.fail(attempt.token, { retryable: true }); active = null
      const code = error.code || (error.message === 'auth_unavailable' ? 'auth_required' : error.message)
      detail = { phase: 'failed', errorCode: ['upload_limit', 'memory_limit', 'image_count_limit', 'invalid_response', 'auth_required', 'active_window_not_identified', 'request_timeout', 'request_busy'].includes(code) ? code : 'request_failed' }; emit()
    } finally { clearTimeout(attempt.timer) }
  }
  function launch(token, needsCapture) {
    if (active) { clearTimeout(active.timer); active.abort.abort() }
    const attempt = { token, abort: new AbortController() }
    active = attempt; lastIdentity = token; detail = { phase: needsCapture ? 'capturing' : 'processing' }; clarificationRequestId = null
    attempt.timer = setTimeout(() => {
      if (!current(attempt)) return
      controller.fail(token, { retryable: true }); attempt.abort.abort(); active = null
      detail = { phase: 'failed', errorCode: 'request_timeout' }; emit()
    }, 50000)
    emit()
    if (current(attempt)) void run(attempt, needsCapture)
    return status()
  }
  function execute(command) {
    validateCommand(command)
    const signature = JSON.stringify({ action: command.action, targetQuestionId: command.targetQuestionId ?? null, replacesTurnIds: command.replacesTurnIds ?? [] })
    if (command.commandId && commands.has(command.commandId)) {
      if (commands.get(command.commandId) !== signature) fail('invalid_command')
      return status()
    }
    checkExpected(command.expected)
    const token = controller.begin(command) // Synchronous admission before any await.
    if (command.commandId) { commands.set(command.commandId, signature); if (commands.size > 32) commands.delete(commands.keys().next().value) }
    return launch(token, true)
  }
  function retry(command) {
    checkExpected(command?.expected)
    if (clarificationRequestId) fail('clarification_required')
    return launch(controller.retryTurn(), false)
  }
  function resolve(command) {
    validateCommand(command, true)
    checkExpected(command.expected)
    if (!clarificationRequestId || command.requestId !== clarificationRequestId) fail('stale_clarification')
    return launch(controller.resolveClarification(command), false)
  }
  function cancel(command) {
    checkExpected(command?.expected)
    if (active) { controller.cancel(active.token); active.abort.abort(); clearTimeout(active.timer); active = null }
    else controller.cancelRetry()
    clarificationRequestId = null; detail = { phase: 'cancelled' }; emit(); return status()
  }
  return { execute, retry, resolve, cancel, boundary, status, acknowledge: identity => controller.acknowledge(identity) }
}

function registerScreenContextIpc(ipcMain, validateSender, isReady, execution) {
  for (const [channel, method] of Object.entries({
    'screen:context-status': 'status', 'screen:context-execute': 'execute',
    'screen:context-cancel': 'cancel', 'screen:context-retry': 'retry', 'screen:context-resolve': 'resolve',
    'screen:context-ack': 'acknowledge',
  })) {
    ipcMain.handle(channel, (event, payload) => {
      validateSender(event)
      if (method !== 'status' && !isReady()) throw Error('Screen analysis requires an active session.')
      if (method === 'status' && payload !== undefined) throw Error('Invalid Screen command.')
      if (['cancel', 'retry'].includes(method) && payload !== undefined && !exact(payload, ['expected'])) throw Error('Invalid Screen command.')
      if (['execute', 'cancel', 'retry', 'resolve'].includes(method) && !payload?.expected) throw Error('Screen command needs current lifecycle ownership.')
      try { return execution[method](payload) }
      catch { throw Error('Screen action unavailable. Refresh the chooser and try again.') }
    })
  }
}

module.exports = { createScreenContextExecution, registerScreenContextIpc, multipart, validateResponse, validateCommand }

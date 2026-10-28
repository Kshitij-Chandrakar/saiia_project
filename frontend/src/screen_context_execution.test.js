import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { isCurrentScreenContextEvent, screenContextCommandFence, screenContextDisplayPayload } from './screen_context_events.js'
import { normalizeScreenResponse } from './screen_intelligence_contract.js'
const require = createRequire(import.meta.url)
const { createScreenContextController } = require('../electron/screen_context_controller.cjs')
const { createScreenContextExecution, registerScreenContextIpc, multipart, validateResponse, validateCommand } = require('../electron/screen_context_execution.cjs')
const tick = () => new Promise(resolve => setImmediate(resolve))

test('development terminal status projects exactly five safe fields; packaged builds are silent', () => {
  const source = readFileSync(new URL('../electron/main.cjs', import.meta.url), 'utf8')
  const wiring = source.slice(source.indexOf('screenExecution = createScreenContextExecution({'), source.indexOf('registerScreenContextIpc(ipcMain,'))
  for (const isPackaged of [false, true]) {
    const lines = []
    const options = vm.runInNewContext(wiring, {
      app: { isPackaged }, screenExecution: null, screenContext: {}, mainWindow: null, overlayWindow: null,
      getDesktopAuthConfig: () => ({ backendUrl: 'http://localhost:8000' }),
      createScreenContextExecution: options => options,
      console: { info: (...args) => lines.push(args) },
    })
    assert.equal(options.developmentDiagnostics, !isPackaged)
    options.publish({ phase: 'failed', errorCode: 'incomplete_output', revision: 0, acceptedImageCount: 0, retryAvailable: true,
      images: 'PRIVATE_IMAGE', evidence: 'PRIVATE_SOURCE', answer: 'PRIVATE_ANSWER', token: 'PRIVATE_TOKEN' })
    assert.equal(lines.length, isPackaged ? 0 : 1)
    if (!isPackaged) {
      assert.equal(lines[0][0], '[screen-context-status]')
      assert.deepEqual(Object.keys(JSON.parse(lines[0][1])), ['phase', 'errorCode', 'revision', 'acceptedImageCount', 'retryAvailable'])
      assert.doesNotMatch(lines[0][1], /PRIVATE_/)
    }
  }
})

export function reply(request, outcome = 'answered', count = 1) {
  const target = request.targetQuestionId || (request.contextKind !== 'reference' && request.priorItems.length === 1 ? request.priorItems[0].questionId : null)
  const delta = { text: 'EXACT_SOURCE def solve(x):\n    return x', complete: outcome === 'answered',
    imageHashes: request.input.images.map(item => item.imageHash), replacesTurnIds: request.replacesTurnIds }
  return { contractVersion: '1', identity: request.identity, outcome, committable: ['answered', 'needs_more_content', 'reference_accepted'].includes(outcome),
    controllerResult: outcome === 'answered' ? { validated: true, evidence: { text: delta.text, complete: true }, answer: 'VALID_ANSWER' } :
      ['needs_more_content', 'reference_accepted'].includes(outcome) ? { validated: true, evidence: { text: delta.text, complete: false } } : null,
    evidenceDelta: ['answered', 'needs_more_content', 'reference_accepted'].includes(outcome) ? delta : null,
    answer: outcome === 'answered' ? 'VALID_ANSWER' : '',
    items: outcome === 'answered' ? Array.from({ length: count }, (_, index) => ({ index: index + 1, display_number: '',
      question: `Question ${index + 1}`, question_type: 'visual', answer: 'VALID_ANSWER', language: '', code: '',
      question_id: target || `${request.identity.turnId}:${index + 1}` })) : [],
    missingDetails: outcome === 'needs_more_content' ? ['Remaining constraints'] : [], conflicts: [],
    clarification: outcome === 'needs_clarification' ? 'Which code version should be used?' : null,
    errorCode: outcome === 'failed' ? 'provider_error' : null,
    metrics: { logicalScreenCalls: 1, httpAttempts: 1, sdkMaxRetries: 0, imagesSupplied: request.input.images.length, newCaptureCount: 1 } }
}

function setup(options = {}) {
  const requests = [], events = [], waiting = [], diagnostics = []
  let captures = 0, outcome = 'answered', count = 1, held = false, execution
  const controller = createScreenContextController({ inspectImage: () => ({ width: 50, height: 40 }),
    onBoundary: () => execution?.boundary(), ...options })
  controller.adoptSession({ runtimeSessionId: 'runtime' })
  execution = createScreenContextExecution({ controller, backendUrl: 'http://127.0.0.1:8000',
    capture: options.capture || (async () => { captures += 1; return { imageDataUrl: `data:image/png;base64,${Buffer.from(`diagram-${captures}`).toString('base64')}` } }),
    authorize: options.authorize || (async () => ({ authorization: 'Bearer PRIVATE_TOKEN', isCurrent: () => true })), publish: event => events.push(event),
    diagnose: event => diagnostics.push(event),
    fetchImpl: async (_url, init) => {
      const form = await new Response(init.body, { headers: { 'content-type': init.headers['Content-Type'] } }).formData()
      const request = JSON.parse(form.get('context')); requests.push(request)
      if (options.httpStatus) return new Response(null, { status: options.httpStatus })
      assert.ok(form.get('image_0').size)
      let response = reply(request, outcome, count)
      if (held) response = await new Promise(resolve => waiting.push(() => resolve(response)))
      return Response.json(response)
    } })
  return { controller, execution, requests, events, waiting, diagnostics,
    get captures() { return captures }, set outcome(value) { outcome = value }, set count(value) { count = value }, set held(value) { held = value },
    async done() { for (let n = 0; n < 100 && ['capturing', 'processing'].includes(execution.status().phase); n++) await tick()
      assert.ok(!['capturing', 'processing'].includes(execution.status().phase)); return execution.status() } }
}

test('ambiguous native target remains an actionable capture failure without upload or captured retry', async () => {
  const s = setup({ capture: async () => { throw Object.assign(new Error('PRIVATE_WINDOW_TITLE'),
    { code: 'active_window_not_identified', reason: 'active_window_ambiguous' }) } })
  s.execution.execute({ action: 'reference' }); await s.done()
  assert.equal(s.execution.status().errorCode, 'active_window_not_identified')
  assert.equal(s.execution.status().retryAvailable, false)
  assert.equal(s.controller.metadata().acceptedImageCount, 0)
  assert.equal(s.requests.length, 0)
  assert.throws(() => s.execution.retry())
  assert.ok(s.diagnostics.some(event => event.stage === 'capture' && event.code === 'active_window_not_identified' && event.captureRejectionReason === 'active_window_ambiguous'))
  assert.doesNotMatch(JSON.stringify(s.diagnostics), /PRIVATE_WINDOW_TITLE/)
})

test('timeout/busy and provider classifications preserve safe captured retry without an invalid-response rejection', async () => {
  for (const [httpStatus, code] of [[504, 'request_timeout'], [429, 'request_busy']]) {
    const s = setup({ httpStatus }); s.execution.execute({ action: 'new' }); await s.done()
    assert.equal(s.execution.status().errorCode, code)
    assert.equal(s.execution.status().retryAvailable, true)
    assert.equal(s.controller.metadata().revision, 0)
    assert.ok(s.diagnostics.some(event => event.code === code))
  }
  const s = setup(); s.execution.execute({ action: 'new' }); await s.done()
  for (const code of ['provider_timeout', 'provider_rate_limited', 'provider_configuration']) {
    const response = reply(s.requests[0], 'failed'); response.errorCode = code
    assert.equal(validateResponse(response, s.requests[0]).errorCode, code)
  }
})

test('three screenshots preserve diagram bytes, exact sources and earlier answers; New inherits nothing', async () => {
  const s = setup()
  s.outcome = 'needs_more_content'; s.execution.execute({ action: 'new' }); await s.done()
  assert.equal(s.events.filter(event => event.result).length, 0)
  s.execution.execute({ action: 'continue' }); await s.done()
  s.outcome = 'answered'; s.execution.execute({ action: 'continue' }); await s.done()
  assert.equal(s.requests[2].input.images.length, 3)
  assert.equal(s.requests[2].input.evidence.length, 2)
  s.execution.execute({ action: 'continue' }); await s.done()
  assert.equal(s.requests[3].input.answers[0].text, 'VALID_ANSWER')
  s.execution.execute({ action: 'new' }); await s.done()
  assert.equal(s.requests[4].input.images.length, 1)
  assert.deepEqual(s.requests[4].input.evidence, [])
  assert.deepEqual(s.requests[4].input.answers, [])
  const safe = JSON.stringify(s.events)
  assert.doesNotMatch(safe, /PRIVATE_TOKEN|dataBase64|EXACT_SOURCE|diagram-/)
})

test('reference → two independent questions retains the source; reference replacement and New isolate everything', async () => {
  const s = setup(); s.outcome = 'reference_accepted'
  s.execution.execute({ action: 'reference' }); await s.done()
  assert.equal(s.execution.status().phase, 'reference_accepted')
  assert.equal(s.controller.metadata().acceptedImageCount, 1)
  assert.equal(s.controller.metadata().answerCount, 0)
  assert.equal(s.events.filter(event => event.result).length, 0)
  const referenceHash = s.requests[0].input.currentImageHash
  s.outcome = 'answered'
  s.execution.execute({ action: 'continue' }); await s.done()
  const firstQuestion = s.controller.metadata().priorItems[0].questionId
  s.execution.execute({ action: 'continue' }); await s.done()
  assert.equal(s.requests[2].contextKind, 'reference')
  assert.equal(s.requests[2].input.images[0].imageHash, referenceHash)
  assert.equal(s.requests[2].input.evidence.length, 2)
  assert.equal(s.requests[2].input.answers.length, 1)
  assert.equal(s.requests[2].targetQuestionId, null)
  assert.equal(s.controller.metadata().priorItems.length, 2)
  assert.notEqual(s.controller.metadata().priorItems[1].questionId, firstQuestion)
  s.outcome = 'reference_accepted'
  s.execution.execute({ action: 'reference' }); await s.done()
  assert.equal(s.requests[3].input.evidence.length, 0)
  assert.equal(s.requests[3].input.answers.length, 0)
  assert.equal(s.requests[3].input.images.length, 1)
  assert.equal(s.controller.metadata().acceptedImageCount, 1)
  s.outcome = 'answered'
  s.execution.execute({ action: 'new' }); await s.done()
  assert.equal(s.requests[4].contextKind, 'question')
  assert.deepEqual(s.requests[4].input.evidence, [])
  assert.deepEqual(s.requests[4].input.answers, [])
  assert.equal(s.requests[4].priorItems.length, 0)
})

test('failed reference replacement stays empty; frozen retry accepts only evidence and does not recapture', async () => {
  const s = setup(); s.execution.execute({ action: 'new' }); await s.done()
  s.outcome = 'failed'; s.execution.execute({ action: 'reference' }); await s.done()
  assert.equal(s.controller.metadata().acceptedImageCount, 0)
  assert.equal(s.controller.metadata().answerCount, 0)
  assert.throws(() => s.execution.execute({ action: 'continue' }))
  s.outcome = 'reference_accepted'; s.execution.retry(); await s.done()
  assert.equal(s.captures, 2)
  assert.deepEqual(s.requests[1].input, s.requests[2].input)
  assert.equal(s.controller.metadata().revision, 1)
  assert.equal(s.controller.metadata().acceptedImageCount, 1)
  assert.equal(s.events.filter(event => event.result).length, 1) // Earlier displayed answer remains separate.
})

test('reference replacement supersedes late work and session/account cleanup releases reference context', async () => {
  const s = setup(); s.held = true; s.execution.execute({ action: 'new' })
  while (!s.waiting.length) await tick()
  s.held = false; s.outcome = 'reference_accepted'; s.execution.execute({ action: 'reference' }); await s.done()
  s.waiting.shift()(); await tick()
  assert.equal(s.controller.metadata().revision, 1)
  assert.equal(s.controller.metadata().answerCount, 0)
  assert.equal(s.events.filter(event => event.result).length, 0)
  s.controller.adoptSession({ runtimeSessionId: 'different-account', accountGeneration: 5 })
  assert.equal(s.controller.metadata().retainedImageCount, 0)
  assert.equal(s.controller.metadata().contextKind, 'question')
})

test('reference intent rejects answers and missing-question workarounds; question intent rejects reference acceptance', async () => {
  const s = setup(); s.outcome = 'reference_accepted'; s.execution.execute({ action: 'reference' }); await s.done()
  for (const outcome of ['answered', 'needs_more_content']) {
    assert.throws(() => validateResponse(reply(s.requests[0], outcome), s.requests[0]), /invalid_response/)
  }
  const wrongIntent = { ...s.requests[0], action: 'new', contextKind: 'question' }
  assert.throws(() => validateResponse(reply(wrongIntent, 'reference_accepted'), wrongIntent), /invalid_response/)
})

test('reference survives the six-image ceiling; overflow rejects without eviction', async () => {
  const s = setup(); s.outcome = 'reference_accepted'; s.execution.execute({ action: 'reference' }); await s.done()
  const hash = s.requests[0].input.currentImageHash
  s.outcome = 'answered'
  for (let turn = 0; turn < 5; turn++) { s.execution.execute({ action: 'continue' }); await s.done() }
  assert.equal(s.requests.at(-1).input.images[0].imageHash, hash)
  s.execution.execute({ action: 'continue' }); await s.done()
  assert.equal(s.execution.status().errorCode, 'image_count_limit')
  assert.equal(s.requests.length, 6)
  assert.equal(s.controller.metadata().acceptedImageCount, 6)
  assert.equal(s.controller.metadata().evidenceCount, 6)
  s.outcome = 'reference_accepted'; s.execution.execute({ action: 'reference' }); await s.done()
  assert.equal(s.controller.metadata().acceptedImageCount, 1)
  assert.deepEqual(s.requests.at(-1).input.evidence, [])
})

test('clarification never commits; bound response, batch target and replacement persist without recapture', async () => {
  const s = setup(); s.count = 2; s.execution.execute({ action: 'new' }); await s.done()
  const accepted = s.controller.metadata(); s.count = 1; s.outcome = 'needs_clarification'
  s.execution.execute({ action: 'continue' }); await s.done()
  assert.equal(s.controller.metadata().revision, accepted.revision)
  const requestId = s.execution.status().clarificationRequestId
  assert.throws(() => s.execution.resolve({ requestId: 'wrong', text: 'Use new code' }))
  s.outcome = 'answered'
  s.execution.resolve({ requestId, text: 'Use the corrected implementation.', targetQuestionId: accepted.priorItems[1].questionId,
    replacesTurnIds: [accepted.sourceTurns[0].turnId] }); await s.done()
  assert.equal(s.captures, 2)
  assert.equal(s.requests[2].identity.turnId, s.requests[1].identity.turnId)
  assert.notEqual(s.requests[2].identity.requestId, requestId)
  assert.equal(s.requests[2].clarificationResponse.requestId, requestId)
  assert.equal(s.requests[2].targetQuestionId, accepted.priorItems[1].questionId)
  s.execution.execute({ action: 'continue', targetQuestionId: accepted.priorItems[1].questionId }); await s.done()
  assert.deepEqual(s.requests[3].replacesTurnIds, [])
  assert.deepEqual(s.requests[3].input.evidence[1].replacesTurnIds, [accepted.sourceTurns[0].turnId])
  assert.deepEqual(s.requests[3].input.clarifications, [s.requests[2].clarificationResponse])
  assert.deepEqual(s.requests[3].priorItems, accepted.priorItems)
})

test('retry freezes capture/context, changes only attempt identity and commits one logical turn', async () => {
  const s = setup(); s.outcome = 'failed'; s.execution.execute({ action: 'new' }); await s.done()
  s.outcome = 'answered'; s.execution.retry()
  assert.throws(() => s.execution.retry()); await s.done()
  assert.equal(s.captures, 1); assert.equal(s.controller.metadata().revision, 1)
  assert.deepEqual(s.requests[0].input, s.requests[1].input)
  assert.equal(s.requests[0].identity.turnId, s.requests[1].identity.turnId)
  assert.notEqual(s.requests[0].identity.requestId, s.requests[1].identity.requestId)
  assert.equal(s.events.filter(event => event.result).length, 1)
  assert.equal(s.controller.metadata().acceptedImageCount, 1)
  assert.deepEqual(s.requests[0], { ...s.requests[1], identity: { ...s.requests[1].identity, requestId: s.requests[0].identity.requestId } })
  const prepared = s.diagnostics.filter(item => item.event === 'prepared')
  assert.deepEqual(prepared.map(item => item.retry), [false, true])
  assert.ok(prepared.every(item => item.intent === 'new' && item.images === 1 && item.evidence === 0 && item.answers === 0 && item.currentImageRegistered))
  assert.ok(s.diagnostics.some(item => item.stage === 'backend_outcome' && item.outcome === 'failed' && item.errorCode === 'provider_error'))
  assert.ok(s.diagnostics.some(item => item.stage === 'controller_commit' && item.outcome === 'answered' && item.revisionAdvanced))
  assert.doesNotMatch(JSON.stringify(s.diagnostics), /PRIVATE_TOKEN|VALID_ANSWER|EXACT_SOURCE|dataBase64|diagram-/)
})

test('valid incomplete-evidence retry accepts the retained screenshot once without an answer', async () => {
  const s = setup(); s.outcome = 'failed'; s.execution.execute({ action: 'new' }); await s.done()
  s.outcome = 'needs_more_content'; s.execution.retry(); await s.done()
  assert.equal(s.captures, 1)
  assert.deepEqual(s.requests[0].input, s.requests[1].input)
  assert.equal(s.controller.metadata().acceptedImageCount, 1)
  assert.equal(s.controller.metadata().revision, 1)
  assert.equal(s.controller.metadata().answerCount, 0)
  assert.equal(s.execution.status().phase, 'needs_more_content')
  assert.equal(s.events.filter(event => event.result).length, 0)
})

for (const boundary of ['cancel', 'new', 'session', 'account']) {
  test(`${boundary} rejects an old response and releases pending clarification`, async () => {
    const s = setup(); s.held = true; s.execution.execute({ action: 'new' })
    while (!s.waiting.length) await tick()
    if (boundary === 'cancel') s.execution.cancel()
    if (boundary === 'session') s.controller.invalidate()
    if (boundary === 'account') s.controller.adoptSession({ runtimeSessionId: 'other', accountGeneration: 3 })
    if (boundary === 'new') { s.held = false; s.execution.execute({ action: 'new' }); await s.done() }
    s.waiting.shift()(); await tick(); await tick()
    assert.equal(s.events.filter(event => event.result).length, boundary === 'new' ? 1 : 0)
    assert.equal(s.controller.metadata().revision, boundary === 'new' ? 1 : 0)
    assert.equal(s.execution.status().clarificationRequestId, null)
  })
}

test('response validation rejects every echoed identity mismatch, malformed outcome and unknown target', async () => {
  const s = setup(); s.execution.execute({ action: 'new' }); await s.done()
  const request = s.requests[0]
  for (const key of Object.keys(request.identity)) {
    const response = reply(request); response.identity = { ...response.identity, [key]: 'wrong' }
    assert.throws(() => validateResponse(response, request), /invalid_response/)
  }
  for (const mutate of [r => { r.committable = false }, r => { r.controllerResult.answer = 'wrong' },
    r => { r.evidenceDelta.imageHashes = [] }, r => { r.items[0].question_id = 'invented' }, r => { r.extra = 'private' }]) {
    const response = reply(request); mutate(response); assert.throws(() => validateResponse(response, request))
  }
  for (const [fieldPath, mutate] of [
    ['evidenceDelta.imageHashes', r => { r.evidenceDelta.imageHashes = ['PRIVATE_SOURCE'] }],
    ['controllerResult.answer', r => { r.controllerResult.answer = 'PRIVATE_ANSWER' }],
    ['controllerResult', r => { delete r.controllerResult.answer }],
    ['identity', r => { r.identity.requestId = 'stale' }],
  ]) {
    const response = structuredClone(reply(request)); mutate(response)
    assert.throws(() => validateResponse(response, request), error => error.code === 'invalid_response' && error.fieldPath === fieldPath)
  }
  assert.throws(() => s.execution.execute({ action: 'continue', targetQuestionId: 'invented' }))
  assert.throws(() => validateCommand({ action: 'new', accessToken: 'evil' }))
})

test('aggregate upload/metadata overflow rejects without dropping evidence or sending', () => {
  const image = { imageHash: 'a'.repeat(64), dataBase64: 'eA==', byteLength: 25 * 1024 * 1024 }
  const snapshot = { identity: {}, action: 'new', priorItems: [], targetQuestionId: null, replacesTurnIds: [], clarificationResponse: null,
    input: { images: [image], evidence: [], answers: [], currentImageHash: image.imageHash } }
  assert.throws(() => multipart(snapshot), /upload_limit/)
  image.byteLength = 1; snapshot.input.evidence = [{ text: 'x'.repeat(256 * 1024) }]
  assert.throws(() => multipart(snapshot), /upload_limit/)
})

test('renderer fences stale session/sequence and preserves existing batch display contract', async () => {
  const s = setup(); s.count = 2; s.execution.execute({ action: 'new' }); await s.done()
  const event = s.events.at(-1)
  assert.ok(isCurrentScreenContextEvent(event, s.execution.status()))
  const payload = screenContextDisplayPayload(event.result)
  assert.equal(normalizeScreenResponse(payload).envelope.status, 'ready')
  assert.equal(normalizeScreenResponse(payload).questions.length, 2)
  s.controller.invalidate()
  assert.equal(isCurrentScreenContextEvent(event, s.execution.status()), false)
})

test('Screen IPC validates sender, readiness, command shapes and never exposes controller mutation', async () => {
  const s = setup(); const handlers = new Map(); let ready = false
  registerScreenContextIpc({ handle: (name, fn) => handlers.set(name, fn) }, event => {
    if (event !== 'trusted') throw Error('untrusted')
  }, () => ready, s.execution)
  assert.equal(handlers.size, 6)
  assert.throws(() => handlers.get('screen:context-status')('hostile'), /untrusted/)
  assert.throws(() => handlers.get('screen:context-execute')('trusted', { action: 'new' }), /active session/)
  ready = true
  for (const command of [null, [], { action: 'new', image: 'evil' }, { action: 'new', targetQuestionId: '../evil' }, { action: 'wrong' }]) {
    assert.throws(() => handlers.get('screen:context-execute')('trusted', command))
  }
  assert.equal(s.captures, 0)
  assert.throws(() => handlers.get('screen:context-retry')('trusted', { url: 'http://evil' }))
  handlers.get('screen:context-execute')('trusted', { action: 'new', commandId: 'ipc-one', expected: screenContextCommandFence(s.execution.status()) }); await s.done()
  const status = handlers.get('screen:context-status')('trusted')
  assert.doesNotMatch(JSON.stringify(status), /PRIVATE_TOKEN|EXACT_SOURCE|dataBase64/)
  assert.equal(status.deliveries[0].answer, 'VALID_ANSWER')
  assert.equal(handlers.get('screen:context-ack')('trusted', status.deliveries[0].identity), true)
})

for (const cleanup of ['cancel', 'new', 'session']) {
  test(`pending clarification is fenced on ${cleanup}`, async () => {
    const s = setup(); s.outcome = 'needs_clarification'; s.execution.execute({ action: 'new' }); await s.done()
    const requestId = s.execution.status().clarificationRequestId
    assert.throws(() => s.execution.resolve({ requestId, text: 'x'.repeat(2001) }))
    if (cleanup === 'cancel') s.execution.cancel()
    if (cleanup === 'new') { s.outcome = 'failed'; s.execution.execute({ action: 'new' }); await s.done() }
    if (cleanup === 'session') s.controller.invalidate()
    assert.throws(() => s.execution.resolve({ requestId, text: 'Use new code' }))
    assert.equal(s.controller.metadata().revision, 0)
  })
}

test('unavailable cloud authorization never sends or downgrades the request', async () => {
  const s = setup({ authorize: async () => { throw Error('auth_unavailable') } })
  s.execution.execute({ action: 'new' }); await s.done()
  assert.equal(s.requests.length, 0)
  assert.equal(s.controller.metadata().revision, 0)
  assert.equal(s.execution.status().retryAvailable, true)
})

test('credential loss during response parsing fails without committing or stranding the operation', async () => {
  let checks = 0
  const s = setup({ authorize: async () => ({ authorization: 'Bearer private', isCurrent: () => ++checks < 3 }) })
  s.execution.execute({ action: 'new' }); await s.done()
  assert.equal(s.execution.status().phase, 'failed')
  assert.equal(s.execution.status().errorCode, 'auth_required')
  assert.equal(s.controller.metadata().revision, 0)
  assert.equal(s.controller.metadata().pendingTurnId, null)
})

test('superseding a capture serializes native hide/restore and never submits the retired image', async () => {
  let execution, captures = 0; const releases = []; const events = []; let sent = 0
  const controller = createScreenContextController({ inspectImage: () => ({ width: 10, height: 10 }) })
  controller.adoptSession({ runtimeSessionId: 'runtime' })
  execution = createScreenContextExecution({ controller, backendUrl: 'http://localhost:8000',
    capture: () => { captures++; return new Promise(resolve => releases.push(() => resolve({ imageDataUrl: 'data:image/png;base64,eA==' }))) },
    authorize: async () => ({ isCurrent: () => true }), publish: event => events.push(event),
    fetchImpl: async (_url, init) => {
      sent++; const form = await new Response(init.body, { headers: { 'content-type': init.headers['Content-Type'] } }).formData()
      return Response.json(reply(JSON.parse(form.get('context'))))
    } })
  execution.execute({ action: 'new' }); await tick()
  execution.execute({ action: 'new' }); await tick()
  assert.equal(captures, 1)
  releases.shift()(); await tick(); assert.equal(captures, 2)
  releases.shift()()
  for (let n = 0; n < 100 && !events.some(event => event.result); n++) await tick()
  assert.equal(sent, 1); assert.equal(controller.metadata().revision, 1)
})

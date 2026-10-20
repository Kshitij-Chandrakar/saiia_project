import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import test from 'node:test'

const require = createRequire(import.meta.url)
const { createScreenContextController } = require('../electron/screen_context_controller.cjs')
const { DesktopAuthSessionManager } = require('../electron/desktop_auth_session.cjs')
const image = number => Buffer.from(`synthetic-image-${number}`)
const result = (text = 'source evidence', answer) => ({ validated: true,
  evidence: { text, complete: answer !== undefined }, ...(answer === undefined ? {} : { answer }) })
const rejects = (fn, code) => assert.throws(fn, error => error.code === code)

function setup(limits) {
  const controller = createScreenContextController({ limits, inspectImage: () => ({ width: 10, height: 10 }) })
  controller.adoptSession({ runtimeSessionId: 'runtime', accountGeneration: 1, cloudSessionId: 'cloud' })
  return controller
}

function capture(controller, action = 'new', number = 1) {
  const token = controller.begin({ action })
  controller.registerImage(token, image(number))
  controller.prepareRequest(token)
  return token
}

test('new execution starts empty; UI selection has no controller mutation API', () => {
  const c = setup()
  c.commitAnswer(capture(c), result('old source', 'old answer'))
  const before = c.metadata()
  const uiChoice = 'new'
  assert.deepEqual(c.metadata(), before)
  assert.equal(c.selectOption, undefined)
  const token = c.begin({ action: uiChoice })
  assert.notEqual(token.threadId, before.threadId)
  assert.equal(c.metadata().evidenceCount, 0)
  assert.equal(c.metadata().answerCount, 0)
  c.fail(token)
  assert.equal(c.metadata().threadId, token.threadId)
  rejects(() => c.begin({ action: 'continue' }), 'no_accepted_context')
})

test('continuation requires accepted evidence; incomplete evidence alone enables it', () => {
  const c = setup()
  rejects(() => c.begin({ action: 'continue' }), 'no_accepted_context')
  c.commitEvidence(capture(c), result())
  assert.equal(c.metadata().revision, 1)
  assert.equal(c.metadata().answerCount, 0)
  const token = capture(c, 'continue', 2)
  const snapshot = c.prepareRequest(token)
  assert.equal(snapshot.input.evidence.length, 1)
  assert.equal(snapshot.input.images.length, 2)
  c.commitAnswer(token, result('remaining constraints', 'successful answer'))
  assert.equal(c.metadata().revision, 2)
  assert.equal(c.metadata().evidenceCount, 2)
  assert.equal(c.metadata().answerCount, 1)
})

test('malformed results cannot partially commit evidence or an answer', () => {
  const c = setup()
  const token = capture(c)
  const before = c.metadata()
  for (const bad of [null, {}, { ...result(), validated: false },
    { ...result(), answer: '' }, { ...result(), evidence: { text: '', complete: true } }]) {
    rejects(() => c.commitAnswer(token, bad), 'invalid_result')
    assert.deepEqual(c.metadata(), before)
  }
  rejects(() => c.commitEvidence(token, result('source', 'unrequested answer')), 'invalid_result')
  c.commitAnswer(token, result('source', 'answer'))
  assert.equal(c.metadata().evidenceCount, 1)
  assert.equal(c.metadata().answerCount, 1)
})

test('commit authority enforces outcome completeness and genuine supporting-image provenance atomically', () => {
  const c = setup(), token = capture(c), before = c.metadata()
  rejects(() => c.commitAnswer(token, { ...result('source', 'answer'), evidence: { text: 'source', complete: false } }), 'invalid_result')
  rejects(() => c.commitEvidence(token, { validated: true, evidence: { text: 'source', complete: true } }), 'invalid_result')
  for (const provenance of [{ imageHashes: null, replacesTurnIds: [] }, { imageHashes: ['invented'], replacesTurnIds: [] },
    { imageHashes: [], replacesTurnIds: [] }, { imageHashes: [], replacesTurnIds: ['invented'] }]) {
    rejects(() => c.commitEvidence(token, result(), provenance), 'invalid_result')
    assert.deepEqual(c.metadata(), before)
  }
})

test('failure and cancellation preserve accepted context, never candidate data', () => {
  const c = setup()
  c.commitAnswer(capture(c), result('valid source', 'valid answer'))
  for (const action of ['fail', 'cancel']) {
    const token = capture(c, 'continue', 2)
    c[action](token)
    assert.equal(c.metadata().evidenceCount, 1)
    assert.equal(c.metadata().answerCount, 1)
    assert.equal(c.metadata().revision, 1)
    assert.equal(c.metadata().retainedImageCount, 1)
    rejects(() => c.commitAnswer(token, result('late', 'late')), 'stale_attempt')
  }
})

test('synchronous admission, duplicate completion, and explicit new supersession', () => {
  const c = setup()
  const token = capture(c)
  rejects(() => c.begin({ action: 'continue' }), 'operation_busy')
  c.commitEvidence(token, result())
  rejects(() => c.commitEvidence(token, result()), 'stale_attempt')
  const old = capture(c, 'continue', 2)
  const next = c.begin({ action: 'new' })
  rejects(() => c.commitAnswer(old, result('stale', 'stale')), 'stale_attempt')
  assert.equal(c.metadata().threadId, next.threadId)
  assert.equal(c.metadata().retainedImageCount, 0)
})

test('every identity and base revision is fenced', () => {
  const c = setup()
  const token = capture(c)
  for (const key of Object.keys(token)) {
    const stale = { ...token, [key]: typeof token[key] === 'number' ? token[key] + 1 : 'other' }
    rejects(() => c.commitEvidence(stale, result()), 'stale_attempt')
  }
  assert.equal(c.metadata().evidenceCount, 0)
  c.commitEvidence(token, result())
})

test('retry preserves turn and immutable input, changes attempt, and cannot commit twice', () => {
  const c = setup()
  c.commitAnswer(capture(c), result('old source', 'old answer'))
  const token = capture(c, 'continue', 2)
  const original = c.prepareRequest(token)
  assert.ok(Object.isFrozen(original.input))
  assert.ok(Object.isFrozen(original.input.images[0]))
  assert.throws(() => { original.input.evidence[0].text = 'tampered' }, TypeError)
  c.fail(token, { retryable: true })
  assert.equal(c.metadata().retainedImageCount, 2)
  const retry = c.retryTurn()
  const request = c.prepareRequest(retry)
  assert.equal(retry.turnId, token.turnId)
  assert.equal(retry.operationId, token.operationId)
  assert.notEqual(retry.requestId, token.requestId)
  assert.equal(request.input, original.input)
  rejects(() => c.commitEvidence(token, result()), 'stale_attempt')
  c.commitAnswer(retry, result('second source', 'second answer'))
  rejects(() => c.commitAnswer(retry, result('duplicate', 'duplicate')), 'stale_attempt')
  assert.equal(c.metadata().answerCount, 2)
})

test('cancellation, new execution, and session disposal remove retry eligibility', () => {
  for (const boundary of ['cancel', 'new', 'session', 'dispose']) {
    const c = setup()
    const token = capture(c)
    if (boundary === 'cancel') {
      c.cancel(token)
    } else {
      c.fail(token, { retryable: true })
      if (boundary === 'new') c.begin({ action: 'new' })
      if (boundary === 'session') c.adoptSession({ runtimeSessionId: 'other' })
      if (boundary === 'dispose') c.dispose()
    }
    assert.equal(c.metadata().retryAvailable, false)
  }
  const c = setup()
  const token = capture(c)
  c.fail(token, { retryable: true })
  c.cancelRetry()
  rejects(() => c.retryTurn(), 'retry_unavailable')
  assert.equal(c.metadata().retainedImageCount, 0)
})

test('six distinct images includes pending/retry; identical pixels still allow a new turn', () => {
  const c = setup()
  for (let n = 1; n <= 6; n++) c.commitEvidence(capture(c, n === 1 ? 'new' : 'continue', n), result(`part ${n}`))
  const overflow = c.begin({ action: 'continue' })
  rejects(() => c.registerImage(overflow, image(7)), 'image_count_limit')
  assert.equal(c.metadata().acceptedImageCount, 6)
  c.cancel(overflow)
  const duplicate = capture(c, 'continue', 6)
  c.commitAnswer(duplicate, result('same pixels, new logical answer', 'answer'))
  assert.equal(c.metadata().acceptedImageCount, 6)
  assert.equal(c.metadata().evidenceCount, 7)
})

test('aggregate budget counts retry images and text, rejects overflow atomically', () => {
  const c = setup({ maxRetainedBytes: 1000 })
  const token = capture(c)
  rejects(() => c.commitAnswer(token, result('x'.repeat(600), 'answer')), 'memory_limit')
  assert.equal(c.metadata().evidenceCount, 0)
  c.fail(token, { retryable: true })
  assert.ok(c.metadata().retainedBytes > 8)
  const retry = c.retryTurn()
  c.commitEvidence(retry, result())
  const next = c.begin({ action: 'continue' })
  rejects(() => c.registerImage(next, Buffer.alloc(600)), 'memory_limit')
  assert.equal(c.metadata().evidenceCount, 1)
  c.cancel(next)
  const invalid = c.begin({ action: 'continue' })
  rejects(() => c.registerImage(invalid, Buffer.alloc(10 * 1024 * 1024 + 1)), 'invalid_image_size')
})

test('pending and retained retry images share the image limit and are released together', () => {
  const c = setup({ maxImages: 2 })
  c.commitEvidence(capture(c), result())
  const token = capture(c, 'continue', 2)
  c.fail(token, { retryable: true })
  assert.equal(c.metadata().acceptedImageCount, 1)
  assert.equal(c.metadata().retainedImageCount, 2)
  const retry = c.retryTurn()
  assert.equal(c.prepareRequest(retry).input.images.length, 2)
  c.cancel(retry)
  assert.equal(c.metadata().retainedImageCount, 1)
  c.commitEvidence(capture(c, 'continue', 3), result('replacement candidate'))
  assert.equal(c.metadata().acceptedImageCount, 2)
})

test('image decoding/pixel validation and owned immutable bytes', () => {
  for (const inspectImage of [() => { throw new Error('private decoder detail') }, () => ({ width: 0, height: 1 }),
    () => ({ width: 2201, height: 2201 })]) {
    const c = createScreenContextController({ inspectImage })
    c.adoptSession({ runtimeSessionId: 'runtime' })
    rejects(() => c.registerImage(c.begin({ action: 'new' }), image(1)), 'invalid_image')
    assert.equal(c.metadata().retainedImageCount, 0)
  }
  const c = setup()
  const token = c.begin({ action: 'new' })
  const bytes = image(1)
  const expected = bytes.toString('base64')
  c.registerImage(token, bytes)
  bytes.fill(0)
  assert.equal(c.prepareRequest(token).input.images[0].dataBase64, expected)
})

test('safe metadata never contains private payloads; cleanup rejects late callbacks without touching history', () => {
  const c = setup()
  const history = [{ answer: 'saved answer' }]
  c.commitAnswer(capture(c), result('PRIVATE_SOURCE', 'PRIVATE_ANSWER'))
  const token = capture(c, 'continue', 2)
  c.fail(token, { retryable: true })
  assert.doesNotMatch(JSON.stringify(c.metadata()), /PRIVATE_|dataBase64|imageHash|synthetic-image/)
  const before = c.metadata().generation
  c.dispose()
  c.dispose()
  assert.ok(c.metadata().generation > before)
  assert.equal(c.metadata().retainedImageCount, 0)
  assert.equal(c.metadata().pendingTurnId, null)
  assert.equal(c.metadata().answerCount, 0)
  assert.equal(c.metadata().retainedBytes, 0)
  rejects(() => c.registerImage(token, image(3)), 'stale_attempt')
  rejects(() => c.commitAnswer(token, result('late', 'late')), 'stale_attempt')
  assert.deepEqual(history, [{ answer: 'saved answer' }])
})

test('real auth manager invalidates before failed remote end/logout and account replacement', async () => {
  for (const action of ['end', 'logout', 'replace', 'clear', 'switch']) {
    const c = setup()
    const token = capture(c)
    const manager = new DesktopAuthSessionManager({ onScreenContextBoundary: () => c.invalidate() })
    manager.session = { access_token: 'fake-token' }
    manager.user = { user_id: 'fake-user' }
    manager.activeInterviewSession = { id: 'cloud' }
    manager.status = 'connected'
    manager._hasFreshVerification = () => true
    manager._backendJson = async () => {
      if (action === 'switch') return { ok: true, payload: { session: { id: 'new-cloud', status: 'active' } } }
      assert.equal(c.metadata().status, 'disposed')
      return { status: 503, ok: false }
    }
    manager.fetchImpl = async () => { assert.equal(c.metadata().status, 'disposed'); throw new Error('offline') }
    manager._writeStoredSession = () => {}
    manager._verifyAndBootstrap = async () => { assert.equal(c.metadata().status, 'disposed'); return {} }
    if (action === 'end') await manager.endInterviewSession('cloud')
    if (action === 'logout') await manager.logout()
    if (action === 'replace') await manager._installExchangedSession({}, { attempt_generation: manager.loginAttemptGeneration })
    if (action === 'clear') manager._clearLocalSession('signed-out')
    if (action === 'switch') await manager.createInterviewSession({ company_name: 'test' }, { idempotencyKey: 'key' })
    assert.equal(c.metadata().status, 'disposed', action)
    rejects(() => c.commitEvidence(token, result()), 'stale_attempt')
  }
})

test('main session finalization disposes before await even if cloud fails; shutdown and owner disposal are hooked', async () => {
  const source = readFileSync(new URL('../electron/main.cjs', import.meta.url), 'utf8')
  const functionSource = source.slice(source.indexOf('async function finalizeActiveInterviewSession('), source.indexOf('function closeStartupWindow('))
  const c = setup()
  capture(c)
  const finalize = vm.runInNewContext(`(${functionSource.trim()})`, {
    screenContext: c,
    grpcRealtimeClient: { close: () => assert.equal(c.metadata().status, 'disposed') },
    desktopAuthSessionManager: { hasActiveInterviewSession: () => true, endActiveInterviewSession: async () => {
      assert.equal(c.metadata().status, 'disposed')
      throw new Error('offline')
    } }, console: { error() {} },
  })
  assert.equal((await finalize()).ok, false)
  assert.match(source, /mainWindow\.on\('closed', \(\) => \{\s*screenContext\.dispose\(\)/)
  assert.match(source, /app\.on\('before-quit', \(event\) => \{\s*screenContext\.invalidate\(\)/)
  assert.match(source, /app\.on\('will-quit', \(\) => \{\s*screenContext\.dispose\(\)/)
  const preload = readFileSync(new URL('../electron/preload.cjs', import.meta.url), 'utf8')
  assert.match(preload, /screen:context-execute/)
  assert.doesNotMatch(preload, /commitAnswer|prepareRequest|dataBase64/)
})

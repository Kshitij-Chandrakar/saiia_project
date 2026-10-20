import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { EventEmitter } from 'node:events'
import { screenContextCommandFence, isCurrentScreenDelivery } from './screen_context_events.js'
const require = createRequire(import.meta.url)
const { createScreenContextController } = require('../electron/screen_context_controller.cjs')
const { createScreenContextExecution, registerScreenContextIpc } = require('../electron/screen_context_execution.cjs')
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }
const tick = () => new Promise(resolve => setImmediate(resolve))
async function until(check) { for (let i = 0; i < 200; i++) { if (check()) return; await tick() } assert.fail('Expected boundary was not reached') }

function fixture(t, options = {}) {
  const requests = [], events = [], diagnostics = []
  let execution, captures = 0
  const controller = createScreenContextController({ inspectImage: () => ({ width: 10, height: 10 }), onBoundary: () => execution?.boundary() })
  controller.adoptSession({ runtimeSessionId: 'runtime' })
  execution = createScreenContextExecution({ controller, backendUrl: 'http://127.0.0.1:8000',
    capture: async ownership => { captures++; return options.capture ? options.capture(ownership) : { imageDataUrl: `data:image/png;base64,${Buffer.from('image-' + captures).toString('base64')}` } },
    authorize: options.authorize || (async () => ({ isCurrent: () => true })),
    diagnose: value => { diagnostics.push(value); options.diagnose?.(value) },
    publish: event => { events.push(event); options.publish?.(event) },
    fetchImpl: async (_url, init) => {
      const form = await new Response(init.body, { headers: { 'Content-Type': init.headers['Content-Type'] } }).formData()
      const request = JSON.parse(form.get('context')); requests.push(request)
      if (options.transport) return options.transport(request)
      const answered = options.outcome !== 'failed'
      const delta = { text: 'source', complete: true, imageHashes: [request.input.currentImageHash], replacesTurnIds: request.replacesTurnIds }
      return Response.json({ contractVersion: '1', identity: request.identity, outcome: answered ? 'answered' : 'failed', committable: answered,
        controllerResult: answered ? { validated: true, evidence: { text: 'source', complete: true }, answer: 'answer' } : null,
        evidenceDelta: answered ? delta : null, answer: answered ? 'answer' : '',
        items: answered ? [{ index: 1, display_number: '', question: 'question', question_type: 'visual', answer: 'answer', language: '', code: '',
          question_id: `${request.identity.turnId}:1` }] : [], missingDetails: [], conflicts: [], clarification: null,
        errorCode: answered ? null : 'provider_error', metrics: { logicalScreenCalls: 1, httpAttempts: 1, sdkMaxRetries: 0, imagesSupplied: request.input.images.length, newCaptureCount: 1 } })
    } })
  t.after(() => { options.publish = options.diagnose = null; execution.cancel(); controller.dispose() })
  return { controller, execution, requests, events, diagnostics, get captures() { return captures },
    async done() { await until(() => !['capturing', 'processing'].includes(execution.status().phase)) } }
}

test('Stop before queued capture starts admits no native work; repeated Stop is harmless', async t => {
  const f = fixture(t)
  f.execution.execute({ action: 'new' }); f.execution.cancel(); f.execution.cancel()
  await tick(); assert.equal(f.captures, 0); assert.equal(f.requests.length, 0)
  assert.equal(f.controller.metadata().retainedBytes, 0)
})

test('Stop during native capture rejects the delayed image and preserves restoration ownership', async t => {
  const capture = deferred(); let ownership
  const f = fixture(t, { capture: value => { ownership = value; return capture.promise } })
  f.execution.execute({ action: 'new' }); await until(() => ownership)
  f.execution.cancel(); assert.equal(ownership.isCurrent(), false); assert.equal(ownership.canRestore(), true)
  capture.resolve({ imageDataUrl: 'data:image/png;base64,eA==' }); await tick(); await tick()
  assert.equal(f.requests.length, 0); assert.equal(f.controller.metadata().retainedImageCount, 0)
  assert.equal(f.execution.status().phase, 'cancelled'); assert.equal(f.execution.status().retryAvailable, false)
})

test('Stop abandons an uncooperative transport locally and cancels its late body exactly once', async t => {
  const transport = deferred(); let cancelled = 0
  const f = fixture(t, { transport: () => transport.promise })
  f.execution.execute({ action: 'new' }); await until(() => f.requests.length === 1)
  f.execution.cancel(); const sequence = f.execution.status().sequence
  transport.resolve({ body: { cancel: async () => { cancelled++ } } })
  await until(() => cancelled === 1)
  assert.equal(f.execution.status().sequence, sequence); assert.equal(f.controller.metadata().revision, 0)
  assert.equal(f.controller.metadata().retainedBytes, 0)
})

test('Stop after validation but before commit rejects a still-successful auth callback', async t => {
  let f, checks = 0
  f = fixture(t, { authorize: async () => ({ isCurrent: () => { if (++checks === 3) f.execution.cancel(); return true } }) })
  f.execution.execute({ action: 'new' }); await f.done(); await tick()
  assert.equal(checks, 3); assert.equal(f.controller.metadata().revision, 0); assert.deepEqual(f.controller.deliveries(), [])
})

for (const action of ['new', 'reference']) test(`${action} supersession survives old catch/finally and keeps the new lock`, async t => {
  const first = deferred(), second = deferred()
  const f = fixture(t, { transport: () => f.requests.length === 1 ? first.promise : second.promise })
  f.execution.execute({ action: 'new' }); await until(() => f.requests.length === 1)
  f.execution.execute({ action }); await until(() => f.requests.length === 2)
  const active = f.execution.status().identity
  first.reject(new Error('late transport failure')); await tick(); await tick()
  assert.equal(f.execution.status().phase, 'processing'); assert.deepEqual(f.execution.status().identity, active)
  f.execution.cancel(); second.reject(new Error('cancelled'))
})

test('duplicate renderer OCR command is idempotent; stale cancel/retry cannot touch replacement work', async t => {
  const capture = deferred()
  const f = fixture(t, { capture: () => capture.promise })
  const command = { action: 'new', commandId: 'ocr-one', expected: screenContextCommandFence(f.execution.status()) }
  f.execution.execute(command); f.execution.execute(command)
  await until(() => f.captures === 1)
  const old = { expected: screenContextCommandFence(f.execution.status()) }
  f.execution.execute({ action: 'reference', commandId: 'ocr-two', expected: old.expected })
  assert.throws(() => f.execution.cancel(old), /stale_command/)
  assert.throws(() => f.execution.retry(old), /stale_command/)
  assert.equal(f.execution.status().contextKind, 'reference')
  f.execution.cancel(); capture.resolve({ imageDataUrl: 'data:image/png;base64,eA==' })
})

test('lost commit notification replays without provider retry; later Stop retains the completed commit', async t => {
  const f = fixture(t, { publish: event => { if (event.result) throw Error('synthetic send failure') } })
  f.execution.execute({ action: 'new' }); await f.done()
  assert.equal(f.controller.metadata().revision, 1); assert.equal(f.execution.status().retryAvailable, false)
  assert.throws(() => f.execution.retry())
  const [delivery] = f.execution.status().deliveries
  const retained = f.controller.metadata().retainedBytes
  f.execution.cancel()
  assert.equal(isCurrentScreenDelivery(delivery, f.execution.status()), true)
  assert.equal(f.execution.acknowledge({ ...delivery.identity, requestId: 'wrong' }), false)
  assert.equal(f.execution.acknowledge(delivery.identity), true)
  assert.equal(f.execution.acknowledge(delivery.identity), false)
  assert.ok(f.controller.metadata().retainedBytes < retained)
  assert.equal(f.controller.metadata().acceptedImageCount, 1)
})

for (const boundary of ['capture', 'prepare_request', 'response_validate']) test(`session end at ${boundary} closes context and rejects queued IPC`, async t => {
  let f, capture = deferred()
  const options = boundary === 'capture' ? { capture: () => capture.promise } : {
    diagnose: event => { if (event.stage === boundary) f.controller.invalidate() },
  }
  f = fixture(t, options)
  const old = screenContextCommandFence(f.execution.status())
  f.execution.execute({ action: 'new' })
  if (boundary === 'capture') { await until(() => f.captures === 1); f.controller.invalidate(); capture.resolve({ imageDataUrl: 'data:image/png;base64,eA==' }) }
  await until(() => f.controller.metadata().status === 'disposed')
  const handlers = new Map(); registerScreenContextIpc({ handle: (key, fn) => handlers.set(key, fn) }, () => {}, () => true, f.execution)
  assert.throws(() => handlers.get('screen:context-execute')({}, { action: 'new', commandId: 'old', expected: old }))
  assert.equal(f.controller.metadata().retainedBytes, 0); assert.deepEqual(f.execution.status().deliveries, [])
})

const main = readFileSync(new URL('../electron/main.cjs', import.meta.url), 'utf8')
function hiddenFixture() {
  const calls = [], make = name => Object.assign(new EventEmitter(), { visible: true, destroyed: false,
    isDestroyed() { return this.destroyed },
    hide() { this.visible = false; calls.push(name + ':hide'); this.emit('hide') },
    show() { this.visible = true; calls.push(name + ':show'); this.emit('show') }, showInactive() { this.show() } })
  const delay = deferred()
  const context = { mainWindow: make('main'), overlayWindow: make('overlay'), overlayVisibilityIntent: 1,
    screenRuntimeEnding: false, quittingAfterSessionFinalize: false, captureWindowQueue: Promise.resolve(),
    getWindowVisibilitySnapshot: window => ({ window, wasVisible: window.visible }), delay: () => delay.promise, ANALYZE_SCREEN_HIDE_DELAY_MS: 0 }
  const source = main.slice(main.indexOf('async function withSaiiaWindowsHidden('), main.indexOf('function getOverlayBoundsStatePath('))
  return { calls, context, delay, make, run: vm.runInNewContext(`(${source.trim()})`, context) }
}

test('Stop during hide skips native task but restores owned main; explicit overlay hide is not undone', async () => {
  const f = hiddenFixture(); let current = true, native = 0
  const pending = f.run(async () => { native++ }, { isCurrent: () => current })
  await tick(); current = false; f.context.overlayVisibilityIntent++
  f.delay.resolve(); await assert.rejects(pending, /stale_attempt/)
  assert.equal(native, 0); assert.equal(f.context.mainWindow.visible, true); assert.equal(f.context.overlayWindow.visible, false)
})

for (const boundary of ['session', 'account', 'logout']) test(`${boundary} invalidation restores owned main but never obsolete overlay`, async () => {
  const f = hiddenFixture(), native = deferred(); let restore = true
  f.delay.resolve()
  const pending = f.run(() => native.promise, { canRestore: () => restore })
  await tick(); restore = false; native.resolve({})
  await pending; assert.equal(f.context.mainWindow.visible, true); assert.equal(f.context.overlayWindow.visible, false)
  assert.equal(f.context.mainWindow.listenerCount('hide'), 0)
})

for (const boundary of ['shutdown', 'finalized', 'destroyed', 'replaced', 'hidden', 'minimized', 'closing']) test(`${boundary} prevents unwanted main restoration`, async () => {
  const f = hiddenFixture(), native = deferred(), original = f.context.mainWindow
  f.delay.resolve(); const pending = f.run(() => native.promise); await tick()
  if (boundary === 'shutdown') f.context.screenRuntimeEnding = true
  if (boundary === 'finalized') f.context.quittingAfterSessionFinalize = true
  if (boundary === 'destroyed') original.destroyed = true
  if (boundary === 'replaced') f.context.mainWindow = f.make('replacement')
  if (boundary === 'hidden') original.hide()
  if (boundary === 'minimized') original.emit('minimize')
  if (boundary === 'closing') original.emit('close')
  native.resolve({}); await pending
  assert.equal(original.visible, false)
  assert.equal(f.calls.includes('replacement:show'), false)
  assert.equal(original.listenerCount('hide'), 0)
})

test('overlapping captures serialize hide and owned restoration before the next task', async () => {
  const f = hiddenFixture(), first = deferred(), second = deferred(); let started = 0
  f.delay.resolve()
  const a = f.run(() => { started++; return first.promise })
  const b = f.run(() => { started++; return second.promise })
  await tick(); assert.equal(started, 1); assert.equal(f.context.mainWindow.visible, false)
  first.resolve({}); await a; await tick(); assert.equal(started, 2)
  assert.deepEqual(f.calls.slice(0, 5), ['main:hide', 'overlay:hide', 'main:show', 'overlay:show', 'main:hide'])
  second.resolve({}); await b; assert.equal(f.context.mainWindow.visible, true)
})

test('capture does not reveal initially hidden windows or mistake a delayed own hide event for user intent', async () => {
  const f = hiddenFixture(), native = deferred()
  f.context.overlayWindow.visible = false
  f.context.mainWindow.hide = function () { this.visible = false; f.calls.push('main:hide') }
  f.delay.resolve(); const pending = f.run(() => native.promise); await tick()
  f.context.mainWindow.emit('hide'); native.resolve({}); await pending
  assert.equal(f.context.mainWindow.visible, true); assert.equal(f.context.overlayWindow.visible, false)
})

test('queued startup cannot reopen admission while logout or shutdown finalization is pending', () => {
  const source = main.slice(main.indexOf('function completeStartupFlow()'), main.indexOf('function collapseStartupWindow('))
  for (const [ending, logout] of [[true, 0], [false, 1]]) {
    let reset = 0
    const complete = vm.runInNewContext(`(${source.trim()})`, { screenRuntimeEnding: ending, screenLogoutPending: logout,
      startupWindowController: { reset: () => reset++ } })
    assert.equal(complete().reason, 'lifecycle-ending'); assert.equal(reset, 0)
  }
})

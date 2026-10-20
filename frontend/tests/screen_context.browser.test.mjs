import { before, after, test } from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import { mkdir } from 'node:fs/promises'
import { createServer } from 'vite'
import { chromium, expect } from '@playwright/test'
const require = createRequire(import.meta.url)
const { createScreenContextController } = require('../electron/screen_context_controller.cjs')
const { createScreenContextExecution } = require('../electron/screen_context_execution.cjs')
let server, browser, url
const artifacts = resolve(import.meta.dirname, '../../tmp/screen-context-phase3')
before(async () => {
  server = await createServer({ root: resolve(import.meta.dirname, '..'), server: { host: '127.0.0.1', port: 0 }, logLevel: 'error' })
  await server.listen(); url = server.resolvedUrls.local[0]
  browser = await chromium.launch({ headless: true }); await mkdir(artifacts, { recursive: true })
})
after(async () => { await browser?.close(); await server?.close() })

async function setup() {
  const context = await browser.newContext({ viewport: { width: 1200, height: 850 } })
  await context.tracing.start({ screenshots: true, snapshots: true })
  const pages = []; const requests = []; const waiting = []; const pageErrors = []; const events = []
  let overlayState = {}, captures = 0, outcome = 'answered', batch = 1, held = false, execution, captureError = null, dropEvents = false, dropAck = false
  const send = (name, data) => {
    if (name === 'screen' && dropEvents) return
    for (const page of pages) void page.evaluate(({ name, data }) => window.screenTestEmit?.(name, data), { name, data }).catch(() => {})
  }
  const controller = createScreenContextController({ inspectImage: () => ({ width: 10, height: 10 }), onBoundary: () => execution?.boundary() })
  controller.adoptSession({ runtimeSessionId: 'playwright-runtime' })
  execution = createScreenContextExecution({ controller, backendUrl: 'http://127.0.0.1:8000',
    capture: async () => { if (captureError) throw captureError; captures += 1; return { imageDataUrl: `data:image/png;base64,${Buffer.from(`diagram-${captures}`).toString('base64')}` } },
    authorize: async () => ({ authorization: 'Bearer PRIVATE_TOKEN', isCurrent: () => true }),
    publish: status => { events.push(status); send('screen', status) },
    fetchImpl: async (_url, init) => {
      const form = await new Response(init.body, { headers: { 'content-type': init.headers['Content-Type'] } }).formData()
      const request = JSON.parse(form.get('context')); requests.push(request)
      const answered = outcome === 'answered', collecting = ['needs_more_content', 'reference_accepted'].includes(outcome)
      const evidence = { text: 'PRIVATE_SOURCE code and diagram', complete: answered }
      const target = request.targetQuestionId || (request.contextKind !== 'reference' && request.priorItems.length === 1 ? request.priorItems[0].questionId : null)
      const result = { contractVersion: '1', identity: request.identity, outcome, committable: answered || collecting,
        controllerResult: answered ? { validated: true, evidence, answer: `Answer for capture ${captures}` } : collecting ? { validated: true, evidence } : null,
        evidenceDelta: answered || collecting ? { ...evidence, imageHashes: request.input.images.map(image => image.imageHash), replacesTurnIds: request.replacesTurnIds } : null,
        answer: answered ? `Answer for capture ${captures}` : '',
        items: answered ? Array.from({ length: batch }, (_, i) => ({ index: i + 1, display_number: '', question: `Diagram problem ${i + 1}`,
          question_type: 'visual', answer: 'Diagram answer', language: '', code: '', question_id: target || `${request.identity.turnId}:${i + 1}` })) : [],
        missingDetails: outcome === 'needs_more_content' ? ['Capture remaining constraints'] : [], conflicts: [],
        clarification: outcome === 'needs_clarification' ? 'Does this code replace the earlier version?' : null,
        errorCode: outcome === 'failed' ? 'provider_error' : null,
        metrics: { logicalScreenCalls: 1, httpAttempts: 1, sdkMaxRetries: 0, imagesSupplied: request.input.images.length, newCaptureCount: 1 } }
      if (held) await new Promise(resolve => waiting.push(resolve))
      return Response.json(result)
    } })
  async function pageAt(path) {
    const page = await context.newPage(); pages.push(page); page.on('pageerror', error => pageErrors.push(error.message))
    await page.exposeFunction('screenTestCall', async (method, payload) => {
      if (method === 'status') return execution.status()
      if (method === 'acknowledge' && dropAck) throw new Error('simulated acknowledgement loss')
      if (['execute', 'cancel', 'retry', 'resolve', 'acknowledge'].includes(method)) return execution[method](payload)
      if (method === 'overlay:get') return overlayState
      if (method === 'overlay:update') { overlayState = payload; send('overlay', payload); return }
      if (method === 'toolbar') { send('toolbar', payload); return }
      return null
    })
    await page.addInitScript(() => {
      const listeners = new Map()
      window.screenTestEmit = (name, value) => listeners.get(name)?.forEach(fn => fn(value))
      const on = name => fn => { if (!listeners.has(name)) listeners.set(name, new Set()); listeners.get(name).add(fn); return () => listeners.get(name).delete(fn) }
      window.electronAPI = {
        getScreenContextStatus: () => window.screenTestCall('status'), onScreenContextEvent: on('screen'),
        executeScreenContext: value => window.screenTestCall('execute', value), cancelScreenContext: value => window.screenTestCall('cancel', value),
        retryScreenContext: value => window.screenTestCall('retry', value), resolveScreenClarification: value => window.screenTestCall('resolve', value),
        acknowledgeScreenContextResult: value => window.screenTestCall('acknowledge', value),
        getOverlayState: () => window.screenTestCall('overlay:get'), onOverlayState: on('overlay'),
        updateOverlayState: value => window.screenTestCall('overlay:update', value),
        triggerToolbarAction: (action, payload) => window.screenTestCall('toolbar', { action, payload }), onToolbarAction: on('toolbar'),
        getAuthState: async () => ({ status: 'signed-out' }), getCloudStartupContext: async () => ({ available: false }),
        getGrpcRealtimeStatus: async () => ({}), getOverlayBounds: async () => ({ width: 1200, height: 850 }),
        resizeOverlayBottomRight: async () => {}, getSystemAudioStatus: async () => ({}),
      }
      window.saiia = window.electronAPI
    })
    await page.route('**/api/**', route => route.fulfill({ json: {} }))
    await page.goto(url + path)
    return page
  }
  const main = await pageAt('desktop?view=main')
  await main.waitForFunction(() => Boolean(window.electronAPI))
  const overlay = await pageAt('?view=overlay')
  const trigger = overlay.getByRole('button', { name: /Analyze Screen/ }).first()
  await trigger.waitFor()
  return { main, overlay, trigger, requests, waiting, controller, execution, events,
    get captures() { return captures }, get overlayState() { return overlayState },
    set outcome(value) { outcome = value }, set batch(value) { batch = value }, set held(value) { held = value },
    set captureError(value) { captureError = value },
    set dropEvents(value) { dropEvents = value }, set dropAck(value) { dropAck = value },
    async execute(action) {
      await trigger.click()
      if (action) await overlay.getByRole('radio', { name: action }).check()
      await overlay.getByRole('button', { name: /^OCR/ }).click()
    },
    async finished(revision) {
      await expect.poll(() => controller.metadata().revision).toBe(revision)
      if (outcome === 'answered') await expect.poll(() => overlayState.questionHistory?.screen?.entries?.length || 0).toBe(revision)
    },
    async close(name) {
      execution.cancel()
      await context.tracing.stop({ path: resolve(artifacts, `${name}.zip`) })
      await context.close(); assert.deepEqual(pageErrors, [])
    } }
}

for (const loss of ['notification', 'acknowledgement']) test(`renderer recreation recovers ${loss} loss without duplicate history or recapture`, { timeout: 30000 }, async () => {
  const s = await setup()
  try {
    s.dropEvents = loss === 'notification'; s.dropAck = loss === 'acknowledgement'
    await s.execute('New question')
    await expect.poll(() => s.controller.metadata().revision).toBe(1)
    if (loss === 'acknowledgement') await s.finished(1)
    assert.equal(s.controller.deliveries().length, 1)
    s.dropEvents = false; s.dropAck = false
    await s.main.reload()
    await expect.poll(() => s.overlayState.questionHistory?.screen?.entries?.length).toBe(1)
    await expect.poll(() => s.controller.deliveries().length).toBe(0)
    const completed = s.events.findLast(event => event.result)
    await s.main.evaluate(event => window.screenTestEmit('screen', event), completed)
    await s.main.evaluate(() => window.electronAPI.getScreenContextStatus())
    assert.equal(s.overlayState.questionHistory.screen.entries.length, 1)
    assert.equal(s.captures, 1); assert.equal(s.requests.length, 1)
  } finally { await s.close(`delivery-${loss}`) }
})

test('ambiguous capture shows focus guidance without offering a nonexistent retained screenshot', { timeout: 30000 }, async () => {
  const s = await setup()
  try {
    s.captureError = Object.assign(new Error('PRIVATE_TITLE'), { code: 'active_window_not_identified', reason: 'active_window_ambiguous' })
    await s.execute('Passage / Data')
    await expect(s.overlay.getByRole('alert')).toHaveText('Could not identify the passage or question window. Focus that window, then reopen Analyze Screen and choose OCR.')
    await expect(s.overlay.getByRole('button', { name: 'Retry captured screenshot', exact: true })).toHaveCount(0)
    assert.equal(s.requests.length, 0); assert.equal(s.controller.metadata().acceptedImageCount, 0)
    s.captureError = null; s.outcome = 'reference_accepted'
    await s.execute('Passage / Data')
    await expect(s.overlay.getByText('Reference saved. Capture your question using Continue previous question.')).toBeVisible()
    assert.equal(s.requests.length, 1)
  } finally { await s.close('ambiguous-capture-recovery') }
})

test('real overlay chooser and shortcut are passive; keyboard dismissal, explicit choice and single capture', { timeout: 30000 }, async () => {
  const s = await setup()
  try {
    await s.trigger.click()
    await expect(s.overlay.getByRole('radio', { name: 'Continue previous question' })).toBeDisabled()
    await expect(s.overlay.getByRole('radio', { name: 'New question' })).toBeChecked()
    await s.overlay.getByRole('radio', { name: 'New question' }).check()
    await s.overlay.getByRole('radio', { name: 'Passage / Data' }).check()
    assert.equal(s.captures, 0); assert.equal(s.controller.metadata().threadId, null)
    await s.overlay.getByRole('radio', { name: 'New question' }).check()
    assert.equal(s.captures, 0); assert.equal(s.requests.length, 0); assert.equal(s.controller.metadata().threadId, null)
    await s.overlay.keyboard.press('Escape'); await expect(s.trigger).toBeFocused()
    // Same toolbar action emitted by the registered Ctrl+Shift+Enter handler.
    await s.overlay.evaluate(() => window.screenTestEmit('toolbar', { action: 'analyze-screen' }))
    await expect(s.overlay.getByRole('dialog', { name: 'Analyze Screen' })).toBeVisible()
    assert.equal(s.captures, 0)
    await s.overlay.screenshot({ path: resolve(artifacts, 'chooser.png') })
    await s.overlay.getByRole('button', { name: /^OCR/ }).evaluate(button => { button.click(); button.click() })
    await s.finished(1); assert.equal(s.captures, 1)
    const completed = s.events.findLast(event => event.result)
    await s.main.evaluate(event => window.screenTestEmit('screen', event), completed)
    await s.main.evaluate(() => window.electronAPI.getScreenContextStatus())
    assert.equal(s.overlayState.questionHistory.screen.entries.length, 1)
    await s.trigger.click()
    await expect(s.overlay.getByRole('button', { name: /^OCR/ })).toBeDisabled()
    await s.overlay.getByRole('radio', { name: 'Continue previous question' }).check()
    await s.overlay.keyboard.press('Escape'); await s.trigger.click()
    await expect(s.overlay.getByRole('radio', { name: 'Continue previous question' })).not.toBeChecked()
    assert.equal(s.controller.metadata().revision, 1)
  } finally { await s.close('chooser') }
})

test('Passage / Data is passive until OCR; two questions retain reference, replacement and New isolate context', { timeout: 45000 }, async () => {
  const s = await setup()
  try {
    s.outcome = 'reference_accepted'; await s.execute('Passage / Data')
    await expect(s.overlay.getByText('Reference saved. Capture your question using Continue previous question.')).toBeVisible()
    assert.equal(s.controller.metadata().acceptedImageCount, 1)
    assert.equal(s.overlayState.questionHistory.screen.entries.length, 0)
    const passageHash = s.requests[0].input.currentImageHash
    const oldThread = s.controller.metadata().threadId
    await s.trigger.click(); await s.overlay.getByRole('radio', { name: 'Passage / Data' }).check()
    assert.equal(s.controller.metadata().threadId, oldThread)
    assert.equal(s.captures, 1)
    await s.overlay.keyboard.press('Escape')
    s.outcome = 'answered'; await s.execute('Continue previous question')
    await expect.poll(() => s.overlayState.questionHistory.screen.entries.length).toBe(1)
    await s.execute('Continue previous question')
    await expect.poll(() => s.overlayState.questionHistory.screen.entries.length).toBe(2)
    assert.equal(s.requests[2].input.images[0].imageHash, passageHash)
    assert.equal(s.requests[2].input.answers.length, 1)
    assert.equal(s.requests[2].targetQuestionId, null)
    assert.equal(s.controller.metadata().priorItems.length, 2)
    s.outcome = 'reference_accepted'; await s.execute('Passage / Data')
    await expect.poll(() => s.requests.length).toBe(4)
    await expect.poll(() => s.controller.metadata().revision).toBe(1)
    assert.deepEqual(s.requests[3].input.evidence, [])
    assert.deepEqual(s.requests[3].input.answers, [])
    assert.equal(s.requests[3].input.images.length, 1)
    await expect(s.overlay.getByText('Displayed answer belongs to an earlier question.')).toBeVisible()
    s.outcome = 'answered'; await s.execute('New question')
    await expect.poll(() => s.overlayState.questionHistory.screen.entries.length).toBe(3)
    assert.equal(s.requests[4].contextKind, 'question')
    assert.deepEqual(s.requests[4].input.evidence, [])
    assert.deepEqual(s.requests[4].input.answers, [])
    await s.trigger.click()
    await s.overlay.screenshot({ path: resolve(artifacts, 'three-option-chooser.png') })
  } finally { await s.close('reference-workflow') }
})

test('New selection leaves running work intact; execution supersedes it and late response cannot overwrite history', { timeout: 30000 }, async () => {
  const s = await setup()
  try {
    await s.execute(); await s.finished(1)
    s.held = true; await s.execute('Continue previous question')
    await expect.poll(() => s.waiting.length).toBe(1)
    const before = s.controller.metadata()
    await s.trigger.click()
    await s.overlay.getByRole('radio', { name: 'New question' }).check()
    assert.equal(s.controller.metadata().threadId, before.threadId)
    assert.equal(s.controller.metadata().pendingTurnId, before.pendingTurnId)
    assert.equal(s.captures, 2)
    s.held = false
    await s.overlay.getByRole('button', { name: /^OCR/ }).click()
    await expect.poll(() => s.overlayState.questionHistory.screen.entries.length).toBe(2)
    const late = s.waiting.shift(); late()
    await s.main.evaluate(() => window.electronAPI.getScreenContextStatus())
    assert.equal(s.overlayState.screenAnswerText, 'Answer for capture 3')
    assert.equal(s.controller.metadata().revision, 1)
    assert.equal(s.requests[2].input.images.length, 1)
  } finally { await s.close('supersession') }
})

test('batch targets remain stable through continuation and result-panel Analyze Screen opens chooser', { timeout: 30000 }, async () => {
  const s = await setup()
  try {
    s.batch = 2; await s.execute(); await s.finished(1)
    const items = s.controller.metadata().priorItems
    assert.equal(items.length, 2)
    // The result-panel button follows the toolbar button in document order.
    await s.overlay.getByRole('button', { name: 'Analyze Screen', exact: true }).last().click()
    await expect(s.overlay.getByRole('dialog', { name: 'Analyze Screen' })).toBeVisible()
    assert.equal(s.captures, 1)
    await s.overlay.getByRole('radio', { name: 'Continue previous question' }).check()
    await s.overlay.getByRole('combobox', { name: 'Continue which question?' }).selectOption(items[1].questionId)
    s.batch = 1
    await s.overlay.getByRole('button', { name: /^OCR/ }).click(); await s.finished(2)
    assert.equal(s.requests[1].targetQuestionId, items[1].questionId)
    assert.deepEqual(s.controller.metadata().priorItems, items)
    await s.trigger.click()
    await s.overlay.getByRole('dialog', { name: 'Analyze Screen' }).getByRole('button', { name: /^Extension/ }).click()
    await expect(s.overlay.getByText('Browser extension connection is not available yet.', { exact: true })).toBeVisible()
    assert.equal(s.captures, 2)
    assert.equal(s.controller.metadata().revision, 2)
  } finally { await s.close('batch-target') }
})

test('three screenshots, earlier diagram and AI answer continuity; New preserves attributed display/history', { timeout: 30000 }, async () => {
  const s = await setup()
  try {
    await s.execute(); await s.finished(1)
    await s.execute('Continue previous question'); await s.finished(2)
    await s.execute('Continue previous question'); await s.finished(3)
    assert.equal(s.requests[2].input.images.length, 3); assert.equal(s.requests[2].input.answers.length, 2)
    s.held = true; await s.execute('New question')
    await expect.poll(() => s.requests.length).toBe(4)
    assert.equal(s.requests[3].input.evidence.length, 0); assert.equal(s.requests[3].input.answers.length, 0)
    await expect(s.overlay.getByText('Displayed answer belongs to an earlier question.')).toBeVisible()
    assert.equal(s.overlayState.questionHistory.screen.entries.length, 3)
    s.execution.cancel(); s.waiting.shift()()
    assert.equal(s.controller.metadata().evidenceCount, 0)
  } finally { await s.close('continuity') }
})

test('More content needed commits only evidence; clarification resolves retained capture with explicit replacement', { timeout: 30000 }, async () => {
  const s = await setup()
  try {
    s.outcome = 'needs_more_content'; await s.execute(); await s.finished(1)
    await expect(s.overlay.getByText('More content needed', { exact: true })).toBeVisible()
    assert.equal(s.overlayState.questionHistory.screen.entries.length, 0)
    s.outcome = 'needs_clarification'; await s.execute('Continue previous question')
    await expect(s.overlay.getByText('Clarification needed', { exact: true })).toBeVisible()
    assert.equal(s.controller.metadata().revision, 1)
    await s.overlay.getByRole('checkbox', { name: 'Screenshot turn 1' }).check()
    await s.overlay.getByRole('textbox', { name: 'Your clarification' }).fill('Use this corrected code.')
    s.outcome = 'answered'
    await s.overlay.getByRole('button', { name: 'Resolve and retry captured screenshot' }).click()
    await expect.poll(() => s.controller.metadata().revision).toBe(2)
    await expect.poll(() => s.overlayState.questionHistory.screen.entries.length).toBe(1)
    assert.equal(s.captures, 2); assert.ok(s.requests[2].clarificationResponse.text)
    assert.equal(s.requests[2].replacesTurnIds.length, 1)
    await s.overlay.screenshot({ path: resolve(artifacts, 'resolved.png') })
  } finally { await s.close('clarification') }
})

test('failed request retries without capture or duplicate history; session cleanup fences a late response', { timeout: 30000 }, async () => {
  const s = await setup()
  try {
    s.outcome = 'failed'; await s.execute()
    await expect(s.overlay.getByRole('button', { name: 'Retry captured screenshot' })).toBeVisible()
    s.outcome = 'answered'; await s.overlay.getByRole('button', { name: 'Retry captured screenshot' }).click()
    await s.finished(1); assert.equal(s.captures, 1)
    s.held = true; await s.execute('Continue previous question')
    await expect.poll(() => s.waiting.length).toBe(1)
    const old = s.execution.status(); s.controller.invalidate(); s.waiting.shift()()
    await expect.poll(() => s.execution.status().status).toBe('disposed')
    await s.overlay.evaluate(event => window.screenTestEmit('screen', event), old)
    await expect(s.overlay.getByText(/No active screen question/)).toBeVisible()
    assert.equal(s.overlayState.questionHistory.screen.entries.length, 1)
    assert.doesNotMatch(JSON.stringify(s.overlayState), /PRIVATE_TOKEN|PRIVATE_SOURCE|dataBase64/)
  } finally { await s.close('retry-session') }
})

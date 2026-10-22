import { before, after, test } from 'node:test'
import assert from 'node:assert/strict'
import { resolve } from 'node:path'
import { createServer } from 'vite'
import { chromium, expect } from '@playwright/test'
import { answerStreamDriver } from './fixtures/answer_stream_driver.mjs'

let server, browser, url
before(async () => {
  server = await createServer({ root: resolve(import.meta.dirname, '..'),
    server: { host: '127.0.0.1', port: 0 }, logLevel: 'error' })
  await server.listen()
  url = server.resolvedUrls.local[0]
  browser = await chromium.launch({ headless: true })
})
after(async () => { await browser?.close(); await server?.close() })

for (const source of ['microphone', 'system', 'both']) {
  test(`negotiated main AND overlay ${source}: primary/fallback prefixes before completion`, { timeout: 30000 }, async () => {
    const page = await browser.newPage(), driver = answerStreamDriver(source, true), deliveries = [], errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort())
    driver.subscribe(snapshot => deliveries.push(page.evaluate(value => window.phase1Snapshot(value), snapshot)))
    await page.exposeFunction('phase1Connect', () => driver.connect())
    await page.exposeFunction('phase1Status', () => driver.client.getStatus())
    await page.exposeFunction('phase1Close', () => driver.close())
    const emit = async (kind, payload, overrides) => { driver.emit(kind, payload, overrides); await Promise.all(deliveries.splice(0)) }
    const both = async text => { for (const selector of ['#main-answer', '#overlay-answer']) await expect(page.locator(selector)).toContainText(text) }
    try {
      await page.goto(url + 'tests/fixtures/answer-stream.html')
      await page.waitForFunction(() => typeof window.phase1Start === 'function')
      await page.evaluate(source => window.phase1Start(source), source)
      await emit('question_detected', { text: 'Synthetic question' })
      await emit('answer_delta', { text: 'Primary prefix A' }); await both('Primary prefix A')
      assert.equal(driver.client.answerCompletedCount, 0)
      await emit('answer_delta', { text: ' and B' }); await both('Primary prefix A and B')
      assert.equal(driver.client.answerCompletedCount, 0)
      const identity = { accepted_turn: '1', display_revision: '1', provider_attempt: 1, retry_attempt: 0 }
      await emit('answer_replaced', { text: '' }, { answer_identity: identity })
      for (const selector of ['#main-answer', '#overlay-answer']) await expect(page.locator(selector)).not.toContainText('Primary prefix')
      await emit('answer_delta', { text: 'Fallback prefix A' }); await both('Fallback prefix A')
      assert.equal(driver.client.answerCompletedCount, 0)
      await emit('answer_delta', { text: ' and B' }); await both('Fallback prefix A and B')
      assert.equal(driver.client.answerCompletedCount, 0)
      await emit('answer_replaced', { text: 'Validated canonical' }, { answer_identity: { ...identity, display_revision: '2' } })
      await emit('answer_completed', { text: 'Validated canonical' }); await both('Validated canonical')
      await page.evaluate(() => window.phase3OverlaySnapshot({ answer: 'discarded late primary', overlayPublicationVersion: 1 }))
      await both('Validated canonical')
      await expect(page.locator('#overlay-answer')).not.toContainText('discarded late primary')
      for (const selector of ['#main-answer', '#overlay-answer']) await expect(page.locator(selector)).not.toContainText('Fallback prefix')
      await page.evaluate(() => window.phase1Session.close())
      assert.deepEqual(errors, [])
    } finally { await driver.close(); await page.close() }
  })
}

test('long answer snapshots update the actual main card before completion', {timeout:30000},async t=>{
 const page=await browser.newPage(),driver=answerStreamDriver('both',true),deliveries=[]
 await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort())
 driver.subscribe(snapshot=>deliveries.push(page.evaluate(value=>window.phase1Snapshot(value),snapshot)))
 await page.exposeFunction('phase1Connect',()=>driver.connect());await page.exposeFunction('phase1Status',()=>driver.client.getStatus());await page.exposeFunction('phase1Close',()=>driver.close())
 const emit=async(kind,payload)=>{driver.emit(kind,payload);await Promise.all(deliveries.splice(0))}
 const a='Synthetic mechanism. '.repeat(500),b='Synthetic tradeoff. '.repeat(500)
 try{
  await page.goto(url+'tests/fixtures/answer-stream.html');await page.waitForFunction(()=>typeof window.phase1Start==='function');await page.evaluate(()=>window.phase1Start('both'))
  await emit('question_detected',{text:'Synthetic long design question'})
  await emit('answer_delta',{text:a});await expect(page.locator('#main-answer .answer-preview')).toHaveText(a.trim());assert.equal(driver.client.answerCompletedCount,0)
  await emit('answer_delta',{text:b});await expect(page.locator('#main-answer .answer-preview')).toHaveText((a+b).trim());assert.equal(driver.client.answerCompletedCount,0)
  const stages=await page.evaluate(()=>window.phase1Stages)
  const local=stages.flatMap((stage,index)=>{const dom=stages.slice(index+1).find(x=>x.stage==='dom_mutation');return stage.stage==='react_state_requested'&&dom?[Number((dom.localMs-stage.localMs).toFixed(2))]:[]})
  const serializeStarted=performance.now()
  const snapshotBytes=driver.snapshots.map(snapshot=>Buffer.byteLength(JSON.stringify(snapshot)))
  const serializeLocalMs=Number((performance.now()-serializeStarted).toFixed(3))
  t.diagnostic(JSON.stringify({syntheticCharacters:(a+b).length,snapshots:driver.snapshots.length,maxSnapshotBytes:Math.max(...snapshotBytes),nodeSerializationLocalMs:serializeLocalMs,browserStateToDomLocalMs:local,paintMeasured:false,providerLatencyMeasured:false}))
  await emit('answer_completed',{text:'Canonical final after long provisional text.'})
  await expect(page.locator('#main-answer .answer-preview')).toHaveText('Canonical final after long provisional text.')
  assert.ok(driver.snapshots.length<20)
 }finally{await driver.close();await page.close()}
})

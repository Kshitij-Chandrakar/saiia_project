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
  test(`Phase 1 rendered ${source}: two actual prefixes precede completion`, { timeout: 30000 }, async t => {
    const page = await browser.newPage(), driver = answerStreamDriver(source)
    await page.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort())
    const deliveries = []
    driver.subscribe(snapshot => deliveries.push(page.evaluate(value => window.phase1Snapshot(value), snapshot)))
    await page.exposeFunction('phase1Connect', () => driver.connect())
    await page.exposeFunction('phase1Status', () => driver.client.getStatus())
    await page.exposeFunction('phase1Close', () => driver.close())
    const emit = async (kind, value) => {
      driver.emit(kind, value)
      await Promise.all(deliveries.splice(0))
    }
    try {
      await page.goto(url + 'tests/fixtures/answer-stream.html')
      await page.waitForFunction(() => typeof window.phase1Start === 'function')
      await page.evaluate(source => window.phase1Start(source), source)
      await emit('question_detected', { text: 'Synthetic question' })
      await emit('answer_delta', { text: 'Prefix A' })
      await expect(page.locator('#root')).toContainText('Prefix A')
      assert.equal(driver.client.getStatus().answerCompletedCount, 0)
      await emit('answer_delta', { text: ' plus B' })
      await expect(page.locator('#root')).toContainText('Prefix A plus B')
      assert.equal(driver.client.getStatus().answerCompletedCount, 0)
      await emit('answer_completed', { text: 'Canonical replacement.' })
      await expect(page.locator('#root')).toContainText('Canonical replacement.')
      await expect(page.locator('#root')).not.toContainText('Prefix A')
      const stages = await page.evaluate(() => window.phase1Stages)
      assert.ok(stages.some(x => x.stage === 'dom_mutation'))
      // Local elapsed times only: never subtract browser and Node timestamps.
      const delays = stages.flatMap((entry, index) => {
        if (entry.stage !== 'react_state_requested') return []
        const dom = stages.slice(index + 1).find(x => x.stage === 'dom_mutation')
        return dom ? [Number((dom.localMs - entry.localMs).toFixed(2))] : []
      })
      t.diagnostic(JSON.stringify({ route: source, nodeStageCount: driver.stages.length,
        browserStageCount: stages.length, stateRequestToDomMs: delays }))
      await page.evaluate(() => window.phase1Session.close())
    } finally { await driver.close(); await page.close() }
  })
}

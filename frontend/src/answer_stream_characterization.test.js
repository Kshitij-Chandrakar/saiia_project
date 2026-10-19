import test from 'node:test'
import assert from 'node:assert/strict'
import { createGrpcAutoSession } from './grpc_auto_session.js'
import { answerStreamDriver } from '../tests/fixtures/answer_stream_driver.mjs'

for (const source of ['microphone', 'system', 'both']) {
  test(`Phase 1 ${source}: real Electron/Auto consumers publish progressive primary and replace final`, async () => {
    const driver = answerStreamDriver(source), answers = []
    const session = await createGrpcAutoSession({ source, stream: { getTracks: () => [], getAudioTracks: () => [] },
      api: { connectGrpcAutoPipeline: () => driver.connect(),
        getGrpcRealtimeStatus: async () => driver.client.getStatus(),
        onGrpcAutoEvent: fn => driver.subscribe(fn),
        closeGrpcRealtime: () => Promise.resolve(driver.close()) },
      createMic: () => ({ start: async () => {}, close() {} }),
      onAnswer: entry => { driver.mark('renderer_consumption'); answers.push(entry) },
    })
    try {
      assert.ok(session)
      driver.emit('question_detected', { text: 'Synthetic question', category: 'technical' })
      driver.emit('answer_started', {})
      driver.emit('answer_delta', { text: 'Prefix A' })
      assert.equal(answers.at(-1).answer, 'Prefix A')
      assert.equal(answers.at(-1).status, 'generating')
      driver.emit('answer_delta', { text: ' plus B' })
      assert.equal(answers.at(-1).answer, 'Prefix A plus B')
      assert.equal(driver.client.getStatus().answerCompletedCount, 0)
      // Known limitation: no reset/fallback events exist on the current wire.
      assert.equal(driver.snapshots.at(-1).currentAnswer, 'Prefix A plus B')
      driver.emit('answer_completed', { text: 'Canonical replacement.' })
      assert.equal(answers.at(-1).answer, 'Canonical replacement.')
      assert.equal(answers.filter(x => x.status === 'complete').length, 1)
      driver.emit('answer_completed', { text: 'duplicate ignored' })
      assert.equal(answers.filter(x => x.status === 'complete').length, 1)
      assert.deepEqual(driver.stages.slice(0, 3).map(x => x.stage),
        ['client_receipt', 'electron_publication', 'renderer_consumption'])
    } finally { await session?.close(); await driver.close() }
  })

  test(`Phase 1 ${source}: terminal error clears partial and closed consumers ignore late text`, async () => {
    const driver = answerStreamDriver(source), answers = []
    const session = await createGrpcAutoSession({ source, stream: { getTracks: () => [], getAudioTracks: () => [] },
      api: { connectGrpcAutoPipeline: () => driver.connect(),
        getGrpcRealtimeStatus: async () => driver.client.getStatus(),
        onGrpcAutoEvent: fn => driver.subscribe(fn), closeGrpcRealtime: async () => driver.close() },
      createMic: () => ({ start: async () => {}, close() {} }), onAnswer: x => answers.push(x) })
    try {
      driver.emit('question_detected', { text: 'Synthetic question' })
      driver.emit('answer_delta', { text: 'Failed partial' })
      driver.emit('answer_error', { code: 'generation_failed' })
      assert.equal(answers.at(-1).answer, '')
      assert.equal(answers.at(-1).status, 'error')
      assert.equal(answers.at(-1).requestId, 'synthetic-turn')
      await session.close()
      const count = answers.length
      driver.emit('answer_delta', { text: 'late' })
      assert.equal(answers.length, count)
    } finally { await session?.close(); await driver.close() }
  })
}

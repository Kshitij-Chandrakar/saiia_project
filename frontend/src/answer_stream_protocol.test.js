import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import test from 'node:test'

const require = createRequire(import.meta.url)
const { readNdjsonStream } = require('../electron/answer_stream_protocol.cjs')

function streamFromByteChunks(chunks) {
  return new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(chunk))
      controller.close()
    },
  })
}

test('desktop stream parser handles split UTF-8 and multiple events', async () => {
  const encoded = new TextEncoder().encode(
    '{"type":"start","request_id":"r1"}\n{"type":"delta","request_id":"r1","text":"caf\u00e9"}\n{"type":"done","request_id":"r1"}\n'
  )
  const split = encoded.indexOf(0xc3) + 1
  assert.equal(encoded[split], 0xa9)
  const events = []
  const result = await readNdjsonStream(
    { body: streamFromByteChunks([encoded.slice(0, split), encoded.slice(split)]) },
    { onEvent: (event) => events.push(event) }
  )

  assert.equal(result.sawDone, true)
  assert.equal(events[1].text, 'café')
  assert.equal(events.at(-1).type, 'done')
})

test('desktop stream parser reports an incomplete transport without a terminal event', async () => {
  const events = []
  const result = await readNdjsonStream(
    {
      body: streamFromByteChunks([
        new TextEncoder().encode('{"type":"delta","request_id":"r1","text":"partial"}\n'),
      ]),
    },
    { onEvent: (event) => events.push(event) }
  )

  assert.equal(result.sawDone, false)
  assert.equal(events[0].text, 'partial')
})

test('actual main-process filter preserves attempt fencing and typed retry failures without raw errors', async () => {
  const { default: vm } = await import('node:vm')
  const { readFileSync } = await import('node:fs')
  const source = readFileSync(new URL('../electron/main.cjs', import.meta.url), 'utf8')
  const start = source.indexOf('function safeStreamString(')
  const code = source.slice(start, source.indexOf('function sendAnswerStreamEvent(', start))
  const safe = vm.runInNewContext(`${code}; safeAnswerStreamEvent`)
  assert.equal(safe({ type: 'replace', request_id: 'turn', answer: '', attempt: 1 }).attempt, 1)
  assert.equal(safe({ type: 'delta', request_id: 'turn', text: 'late', attempt: 0 }).attempt, 0)
  const failure = safe({ type: 'error', request_id: 'turn', error: 'generation_failed', retry_attempt: 2, message: 'SECRET' })
  assert.equal(failure.error, 'generation_failed')
  assert.equal(failure.retry_attempt, 2)
  assert.equal(failure.message, 'Unable to generate an answer')
  assert.equal(safe({ type: 'error', request_id: 'turn', error: 'persistence_unavailable' }).error, 'persistence_unavailable')
})

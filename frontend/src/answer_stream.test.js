import test from 'node:test'
import assert from 'node:assert/strict'

import { createNdjsonEventParser, readNdjsonStream, stripInternalControlMarkers } from './answer_stream.js'

function streamFromChunks(chunks) {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(new TextEncoder().encode(chunk))
      }
      controller.close()
    },
  })
}

test('parses split NDJSON events without losing delta text', () => {
  const events = []
  const parser = createNdjsonEventParser((event) => events.push(event))

  parser.push('{"type":"delta","text":"System ')
  parser.push('design"}\n{"type":"done"}\n')
  parser.flush()

  assert.deepEqual(events, [
    { type: 'delta', text: 'System design' },
    { type: 'done' },
  ])
})

test('parses multiple events in one chunk preserving spaces and newlines', () => {
  const events = []
  const parser = createNdjsonEventParser((event) => events.push(event))

  parser.push('{"type":"delta","text":"- First item\\n"}\n{"type":"delta","text":"\\nReal-life example:\\n"}\n')
  parser.flush()

  assert.equal(events.map((event) => event.text || '').join(''), '- First item\n\nReal-life example:\n')
})

test('readNdjsonStream emits deltas before done without artificial timers', async () => {
  const events = []
  const response = {
    body: streamFromChunks([
      '{"type":"start","request_id":"r1"}\n',
      '{"type":"delta","request_id":"r1","text":"What "}\n',
      '{"type":"delta","request_id":"r1","text":"is streaming?"}\n',
      '{"type":"done","request_id":"r1"}\n',
    ]),
  }

  await readNdjsonStream(response, {
    onEvent: (event) => events.push(event),
  })

  assert.equal(events[1].type, 'delta')
  assert.equal(events.at(-1).type, 'done')
  assert.equal(events.filter((event) => event.type === 'delta').map((event) => event.text).join(''), 'What is streaming?')
})

test('readNdjsonStream cancels cleanly when aborted', async () => {
  const controller = new AbortController()
  const events = []
  const response = {
    body: new ReadableStream({
      start(streamController) {
        streamController.enqueue(new TextEncoder().encode('{"type":"delta","text":"Hello"}\n'))
      },
    }),
  }

  controller.abort()
  await readNdjsonStream(response, {
    signal: controller.signal,
    onEvent: (event) => events.push(event),
  })

  assert.deepEqual(events, [])
})

test('metadata events remain separate from answer deltas', async () => {
  const events = []
  const response = {
    body: streamFromChunks([
      '{"type":"metadata","metadata":{"generate_category":"technical"}}\n',
      '{"type":"delta","text":"AI is software."}\n',
      '{"type":"done"}\n',
    ]),
  }

  await readNdjsonStream(response, {
    onEvent: (event) => events.push(event),
  })

  const visibleAnswer = events
    .filter((event) => event.type === 'delta')
    .map((event) => stripInternalControlMarkers(event.text))
    .join('')

  assert.equal(visibleAnswer, 'AI is software.')
  assert.equal(events[0].metadata.generate_category, 'technical')
})

test('frontend fallback strips only complete known internal markers', () => {
  assert.equal(stripInternalControlMarkers('[[category:technical]]AI is software.'), 'AI is software.')
  assert.equal(stripInternalControlMarkers('Example: [[1, 2], [3, 4]]'), 'Example: [[1, 2], [3, 4]]')
  assert.equal(stripInternalControlMarkers('[[unknown:value]] is text'), '[[unknown:value]] is text')
})

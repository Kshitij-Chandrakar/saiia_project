export const MAX_NDJSON_LINE_CHARS = 1024 * 1024

// Opt-in local Performance marks: IDs/stage names only, never answer content.
export function markChatTiming(requestId, stage) {
  if (import.meta.env?.VITE_MANUAL_CHAT_LATENCY_AUDIT !== 'true' || !requestId) return
  const name = `intervu-chat:${requestId}:${stage}`
  if (performance.getEntriesByName(name).length) return
  performance.mark(name)
  const marks = performance.getEntriesByType('mark').filter((entry) => entry.name.startsWith('intervu-chat:'))
  for (const entry of marks.slice(0, Math.max(0, marks.length - 500))) performance.clearMarks(entry.name)
}

export function createNdjsonEventParser(onEvent) {
  let buffer = ''

  const push = (chunk) => {
    buffer += chunk
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (line.length > MAX_NDJSON_LINE_CHARS) {
        throw new Error('Answer stream event is too large.')
      }
      const trimmed = line.trim()
      if (!trimmed) {
        continue
      }
      onEvent(JSON.parse(trimmed))
    }
    if (buffer.length > MAX_NDJSON_LINE_CHARS) {
      throw new Error('Answer stream event is too large.')
    }
  }

  const flush = () => {
    const trimmed = buffer.trim()
    buffer = ''
    if (trimmed) {
      onEvent(JSON.parse(trimmed))
    }
  }

  return { push, flush }
}

export function stripInternalControlMarkers(text) {
  return String(text || '')
    .replace(/\[\[\s*(category|type|mode|intent|answer_type)\s*:\s*[A-Za-z0-9_. -]{0,80}\s*\]\]/gi, '')
}

export async function readNdjsonStream(response, { onEvent, signal } = {}) {
  if (!response.body?.getReader) {
    throw new Error('Streaming responses are not supported in this renderer.')
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let sawDone = false
  const handleEvent = typeof onEvent === 'function' ? onEvent : () => {}
  const parser = createNdjsonEventParser((event) => {
    if (event?.type === 'done') {
      sawDone = true
    }
    handleEvent(event)
  })

  while (true) {
    if (signal?.aborted) {
      try {
        await reader.cancel()
      } catch {
        // Ignore cancellation cleanup failures.
      }
      return { sawDone: false, aborted: true }
    }
    const { value, done } = await reader.read()
    if (done) {
      break
    }
    parser.push(decoder.decode(value, { stream: true }))
  }
  parser.push(decoder.decode())
  parser.flush()
  return { sawDone, aborted: false }
}

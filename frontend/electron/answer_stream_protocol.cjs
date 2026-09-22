const MAX_NDJSON_LINE_CHARS = 1024 * 1024

async function readNdjsonStream(response, { onEvent, signal } = {}) {
  if (!response?.body?.getReader) {
    throw new Error('Streaming responses are not supported in this runtime.')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  const handleEvent = typeof onEvent === 'function' ? onEvent : () => {}
  let buffer = ''
  let sawDone = false
  const cancel = () => { void reader.cancel().catch(() => {}) }
  signal?.addEventListener('abort', cancel, { once: true })

  const consumeLine = (line) => {
    if (sawDone || signal?.aborted) return
    if (line.length > MAX_NDJSON_LINE_CHARS) {
      throw new Error('Answer stream event is too large.')
    }
    const trimmed = line.trim()
    if (!trimmed) {
      return
    }
    const event = JSON.parse(trimmed)
    if (!event || typeof event !== 'object' || Array.isArray(event)) {
      throw new Error('Invalid answer stream event.')
    }
    if (event.type === 'done') {
      sawDone = true
    }
    handleEvent(event)
  }

  try {
    while (true) {
      if (signal?.aborted) {
        return { sawDone: false, aborted: true }
      }
      const { value, done } = await reader.read()
      if (done) {
        break
      }
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      if (buffer.length > MAX_NDJSON_LINE_CHARS) {
        throw new Error('Answer stream event is too large.')
      }
      for (const line of lines) {
        consumeLine(line)
      }
      if (sawDone) break
    }
    buffer += decoder.decode()
    consumeLine(buffer)
    return { sawDone, aborted: false }
  } finally {
    signal?.removeEventListener('abort', cancel)
    try { await reader.cancel() } catch { /* Closed transport. */ }
    reader.releaseLock()
  }
}

module.exports = {
  MAX_NDJSON_LINE_CHARS,
  readNdjsonStream,
}

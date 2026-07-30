export function createNdjsonEventParser(onEvent) {
  let buffer = ''

  const push = (chunk) => {
    buffer += chunk
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed) {
        continue
      }
      onEvent(JSON.parse(trimmed))
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
  const parser = createNdjsonEventParser(onEvent || (() => {}))

  while (true) {
    if (signal?.aborted) {
      try {
        await reader.cancel()
      } catch {
        // Ignore cancellation cleanup failures.
      }
      return
    }
    const { value, done } = await reader.read()
    if (done) {
      break
    }
    parser.push(decoder.decode(value, { stream: true }))
  }
  parser.push(decoder.decode())
  parser.flush()
}

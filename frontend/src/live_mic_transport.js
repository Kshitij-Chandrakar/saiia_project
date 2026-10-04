// Shared microphone PCM capture. Callers own transport and generation.
export function createPcmMicCapture({ stream, isActive, downsample = downsampleToInt16Mono, onChunk, AudioContextClass = window.AudioContext }) {
  let audioContext, sourceNode, processor, closed = false
  const close = () => {
    if (closed) return
    closed = true
    if (processor) { processor.onaudioprocess = null; processor.disconnect() }
    sourceNode?.disconnect()
    audioContext?.close().catch(() => {})
  }
  try {
    audioContext = new AudioContextClass()
    sourceNode = audioContext.createMediaStreamSource(stream)
    processor = audioContext.createScriptProcessor(4096, 1, 1)
    processor.onaudioprocess = (event) => {
      if (closed || !isActive()) return
      const pcm16 = downsample(event.inputBuffer.getChannelData(0), audioContext.sampleRate, 16000)
      if (pcm16.length) onChunk(pcm16.buffer)
    }
    sourceNode.connect(processor)
    processor.connect(audioContext.destination)
  } catch (error) { close(); throw error }
  return { audioContext, sourceNode, processor, close }
}

export function createLiveMicTransport({ stream, url, isActive, downsample, WebSocketClass = WebSocket, AudioContextClass = window.AudioContext }) {
  const socket = new WebSocketClass(url)
  socket.binaryType = 'arraybuffer'
  let sending = true, closed = false, capture
  const pauseAudio = () => { sending = false }
  const close = (terminate = true) => {
    if (closed) return
    closed = true
    pauseAudio()
    capture?.close()
    try {
      if (terminate && socket.readyState === WebSocketClass.OPEN) socket.send(JSON.stringify({ type: 'terminate' }))
      socket.close()
    } catch { /* Already disconnected. */ }
  }
  try {
    capture = createPcmMicCapture({ stream, downsample, AudioContextClass,
      isActive: () => sending && isActive() && socket.readyState === WebSocketClass.OPEN,
      onChunk: (buffer) => socket.send(buffer),
    })
  } catch (error) { close(false); throw error }
  return { ...capture, socket, pauseAudio, close }
}

export function downsampleToInt16Mono(float32Array, inputSampleRate, outputSampleRate = 16000) {
  if (!float32Array?.length) {
    return new Int16Array(0)
  }

  if (inputSampleRate === outputSampleRate) {
    const direct = new Int16Array(float32Array.length)
    for (let index = 0; index < float32Array.length; index += 1) {
      const sample = Math.max(-1, Math.min(1, float32Array[index]))
      direct[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff
    }
    return direct
  }

  const ratio = inputSampleRate / outputSampleRate
  const nextLength = Math.max(1, Math.round(float32Array.length / ratio))
  const result = new Int16Array(nextLength)
  let offsetResult = 0
  let offsetBuffer = 0

  while (offsetResult < result.length) {
    const nextOffsetBuffer = Math.min(
      float32Array.length,
      Math.round((offsetResult + 1) * ratio)
    )
    let accumulator = 0
    let count = 0
    for (let sampleIndex = offsetBuffer; sampleIndex < nextOffsetBuffer; sampleIndex += 1) {
      accumulator += float32Array[sampleIndex]
      count += 1
    }
    const sample = count ? accumulator / count : 0
    const normalized = Math.max(-1, Math.min(1, sample))
    result[offsetResult] = normalized < 0 ? normalized * 0x8000 : normalized * 0x7fff
    offsetResult += 1
    offsetBuffer = nextOffsetBuffer
  }

  return result
}

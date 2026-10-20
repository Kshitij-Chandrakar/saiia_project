// Shared microphone PCM capture. Callers own transport and generation.
export function createPcmMicCapture({ stream, isActive, downsample = downsampleToInt16Mono, onChunk, AudioContextClass = window.AudioContext, contextSampleRate, continuous = false, monotonicNow = () => performance.now() }) {
  let audioContext, sourceNode, processor, closed = false
  const close = () => {
    if (closed) return
    closed = true
    if (processor) { processor.onaudioprocess = null; processor.disconnect() }
    sourceNode?.disconnect()
    audioContext?.close().catch(() => {})
  }
  try {
    audioContext = new AudioContextClass(contextSampleRate ? { sampleRate: contextSampleRate } : undefined)
    if (continuous) downsample = createContinuousDownsampler()
    const outputSampleRate = 16000
    let timelineStart, clockAnchor, outputSamples = 0, skipped = false, discontinuity = false
    sourceNode = audioContext.createMediaStreamSource(stream)
    processor = audioContext.createScriptProcessor(4096, 1, 1)
    processor.onaudioprocess = (event) => {
      if (closed) return
      if (!isActive()) { skipped = true; return }
      const input = event.inputBuffer.getChannelData(0)
      const now = continuous ? monotonicNow() : 0
      const contextTime = continuous ? audioContext.currentTime : 0
      // Match PcmMixer's 300 ms elapsed-clock tolerance. Callback scheduling
      // delays advance both clocks; a suspended context advances only one.
      const clockGap = continuous && clockAnchor &&
        now - clockAnchor.mono - (contextTime - clockAnchor.context) * 1000 > 300
      if (continuous && (timelineStart === undefined || skipped || clockGap)) {
        // A nominal Web Audio block clock, not a hardware ADC timestamp.
        // playbackTime describes output scheduling; cap at current context time
        // and retain the unknown input/driver latency as an explicit limitation.
        const contextEnd = Number.isFinite(event.playbackTime) ? Math.min(event.playbackTime, audioContext.currentTime) : audioContext.currentTime
        timelineStart = now + (contextEnd - audioContext.currentTime - input.length / audioContext.sampleRate) * 1000
        outputSamples = 0
        clockAnchor = { mono: now, context: contextTime }
        if (skipped || clockGap) { downsample = createContinuousDownsampler(); discontinuity = true }
      }
      const pcm16 = downsample(input, audioContext.sampleRate, outputSampleRate)
      if (pcm16.length) onChunk(pcm16.buffer, continuous ? {
        sampleRate: outputSampleRate, startMonotonicMs: timelineStart + outputSamples / outputSampleRate * 1000,
        discontinuity,
      } : undefined)
      if (pcm16.length) discontinuity = false
      outputSamples += pcm16.length
      skipped = false
    }
    sourceNode.connect(processor)
    processor.connect(audioContext.destination)
  } catch (error) { close(); throw error }
  return { audioContext, sourceNode, processor, close }
}

// Browser AudioContext performs native rate conversion when 16 kHz is honored.
// Carry fractional sample areas when a device/context supplies another rate.
export function createContinuousDownsampler() {
  let area = 0, filled = 0
  return (samples, inputRate, outputRate = 16000) => {
    if (inputRate < outputRate) throw Error('Unsupported microphone sample rate')
    const width = inputRate / outputRate, output = []
    for (const sample of samples) {
      let remaining = 1
      while (remaining > 1e-9) {
        const used = Math.min(remaining, width - filled)
        area += sample * used; filled += used; remaining -= used
        if (filled >= width - 1e-9) {
          const value = Math.max(-1, Math.min(1, area / width))
          output.push(value < 0 ? value * 32768 : value * 32767)
          area = filled = 0
        }
      }
    }
    return Int16Array.from(output)
  }
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

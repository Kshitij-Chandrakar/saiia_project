import { createPcmMicCapture } from './live_mic_transport.js'

// Shared experimental PCM capture for diagnostics and opt-in G6 manual sessions.
export function createGrpcMicTest({ api, getUserMedia = (constraints) => navigator.mediaDevices.getUserMedia(constraints), createCapture = createPcmMicCapture, ownsStream = true, continuous = false,
  monotonicNow = () => performance.now(), wallNow = () => Date.now() }) {
  let capture, stream, running = false, pending = false, generation = 0, queued = 0, sending = Promise.resolve()
  const pacing = new Map()
  const stopCapture = () => {
    generation++
    for (const [timer, resolve] of pacing) { clearTimeout(timer); resolve() }
    pacing.clear()
    queued = 0; pending = false; sending = Promise.resolve()
    tail = new Uint8Array(0)
    running = false
    capture?.close()
    capture = null
    if (ownsStream) stream?.getTracks().forEach((track) => track.stop())
    stream = null
  }
  let tail = new Uint8Array(0), enqueue, tailStart, nextChunkStart
  const start = async () => {
    const run = ++generation
    try {
      const status = await api.getGrpcRealtimeStatus()
      if (run !== generation) return
      if (!status.audioEnabled || status.connectionStatus !== 'connected') throw Error('unavailable')
      if (ownsStream && (status.manualPipelineReady || status.autoPipelineReady)) throw Error('manual capture active')
      const microphone = await getUserMedia(status.sttEnabled ? { audio: { channelCount: 1, sampleRate: 16000 } } : { audio: true })
      if (run !== generation) { if (ownsStream) microphone.getTracks().forEach((track) => track.stop()); return }
      stream = microphone
      running = true
      const metadata = () => ({ inputSampleRate: capture?.audioContext?.sampleRate || 0,
        inputChannelCount: stream?.getAudioTracks?.()[0]?.getSettings?.().channelCount || 1 })
      let nextSlot = 0
      tailStart = nextChunkStart = undefined
      // One fixed conversion for this run. Later wall-clock changes cannot
      // rewrite elapsed audio time, and monotonic values never cross IPC.
      const epochOffset = wallNow() - monotonicNow()
      enqueue = (data, frameStart = monotonicNow()) => {
        const queuedAt = monotonicNow()
        pending = true
        queued++
        sending = sending.then(async () => {
          if (run !== generation) return null
          // Combined audio must not replay a renderer backlog after an IPC stall.
          // 500 ms includes a 256 ms capture block plus a retained 100 ms tail.
          if (continuous && (monotonicNow() - queuedAt > 300 || monotonicNow() - frameStart > 500)) return { connectionStatus: 'connected' }
          const result = await api.sendGrpcRealtimeAudioChunk(data, { ...metadata(), ...(continuous ? { captureTimestampMs: Math.round(epochOffset + frameStart) } : {}) })
          if (run !== generation) return null
          // Keep G4 frames near realtime, including when one capture callback produces several frames.
          if (status.sttEnabled) {
            const now = continuous ? monotonicNow() : Date.now()
            nextSlot = Math.max((nextSlot || now) + 100, now - 1000)
            const wait = nextSlot - now
            if (wait > 0) await new Promise(resolve => {
              const timer = setTimeout(() => { pacing.delete(timer); resolve() }, wait)
              pacing.set(timer, resolve)
            })
          }
          return result
        }).then((result) => {
          if (run === generation && result?.connectionStatus !== 'connected') stopCapture()
        }).catch(() => { if (run === generation) stopCapture() }).finally(() => { if (run === generation) { queued--; pending = queued > 0 } })
      }
      capture = createCapture({ stream, contextSampleRate: status.sttEnabled ? 16000 : undefined,
        continuous, monotonicNow,
        isActive: () => running && (status.sttEnabled ? queued <= 8 : !pending),
        onChunk: (data, timing) => {
          if (run !== generation || !running) return
          if (!status.sttEnabled) { enqueue(data); return }
          if (data.byteLength % 2) { stopCapture(); return }
          const outputRate = timing?.sampleRate || 16000
          if (outputRate !== 16000) { stopCapture(); return }
          const chunkStart = Number.isFinite(timing?.startMonotonicMs) ? timing.startMonotonicMs :
            nextChunkStart ?? monotonicNow() - data.byteLength / 2 / outputRate * 1000
          if (continuous && timing?.discontinuity) { tail = new Uint8Array(0); tailStart = undefined }
          const mergedStart = tail.length ? tailStart : chunkStart
          // Explicit signed PCM16 little-endian; no Float32 buffer crosses IPC.
          const samples = new Int16Array(data)
          const bytes = new Uint8Array(data.byteLength)
          const view = new DataView(bytes.buffer)
          for (let i = 0; i < samples.length; i++) view.setInt16(i * 2, samples[i], true)
          const merged = new Uint8Array(tail.length + bytes.length)
          merged.set(tail); merged.set(bytes, tail.length)
          let offset = 0
          for (; offset + 3200 <= merged.length; offset += 3200) enqueue(merged.slice(offset, offset + 3200).buffer, mergedStart + offset / 2 / outputRate * 1000)
          tail = merged.slice(offset)
          tailStart = mergedStart + offset / 2 / outputRate * 1000
          nextChunkStart = chunkStart + data.byteLength / 2 / outputRate * 1000
        },
      })
      if (status.sttEnabled && capture.audioContext?.state === 'suspended') await capture.audioContext.resume()

    } catch { if (run === generation) stopCapture(); throw Error('Experimental gRPC microphone test unavailable. Check flags, connection, and microphone permission.') }
  }
  const stop = async () => {
    running = false
    // Preserve the last words: zero-pad only the final sub-100 ms frame.
    if (tail.length && enqueue) {
      const finalFrame = new Uint8Array(3200)
      finalFrame.set(tail); tail = new Uint8Array(0)
      enqueue(finalFrame.buffer, tailStart)
    }
    // Drain already captured frames before finalizing the provider.
    await sending
    stopCapture()
    return api.stopGrpcRealtimeAudio()
  }
  return { start, stop, close: stopCapture }
}

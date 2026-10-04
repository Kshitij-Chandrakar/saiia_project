import { createPcmMicCapture } from './live_mic_transport.js'

// Explicit diagnostic-only capture; never called by normal manual/auto recording.
export function createGrpcMicTest({ api, getUserMedia = (constraints) => navigator.mediaDevices.getUserMedia(constraints), createCapture = createPcmMicCapture }) {
  let capture, stream, running = false, pending = false, generation = 0, queued = 0, sending = Promise.resolve()
  const stopCapture = () => {
    generation++
    tail = new Uint8Array(0)
    running = false
    capture?.close()
    capture = null
    stream?.getTracks().forEach((track) => track.stop())
    stream = null
  }
  let tail = new Uint8Array(0), enqueue
  const start = async () => {
    const run = ++generation
    try {
      const status = await api.getGrpcRealtimeStatus()
      if (run !== generation) return
      if (!status.audioEnabled || status.connectionStatus !== 'connected') throw Error('unavailable')
      const microphone = await getUserMedia(status.sttEnabled ? { audio: { channelCount: 1, sampleRate: 16000 } } : { audio: true })
      if (run !== generation) { microphone.getTracks().forEach((track) => track.stop()); return }
      stream = microphone
      running = true
      const metadata = () => ({ inputSampleRate: capture?.audioContext?.sampleRate || 0,
        inputChannelCount: stream?.getAudioTracks?.()[0]?.getSettings?.().channelCount || 1 })
      enqueue = (data) => {
        pending = true
        queued++
        sending = sending.then(async () => {
          if (run !== generation) return null
          const started = Date.now()
          const result = await api.sendGrpcRealtimeAudioChunk(data, metadata())
          // Keep G4 frames near realtime, including when one capture callback produces several frames.
          if (status.sttEnabled) await new Promise(resolve => setTimeout(resolve, Math.max(0, 100 - (Date.now() - started))))
          return result
        }).then((result) => {
          if (run === generation && result?.connectionStatus !== 'connected') stopCapture()
        }).catch(() => { if (run === generation) stopCapture() }).finally(() => { queued--; pending = queued > 0 })
      }
      capture = createCapture({ stream, contextSampleRate: status.sttEnabled ? 16000 : undefined,
        isActive: () => running && (status.sttEnabled ? queued <= 8 : !pending),
        onChunk: (data) => {
          if (!status.sttEnabled) { enqueue(data); return }
          if (data.byteLength % 2) { stopCapture(); return }
          // Explicit signed PCM16 little-endian; no Float32 buffer crosses IPC.
          const samples = new Int16Array(data)
          const bytes = new Uint8Array(data.byteLength)
          const view = new DataView(bytes.buffer)
          for (let i = 0; i < samples.length; i++) view.setInt16(i * 2, samples[i], true)
          const merged = new Uint8Array(tail.length + bytes.length)
          merged.set(tail); merged.set(bytes, tail.length)
          let offset = 0
          for (; offset + 3200 <= merged.length; offset += 3200) enqueue(merged.slice(offset, offset + 3200).buffer)
          tail = merged.slice(offset)
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
      enqueue(finalFrame.buffer)
    }
    // Drain already captured frames before finalizing the provider.
    await sending
    stopCapture()
    return api.stopGrpcRealtimeAudio()
  }
  return { start, stop, close: stopCapture }
}

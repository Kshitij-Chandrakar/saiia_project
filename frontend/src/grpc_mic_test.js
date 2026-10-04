import { createPcmMicCapture } from './live_mic_transport.js'

// Explicit diagnostic-only capture; never called by normal manual/auto recording.
export function createGrpcMicTest({ api, getUserMedia = () => navigator.mediaDevices.getUserMedia({ audio: true }), createCapture = createPcmMicCapture }) {
  let capture, stream, running = false, pending = false, generation = 0
  const stopCapture = () => {
    generation++
    running = false
    capture?.close()
    capture = null
    stream?.getTracks().forEach((track) => track.stop())
    stream = null
  }
  const start = async () => {
    const run = ++generation
    try {
      const status = await api.getGrpcRealtimeStatus()
      if (run !== generation) return
      if (!status.audioEnabled || status.connectionStatus !== 'connected') throw Error('unavailable')
      const microphone = await getUserMedia()
      if (run !== generation) { microphone.getTracks().forEach((track) => track.stop()); return }
      stream = microphone
      running = true
      capture = createCapture({ stream, isActive: () => running && !pending,
        onChunk: (data) => {
          pending = true
          Promise.resolve().then(() => api.sendGrpcRealtimeAudioChunk(data)).then((result) => {
            if (run === generation && result.connectionStatus !== 'connected') stopCapture()
          }).catch(() => { if (run === generation) stopCapture() }).finally(() => { pending = false })
        },
      })
    } catch { if (run === generation) stopCapture(); throw Error('Experimental gRPC microphone test unavailable. Check flags, connection, and microphone permission.') }
  }
  const stop = async () => { stopCapture(); return api.stopGrpcRealtimeAudio() }
  return { start, stop, close: stopCapture }
}

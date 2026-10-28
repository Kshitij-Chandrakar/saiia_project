// Acquire only after the main-process relay reports server-authorized ready.
// Existing PCM capture sends the single resulting stream; Both has one lease.
export async function createHostedAudioCapture({ source, signal, mediaDevices = navigator.mediaDevices,
  AudioContextClass = window.AudioContext }) {
  const streams = [], nodes = [], listeners = []
  let context, output, closed = false, ending = false
  const close = () => {
    if (closed) return
    closed = true
    signal?.removeEventListener('abort', close)
    for (const [track, listener] of listeners) track.removeEventListener('ended', listener)
    output?.getTracks().forEach(track => track.stop())
    streams.forEach(stream => stream.getTracks().forEach(track => track.stop()))
    nodes.forEach(node => node.disconnect())
    void context?.close().catch(() => {})
  }
  signal?.addEventListener('abort', close, { once: true })
  const acquire = async action => {
    const value = await action()
    if (closed || signal?.aborted) { value.getTracks().forEach(track => track.stop()); throw Error('Authorization ended') }
    streams.push(value)
    return value
  }
  try {
    if (signal?.aborted) throw Error('Authorization ended')
    if (source !== 'system') await acquire(() => mediaDevices.getUserMedia({ audio: true }))
    if (source !== 'microphone') {
      const desktop = await acquire(() => mediaDevices.getDisplayMedia({ video: { width: 16, height: 16, frameRate: 1 }, audio: true }))
      if (!desktop.getAudioTracks().length) throw Error('System audio unavailable')
    }
    if (closed || streams.some(stream => !stream.getAudioTracks().length)) throw Error('Audio source unavailable')
    if (source === 'both') {
      context = new AudioContextClass({ sampleRate: 16000 })
      const destination = context.createMediaStreamDestination()
      for (const stream of streams) {
        const node = context.createMediaStreamSource(stream), gain = context.createGain()
        gain.gain.value = 0.5 // Bounded PCM amplitude; no duplicate source/lease billing.
        node.connect(gain); gain.connect(destination); nodes.push(node, gain)
      }
      output = destination.stream
      await context.resume()
    } else output = streams[0]
    for (const stream of streams) for (const track of stream.getTracks()) {
      const listener = () => {
        if (closed || ending) return
        ending = true
        // A virtual mixer track does not end when a physical input disappears.
        // Signal the existing Auto lifecycle before releasing all owned tracks.
        output.getAudioTracks().forEach(item => item.dispatchEvent(new Event('ended')))
        close()
      }
      track.addEventListener('ended', listener); listeners.push([track, listener])
      if (track.readyState === 'ended') throw Error('Audio source unavailable')
    }
    return { stream: output, close, status: () => streams.flatMap(value => value.getAudioTracks().map(track => ({ label: track.label, state: track.readyState, muted: track.muted }))) }
  } catch { close(); throw Error('Required audio source unavailable') }
}

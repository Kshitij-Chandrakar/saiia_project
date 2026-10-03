// Audio/STT only. Callers own transcript handling and answer generation.
export function createLiveMicTransport({ stream, url, isActive, downsample, WebSocketClass = WebSocket, AudioContextClass = window.AudioContext }) {
  const socket = new WebSocketClass(url)
  socket.binaryType = 'arraybuffer'
  let audioContext, sourceNode, processor
  let sending = true
  let closed = false
  const pauseAudio = () => { sending = false }
  const close = (terminate = true) => {
    if (closed) return
    closed = true
    pauseAudio()
    if (processor) {
      processor.onaudioprocess = null
      processor.disconnect()
    }
    sourceNode?.disconnect()
    audioContext?.close().catch(() => {})
    try {
      if (terminate && socket.readyState === WebSocketClass.OPEN) socket.send(JSON.stringify({ type: 'terminate' }))
      socket.close()
    } catch { /* Already disconnected. */ }
  }
  try {
    audioContext = new AudioContextClass()
    sourceNode = audioContext.createMediaStreamSource(stream)
    processor = audioContext.createScriptProcessor(4096, 1, 1)
    processor.onaudioprocess = (event) => {
      if (!sending || !isActive() || socket.readyState !== WebSocketClass.OPEN) return
      const pcm16 = downsample(event.inputBuffer.getChannelData(0), audioContext.sampleRate, 16000)
      if (pcm16.length) socket.send(pcm16.buffer)
    }
    sourceNode.connect(processor)
    processor.connect(audioContext.destination)
  } catch (error) {
    close(false)
    throw error
  }
  return { socket, audioContext, sourceNode, processor, pauseAudio, close }
}

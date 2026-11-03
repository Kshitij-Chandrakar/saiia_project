// Main-process transport adapter. No bearer, URL override or owner capability crosses IPC.
const { EventEmitter } = require('node:events')
const WebSocket = require('ws')

async function boundedBody(response) {
  const reader = response.body.getReader(), chunks = []
  let size = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      size += value.length
      if (size > 4096) throw Error('hosted_unavailable')
      chunks.push(value)
    }
    return Buffer.concat(chunks).toString('utf8')
  } finally { await reader.cancel().catch(() => {}) }
}

function destination(base, deployment, allowLoopback) {
  const url = new URL(base)
  const local = ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)
  if (process.env.NODE_TLS_REJECT_UNAUTHORIZED === '0' || !deployment || url.username || url.password || url.search || url.hash || url.pathname !== '/' ||
      (url.protocol !== 'https:' && !(allowLoopback && local && url.protocol === 'http:'))) throw Error('hosted_unavailable')
  return url
}

function createHostedAudioTransport({ baseUrl, deployment, allowLoopback = false,
  getAuthorization, fetchImpl = fetch, WebSocketClass = WebSocket }) {
  const base = destination(baseUrl, deployment, allowLoopback)
  let socket, canceled = false, verified = false
  const health = async () => {
    const auth = await getAuthorization()
    if (!auth?.isCurrent?.()) throw Error('auth_unavailable')
    const response = await fetchImpl(new URL('/api/account/audio/capabilities', base), {
      headers: { Authorization: auth.authorization }, redirect: 'error', cache: 'no-store',
      signal: AbortSignal.timeout(5000),
    })
    if (!response.ok || Number(response.headers.get('content-length') || 0) > 4096) throw Error('hosted_unavailable')
    const text = await boundedBody(response)
    if (text.length > 4096 || !auth.isCurrent() || canceled) throw Error('hosted_unavailable')
    const value = JSON.parse(text)
    if (value.protocol_version !== 1 || value.deployment_id !== deployment || !value.auto_available) throw Error('hosted_unavailable')
    verified = true
    return value
  }
  return {
    CheckHealth: (_request, _options, callback) => { void health().then(value => callback(null, value), () => callback(Error('hosted_unavailable'))) },
    waitForReady: (_deadline, callback) => { void health().then(() => callback(), () => callback(Error('hosted_unavailable'))) },
    StreamInterview: metadata => {
      if (!verified || canceled) throw Error('hosted_unavailable')
      const stream = new EventEmitter()
      let start, audio, stop, sequence = 0, authorized = false
      const pings = []
      const emitFailure = () => { authorized = false; stream.emit('error', Error('hosted_unavailable')) }
      const send = value => {
        if (!socket || socket.readyState !== 1 || socket.bufferedAmount > 12800) throw Error('hosted_backpressure')
        socket.send(value)
      }
      stream.write = event => {
        if (canceled) throw Error('hosted_unavailable')
        if (event.start_session) {
          if (socket || !event.start_session.cloud_context_requested) throw Error('hosted_unavailable')
          start = event.request_id
          const endpoint = new URL('/api/account/audio/stream', base)
          endpoint.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:'
          const authorization = metadata?.get('authorization')
          if (!Array.isArray(authorization) || authorization.length !== 1) throw Error('auth_unavailable')
          // Explicit parser/handshake bounds, no compression or redirect credential handoff.
          socket = new WebSocketClass(endpoint, { headers: { Origin: base.origin, Authorization: authorization[0] },
            rejectUnauthorized: true, maxPayload: 4 * 1024 * 1024, perMessageDeflate: false, followRedirects: false, handshakeTimeout: 5000 })
          socket.binaryType = 'arraybuffer'
          socket.addEventListener('open', () => {
            if (canceled) { socket.close(); return }
            try { send(JSON.stringify({ stream_id: event.session_id, session_id: event.start_session.active_session_id,
              source: event.start_session.source,
              ...(event.start_session.selected_resume_id ? { selected_resume_id: event.start_session.selected_resume_id } : {}),
              ...(event.start_session.selected_job_context_id ? { selected_job_context_id: event.start_session.selected_job_context_id } : {}) })) } catch { emitFailure() }
          })
          socket.addEventListener('message', message => {
            try {
              if (canceled) return
              if (typeof message.data !== 'string' || message.data.length > 4 * 1024 * 1024) throw Error('hosted_unavailable')
              const value = JSON.parse(message.data)
              if (value.request_id === 'relay-start') value.request_id = start
              if (value.ready) authorized = true
              if (value.pong) value.request_id = pings.shift()
              if (value.status?.code === 'audio_chunk_received') { value.request_id = audio; audio = null }
              if (['ended', 'system_cleanup_pending'].includes(value.status?.code)) { value.request_id = stop; authorized = false }
              if (value.error) authorized = false
              stream.emit('data', value)
            } catch { emitFailure() }
          })
          socket.addEventListener('error', emitFailure)
          socket.addEventListener('close', () => { authorized = false; if (!canceled) stream.emit('end') })
        } else if (event.audio_chunk) {
          const pcm = event.audio_chunk.audio
          if (!authorized || audio || !Buffer.isBuffer(pcm) || pcm.length < 2 || pcm.length > 6400 || pcm.length % 2) throw Error('hosted_unavailable')
          const frame = Buffer.allocUnsafe(8 + pcm.length)
          frame.writeBigUInt64BE(BigInt(++sequence)); pcm.copy(frame, 8)
          audio = event.request_id
          send(frame)
        } else if (event.ping) {
          if (!authorized || pings.length >= 2) throw Error('hosted_unavailable')
          pings.push(event.request_id); send('ping')
        } else if (event.end_session || event.cancel) {
          authorized = false; stop = event.request_id; send('stop')
        } else throw Error('hosted_unavailable')
      }
      stream.cancel = () => { authorized = false; canceled = true; socket?.close() }
      return stream
    },
    close: () => { canceled = true; socket?.close() },
  }
}

module.exports = { createHostedAudioTransport, destination }

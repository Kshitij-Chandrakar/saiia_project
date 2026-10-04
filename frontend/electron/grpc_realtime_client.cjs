const path = require('path')
const { randomUUID } = require('crypto')

function createTransport(address, protoPath) {
  const grpc = require('@grpc/grpc-js')
  const loader = require('@grpc/proto-loader')
  const definition = loader.loadSync(protoPath, { keepCase: true, longs: String, oneofs: true })
  const Service = grpc.loadPackageDefinition(definition).intervuai.realtime.v1.InterviewRealtimeService
  return new Service(address, grpc.credentials.createInsecure(), {
    'grpc.max_receive_message_length': 4 * 1024 * 1024,
    'grpc.max_send_message_length': 4 * 1024 * 1024,
  })
}

class GrpcRealtimeClient {
  constructor({ env = process.env, transportFactory = createTransport, timeoutMs = 3000,
    protoPath = path.join(__dirname, 'protos', 'interview_realtime.proto') } = {}) {
    this.enabled = String(env.ELECTRON_GRPC_REALTIME_ENABLED || 'false').toLowerCase() === 'true'
    this.host = env.ELECTRON_GRPC_REALTIME_HOST || '127.0.0.1'
    this.port = Number(env.ELECTRON_GRPC_REALTIME_PORT || 50051)
    this.transportFactory = transportFactory
    this.protoPath = protoPath
    this.timeoutMs = timeoutMs
    this.status = this.enabled ? 'disconnected' : 'disabled'
    this.lastPing = 'not sent'
    this.lastError = ''
    this.pending = new Map()
    this.epoch = 0
  }

  getStatus() {
    return { enabled: this.enabled, connectionStatus: this.status, lastPingResult: this.lastPing, lastErrorMessage: this.lastError }
  }

  connect() {
    if (!this.enabled || this.status === 'connected') return Promise.resolve(this.getStatus())
    if (this.connecting) return this.connecting
    const epoch = this.epoch
    this.status = 'connecting'
    const task = (async () => {
      try {
        // G2 deliberately provides no external-host override before TLS/auth exists.
        if (!['127.0.0.1', 'localhost', '::1'].includes(this.host) || !Number.isInteger(this.port) || this.port < 1 || this.port > 65535) {
          throw Error('invalid configuration')
        }
        const address = this.host === '::1' ? `[::1]:${this.port}` : `${this.host}:${this.port}`
        this.client = this.transportFactory(address, this.protoPath)
        await new Promise((resolve, reject) => this.client.waitForReady(Date.now() + this.timeoutMs, (error) => error ? reject(error) : resolve()))
        if (epoch !== this.epoch) return this.getStatus()
        const stream = this.client.StreamInterview()
        this.stream = stream
        stream.on('data', (event) => {
          if (epoch !== this.epoch) return
          const pending = this.pending.get(event.request_id)
          if (pending && event[pending.kind] !== undefined) {
            clearTimeout(pending.timer)
            this.pending.delete(event.request_id)
            pending.resolve()
          } else if (event.error) this.fail()
        })
        stream.on('error', () => { if (epoch === this.epoch) this.fail() })
        stream.on('end', () => { if (epoch === this.epoch) this.close() })
        this.sessionId = randomUUID()
        await this.startSession()
        if (epoch === this.epoch) { this.status = 'connected'; this.lastError = '' }
      } catch {
        if (epoch === this.epoch) this.fail()
      }
      return this.getStatus()
    })()
    this.connecting = task
    task.finally(() => { if (this.connecting === task) this.connecting = null })
    return task
  }

  request(payload, kind) {
    if (!this.stream) return Promise.reject(Error('not connected'))
    const requestId = randomUUID()
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(requestId); reject(Error('timeout')) }, this.timeoutMs)
      this.pending.set(requestId, { kind, resolve, reject, timer })
      try { this.stream.write({ session_id: this.sessionId, request_id: requestId, ...payload }) }
      catch { clearTimeout(timer); this.pending.delete(requestId); reject(Error('transport unavailable')) }
    })
  }

  startSession() { return this.request({ start_session: { mode: 'diagnostics' } }, 'ready') }

  async ping() {
    if (!this.enabled) return this.getStatus()
    if (this.status !== 'connected') { this.lastPing = 'not connected'; return this.getStatus() }
    const epoch = this.epoch
    try { await this.request({ ping: {} }, 'pong'); if (epoch === this.epoch) this.lastPing = 'pong' }
    catch { if (epoch === this.epoch) { this.fail(); this.lastPing = 'failed' } }
    return this.getStatus()
  }

  async finish(kind) {
    try { if (this.stream) await this.request({ [kind]: {} }, 'status') } catch { /* Safe local cleanup below. */ }
    return this.close()
  }
  cancel() { return this.finish('cancel') }
  endSession() { return this.finish('end_session') }

  fail() {
    this.close()
    this.status = 'error'
    // Never forward gRPC details/metadata, which may contain sensitive values.
    this.lastError = 'Local gRPC connection failed. Check configuration and the G1 server.'
  }

  close() {
    this.epoch++
    const stream = this.stream, client = this.client
    this.stream = null
    this.client = null
    this.sessionId = null
    this.connecting = null
    for (const item of this.pending.values()) { clearTimeout(item.timer); item.reject(Error('closed')) }
    this.pending.clear()
    try { stream?.cancel() } catch { /* Already closed. */ }
    try { client?.close() } catch { /* Already closed. */ }
    this.status = this.enabled ? 'disconnected' : 'disabled'
    this.lastPing = 'not sent'
    this.lastError = ''
    return this.getStatus()
  }
}

function registerGrpcRealtimeIpc(ipcMain, validateSender, client) {
  for (const [channel, method] of [['getStatus', 'getStatus'], ['connect', 'connect'], ['ping', 'ping'], ['close', 'close']]) {
    ipcMain.handle(`grpcRealtime:${channel}`, async (event) => { validateSender(event); return client[method]() })
  }
}

module.exports = { GrpcRealtimeClient, registerGrpcRealtimeIpc }

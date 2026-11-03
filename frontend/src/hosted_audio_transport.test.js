import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { createServer } from 'node:http'
import { once } from 'node:events'
const require = createRequire(import.meta.url)
const { createHostedAudioTransport, destination } = require('../electron/hosted_audio_transport.cjs')

for (const url of ['http://example.com', 'https://user:pass@example.com', 'https://example.com/?x=1', 'https://example.com/#x', 'https://example.com/path']) {
  test(`reject untrusted relay URL ${url}`, () => assert.throws(() => destination(url, 'reviewed', false)))
}
test('insecure loopback needs explicit test construction; deployment version mandatory', () => {
  assert.throws(() => destination('http://127.0.0.1:9000', 'v1', false))
  assert.throws(() => destination('https://example.com', '', false))
  assert.equal(destination('http://127.0.0.1:9000', 'v1', true).hostname, '127.0.0.1')
})

function fixture({ current = true, deployment = 'v1', slow = false } = {}) {
  const sockets = [], requests = []
  class Socket extends EventTarget {
    constructor(url, options) { super(); this.url = url; this.options = options; this.readyState = 1; this.bufferedAmount = slow ? 12801 : 0; this.sent = []; sockets.push(this) }
    send(value) { this.sent.push(value) }
    close() { this.readyState = 3 }
    event(kind, value) { const event = new Event(kind); if (kind === 'message') Object.defineProperty(event, 'data', { value: JSON.stringify(value) }); this.dispatchEvent(event) }
  }
  const client = createHostedAudioTransport({ baseUrl: 'https://backend.example', deployment: 'v1',
    getAuthorization: async () => ({ authorization: 'Bearer synthetic-private', isCurrent: () => current }),
    WebSocketClass: Socket, fetchImpl: async (url, options) => { requests.push({ url, options }); return new Response(JSON.stringify({ protocol_version: 1, deployment_id: deployment, auto_available: true })) } })
  const ready = () => new Promise((resolve, reject) => client.waitForReady(1, error => error ? reject(error) : resolve()))
  return { client, ready, sockets, requests }
}
const start = { session_id: 'stream', request_id: 'main-request', start_session: { active_session_id: 'owned-session', source: 'both', cloud_context_requested: true } }
const metadata = { get: () => ['Bearer synthetic-private'] }

test('server readiness/version and current account precede any socket; redirects denied', async () => {
  for (const options of [{ current: false }, { deployment: 'other' }]) {
    const f = fixture(options); await assert.rejects(f.ready()); assert.equal(f.sockets.length, 0)
    assert.throws(() => f.client.StreamInterview(metadata))
  }
  const f = fixture(); await f.ready()
  assert.equal(f.requests[0].options.redirect, 'error')
})
test('authorization, sequential PCM, correlation and bounded backpressure reuse existing event contract', async () => {
  const f = fixture(); await f.ready()
  const stream = f.client.StreamInterview(metadata), events = []
  stream.on('data', value => events.push(value)); stream.on('error', () => {})
  stream.write(start)
  const socket = f.sockets[0]; socket.event('open')
  assert.equal(socket.options.headers.Origin, 'https://backend.example')
  assert.equal(socket.options.followRedirects, false)
  assert.equal(socket.options.maxPayload, 4 * 1024 * 1024)
  assert.doesNotMatch(socket.url.toString(), /synthetic-private/)
  const audio = { request_id: 'pcm1', audio_chunk: { audio: Buffer.alloc(3200) } }
  assert.throws(() => stream.write(audio))
  socket.event('message', { request_id: 'relay-start', ready: {} })
  assert.equal(events[0].request_id, 'main-request')
  stream.write(audio)
  assert.equal(socket.sent[1].readBigUInt64BE(), 1n)
  assert.throws(() => stream.write(audio))
  socket.event('message', { request_id: 'relay-pcm', status: { code: 'audio_chunk_received' } })
  assert.equal(events.at(-1).request_id, 'pcm1')
  socket.bufferedAmount = 12801
  assert.throws(() => stream.write({ request_id: 'pcm2', audio_chunk: { audio: Buffer.alloc(3200) } }))
  f.client.close(); assert.equal(socket.readyState, 3)
})
test('disconnect never opens another socket or replays buffered audio', async () => {
  const f = fixture(); await f.ready(); const stream = f.client.StreamInterview(metadata)
  stream.on('end', () => {}); stream.on('error', () => {})
  stream.write(start); f.sockets[0].event('open'); f.sockets[0].event('close')
  assert.throws(() => stream.write({ audio_chunk: { audio: Buffer.alloc(3200) } }))
  assert.equal(f.sockets.length, 1)
  f.client.close()
})

test('real network capability redirect never forwards credentials to another destination', async () => {
  let received = 0
  const other = createServer((_request, response) => { received++; response.end('{}') })
  other.listen(0, '127.0.0.1'); await once(other, 'listening')
  const server = createServer((_request, response) => {
    response.writeHead(302, { Location: `http://127.0.0.1:${other.address().port}/steal` }); response.end()
  })
  server.listen(0, '127.0.0.1'); await once(server, 'listening')
  const client = createHostedAudioTransport({ baseUrl: `http://127.0.0.1:${server.address().port}`, deployment: 'v1', allowLoopback: true,
    getAuthorization: async () => ({ authorization: 'Bearer synthetic-private', isCurrent: () => true }) })
  try {
    await assert.rejects(new Promise((resolve, reject) => client.waitForReady(1, error => error ? reject(error) : resolve())))
    assert.equal(received, 0)
  } finally { client.close(); server.closeAllConnections(); other.closeAllConnections(); await Promise.all([new Promise(resolve => server.close(resolve)), new Promise(resolve => other.close(resolve))]) }
})

test('real socket parser rejects oversized answer before publication', async () => {
  const { WebSocketServer } = require('ws')
  const server = createServer((_request, response) => {
    response.writeHead(200, { 'Content-Type': 'application/json' })
    response.end(JSON.stringify({ protocol_version: 1, deployment_id: 'v1', auto_available: true }))
  })
  const sockets = new WebSocketServer({ noServer: true, perMessageDeflate: false })
  server.on('upgrade', (request, socket, head) => sockets.handleUpgrade(request, socket, head, ws => {
    ws.on('error', () => {})
    ws.once('message', () => { ws.send('x'.repeat(4 * 1024 * 1024 + 1)) })
  }))
  server.listen(0, '127.0.0.1'); await once(server, 'listening')
  const client = createHostedAudioTransport({ baseUrl: `http://127.0.0.1:${server.address().port}`, deployment: 'v1', allowLoopback: true,
    getAuthorization: async () => ({ authorization: 'Bearer synthetic-private', isCurrent: () => true }) })
  try {
    await new Promise((resolve, reject) => client.waitForReady(1, error => error ? reject(error) : resolve()))
    const stream = client.StreamInterview(metadata)
    const rejected = once(stream, 'error')
    stream.on('data', () => assert.fail('Oversized message must not be published'))
    stream.write(start)
    await rejected
  } finally { client.close(); for (const ws of sockets.clients) ws.terminate(); sockets.close(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve)) }
})

// Launched only by the guarded Python fixture; all audio/providers/storage are synthetic.
import { createRequire } from 'node:module'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { EventEmitter } from 'node:events'
import { createInterface } from 'node:readline'
import { createGrpcAutoSession } from '../../src/grpc_auto_session.js'
const require = createRequire(import.meta.url)
const { GrpcRealtimeClient, registerGrpcRealtimeIpc } = require('../../electron/grpc_realtime_client.cjs')
const [port, source] = process.argv.slice(2)
if (!/^\d+$/.test(port) || !['microphone', 'system', 'both'].includes(source)) throw Error('invalid fixture input')
// Independent process: no dotenv, real credentials or external endpoint.
const client = new GrpcRealtimeClient({ env: { ELECTRON_GRPC_REALTIME_ENABLED: 'true', ELECTRON_GRPC_AUDIO_ENABLED: 'true', ELECTRON_GRPC_REALTIME_PORT: port },
  getCloudAuthorization: async () => ({ authorization: 'Bearer synthetic-test-only', isCurrent: () => true }) })
client.health = { ...client.health, grpc_health: 'healthy', grpc_system_audio_available: true, grpc_combined_audio_available: true }
const handlers = new Map(), renderer = new EventEmitter(), exposed = {}
renderer.invoke = (channel, ...args) => handlers.get(channel)({}, ...args)
renderer.send = () => {}
registerGrpcRealtimeIpc({ handle: (channel, callback) => handlers.set(channel, callback) }, () => {}, client, () => {}, () => {},
  snapshot => renderer.emit('grpcRealtime:autoEvent', {}, snapshot))
runInNewContext(readFileSync(new URL('../../electron/preload.cjs', import.meta.url), 'utf8'), {
  require: name => { if (name !== 'electron') throw Error('unexpected preload import'); return {
    ipcRenderer: renderer, contextBridge: { exposeInMainWorld: (name, api) => { exposed[name] = api } } } },
})
const send = value => process.stdout.write(JSON.stringify(value) + '\n')
const api = exposed.electronAPI
const session = await createGrpcAutoSession({ source, context: { activeSessionId: '11111111-1111-4111-8111-111111111111' }, api,
  stream: { getTracks: () => [], getAudioTracks: () => [] }, createMic: () => ({ start: async () => {}, close() {} }),
  onAnswer: entry => send({ stage: 'answer', entry }), onError: () => send({ stage: 'error' }) })
if (!session || client.getStatus().answerStreamVersion !== 1) throw Error('negotiation failed')
send({ stage: 'ready' })
const input = createInterface({ input: process.stdin })
for await (const command of input) {
  if (command === 'close') { await session.close(); send({ stage: 'closed' }); input.close(); break }
}

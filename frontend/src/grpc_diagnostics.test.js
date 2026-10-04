import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

const source = readFileSync(new URL('./components/MainDiagnosticsWindow.jsx', import.meta.url), 'utf8')
const body = source.split('function GrpcRealtimeDiagnostics() {')[1].split('  if (!state) return null')[0]
const flush = () => new Promise(resolve => setImmediate(resolve))
function mount(api) {
  let state, cleanup, interval, cleared = false
  const context = { window: { electronAPI: api }, useState: initial => [initial, value => {
    if (initial === null) state = typeof value === 'function' ? value(state) : value
  }], useRef: current => ({ current }), useEffect: effect => { cleanup = effect() },
  setInterval: (fn, delay) => { assert.equal(delay, 3000); interval = fn; return 1 },
  clearInterval: id => { assert.equal(id, 1); cleared = true } }
  const run = vm.runInNewContext(`(function () {${body}; return run })()`, context)
  return { run, state: () => state, tick: () => interval?.(), unmount: () => cleanup?.(), cleared: () => cleared }
}

test('initial failure remains visible and all actions retry with an immediate status refresh', async () => {
  let calls = 0
  const actions = []
  const api = { getGrpcRealtimeStatus: async () => {
    calls++
    if (calls === 1) throw Error('secret-token transcript')
    return { enabled: true, connectionStatus: 'connected', lastErrorMessage: 'secret-token transcript' }
  } }
  for (const method of ['connectGrpcRealtime', 'pingGrpcRealtime', 'closeGrpcRealtime']) {
    api[method] = async () => { actions.push(method); return {} }
  }
  const f = mount(api)
  await flush()
  assert.equal(f.state().enabled, null)
  assert.equal(f.state().connectionStatus, 'unavailable')
  assert.doesNotMatch(JSON.stringify(f.state()), /secret-token|transcript/)
  for (const method of Object.keys(api).slice(1)) await f.run(method)
  assert.equal(actions.length, 3)
  assert.equal(calls, 4)
  assert.doesNotMatch(f.state().lastErrorMessage, /secret-token|transcript/)
  assert.match(source, /state\.enabled !== false/)
  f.unmount()
})

test('polling updates disconnects without overlapping requests and cleans up on unmount', async () => {
  let calls = 0, resolve
  const f = mount({ getGrpcRealtimeStatus: () => {
    calls++
    return new Promise(done => { resolve = done })
  } })
  f.tick(); f.tick()
  assert.equal(calls, 1)
  resolve({ enabled: true, connectionStatus: 'connected' })
  await flush()
  assert.equal(f.state().connectionStatus, 'connected')
  f.tick()
  assert.equal(calls, 2)
  resolve({ enabled: true, connectionStatus: 'disconnected' })
  await flush()
  assert.equal(f.state().connectionStatus, 'disconnected')
  f.tick()
  f.unmount()
  resolve({ enabled: true, connectionStatus: 'connected' })
  await flush()
  f.tick()
  assert.equal(calls, 3)
  assert.equal(f.state().connectionStatus, 'disconnected')
  assert.equal(f.cleared(), true)
})

test('no polling is installed without the status API', () => {
  const f = mount({})
  f.tick(); f.unmount()
  assert.equal(f.state(), undefined)
  assert.equal(f.cleared(), false)
})

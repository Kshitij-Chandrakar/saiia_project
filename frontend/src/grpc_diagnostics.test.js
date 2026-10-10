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

const appSource = readFileSync(new URL('./App.jsx', import.meta.url), 'utf8')
const autoStatusEffect = appSource.split('if (!window.electronAPI?.getGrpcRealtimeStatus) return')[1].split('  }, [])')[0]
test('main Auto status retries failures without Connect and cleans up pending refreshes', async () => {
  let interval, state, resolve, calls = 0, cleared = false
  const cleanup = vm.runInNewContext(`(function(){${autoStatusEffect}})()`, {
    window: { electronAPI: { getGrpcRealtimeStatus: () => {
      if (++calls === 1) return Promise.reject(Error('private details'))
      return new Promise(done => { resolve = done })
    } } },
    setAutoGrpcStatus: value => { state = value },
    setInterval: (fn, ms) => { assert.equal(ms, 3000); interval = fn; return 1 },
    clearInterval: () => { cleared = true },
  })
  await flush()
  interval(); interval()
  assert.equal(calls, 2)
  resolve({ autoPipelineEnabled: true })
  await flush()
  assert.equal(state.autoPipelineEnabled, true)
  interval(); cleanup(); resolve({ autoPipelineEnabled: false })
  await flush()
  assert.equal(state.autoPipelineEnabled, true)
  assert.equal(cleared, true)
})

test('local test controls are visible above runtime diagnostics and explain disabled gates', async () => {
  const { createRequire } = await import('node:module')
  const require = createRequire(import.meta.url)
  const React = require('react')
  const { renderToStaticMarkup } = require('react-dom/server')
  const { transformSync } = require('esbuild')
  const component = source.split('function LocalTestSessionControls(')[1].split('export default function MainDiagnosticsWindow')[0]
  const code = transformSync('function LocalTestSessionControls(' + component, { loader: 'jsx', jsxFactory: 'React.createElement' }).code
  const Controls = vm.runInNewContext(code + '; LocalTestSessionControls', {
    React, MetaRow: ({ label, value }) => React.createElement('p', null, label + ': ' + value),
  })
  const render = props => renderToStaticMarkup(React.createElement(Controls, props))
  const available = render({ localTestSession: false, diagnostics: { autoGrpcFlagEnabled: true } })
  const lowMic = render({ diagnostics: { questionIntake: { low_audio_warning: true, mic_rms_level: 0.001 } } })
  assert.match(lowMic, /Mic input is too low\. Move closer or increase microphone gain\./)
  assert.match(lowMic, /mic_rms_level: 0\.001/)
  assert.match(available, />Use local test session<\/button>/)
  assert.match(available, /disabled="">Restore cloud session/)
  assert.match(available, /Auto gRPC flag enabled: yes/)
  for (const reason of ['available only in development', 'USE_GRPC_AUTO_PIPELINE is disabled', 'not running in Electron']) {
    const html = render({ reason })
    assert.equal((html.match(/disabled=""/g) || []).length, 2)
    assert.ok(html.includes(reason))
  }
  const active = render({ localTestSession: true, activeSessionSuspended: true })
  assert.match(active, /disabled="">Use local test session/)
  assert.match(active, /Local test session: on/)
  assert.match(active, /Active session suspended: yes/)
  assert.ok(source.indexOf('<LocalTestSessionControls localTestSession=') < source.indexOf('<GrpcRealtimeDiagnostics />'))
})

test('generic Pipeline reflects Auto gRPC without changing routing', () => {
  const expression = source.match(/label="Pipeline" value=\{([^\n]+)\} \/>/)[1]
  const display = generationDiagnostics => vm.runInNewContext(expression, { generationDiagnostics })
  assert.equal(display({ autoModePipeline: 'grpc_realtime' }), 'gRPC realtime')
  assert.equal(display({ autoModePipeline: 'existing_default' }), 'REST/WebSocket (default)')
  assert.equal(display({ autoModePipeline: 'fallback' }), 'REST/WebSocket (default)')
  assert.equal(display({ manualPipeline: 'gRPC realtime' }), 'gRPC realtime')
})

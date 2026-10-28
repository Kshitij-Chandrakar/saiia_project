// Test-only physical-device panel. Uses the shipped capture/IPC lifecycle.
import { createGrpcAutoSession } from '../../../src/grpc_auto_session.js'

window.installPhysicalAcceptance = ({ sessionId, hosted = false }) => {
  const panel = document.createElement('section')
  panel.style.cssText = 'position:fixed;inset:12px;z-index:999999;background:white;color:#14213d;padding:20px;overflow:auto;border:3px solid #2563eb;font:16px system-ui'
  panel.setAttribute('aria-label', 'Isolated physical acceptance')
  const title = document.createElement('h1')
  title.textContent = 'Isolated physical acceptance — no provider calls'
  panel.append(title)
  const output = document.createElement('pre')
  output.style.whiteSpace = 'pre-wrap'
  let session, stream, opening = false, timing, timedStop
  const mark = key => { if (timing) timing[key] = performance.now() }
  const api = {
    ...window.electronAPI,
    connectGrpcAutoPipeline: async context => {
      mark('authorization_request_ms')
      const result = await window.electronAPI.connectGrpcAutoPipeline(context)
      if (result.autoPipelineReady) mark('authorization_confirmed_ms')
      return result
    },
    sendGrpcRealtimeAudioChunk: (...args) => {
      if (timing && !timing.capture_first_frame_ms) mark('capture_first_frame_ms')
      return window.electronAPI.sendGrpcRealtimeAudioChunk(...args)
    },
    closeGrpcRealtime: async (...args) => {
      mark('local_forwarding_revoked_ms')
      const result = await window.electronAPI.closeGrpcRealtime(...args)
      mark('server_stop_ack_ms')
      return result
    },
  }
  const deviceEvents = []
  const captureState = () => ({
    tracks: session?.captureStatus?.().tracks || (stream?.getAudioTracks() || []).map(track => ({ label: track.label, state: track.readyState, muted: track.muted })),
    events: [...deviceEvents],
  })
  const deviceEvent = event => {
    deviceEvents.push({ event, at_ms: Math.round(performance.now()) })
    if (deviceEvents.length > 12) deviceEvents.shift()
  }
  navigator.mediaDevices.addEventListener('devicechange', () => deviceEvent('devicechange'))
  const controls = []
  const report = value => { output.textContent = JSON.stringify(value, null, 2) }
  const stop = async () => {
    clearTimeout(timedStop)
    mark('stop_requested_ms')
    const closing = session
    session = null
    stream?.getTracks().forEach(track => track.stop())
    stream = null
    await closing?.close()
    if (timing && closing) {
      const settled = await api.getSubscription()
      mark('final_settlement_read_ms')
      timing.final = settled
      window.physicalTimingResult = structuredClone(timing)
    }
  }
  const button = (label, action) => {
    const node = document.createElement('button')
    node.textContent = label
    node.style.cssText = 'margin:6px;padding:12px;color:#14213d;background:#edf4ff;border:1px solid #7394c4;border-radius:6px'
    controls.push(node)
    node.onclick = async () => {
      controls.forEach(control => { control.disabled = true })
      try { await action() } catch { report({ error: 'Device or authority unavailable. Inspect safe server status.' }) }
      finally { controls.forEach(control => { control.disabled = false }) }
    }
    panel.append(node)
  }
  const start = async source => {
    if (opening || session) return
    opening = true
    try {
      session = await createGrpcAutoSession({ api, source,
        getUserMedia: async () => {
          stream = await navigator.mediaDevices.getUserMedia({ audio: true })
          deviceEvents.length = 0
          for (const track of stream.getAudioTracks()) {
            for (const event of ['ended', 'mute', 'unmute']) track.addEventListener(event, () => deviceEvent(event))
          }
          mark('capture_started_ms')
          return stream
        },
        context: { activeSessionId: sessionId },
        onStartupFailure: error => report({ error }), onError: () => {
          // The panel owns this MediaStream, as App does in the normal renderer.
          stream?.getTracks().forEach(track => track.stop())
          stream = null
          report({ error: 'Auto stopped' })
        },
        onLifecycle: report, onCloudStatus: status => report({ ready: status.autoPipelineReady, source }) })
      if (!session) await stop()
    } finally { opening = false }
  }
  for (const source of ['microphone', 'system', 'both']) button(`Start ${source}`, () => start(source))
  if (!hosted) button('Start synchronized 120-second silence check', async () => {
    if (session || opening) return
    timing = { tolerance_ms: 50, target_running_ms: 120000, baseline: await api.getSubscription() }
    mark('start_requested_ms')
    await start('microphone')
    if (session) timedStop = setTimeout(async () => {
      await stop()
      report({ capture: 'stopped', timing: window.physicalTimingResult })
    }, 120000)
  })
  button('Stop', async () => { await stop(); report({ capture: 'stopped', ...(timing ? { timing: window.physicalTimingResult } : {}) }) })
  button('Read safe status', async () => {
    const value = await window.electronAPI.getGrpcRealtimeStatus()
    report({ connection: value.connectionStatus, auto: value.autoStatus,
      failure: value.grpc_last_failure_reason, audioChunks: value.audioChunksSent,
      system: value.systemAudio, pcm: value.pcmDiagnostics, microphone: captureState(),
      availableInputs: (await navigator.mediaDevices.enumerateDevices()).filter(device => device.kind === 'audioinput').map(device => device.label) })
  })
  button('Read current plan / usage', async () => report(await window.electronAPI.getSubscription()))
  button('Logout and stop', async () => { await stop(); await window.electronAPI.logoutAuth(); report({ loggedOut: true }) })
  panel.append(output)
  document.body.append(panel)
}

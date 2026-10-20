import test from 'node:test'
import assert from 'node:assert/strict'
import { createGrpcMicTest } from './grpc_mic_test.js'
import { createPcmMicCapture } from './live_mic_transport.js'

const flush = () => new Promise(resolve => setImmediate(resolve))

async function fixture(t, send) {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const clock = { mono: 0, wall: 100000 }
  const frames = []
  let capture
  const mic = createGrpcMicTest({ continuous: true, ownsStream: false,
    monotonicNow: () => clock.mono, wallNow: () => clock.wall,
    getUserMedia: async () => ({}),
    createCapture: options => { capture = options; return { close() {} } },
    api: { getGrpcRealtimeStatus: async () => ({ audioEnabled: true, sttEnabled: true, connectionStatus: 'connected' }),
      sendGrpcRealtimeAudioChunk: async (data, metadata) => {
        frames.push({ data: new Int16Array(data), at: metadata.captureTimestampMs })
        if (send) { const result = await send(frames.length); if (result) return result }
        return { connectionStatus: 'connected' }
      } } })
  await mic.start()
  t.after(() => mic.close())
  return { clock, frames, mic,
    chunk(samples, start, discontinuity = false) {
      capture.onChunk(Int16Array.from(samples).buffer, { sampleRate: 16000, startMonotonicMs: start, discontinuity })
    },
    async step(ms) { clock.mono += ms; t.mock.timers.tick(ms); await flush() } }
}

test('one callback splits into unique frames spaced by sample duration', async t => {
  const f = await fixture(t)
  f.clock.mono = 300
  f.chunk(new Int16Array(4800).fill(7), 0)
  await flush(); await f.step(100); await f.step(100)
  assert.deepEqual(f.frames.map(frame => frame.at), [100000, 100100, 100200])
  assert.equal(f.frames.length, 3)
  assert.ok(f.frames.every(frame => frame.data.length === 1600 && frame.data[0] === 7))
})

test('retained tail keeps its original start time across callback boundaries', async t => {
  const f = await fixture(t)
  f.clock.mono = 125
  f.chunk(new Int16Array(2000).fill(1), 0)
  await flush(); await f.step(100)
  f.chunk(new Int16Array(1200).fill(2), 125)
  await flush()
  assert.deepEqual(f.frames.map(frame => frame.at), [100000, 100100])
  assert.ok(f.frames[1].data.slice(0, 400).every(x => x === 1))
  assert.ok(f.frames[1].data.slice(400).every(x => x === 2))
})

test('wall-clock adjustment cannot alter frame timestamps or local queue age', async t => {
  const f = await fixture(t)
  f.clock.mono = 100; f.chunk(new Int16Array(1600), 0)
  await flush(); await f.step(100)
  f.clock.wall += 86400000
  f.chunk(new Int16Array(1600), 100)
  await flush(); await f.step(100)
  f.clock.wall -= 172800000
  f.chunk(new Int16Array(1600), 200)
  await flush()
  assert.deepEqual(f.frames.map(frame => frame.at), [100000, 100100, 100200])
})

test('IPC stall discards stale sample frames before sending and accepts fresh audio', async t => {
  let release
  const f = await fixture(t, count => count === 1 ? new Promise(resolve => { release = resolve }) : undefined)
  f.clock.mono = 200; f.chunk(new Int16Array(3200), 0)
  await flush()
  f.clock.mono = 800; release()
  await flush(); await f.step(100)
  assert.deepEqual(f.frames.map(frame => frame.at), [100000])
  f.chunk(new Int16Array(1600), 800)
  await flush()
  assert.deepEqual(f.frames.map(frame => frame.at), [100000, 100800])
})

test('Stop/restart invalidates old queued frames and resets sample timing', async t => {
  let release
  const f = await fixture(t, count => count === 1 ? new Promise(resolve => { release = resolve }) : undefined)
  f.clock.mono = 200; f.chunk(new Int16Array(3200).fill(1), 0)
  await flush(); f.mic.close()
  f.clock.mono = 1000; f.clock.wall = 101000
  await f.mic.start()
  f.chunk(new Int16Array(1600).fill(2), 900)
  release(); await flush(); await f.step(100)
  assert.deepEqual(f.frames.map(frame => frame.at), [100000, 100900])
  assert.equal(f.frames[1].data[0], 2)
})

test('capture discontinuity discards pre-gap tail instead of stitching old audio', async t => {
  const f = await fixture(t)
  f.clock.mono = 50; f.chunk(new Int16Array(800).fill(1), 0)
  f.clock.mono = 1100; f.chunk(new Int16Array(1600).fill(2), 1000, true)
  await flush()
  assert.deepEqual(f.frames.map(frame => frame.at), [101000])
  assert.ok(f.frames[0].data.every(x => x === 2))
})

for (const rate of [16000, 44100, 48000]) test(`Web Audio ${rate} Hz irregular callbacks preserve the output sample clock`, () => {
  const chunks = []
  let mono = 0, processor, context
  class Context {
    constructor() { this.sampleRate = rate; this.currentTime = 0; context = this }
    createMediaStreamSource() { return { connect() {}, disconnect() {} } }
    createScriptProcessor() { processor = { connect() {}, disconnect() {} }; return processor }
    close() { return Promise.resolve() }
  }
  const capture = createPcmMicCapture({ stream: {}, isActive: () => true, continuous: true,
    AudioContextClass: Context, monotonicNow: () => mono,
    onChunk: (data, timing) => chunks.push({ count: data.byteLength / 2, timing }) })
  let input = 0
  for (const count of [997, 173, 4096, 555, 1, 3072]) {
    input += count
    // Callback delivery is delayed; playback/context clock, not callback arrival,
    // defines the nominal first block interval. Physical input latency is unknown.
    mono = input / rate * 1000 + 25
    context.currentTime = mono / 1000
    processor.onaudioprocess({ playbackTime: input / rate,
      inputBuffer: { getChannelData: () => new Float32Array(count).fill(.25) } })
  }
  let output = 0
  for (const { count, timing } of chunks) {
    assert.equal(timing.sampleRate, 16000)
    assert.ok(Math.abs(timing.startMonotonicMs - output / 16000 * 1000) < 1e-7)
    output += count
  }
  assert.equal(output, Math.floor(input * 16000 / rate + 1e-6))
  capture.close()
})

function captureClock({ rate = 16000, continuous = true } = {}) {
  let processor, context, active = true, mono = 0
  const chunks = []
  class Context {
    constructor() { this.sampleRate = rate; this.currentTime = 0; context = this }
    createMediaStreamSource() { return { connect() {}, disconnect() {} } }
    createScriptProcessor() { processor = { connect() {}, disconnect() {} }; return processor }
    close() { return Promise.resolve() }
  }
  const capture = createPcmMicCapture({ stream: {}, continuous, AudioContextClass: Context,
    monotonicNow: () => mono, isActive: () => active,
    onChunk: (data, timing) => chunks.push({ samples: new Int16Array(data), ...timing }) })
  const callback = processor.onaudioprocess
  return { chunks, capture, inactive() { active = false }, activate() { active = true },
    tick(wall, audio, count = 1600, value = .5) {
      mono = wall; context.currentTime = audio / 1000
      callback({ playbackTime: context.currentTime,
        inputBuffer: { getChannelData: () => new Float32Array(count).fill(value) } })
    } }
}

test('frozen context then repeated resume reanchors fresh sample timestamps; close fences callbacks', () => {
  const f = captureClock()
  f.tick(100, 100)
  f.tick(1100, 100)
  f.tick(1200, 200)
  f.tick(2200, 200)
  f.tick(2300, 300)
  assert.deepEqual(f.chunks.map(x => x.startMonotonicMs), [0, 1000, 1100, 2100, 2200])
  assert.deepEqual(f.chunks.map(x => x.discontinuity), [false, true, false, true, false])
  f.capture.close(); f.tick(4000, 300)
  assert.equal(f.chunks.length, 5)
})

test('ordinary callback delay advances both clocks and bounded clock jitter preserves continuity', () => {
  const f = captureClock()
  f.tick(100, 100)
  f.tick(1100, 1100)
  f.tick(1300, 1200)
  assert.deepEqual(f.chunks.map(x => x.discontinuity), [false, false, false])
  assert.deepEqual(f.chunks.map(x => x.startMonotonicMs), [0, 100, 200])
  f.capture.close()
})

test('inactive first callback initializes safely; resumption resets fractional downsampler', () => {
  const f = captureClock({ rate: 48000 })
  f.tick(1, 1, 1, 1) // Fractional area must not bleed into resumed zero input.
  f.tick(1000, 1, 3, 0)
  assert.equal(f.chunks.length, 1)
  assert.equal(f.chunks[0].samples[0], 0)
  assert.equal(f.chunks[0].discontinuity, true)
  f.capture.close()
  const inactive = captureClock()
  inactive.inactive(); inactive.tick(1000, 0)
  assert.equal(inactive.chunks.length, 0)
  inactive.activate(); inactive.tick(1100, 100)
  assert.equal(inactive.chunks[0].startMonotonicMs, 1000)
  assert.equal(inactive.chunks[0].discontinuity, true)
  inactive.capture.close()
})

test('discontinuity invalidates queued frames and tail even within queue-age tolerance', async t => {
  let release
  const f = await fixture(t, n => n === 1 ? new Promise(resolve => { release = resolve }) : undefined)
  f.clock.mono = 200; f.chunk(new Int16Array(3600).fill(1), 0)
  await flush()
  f.clock.mono = 250; f.chunk(new Int16Array(1600).fill(2), 150, true)
  release(); await flush(); await f.step(100)
  assert.deepEqual(f.frames.map(x => x.at), [100000, 100150])
  assert.ok(f.frames[1].data.every(x => x === 2))
})

test('backend termination during suspension closes run; resumed callback cannot restart it', async t => {
  const f = await fixture(t)
  // Explicit close is the owner lifecycle's backend-source-loss cleanup boundary.
  f.clock.mono = 50; f.chunk(new Int16Array(800), 0)
  f.mic.close()
  f.clock.mono = 2000; f.chunk(new Int16Array(1600), 1900, true)
  await flush()
  assert.equal(f.frames.length, 0)
})

test('non-continuous capture retains legacy metadata behavior across clock gaps', () => {
  const f = captureClock({ continuous: false })
  f.tick(100, 100); f.tick(2000, 100)
  assert.equal(f.chunks.length, 2)
  assert.equal(f.chunks[1].startMonotonicMs, undefined)
  f.capture.close()
})


test('backend disconnected result fences resumed capture until explicit start', async t => {
  let release
  const f = await fixture(t, () => new Promise(resolve => { release = resolve }))
  f.clock.mono = 100; f.chunk(new Int16Array(1600), 0)
  await flush()
  f.clock.mono = 1100; f.chunk(new Int16Array(1600), 1000, true)
  release({ connectionStatus: 'disconnected' }); await flush(); await f.step(100)
  f.chunk(new Int16Array(1600), 1100)
  await flush()
  assert.equal(f.frames.length, 1)
})

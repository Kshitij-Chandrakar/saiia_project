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
        if (send) await send(frames.length)
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

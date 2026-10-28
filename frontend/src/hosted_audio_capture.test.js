import test from 'node:test'
import assert from 'node:assert/strict'
import { createHostedAudioCapture } from './hosted_audio_capture.js'

class Track extends EventTarget {
  readyState = 'live'
  stop() { this.readyState = 'ended' }
}
const stream = () => {
  const track = new Track()
  return { getTracks: () => [track], getAudioTracks: () => [track] }
}
test('Both mixes once and physical track loss releases every owned source', async () => {
  const mic = stream(), system = stream(), mixed = stream(), gains = []
  let closed = 0
  class Context {
    createMediaStreamDestination() { return { stream: mixed } }
    createMediaStreamSource() { return { connect() {}, disconnect() {} } }
    createGain() { const value = { gain: {}, connect() {}, disconnect() {} }; gains.push(value); return value }
    async resume() {}
    async close() { closed++ }
  }
  const capture = await createHostedAudioCapture({ source: 'both', AudioContextClass: Context,
    mediaDevices: { getUserMedia: async () => mic, getDisplayMedia: async () => system } })
  assert.equal(capture.stream, mixed)
  assert.deepEqual(gains.map(value => value.gain.value), [0.5, 0.5])
  let ended = 0
  mixed.getAudioTracks()[0].addEventListener('ended', () => { ended++ })
  mic.getAudioTracks()[0].dispatchEvent(new Event('ended'))
  assert.equal(ended, 1)
  for (const value of [mic, system, mixed]) assert.equal(value.getTracks()[0].readyState, 'ended')
  capture.close(); assert.equal(closed, 1)
})
test('failure opening required system source releases the already acquired mic', async () => {
  const mic = stream()
  await assert.rejects(createHostedAudioCapture({ source: 'both', AudioContextClass: class {},
    mediaDevices: { getUserMedia: async () => mic, getDisplayMedia: async () => { throw Error('denied') } } }))
  assert.equal(mic.getTracks()[0].readyState, 'ended')
})
test('microphone ended signal is bounded and close remains idempotent', async () => {
  const mic = stream()
  const capture = await createHostedAudioCapture({ source: 'microphone', AudioContextClass: class {},
    mediaDevices: { getUserMedia: async () => mic } })
  mic.getTracks()[0].dispatchEvent(new Event('ended'))
  assert.equal(mic.getTracks()[0].readyState, 'ended')
  capture.close()
})

test('authorization loss while system selection is pending stops mic immediately and releases late source', async () => {
  const mic = stream(), system = stream(), controller = new AbortController()
  let resolveSystem, selecting
  const pending = new Promise(resolve => { resolveSystem = resolve })
  const selected = new Promise(resolve => { selecting = resolve })
  const opening = createHostedAudioCapture({ source: 'both', signal: controller.signal, AudioContextClass: class {},
    mediaDevices: { getUserMedia: async () => mic, getDisplayMedia: () => { selecting(); return pending } } })
  await selected
  controller.abort()
  assert.equal(mic.getTracks()[0].readyState, 'ended')
  resolveSystem(system)
  await assert.rejects(opening)
  assert.equal(system.getTracks()[0].readyState, 'ended')
})

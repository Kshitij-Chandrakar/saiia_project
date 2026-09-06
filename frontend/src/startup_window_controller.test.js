import assert from 'node:assert/strict'
import test from 'node:test'
import { createStartupWindowController } from '../electron/startup_window_controller.cjs'

const mascotLayout = { width: 144, height: 144, minWidth: 144, minHeight: 144 }

function createFakeWindow(bounds = { x: 100, y: 80, width: 428, height: 462 }) {
  let currentBounds = { ...bounds }
  let minimumSize = [428, 384]
  const calls = []
  return {
    calls,
    isDestroyed: () => false,
    getBounds: () => ({ ...currentBounds }),
    getMinimumSize: () => [...minimumSize],
    setMinimumSize: (width, height) => {
      minimumSize = [width, height]
      calls.push(['setMinimumSize', width, height])
    },
    setBounds: (nextBounds) => {
      currentBounds = { ...nextBounds }
      calls.push(['setBounds', { ...nextBounds }])
    },
    show: () => calls.push(['show']),
    focus: () => calls.push(['focus']),
    get currentBounds() {
      return { ...currentBounds }
    },
  }
}

function createFakeScreen(workArea = { x: 0, y: 0, width: 1280, height: 720 }) {
  const calls = []
  return {
    calls,
    getDisplayMatching: (bounds) => {
      calls.push({ ...bounds })
      return { workArea: { ...workArea } }
    },
  }
}

test('collapse saves bounds once and restore is idempotent', () => {
  const screen = createFakeScreen()
  const controller = createStartupWindowController({ screen, mascotLayout })
  const window = createFakeWindow()

  assert.deepEqual(controller.collapse(window), { ok: true, collapsed: true })
  assert.deepEqual(window.currentBounds, { x: 384, y: 80, width: 144, height: 144 })
  const callsAfterCollapse = window.calls.length
  assert.deepEqual(controller.collapse(window), { ok: true, collapsed: true })
  assert.equal(window.calls.length, callsAfterCollapse)

  assert.deepEqual(controller.restore(window), { ok: true, collapsed: false })
  assert.deepEqual(window.currentBounds, { x: 100, y: 80, width: 428, height: 462 })
  assert.deepEqual(window.calls.slice(-4), [
    ['setMinimumSize', 428, 384],
    ['setBounds', { x: 100, y: 80, width: 428, height: 462 }],
    ['show'],
    ['focus'],
  ])
  assert.deepEqual(controller.restore(window), { ok: true, collapsed: false })
  assert.equal(window.calls.at(-1)[0], 'focus')
})

test('restore clamps saved bounds to the current display work area', () => {
  const screens = [
    createFakeScreen({ x: 0, y: 0, width: 1280, height: 720 }),
    createFakeScreen({ x: 0, y: 0, width: 800, height: 500 }),
  ]
  const screen = {
    getDisplayMatching: (bounds) => screens.shift().getDisplayMatching(bounds),
  }
  const controller = createStartupWindowController({ screen, mascotLayout })
  const window = createFakeWindow({ x: 1000, y: 300, width: 428, height: 462 })

  controller.collapse(window)
  controller.restore(window)

  assert.deepEqual(window.currentBounds, { x: 372, y: 38, width: 428, height: 462 })
})

test('failed native collapse does not enter mascot state or lose the expanded window', () => {
  const screen = createFakeScreen()
  const controller = createStartupWindowController({ screen, mascotLayout })
  const window = createFakeWindow()
  const originalSetBounds = window.setBounds
  window.setBounds = () => {
    throw new Error('native bounds failure')
  }

  assert.deepEqual(controller.collapse(window), { ok: false, reason: 'startup-window-collapse-failed' })
  assert.equal(controller.isCollapsed(), false)
  assert.deepEqual(window.currentBounds, { x: 100, y: 80, width: 428, height: 462 })
  window.setBounds = originalSetBounds
  assert.deepEqual(controller.collapse(window), { ok: true, collapsed: true })
})

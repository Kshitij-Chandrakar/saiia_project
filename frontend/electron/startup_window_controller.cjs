'use strict'

function clampWindowBounds(bounds, workArea) {
  const width = Math.min(Math.max(1, bounds.width), workArea.width)
  const height = Math.min(Math.max(1, bounds.height), workArea.height)
  const maxX = workArea.x + workArea.width - width
  const maxY = workArea.y + workArea.height - height

  return {
    x: Math.min(maxX, Math.max(workArea.x, bounds.x)),
    y: Math.min(maxY, Math.max(workArea.y, bounds.y)),
    width,
    height,
  }
}

function createStartupWindowController({ screen, mascotLayout }) {
  let collapsed = false
  let expandedState = null

  function getMascotBounds(expandedBounds) {
    const display = screen.getDisplayMatching(expandedBounds)
    return clampWindowBounds(
      {
        x: expandedBounds.x + expandedBounds.width - mascotLayout.width,
        y: expandedBounds.y,
        width: mascotLayout.width,
        height: mascotLayout.height,
      },
      display.workArea,
    )
  }

  function collapse(window) {
    if (!window || window.isDestroyed()) {
      return { ok: false, reason: 'startup-window-unavailable' }
    }
    if (collapsed) {
      return { ok: true, collapsed: true }
    }

    const bounds = window.getBounds()
    const [minWidth, minHeight] = window.getMinimumSize()
    const nextState = { bounds: { ...bounds }, minWidth, minHeight }

    try {
      window.setMinimumSize(mascotLayout.minWidth, mascotLayout.minHeight)
      window.setBounds(getMascotBounds(bounds))
    } catch {
      try {
        window.setMinimumSize(minWidth, minHeight)
      } catch {
        // Leave the native window usable if the platform rejects the rollback.
      }
      return { ok: false, reason: 'startup-window-collapse-failed' }
    }

    expandedState = nextState
    collapsed = true
    return { ok: true, collapsed: true }
  }

  function restore(window) {
    if (!collapsed) {
      return { ok: true, collapsed: false }
    }
    if (!window || window.isDestroyed()) {
      return { ok: false, reason: 'startup-window-unavailable' }
    }

    const savedState = expandedState
    if (!savedState) {
      collapsed = false
      return { ok: true, collapsed: false }
    }

    try {
      window.setMinimumSize(savedState.minWidth, savedState.minHeight)
      const display = screen.getDisplayMatching(savedState.bounds)
      window.setBounds(clampWindowBounds(savedState.bounds, display.workArea))
    } catch {
      return { ok: false, reason: 'startup-window-restore-failed' }
    }

    expandedState = null
    collapsed = false
    window.show()
    window.focus()
    return { ok: true, collapsed: false }
  }

  function reset() {
    collapsed = false
    expandedState = null
  }

  return {
    collapse,
    restore,
    reset,
    isCollapsed: () => collapsed,
  }
}

module.exports = { clampWindowBounds, createStartupWindowController }

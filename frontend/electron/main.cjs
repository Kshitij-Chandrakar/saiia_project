const { app, BrowserWindow, globalShortcut, ipcMain, screen, systemPreferences } = require('electron')
const path = require('path')

if (!app.requestSingleInstanceLock()) {
  app.quit()
}

let mainWindow
let overlayWindow
let isScreenSharing = false
let overlayVisible = true

const overlayState = {
  answer: '',
  error: '',
  status: '',
  transcript: '',
  fontSize: 14,
  provider: '',
  category: '',
  generationMs: null,
  totalPipelineMs: null,
  privacyMessage:
    'Visibility during screen sharing depends on OS, meeting app, and whether the user shares full screen, window, or tab.',
}

function getRendererUrl(view) {
  const devURL = process.env.VITE_DEV_SERVER_URL || (!app.isPackaged ? 'http://localhost:5173' : '')
  if (devURL) {
    return view === 'overlay' ? `${devURL}?view=overlay` : devURL
  }

  return null
}

function loadWindow(window, view) {
  const rendererUrl = getRendererUrl(view)
  if (rendererUrl) {
    window.loadURL(rendererUrl)
    return
  }

  window.loadFile(path.join(__dirname, '../dist/index.html'), {
    query: view === 'overlay' ? { view: 'overlay' } : {},
  })
}

function broadcastOverlayState() {
  const payload = {
    ...overlayState,
    visible: overlayVisible && !!(overlayWindow && overlayWindow.isVisible()),
  }

  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('overlay:state', payload)
  }
  if (overlayWindow && !overlayWindow.isDestroyed()) {
    overlayWindow.webContents.send('overlay:state', payload)
  }
}

function syncOverlayVisibility(visible) {
  overlayVisible = visible

  if ((!overlayWindow || overlayWindow.isDestroyed()) && visible) {
    createOverlayWindow()
    broadcastOverlayState()
    return
  }

  if (!overlayWindow || overlayWindow.isDestroyed()) {
    broadcastOverlayState()
    return
  }

  if (visible) {
    overlayWindow.showInactive()
  } else {
    overlayWindow.hide()
  }

  broadcastOverlayState()
}

function toggleOverlayVisibility() {
  const isCurrentlyVisible = !!(
    overlayWindow &&
    !overlayWindow.isDestroyed() &&
    overlayWindow.isVisible()
  )
  syncOverlayVisibility(!isCurrentlyVisible)
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 960,
    height: 760,
    minWidth: 820,
    minHeight: 640,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  loadWindow(mainWindow, 'main')

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

function createOverlayWindow() {
  overlayWindow = new BrowserWindow({
    width: 480,
    height: 320,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    hasShadow: false,
    resizable: true,
    movable: true,
    focusable: true,
    show: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  overlayWindow.setAlwaysOnTop(true, 'screen-saver')
  overlayWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })
  loadWindow(overlayWindow, 'overlay')

  overlayWindow.once('ready-to-show', () => {
    if (overlayVisible) {
      overlayWindow.showInactive()
    } else {
      overlayWindow.hide()
    }
    broadcastOverlayState()
  })

  overlayWindow.on('show', () => {
    overlayVisible = true
    broadcastOverlayState()
  })

  overlayWindow.on('hide', () => {
    overlayVisible = false
    broadcastOverlayState()
  })

  overlayWindow.on('closed', () => {
    overlayVisible = false
    overlayWindow = null
    broadcastOverlayState()
  })
}

function checkScreenSharing() {
  if (process.platform !== 'darwin') {
    return
  }

  const displays = screen.getAllDisplays()
  if (displays.length > 1) {
    if (!isScreenSharing) {
      isScreenSharing = true
      syncOverlayVisibility(false)
    }
  } else if (isScreenSharing) {
    isScreenSharing = false
    syncOverlayVisibility(true)
  }
}

app.on('ready', () => {
  createMainWindow()
  createOverlayWindow()

  if (process.platform === 'darwin' && typeof systemPreferences.subscribeNotification === 'function') {
    systemPreferences.subscribeNotification('com.apple.screenIsCaptured', () => {
      if (typeof systemPreferences.isScreenCaptured === 'function' && systemPreferences.isScreenCaptured()) {
        syncOverlayVisibility(false)
      } else if (!isScreenSharing) {
        syncOverlayVisibility(true)
      }
    })
  }

  setInterval(checkScreenSharing, 1000)

  globalShortcut.unregister('Control+H')
  const hideOk = globalShortcut.register('Control+H', () => {
    toggleOverlayVisibility()
  })

  if (!hideOk) {
    console.error(
      'Failed to register Ctrl+H for overlay hide/show. Another app may already be using this shortcut.'
    )
  } else {
    console.log('Ctrl+H registered for overlay hide/show')
  }

  app.on('activate', () => {
    if (mainWindow === null) {
      createMainWindow()
    }
    if (overlayWindow === null) {
      createOverlayWindow()
    }
  })
})

ipcMain.on('overlay:update-state', (_event, nextState) => {
  Object.assign(overlayState, nextState)
  broadcastOverlayState()
})

ipcMain.handle('overlay:get-state', () => ({
  ...overlayState,
  visible: overlayVisible && !!(overlayWindow && overlayWindow.isVisible()),
}))

ipcMain.handle('overlay:toggle-visibility', () => {
  toggleOverlayVisibility()
  return {
    visible: overlayVisible && !!(overlayWindow && overlayWindow.isVisible()),
  }
})

app.on('will-quit', () => {
  globalShortcut.unregisterAll()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

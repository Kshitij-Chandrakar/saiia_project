const { contextBridge, ipcRenderer } = require('electron')

const electronAPI = {
  updateOverlayState: (state) => {
    ipcRenderer.send('overlay:update-state', state)
  },
  getOverlayState: () => ipcRenderer.invoke('overlay:get-state'),
  toggleOverlayVisibility: () => ipcRenderer.invoke('overlay:toggle-visibility'),
  resetOverlayPosition: () => ipcRenderer.invoke('overlay:reset-position'),
  getOverlayBounds: () => ipcRenderer.invoke('overlay:get-bounds'),
  resizeOverlayBottomRight: (size) => ipcRenderer.invoke('overlay:resize-bottom-right', size),
  triggerToolbarAction: (action, payload) =>
    ipcRenderer.invoke('toolbar:trigger', action, payload),
  setOverlayOpacity: (value) => ipcRenderer.invoke('overlay:set-opacity', value),
  openMainPanel: () => ipcRenderer.invoke('window:open-main-panel'),
  listScreenSources: () => ipcRenderer.invoke('screen:list-sources'),
  captureScreen: (sourceId) => ipcRenderer.invoke('screen:capture', sourceId),
  captureActiveWindow: () => ipcRenderer.invoke('screen:capture-active-window'),
  captureActiveWindowSequence: () => ipcRenderer.invoke('screen:capture-active-window-sequence'),
  onOverlayState: (fn) => {
    const listener = (_event, payload) => fn(payload)
    ipcRenderer.on('overlay:state', listener)
    return () => ipcRenderer.removeListener('overlay:state', listener)
  },
  onToolbarAction: (fn) => {
    const listener = (_event, payload) => fn(payload)
    ipcRenderer.on('toolbar:action', listener)
    return () => ipcRenderer.removeListener('toolbar:action', listener)
  },
}

contextBridge.exposeInMainWorld('electronAPI', electronAPI)
contextBridge.exposeInMainWorld('saiia', {
  captureActiveWindow: electronAPI.captureActiveWindow,
  captureActiveWindowSequence: electronAPI.captureActiveWindowSequence,
  captureScreen: electronAPI.captureScreen,
  listScreenSources: electronAPI.listScreenSources,
})

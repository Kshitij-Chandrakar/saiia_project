const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  updateOverlayState: (state) => {
    ipcRenderer.send('overlay:update-state', state)
  },
  getOverlayState: () => ipcRenderer.invoke('overlay:get-state'),
  toggleOverlayVisibility: () => ipcRenderer.invoke('overlay:toggle-visibility'),
  onOverlayState: (fn) => {
    const listener = (_event, payload) => fn(payload)
    ipcRenderer.on('overlay:state', listener)
    return () => ipcRenderer.removeListener('overlay:state', listener)
  },
})

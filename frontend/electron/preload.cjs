const { contextBridge, ipcRenderer } = require('electron')

const electronAPI = {
  sendGrpcRealtimeAudioChunk: (data, metadata) => ipcRenderer.invoke('grpcRealtime:audioChunk', data, metadata),
  stopGrpcRealtimeAudio: () => ipcRenderer.invoke('grpcRealtime:manualStop'),
  connectGrpcAutoPipeline: (context) => ipcRenderer.invoke('grpcRealtime:connectAuto', context),
  onGrpcAutoEvent: (callback) => {
    const listener = (_event, snapshot) => callback(snapshot)
    ipcRenderer.on('grpcRealtime:autoEvent', listener)
    return () => ipcRenderer.removeListener('grpcRealtime:autoEvent', listener)
  },
  connectGrpcManualPipeline: () => ipcRenderer.invoke('grpcRealtime:connectManual'),
  onGrpcManualEvent: (fn) => {
    const listener = (_event, snapshot) => fn(snapshot)
    ipcRenderer.on('grpcRealtime:manualEvent', listener)
    return () => ipcRenderer.removeListener('grpcRealtime:manualEvent', listener)
  },
  onGrpcManualUiTiming: (fn) => {
    const listener = (_event, timing) => fn(timing)
    ipcRenderer.on('grpcRealtime:uiTiming', listener)
    return () => ipcRenderer.removeListener('grpcRealtime:uiTiming', listener)
  },
  reportGrpcManualUiTiming: (run, field, at) => ipcRenderer.invoke('grpcRealtime:uiTiming', run, field, at),
  getGrpcRealtimeStatus: () => ipcRenderer.invoke('grpcRealtime:getStatus'),
  connectGrpcRealtime: () => ipcRenderer.invoke('grpcRealtime:connect'),
  pingGrpcRealtime: () => ipcRenderer.invoke('grpcRealtime:ping'),
  closeGrpcRealtime: () => ipcRenderer.invoke('grpcRealtime:close'),
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
  completeStartup: () => ipcRenderer.invoke('startup:complete'),
  resizeStartupWindow: (view) => ipcRenderer.invoke('startup:resize', view),
  collapseStartupWindow: () => ipcRenderer.invoke('startup:collapse'),
  restoreStartupWindow: () => ipcRenderer.invoke('startup:restore'),
  closeStartupWindow: () => ipcRenderer.invoke('startup:close'),
  openDashboard: () => ipcRenderer.invoke('dashboard:open'),
  getAuthState: () => ipcRenderer.invoke('auth:get-state'),
  startAuthLogin: () => ipcRenderer.invoke('auth:start-login'),
  logoutAuth: () => ipcRenderer.invoke('auth:logout'),
  getCloudStartupContext: () => ipcRenderer.invoke('cloud:get-startup-context'),
  refreshCloudStartupContext: () => ipcRenderer.invoke('cloud:refresh-startup-context'),
  listCloudResumes: () => ipcRenderer.invoke('cloud:list-resumes'),
  createInterviewSession: (payload, options) => ipcRenderer.invoke('cloud:create-interview-session', payload, options),
  listInterviewSessions: (options) => ipcRenderer.invoke('cloud:list-interview-sessions', options),
  endInterviewSession: (sessionId) => ipcRenderer.invoke('cloud:end-interview-session', sessionId),
  listMyAnswers: (sessionId) => ipcRenderer.invoke('cloud:list-my-answers', sessionId),
  saveMyAnswer: (sessionId, body) => ipcRenderer.invoke('cloud:save-my-answer', sessionId, body),
  generateAnswer: (body) => ipcRenderer.invoke('generate:answer', body),
  startAnswerStream: (body) => ipcRenderer.invoke('generate:answer:stream:start', body),
  cancelAnswerStream: (streamId) => ipcRenderer.invoke('generate:answer:stream:cancel', streamId),
  onAnswerStreamEvent: (requestId, fn) => {
    if (typeof requestId !== 'string' || typeof fn !== 'function') throw new Error('Invalid stream subscription.')
    const listener = (_event, payload) => {
      if (payload?.client_request_id === requestId) fn(payload)
    }
    ipcRenderer.on('generate:answer:stream:event', listener)
    return () => ipcRenderer.removeListener('generate:answer:stream:event', listener)
  },
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
  collapseStartupWindow: electronAPI.collapseStartupWindow,
  closeStartupWindow: electronAPI.closeStartupWindow,
  getAuthState: electronAPI.getAuthState,
  getCloudStartupContext: electronAPI.getCloudStartupContext,
  generateAnswer: electronAPI.generateAnswer,
  startAnswerStream: electronAPI.startAnswerStream,
  cancelAnswerStream: electronAPI.cancelAnswerStream,
  onAnswerStreamEvent: electronAPI.onAnswerStreamEvent,
  createInterviewSession: electronAPI.createInterviewSession,
  endInterviewSession: electronAPI.endInterviewSession,
  listInterviewSessions: electronAPI.listInterviewSessions,
  listMyAnswers: electronAPI.listMyAnswers,
  saveMyAnswer: electronAPI.saveMyAnswer,
  listScreenSources: electronAPI.listScreenSources,
  listCloudResumes: electronAPI.listCloudResumes,
  logoutAuth: electronAPI.logoutAuth,
  openDashboard: electronAPI.openDashboard,
  refreshCloudStartupContext: electronAPI.refreshCloudStartupContext,
  restoreStartupWindow: electronAPI.restoreStartupWindow,
  startAuthLogin: electronAPI.startAuthLogin,
})

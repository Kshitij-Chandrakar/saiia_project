// Isolated executable acceptance only. Production main/preload are unchanged.
const { app, safeStorage, shell } = require('electron')
const fs = require('node:fs')
const path = require('node:path')
app.setPath('userData', process.env.C132_ELECTRON_DATA)
app.setName('Intervucopilot isolated acceptance')
if (process.env.C132_HOSTED_ACCEPTANCE === 'true') {
  global.__C132_ISOLATED_HOSTED__ = true
  if (process.env.C132_PHYSICAL_ACCEPTANCE !== 'true') {
    app.commandLine.appendSwitch('use-fake-device-for-media-stream')
    app.commandLine.appendSwitch('use-fake-ui-for-media-stream')
  }
}
// Do not change the user's OS protocol registration or launch an external tab.
app.setAsDefaultProtocolClient = () => true
global.subscriptionOpened = []
// Fault injection is restricted to this synthetic packaged entry point.
global.subscriptionHeartbeatTimers = []
const interval = global.setInterval
global.setInterval = (callback, milliseconds, ...args) => {
  const handle = interval(callback, milliseconds, ...args)
  if (milliseconds === 5000) global.subscriptionHeartbeatTimers.push(handle)
  return handle
}
shell.openExternal = async url => { global.subscriptionOpened.push(url) }
app.on('ready', () => {
  const session = JSON.parse(process.env.C132_ELECTRON_SESSION)
  delete process.env.C132_ELECTRON_SESSION
  fs.mkdirSync(app.getPath('userData'), { recursive: true })
  if (!safeStorage.isEncryptionAvailable()) throw Error('Windows secure storage unavailable')
  fs.writeFileSync(path.join(app.getPath('userData'), 'desktop-auth-session.bin'), safeStorage.encryptString(JSON.stringify(session)))
})
require('../../../electron/main.cjs')

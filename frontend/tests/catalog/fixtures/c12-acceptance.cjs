// Acceptance artifact only: never a production entry point or entitlement bypass.
const { app, safeStorage, globalShortcut, shell, session } = require('electron')
const fs = require('node:fs')
const path = require('node:path')
app.setName('Intervucopilot C12 Acceptance')
app.setAppUserModelId('in.intervucopilot.c12acceptance')
const profileRoot = path.join(process.env.LOCALAPPDATA || app.getPath('appData'), 'Intervucopilot-C12-Acceptance', 'UserData')
const profile = path.resolve(process.env.C12_ACCEPTANCE_USER_DATA || profileRoot)
if (profile !== profileRoot && !profile.startsWith(profileRoot + path.sep)) throw Error('Acceptance profile must stay inside its isolated root')
app.setPath('userData', profile)
// Neither startup nor the acceptance installer may take over normal protocol/shortcuts.
app.setAsDefaultProtocolClient = () => false
globalShortcut.register = () => false
for (const key of ['SUPABASE_URL','VITE_SUPABASE_URL','SAIIA_BACKEND_URL','VITE_BACKEND_URL']) process.env[key] = 'http://127.0.0.1:5296'
for (const key of ['SUPABASE_ANON_KEY','VITE_SUPABASE_ANON_KEY']) process.env[key] = 'synthetic-public-key'
process.env.SAIIA_WEB_AUTH_URL = 'http://127.0.0.1:5297/auth/desktop-login'
process.env.SAIIA_WEB_DASHBOARD_URL = 'http://127.0.0.1:5297/auth/dashboard'
for (const key of ['USE_GRPC_MANUAL_PIPELINE','USE_GRPC_AUTO_PIPELINE','USE_GRPC_CLOUD_CONTEXT_PIPELINE','ELECTRON_GRPC_REALTIME_ENABLED','ELECTRON_GRPC_AUDIO_ENABLED','ELECTRON_HOSTED_AUDIO_ENABLED']) process.env[key] = 'false'
process.env.ELECTRON_GRPC_REALTIME_HOST = '127.0.0.1'
process.env.ELECTRON_GRPC_REALTIME_PORT = '1'
delete process.env.VITE_DEV_SERVER_URL
// Keep an observable record, and actually launch only the configured loopback destination.
global.c12OpenedUrls = []
const open = shell.openExternal.bind(shell)
shell.openExternal = async url => {
  const parsed = new URL(url)
  if (parsed.origin !== 'http://127.0.0.1:5297') throw Error('Acceptance external URL rejected')
  global.c12OpenedUrls.push(url)
  return open(url)
}
app.on('ready', () => {
  session.defaultSession.webRequest.onBeforeRequest((details, callback) => {
    const url = new URL(details.url)
    callback({ cancel: !['file:', 'data:', 'devtools:'].includes(url.protocol) && !['127.0.0.1', 'localhost'].includes(url.hostname) })
  })
  if (!process.env.C12_ACCEPTANCE_SESSION) return
  const record = JSON.parse(process.env.C12_ACCEPTANCE_SESSION)
  delete process.env.C12_ACCEPTANCE_SESSION
  if (!safeStorage.isEncryptionAvailable()) throw Error('Windows secure storage is unavailable')
  fs.mkdirSync(profile, { recursive: true })
  fs.writeFileSync(path.join(profile, 'desktop-auth-session.bin'), safeStorage.encryptString(JSON.stringify(record)))
})
require('../../../electron/main.cjs')

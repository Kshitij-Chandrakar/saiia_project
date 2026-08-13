import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { DESKTOP_AUTH_STATUSES, getDesktopAuthViewModel } from './desktop_auth_ui.js'

const startupSource = readFileSync(new URL('./components/StartupLoginScreen.jsx', import.meta.url), 'utf8')
const diagnosticsSource = readFileSync(new URL('./components/MainDiagnosticsWindow.jsx', import.meta.url), 'utf8')
const cssSource = readFileSync(new URL('./styles/glass.css', import.meta.url), 'utf8')
const mainSource = readFileSync(new URL('../electron/main.cjs', import.meta.url), 'utf8')
const preloadSource = readFileSync(new URL('../electron/preload.cjs', import.meta.url), 'utf8')
const sessionSource = readFileSync(new URL('../electron/desktop_auth_session.cjs', import.meta.url), 'utf8')
const sensitivePattern = new RegExp([
  ['access', 'token'].join('_'),
  ['refresh', 'token'].join('_'),
  ['service', 'role'].join('_'),
  'Author' + 'ization',
].join('|'))

test('startup login screen renders for signed-out and token-expired states', () => {
  const visibleStatuses = new Set([
    DESKTOP_AUTH_STATUSES.SIGNED_OUT,
    DESKTOP_AUTH_STATUSES.TOKEN_EXPIRED,
    DESKTOP_AUTH_STATUSES.SIGNING_IN,
  ])

  assert.equal(visibleStatuses.has(getDesktopAuthViewModel({ status: 'signed-out' }).status), true)
  assert.equal(visibleStatuses.has(getDesktopAuthViewModel({ status: 'token-expired' }).status), true)
  assert.equal(visibleStatuses.has(getDesktopAuthViewModel({ status: 'signing-in' }).status), true)
  assert.equal(visibleStatuses.has(getDesktopAuthViewModel({ status: 'connected' }).status), false)
  assert.match(startupSource, /const LOGIN_VISIBLE_STATUSES = new Set/)
  assert.match(startupSource, /DESKTOP_AUTH_STATUSES\.SIGNED_OUT/)
  assert.match(startupSource, /DESKTOP_AUTH_STATUSES\.TOKEN_EXPIRED/)
  assert.match(startupSource, /if \(!shouldShowStartupLogin\(nextState\)\)/)
})

test('startup login screen uses mascot asset in header and center positions', () => {
  assert.match(startupSource, /import mascotUrl from '\.\.\/assets\/intervu-mascot\.svg'/)
  assert.match(startupSource, /startup-login-brand__mascot-frame/)
  assert.match(startupSource, /startup-login-mascot"/)
  assert.match(cssSource, /\.startup-login-brand__mascot-frame,[\s\S]*?\.startup-login-mascot-frame\s*{[\s\S]*?overflow: hidden;/)
  assert.match(cssSource, /\.startup-login-brand__mascot-frame,[\s\S]*?\.startup-login-brand__mascot\s*{[\s\S]*?width: 37px;[\s\S]*?height: 37px;/)
  assert.match(cssSource, /\.startup-login-mascot-frame\s*{[\s\S]*?width: 96px;[\s\S]*?height: 96px;/)
  assert.match(cssSource, /\.startup-login-mascot\s*{[\s\S]*?width: 96px;[\s\S]*?height: 96px;/)
  assert.match(cssSource, /\.startup-login-brand__mascot\s*{[\s\S]*?transform: scale\(1\.44\);/)
  assert.match(cssSource, /\.startup-login-mascot\s*{[\s\S]*?transform: scale\(1\.52\);/)
})

test('startup login button uses safe preload auth login method and guards duplicate clicks', () => {
  assert.match(startupSource, /saiiaApi\?\.startAuthLogin/)
  assert.match(startupSource, /await saiiaApi\.startAuthLogin\(\)/)
  assert.match(startupSource, /saiiaApi\?\.getCloudStartupContext/)
  assert.match(startupSource, /window\.setInterval/)
  assert.match(startupSource, /if \(loginPending \|\| typeof saiiaApi\?\.startAuthLogin !== 'function'\)/)
  assert.match(startupSource, /disabled={loginPending \|\| authState\.loginDisabled}/)
  assert.doesNotMatch(startupSource, /supabase/i)
  assert.doesNotMatch(startupSource, /fetch\(/)
})

test('startup login reports desktop auth configuration failures safely', () => {
  const configError = 'Desktop cloud auth is not configured. Set SUPABASE_URL or VITE_SUPABASE_URL, SUPABASE_ANON_KEY or VITE_SUPABASE_ANON_KEY, and SAIIA_WEB_AUTH_URL or VITE_SAIIA_WEB_AUTH_URL in the environment that launches Electron.'
  const model = getDesktopAuthViewModel({
    status: DESKTOP_AUTH_STATUSES.SIGNED_OUT,
    error: configError,
    user_id: 'stale-user',
    email: 'stale@example.test',
  })

  assert.equal(model.status, DESKTOP_AUTH_STATUSES.SIGNED_OUT)
  assert.equal(model.detail, configError)
  assert.equal(model.email, null)
  assert.match(startupSource, /const errorDetail = authState\.error \|\| ''/)
  assert.match(startupSource, /const errorText = getStartupErrorMessage\(errorDetail\)/)
  assert.match(startupSource, /return 'Desktop auth is not configured\.'/)
  assert.match(startupSource, /const subtitle = 'Log in to Intervu AI and start your interview\.'/)
})

test('desktop auth config requires Supabase URL, anon key, and website handoff URL in Electron main env', () => {
  assert.match(mainSource, /const DESKTOP_AUTH_ENV_KEYS = new Set\(\[/)
  assert.match(mainSource, /path\.join\(repoRoot, '\.env'\)/)
  assert.match(mainSource, /path\.join\(frontendRoot, '\.env\.local'\)/)
  assert.match(mainSource, /path\.join\(frontendRoot, '\.env'\)/)
  assert.match(mainSource, /Object\.prototype\.hasOwnProperty\.call\(process\.env, key\)/)
  assert.match(mainSource, /if \(!DESKTOP_AUTH_ENV_KEYS\.has\(key\)\) {[\s\S]*?return/)
  assert.doesNotMatch(mainSource, /SUPABASE_SERVICE_ROLE_KEY/)
  assert.doesNotMatch(mainSource, /GOOGLE_CLIENT_SECRET/)
  assert.match(mainSource, /process\.env\.SUPABASE_URL \|\| process\.env\.VITE_SUPABASE_URL/)
  assert.match(mainSource, /process\.env\.SUPABASE_ANON_KEY \|\| process\.env\.VITE_SUPABASE_ANON_KEY/)
  assert.match(mainSource, /process\.env\.SAIIA_WEB_AUTH_URL \|\| process\.env\.VITE_SAIIA_WEB_AUTH_URL/)
  assert.match(sessionSource, /!this\.supabaseUrl \|\| !this\.supabaseAnonKey \|\| !this\.webAuthUrl/)
  assert.match(sessionSource, /MISSING_DESKTOP_AUTH_CONFIG_MESSAGE/)
  assert.match(sessionSource, /environment that launches Electron/)
})

test('startup login gate hides runtime UI before auth completion', () => {
  const gateIndex = diagnosticsSource.indexOf('if (!startupAuthenticated && shouldShowStartupLogin())')
  const runtimeIndex = diagnosticsSource.indexOf('<div className="diagnostics-scroll">')

  assert.ok(gateIndex >= 0)
  assert.ok(runtimeIndex > gateIndex)
  assert.match(diagnosticsSource, /<StartupLoginScreen/)
  assert.match(diagnosticsSource, /onAuthenticated={\(\) => setStartupAuthenticated\(true\)}/)
})

test('startup login completion uses narrow Electron startup hook', () => {
  assert.match(preloadSource, /completeStartup: \(\) => ipcRenderer\.invoke\('startup:complete'\)/)
  assert.match(mainSource, /ipcMain\.handle\('startup:complete'/)
  assert.match(mainSource, /validateAuthIpc\(event\)/)
  assert.match(startupSource, /electronApi\?\.completeStartup\?\.\(\)/)
})

test('main process starts compact and keeps overlay hidden before startup completion', () => {
  const readyStart = mainSource.indexOf("app.on('ready'")
  const readyEnd = mainSource.indexOf("function validateAuthIpc")
  const readyBlock = mainSource.slice(readyStart, readyEnd)

  assert.match(mainSource, /let startupFlowComplete = false/)
  assert.match(mainSource, /let overlayVisible = false/)
  assert.match(mainSource, /width: 426,[\s\S]*?height: 384,[\s\S]*?minWidth: 426,[\s\S]*?minHeight: 384,/)
  assert.match(mainSource, /show: false,/)
  assert.doesNotMatch(readyBlock, /buildApplicationMenu\(\)[\s\S]*?createMainWindow\(\)[\s\S]*?createOverlayWindow\(\)[\s\S]*?startForegroundWindowTracking\(\)/)
  assert.match(readyBlock, /if \(startupFlowComplete && overlayWindow === null\) {[\s\S]*?createOverlayWindow\(\)/)
  assert.match(mainSource, /function createOverlayWindow\(\) {[\s\S]*?if \(!startupFlowComplete\) {[\s\S]*?return null/)
  assert.match(mainSource, /const hideOk = globalShortcut\.register\('Control\+H', \(\) => {[\s\S]*?if \(!startupFlowComplete\) {[\s\S]*?return/)
  assert.match(mainSource, /ipcMain\.handle\('overlay:toggle-visibility', \(\) => {[\s\S]*?if \(!startupFlowComplete\) {[\s\S]*?return { visible: false }/)
  assert.match(mainSource, /function completeStartupFlow\(\)[\s\S]*?mainWindow\.setSize\(620, 860\)[\s\S]*?syncOverlayVisibility\(true\)/)
})

test('main process logout resets startup flow and hides overlay before login', () => {
  assert.match(mainSource, /function resetStartupFlow\(\)[\s\S]*?startupFlowComplete = false[\s\S]*?syncOverlayVisibility\(false\)/)
  assert.match(mainSource, /function resetStartupFlow\(\)[\s\S]*?mainWindow\.setMinimumSize\(426, 384\)[\s\S]*?mainWindow\.setSize\(426, 384\)[\s\S]*?mainWindow\.show\(\)/)
  assert.match(mainSource, /ipcMain\.handle\('auth:logout', async \(event\) => {[\s\S]*?const state = await desktopAuthSessionManager\.logout\(\)[\s\S]*?if \(state\.status === 'signed-out' \|\| state\.status === 'token-expired'\) {[\s\S]*?resetStartupFlow\(\)/)
  assert.match(mainSource, /const hideOk = globalShortcut\.register\('Control\+H', \(\) => {[\s\S]*?if \(!startupFlowComplete\) {[\s\S]*?return[\s\S]*?toggleOverlayVisibility\(\)/)
})

test('startup login close button uses narrow validated Electron startup hook', () => {
  assert.match(startupSource, /aria-label="Close startup login"/)
  assert.match(startupSource, /const closeWindow = saiiaApi\?\.closeStartupWindow \|\| electronApi\?\.closeStartupWindow/)
  assert.match(startupSource, /closeWindow\?\.\(\)\.catch\?\.\(\(\) => {}\)/)
  assert.match(startupSource, /onClick={closeStartupWindow}/)
  assert.match(preloadSource, /closeStartupWindow: \(\) => ipcRenderer\.invoke\('startup:close'\)/)
  assert.match(preloadSource, /closeStartupWindow: electronAPI\.closeStartupWindow/)
  assert.match(mainSource, /ipcMain\.handle\('startup:close'/)
  assert.match(mainSource, /function closeStartupWindow\(\)[\s\S]*?if \(!startupFlowComplete\) {[\s\S]*?globalShortcut\.unregisterAll\(\)[\s\S]*?app\.quit\(\)/)
  assert.match(mainSource, /ipcMain\.handle\('startup:close', \(event\) => {[\s\S]*?validateAuthIpc\(event\)/)
})

test('startup login source and styles do not expose token or session values', () => {
  assert.doesNotMatch(startupSource, sensitivePattern)
  assert.doesNotMatch(cssSource, sensitivePattern)
  assert.doesNotMatch(startupSource, /SUPABASE_URL|SUPABASE_ANON_KEY|SAIIA_WEB_AUTH_URL|SAIIA_DESKTOP_AUTH_PROVIDER|GOOGLE_CLIENT_SECRET/)
})

test('startup login CSS keeps Figma dimensions and visual values', () => {
  assert.match(cssSource, /\.startup-login-card\s*{[\s\S]*?width: 426px;[\s\S]*?height: 384px;/)
  assert.match(cssSource, /\.startup-login-window\s*{[\s\S]*?width: 426px;[\s\S]*?height: 384px;[\s\S]*?overflow: hidden;/)
  assert.match(cssSource, /\.startup-login-window\s*{[\s\S]*?box-sizing: border-box;/)
  assert.match(cssSource, /\.startup-login-card\s*{[\s\S]*?box-sizing: border-box;/)
  assert.match(cssSource, /\.startup-login-header\s*{[\s\S]*?box-sizing: border-box;[\s\S]*?height: 45px;[\s\S]*?border-bottom: 1px solid #d9d9d9;/)
  assert.match(cssSource, /\.startup-login-card\s*{[\s\S]*?gap: 34px;/)
  assert.match(cssSource, /\.startup-login-main\s*{[\s\S]*?width: 301px;[\s\S]*?height: 305px;[\s\S]*?gap: 15px;/)
  assert.match(cssSource, /\.startup-login-features\s*{[\s\S]*?width: 210px;[\s\S]*?height: 83px;[\s\S]*?gap: 7px;/)
  assert.match(cssSource, /font-family: Inter/)
  assert.match(cssSource, /#6d5de7/i)
  assert.match(cssSource, /#6e6f6f/i)
  assert.match(cssSource, /#3f3f46/i)
  assert.match(cssSource, /#d9d9d9/i)
  assert.match(cssSource, /border-radius: 18px;/)
  assert.match(cssSource, /box-shadow: 0 4px 15px rgba\(91, 77, 212, 0\.25\);/)
})

test('startup login keeps long configuration errors in a bounded message area', () => {
  assert.match(startupSource, /const errorDetail = authState\.error \|\| ''/)
  assert.match(startupSource, /const errorText = getStartupErrorMessage\(errorDetail\)/)
  assert.match(startupSource, /className={`startup-login-main\$\{errorText \? ' startup-login-main--error' : ''\}`}/)
  assert.match(startupSource, /<p className="startup-login-error" aria-live="polite" title={errorDetail}>/)
  assert.match(startupSource, /return 'Desktop auth is not configured\.'/)
  assert.match(cssSource, /\.startup-login-error\s*{[\s\S]*?position: absolute;[\s\S]*?top: 160px;[\s\S]*?height: 14px;[\s\S]*?overflow: hidden;[\s\S]*?font-size: 10px;/)
  assert.doesNotMatch(cssSource, /\.startup-login-main--error \.startup-login-features\s*{[\s\S]*?height: 54px;/)
})

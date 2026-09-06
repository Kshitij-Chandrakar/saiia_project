import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import {
  DESKTOP_AUTH_ERROR_CODES,
  DESKTOP_AUTH_STATUSES,
  getDesktopAuthViewModel,
  getDesktopStartupErrorView,
} from './desktop_auth_ui.js'

const startupSource = readFileSync(new URL('./components/StartupLoginScreen.jsx', import.meta.url), 'utf8')
const startupChoiceSource = readFileSync(new URL('./components/StartupSessionChoiceScreen.jsx', import.meta.url), 'utf8')
const startupSetupSource = readFileSync(new URL('./components/StartupSessionSetupScreen.jsx', import.meta.url), 'utf8')
const diagnosticsSource = readFileSync(new URL('./components/MainDiagnosticsWindow.jsx', import.meta.url), 'utf8')
const appSource = readFileSync(new URL('./App.jsx', import.meta.url), 'utf8')
const cssSource = readFileSync(new URL('./styles/glass.css', import.meta.url), 'utf8')
const mainSource = readFileSync(new URL('../electron/main.cjs', import.meta.url), 'utf8')
const preloadSource = readFileSync(new URL('../electron/preload.cjs', import.meta.url), 'utf8')
const sessionSource = readFileSync(new URL('../electron/desktop_auth_session.cjs', import.meta.url), 'utf8')
const figmaLoginCssSource = cssSource.slice(cssSource.indexOf('/* Figma Login - Version B'))
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

test('startup login screen uses the exported Figma assets in header and center positions', () => {
  assert.match(startupSource, /import loginMascotUrl from '\.\.\/assets\/startup-login\/login-mascot\.png'/)
  assert.match(startupSource, /import loginLogoUrl from '\.\.\/assets\/startup-login\/login-logo\.svg'/)
  assert.match(startupSource, /import loginArrowUrl from '\.\.\/assets\/startup-login\/login-arrow\.svg'/)
  assert.match(startupSource, /import loginOpenBrowserUrl from '\.\.\/assets\/startup-login\/login-open-browser\.svg'/)
  assert.match(startupSource, /import loginSecurityUrl from '\.\.\/assets\/startup-login\/login-security\.svg'/)
  assert.match(startupSource, /import loginCloseUrl from '\.\.\/assets\/startup-login\/login-close\.svg'/)
  assert.match(startupSource, /import loginBackgroundEllipseLeftUrl from '\.\.\/assets\/startup-login\/login-bg-ellipse-left\.svg'/)
  assert.match(startupSource, /import loginBackgroundEllipseRightUrl from '\.\.\/assets\/startup-login\/login-bg-ellipse-right\.svg'/)
  assert.match(startupSource, /import loginBackgroundGroupLeftUrl from '\.\.\/assets\/startup-login\/login-bg-group-left\.svg'/)
  assert.match(startupSource, /import loginBackgroundGroupRightUrl from '\.\.\/assets\/startup-login\/login-bg-group-right\.svg'/)
  assert.match(startupSource, /startup-login-brand__logo/)
  assert.match(startupSource, /startup-login-mascot"/)
  assert.match(figmaLoginCssSource, /\.startup-login-brand__logo\s*{[\s\S]*?width: 24px;[\s\S]*?height: 24px;/)
  assert.match(figmaLoginCssSource, /\.startup-login-mascot-frame\s*{[\s\S]*?width: 185px;[\s\S]*?height: 124px;/)
  assert.match(figmaLoginCssSource, /\.startup-login-mascot\s*{[\s\S]*?width: 185px;[\s\S]*?height: 124px;/)
  assert.match(startupSource, /Welcome to Intervu AI/)
  assert.match(startupSource, /Login with Intervu AI/)
  assert.match(startupSource, /Authentication is securely completed in your browser\./)
  assert.doesNotMatch(startupSource, /<svg|<path/)
})

test('startup login shows the Figma opening-browser state while auth is pending', () => {
  assert.match(startupSource, /const isOpeningBrowser = !startupPollFailed && \(loginPending \|\| authState\.status === DESKTOP_AUTH_STATUSES\.SIGNING_IN\)/)
  assert.match(startupSource, /isOpeningBrowser \? \(/)
  assert.match(startupSource, /Opening Your Browser/)
  assert.match(startupSource, /We’re securely connecting you to Intervu AI Sign In\./)
  assert.match(startupSource, /Your browser will open automatically\./)
  assert.match(startupSource, /className="startup-login-opening-loading" aria-hidden="true"/)
  assert.match(startupSource, /className="startup-login-opening-dots"/)
  assert.match(startupSource, /className="startup-login-opening-announcement" role="status" aria-live="polite"/)
  assert.match(figmaLoginCssSource, /\.startup-login-opening-mascot\s*\{[\s\S]*?width: 234px;[\s\S]*?height: 156px;/)
  assert.match(figmaLoginCssSource, /\.startup-login-opening-dots\s*\{[\s\S]*?gap: 8px;[\s\S]*?width: 52px;[\s\S]*?height: 12px;/)
  assert.match(figmaLoginCssSource, /\.startup-login-opening-dot\s*\{[\s\S]*?background: #9dbde2;[\s\S]*?animation: startup-login-opening-dot-bounce 1\.2s/)
  assert.match(figmaLoginCssSource, /@keyframes startup-login-opening-dot-bounce[\s\S]*?transform: translateY\(-4px\)/)
  assert.match(figmaLoginCssSource, /@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.startup-login-opening-dot\s*\{[\s\S]*?animation: none;/)
})

test('startup login exposes recoverable poll failures without overwriting newer auth attempts', () => {
  assert.match(startupSource, /const \[startupPollFailed, setStartupPollFailed\] = useState\(false\)/)
  assert.match(startupSource, /const loadStartupContext = saiiaApi\?\.getCloudStartupContext \|\| saiiaApi\?\.getAuthState/)
  assert.match(startupSource, /if \(active && requestId === requestIdRef\.current\) \{\s*setStartupPollFailed\(true\)/)
  assert.match(startupSource, /if \(\(loginPending && !startupPollFailed\) \|\| typeof saiiaApi\?\.startAuthLogin !== 'function'\)/)
  assert.match(startupSource, /disabled=\{!startupPollFailed && \(loginPending \|\| authState\.loginDisabled\)\}/)
  assert.match(startupSource, /setStartupPollFailed\(false\)\s*\n\s*setAuthState\(getDesktopAuthViewModel\(\{ status: DESKTOP_AUTH_STATUSES\.SIGNING_IN \}\)\)/)
  assert.match(startupSource, /let active = true[\s\S]*?if \(active\) \{\s*applyAuthState\(state, requestId\)/)
  assert.match(startupSource, /active = false[\s\S]*?window\.clearInterval\(pollId\)/)
})

test('startup login button uses safe preload auth login method and guards duplicate clicks', () => {
  assert.match(startupSource, /saiiaApi\?\.startAuthLogin/)
  assert.match(startupSource, /await saiiaApi\.startAuthLogin\(\)/)
  assert.match(startupSource, /saiiaApi\?\.getCloudStartupContext/)
  assert.match(startupSource, /window\.setInterval/)
  assert.match(startupSource, /if \(\(loginPending && !startupPollFailed\) \|\| typeof saiiaApi\?\.startAuthLogin !== 'function'\)/)
  assert.match(startupSource, /disabled=\{!startupPollFailed && \(loginPending \|\| authState\.loginDisabled\)\}/)
  assert.doesNotMatch(startupSource, /completeStartup\?\.\(\)/)
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
  assert.equal(getDesktopStartupErrorView(model).message, 'Desktop auth is not configured.')
  assert.match(startupSource, /const errorView = startupPollFailed[\s\S]*?getDesktopStartupErrorView\(authState\)/)
  assert.match(startupSource, /const subtitle = 'Sign in to continue to your Intervu AI workspace\.'/)
})

test('startup login maps safe auth failures to actionable copy', () => {
  const cases = [
    [
      { status: DESKTOP_AUTH_STATUSES.TOKEN_EXPIRED },
      'Your session has expired. Please sign in again to continue.',
      'Sign in again',
    ],
    [
      { status: DESKTOP_AUTH_STATUSES.SIGNED_OUT, error_code: DESKTOP_AUTH_ERROR_CODES.LOGIN_TIMEOUT },
      'Sign-in timed out. Please try signing in again.',
      'Try again',
    ],
    [
      { status: DESKTOP_AUTH_STATUSES.SIGNED_OUT, error_code: DESKTOP_AUTH_ERROR_CODES.BROWSER_LAUNCH_FAILED },
      'We couldn\'t open your browser. Please try again.',
      'Try again',
    ],
    [
      { status: DESKTOP_AUTH_STATUSES.BACKEND_UNAVAILABLE },
      'We couldn\'t connect to the sign-in service. Please check your connection and try again.',
      'Try again',
    ],
  ]

  for (const [state, message, actionLabel] of cases) {
    assert.deepEqual(getDesktopStartupErrorView(state), { message, actionLabel })
  }
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
  assert.doesNotMatch(mainSource, /SAIIA_DESKTOP_AUTH_PROVIDER|VITE_SUPABASE_DESKTOP_AUTH_PROVIDER/)
  assert.match(sessionSource, /!this\.supabaseUrl \|\| !this\.supabaseAnonKey \|\| !this\.webAuthUrl/)
  assert.match(sessionSource, /\['http:', 'https:'\]\.includes\(authUrl\.protocol\)/)
  assert.match(sessionSource, /MISSING_DESKTOP_AUTH_CONFIG_MESSAGE/)
  assert.match(sessionSource, /environment that launches Electron/)
})

test('startup login gate hides runtime UI before auth and session choice completion', () => {
  const gateIndex = diagnosticsSource.indexOf('if (!startupAuthenticated && shouldShowStartupLogin())')
  const choiceIndex = diagnosticsSource.indexOf("if (startupAuthenticated && startupScreen === 'session-choice')")
  const setupIndex = diagnosticsSource.indexOf("if (startupAuthenticated && startupScreen === 'session-setup')")
  const runtimeIndex = diagnosticsSource.indexOf('<div className="diagnostics-scroll">')

  assert.ok(gateIndex >= 0)
  assert.ok(choiceIndex > gateIndex)
  assert.ok(setupIndex > choiceIndex)
  assert.ok(runtimeIndex > setupIndex)
  assert.match(diagnosticsSource, /<StartupLoginScreen/)
  assert.match(diagnosticsSource, /<StartupSessionChoiceScreen/)
  assert.match(diagnosticsSource, /<StartupSessionSetupScreen/)
  assert.match(diagnosticsSource, /const \[startupScreen, setStartupScreen\] = useState\('login'\)/)
  assert.match(diagnosticsSource, /const \[startupSessionConfig, setStartupSessionConfig\] = useState\(null\)/)
  assert.match(diagnosticsSource, /setStartupScreen\('session-choice'\)/)
  assert.match(
    diagnosticsSource,
    /onCreateSession={\(\) => {[\s\S]*?setStartupSessionConfig\(null\)[\s\S]*?onStartupSessionConfigChange\?\.\(null\)[\s\S]*?setStartupScreen\('session-setup'\)[\s\S]*?}}/
  )
})

test('startup session setup completion uses narrow Electron startup hook', () => {
  assert.match(preloadSource, /completeStartup: \(\) => ipcRenderer\.invoke\('startup:complete'\)/)
  assert.match(preloadSource, /listCloudResumes: \(\) => ipcRenderer\.invoke\('cloud:list-resumes'\)/)
  assert.match(preloadSource, /createInterviewSession: \(payload, options\) => ipcRenderer\.invoke\('cloud:create-interview-session', payload, options\)/)
  assert.match(preloadSource, /listInterviewSessions: \(options\) => ipcRenderer\.invoke\('cloud:list-interview-sessions', options\)/)
  assert.match(preloadSource, /endInterviewSession: \(sessionId\) => ipcRenderer\.invoke\('cloud:end-interview-session', sessionId\)/)
  assert.match(preloadSource, /generateAnswer: \(body\) => ipcRenderer\.invoke\('generate:answer', body\)/)
  assert.match(preloadSource, /listCloudResumes: electronAPI\.listCloudResumes/)
  assert.match(preloadSource, /createInterviewSession: electronAPI\.createInterviewSession/)
  assert.match(preloadSource, /listInterviewSessions: electronAPI\.listInterviewSessions/)
  assert.match(preloadSource, /endInterviewSession: electronAPI\.endInterviewSession/)
  assert.match(preloadSource, /generateAnswer: electronAPI\.generateAnswer/)
  assert.match(mainSource, /ipcMain\.handle\('startup:complete'/)
  assert.match(mainSource, /ipcMain\.handle\('cloud:list-resumes', async \(event\) => {[\s\S]*?validateAuthIpc\(event\)[\s\S]*?desktopAuthSessionManager\.listCloudResumes\(\)/)
  assert.match(mainSource, /ipcMain\.handle\('cloud:create-interview-session', async \(event, payload, options\) => {[\s\S]*?desktopAuthSessionManager\.createInterviewSession\(payload, options\)/)
  assert.match(mainSource, /ipcMain\.handle\('cloud:list-interview-sessions', async \(event, options\) => {[\s\S]*?desktopAuthSessionManager\.listInterviewSessions\(options\)/)
  assert.match(mainSource, /ipcMain\.handle\('cloud:end-interview-session', async \(event, sessionId\) => {[\s\S]*?desktopAuthSessionManager\.endInterviewSession\(sessionId\)/)
  assert.match(mainSource, /ipcMain\.handle\('generate:answer', async \(event, body\) => {[\s\S]*?validateAuthIpc\(event\)[\s\S]*?desktopAuthSessionManager\.generateAnswer\(body\)/)
  assert.match(mainSource, /validateAuthIpc\(event\)/)
  assert.match(mainSource, /desktopAuthSessionManager\.getSafeState\(\)\.status !== 'connected'/)
  assert.match(sessionSource, /async listCloudResumes\(\)/)
  assert.match(sessionSource, /async createInterviewSession\(payload, options = \{\}\)/)
  assert.match(sessionSource, /async listInterviewSessions\(options = \{\}\)/)
  assert.match(sessionSource, /async endInterviewSession\(sessionId\)/)
  assert.match(sessionSource, /this\.activeInterviewSession = sessionRecord/)
  assert.match(sessionSource, /await this\.endActiveInterviewSession\(\)/)
  assert.match(sessionSource, /this\._backendJson\('\/api\/resumes', 'GET', this\.session\.access_token\)/)
  assert.match(sessionSource, /function safeCloudResumeItem/)
  assert.match(sessionSource, /function safeInterviewSessionItem/)
  assert.doesNotMatch(startupChoiceSource, /completeStartup/)
  assert.match(startupSetupSource, /saiiaApi\?\.createInterviewSession/)
  assert.match(startupSetupSource, /await saiiaApi\.createInterviewSession\(/)
  assert.match(startupSetupSource, /activeSessionId: session\.id/)
  assert.match(startupSetupSource, /electronApi\?\.completeStartup\?\.\(\)/)
  assert.match(startupSetupSource, /const result = await electronApi\?\.completeStartup\?\.\(\)/)
  assert.match(startupSetupSource, /if \(result\?\.ok !== true\) {[\s\S]*?setMessage/)
  assert.match(startupSetupSource, /onStartSession\?\.\(\{/)
})

test('main process starts compact and keeps overlay hidden before startup completion', () => {
  const readyStart = mainSource.indexOf("app.on('ready'")
  const readyEnd = mainSource.indexOf("function validateAuthIpc")
  const readyBlock = mainSource.slice(readyStart, readyEnd)

  assert.match(mainSource, /let startupFlowComplete = false/)
  assert.match(mainSource, /let overlayVisible = false/)
  assert.match(mainSource, /width: 504,[\s\S]*?height: 462,[\s\S]*?minWidth: 426,[\s\S]*?minHeight: 384,/)
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
  assert.match(mainSource, /function resetStartupFlow\(\)[\s\S]*?mainWindow\.setMinimumSize\(426, 384\)[\s\S]*?mainWindow\.setSize\(504, 462\)[\s\S]*?mainWindow\.show\(\)/)
  assert.match(mainSource, /ipcMain\.handle\('auth:logout', async \(event\) => {[\s\S]*?const state = await desktopAuthSessionManager\.logout\(\)[\s\S]*?if \(state\.status === 'signed-out' \|\| state\.status === 'token-expired'\) {[\s\S]*?resetStartupFlow\(\)/)
  assert.match(mainSource, /async function finalizeActiveInterviewSession\(reason = 'ended'\)/)
  assert.match(mainSource, /await finalizeActiveInterviewSession\('ended'\)/)
  assert.match(mainSource, /app\.on\('before-quit', \(event\) => {[\s\S]*?desktopAuthSessionManager\?\.hasActiveInterviewSession/)
  assert.match(mainSource, /const hideOk = globalShortcut\.register\('Control\+H', \(\) => {[\s\S]*?if \(!startupFlowComplete\) {[\s\S]*?return[\s\S]*?toggleOverlayVisibility\(\)/)
  assert.match(diagnosticsSource, /setStartupAuthenticated\(false\)[\s\S]*?setStartupScreen\('login'\)[\s\S]*?setStartupSessionConfig\(null\)/)
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
  assert.doesNotMatch(startupChoiceSource, sensitivePattern)
  assert.doesNotMatch(startupSetupSource, sensitivePattern)
  assert.doesNotMatch(cssSource, sensitivePattern)
  assert.doesNotMatch(startupSource, /SUPABASE_URL|SUPABASE_ANON_KEY|SAIIA_WEB_AUTH_URL|SAIIA_DESKTOP_AUTH_PROVIDER|GOOGLE_CLIENT_SECRET/)
})

test('startup login CSS keeps Figma dimensions and visual values', () => {
  assert.match(figmaLoginCssSource, /\.startup-login-card\s*{[\s\S]*?width: 430px;[\s\S]*?height: 460px;/)
  assert.match(figmaLoginCssSource, /\.startup-login-window\s*{[\s\S]*?align-items: center;[\s\S]*?justify-content: center;/)
  assert.match(figmaLoginCssSource, /\.startup-login-window\s*{[\s\S]*?box-sizing: border-box;/)
  assert.match(figmaLoginCssSource, /\.startup-login-card\s*{[\s\S]*?box-sizing: border-box;/)
  assert.match(figmaLoginCssSource, /\.startup-login-header\s*{[\s\S]*?width: 430px;[\s\S]*?height: 52px;[\s\S]*?border-bottom: 1px solid rgba\(197, 198, 205, 0\.2\);/)
  assert.match(figmaLoginCssSource, /\.startup-login-header\s*{[\s\S]*?z-index: 2;/)
  assert.match(figmaLoginCssSource, /\.startup-login-main\s*{[\s\S]*?z-index: 1;/)
  assert.match(figmaLoginCssSource, /\.startup-login-main\s*{[\s\S]*?width: 430px;[\s\S]*?height: 460px;/)
  assert.match(figmaLoginCssSource, /\.startup-login-button\s*{[\s\S]*?width: 320px;[\s\S]*?height: 54px;[\s\S]*?background: #0058be;/)
  assert.match(figmaLoginCssSource, /\.startup-login-button:hover\s*{[\s\S]*?background: #004a9f;[\s\S]*?color: #ffffff;/)
  assert.match(figmaLoginCssSource, /\.startup-login-button:active\s*{[\s\S]*?background: #003f88;[\s\S]*?transform: none;/)
  assert.match(figmaLoginCssSource, /\.startup-login-button:disabled,[\s\S]*?\.startup-login-button:disabled:hover\s*{[\s\S]*?background: #6b9ad0;[\s\S]*?color: #ffffff;[\s\S]*?opacity: 0\.78;/)
  assert.match(figmaLoginCssSource, /\.startup-login-decoration--group-left\s*{[\s\S]*?left: -125px;[\s\S]*?top: 152px;/)
  assert.match(figmaLoginCssSource, /\.startup-login-button:focus-visible,[\s\S]*?\.startup-login-close:focus-visible/)
  assert.match(figmaLoginCssSource, /font-family: Inter/)
  assert.match(figmaLoginCssSource, /#0058be/i)
  assert.match(figmaLoginCssSource, /#667085/i)
  assert.match(figmaLoginCssSource, /#091426/i)
  assert.match(figmaLoginCssSource, /\.startup-login-close img\s*{[\s\S]*?width: 10\.5px;[\s\S]*?height: 10\.5px;/)
})

test('startup session choice screen matches Figma shell and safe placeholder behavior', () => {
  assert.match(startupChoiceSource, /Start a New Session/)
  assert.match(startupChoiceSource, /Choose how you'd like to continue\./)
  assert.match(startupChoiceSource, /Free Session/)
  assert.match(startupChoiceSource, /10 minutes available/)
  assert.match(startupChoiceSource, /Create New Session/)
  assert.match(startupChoiceSource, /Buy Credits/)
  assert.match(startupChoiceSource, /Past sessions will be available in a later phase\./)
  assert.match(startupChoiceSource, /aria-label="Intervu AI startup session choices"/)
  assert.match(startupChoiceSource, /aria-label="10 of 10 minutes remaining"/)
  assert.match(cssSource, /\.startup-choice-card\s*{[\s\S]*?width: 504px;[\s\S]*?height: 462px;/)
  assert.match(cssSource, /\.startup-choice-header\s*{[\s\S]*?height: 65px;/)
  assert.match(cssSource, /\.startup-choice-tabs\s*{[\s\S]*?width: 456px;[\s\S]*?height: 50px;/)
  assert.match(cssSource, /\.startup-choice-option\s*{[\s\S]*?height: 140px;[\s\S]*?border-radius: 16px;/)
  assert.match(cssSource, /\.startup-choice-footer\s*{[\s\S]*?width: 456px;[\s\S]*?height: 46px;/)
})

test('startup session setup screen collects local setup and routes back or into runtime', () => {
  assert.match(startupSetupSource, /const EMPTY_SETUP = {[\s\S]*?title: ''[\s\S]*?role: ''[\s\S]*?company: ''[\s\S]*?jobContext: ''[\s\S]*?selectedResumeId: ''[\s\S]*?selectedResumeName: ''/)
  assert.match(startupSetupSource, /Session title/)
  assert.match(startupSetupSource, /Target role/)
  assert.match(startupSetupSource, /Company name/)
  assert.match(startupSetupSource, /Job description \/ context/)
  assert.match(startupSetupSource, /Resume \/ reference document/)
  assert.match(startupSetupSource, /saiiaApi\.listCloudResumes/)
  assert.match(startupSetupSource, /Loading resumes\.\.\./)
  assert.match(startupSetupSource, /No uploaded resumes found\. Upload a resume from the web dashboard first\./)
  assert.match(startupSetupSource, /Open dashboard to upload resume/)
  assert.match(startupSetupSource, /const READINESS_LABELS = {[\s\S]*?ready: 'Ready'[\s\S]*?processing: 'Processing'[\s\S]*?not_indexed: 'Needs indexing'[\s\S]*?needs_confirmation: 'Needs confirmation'[\s\S]*?failed: 'Failed'/)
  assert.match(startupSetupSource, /getResumeReadinessLabel\(resume\)/)
  assert.match(startupSetupSource, /value={draft\.selectedResumeId}/)
  assert.match(startupSetupSource, /selectedResumeName: selected\?\.display_name \|\| ''/)
  assert.match(startupSetupSource, /const \[resumeLoadError, setResumeLoadError\] = useState\(''\)/)
  assert.match(startupSetupSource, /const cloudSessionStorageUnavailable = resumeLoadError === 'Cloud temporarily unavailable\.'/)
  assert.match(startupSetupSource, /const selectedResumeMissing = Boolean\(draft\.selectedResumeId && !selectedResume\)/)
  assert.match(startupSetupSource, /const selectedResumeBlocked = Boolean\(\s*draft\.selectedResumeId && \(resumesLoading \|\| selectedResumeMissing \|\| selectedResume\.can_generate !== true\)\s*\)/)
  assert.match(startupSetupSource, /const startBlockedByResumeLoad = resumesLoading \|\| Boolean\(resumeLoadError\)/)
  assert.match(startupSetupSource, /const startDisabled = Boolean\(\s*starting \|\|[\s\S]*startBlockedByResumeLoad[\s\S]*selectedResumeBlocked\s*\)/)
  assert.match(startupSetupSource, /Cloud session storage is temporarily unavailable\. Please restart the backend and try again\./)
  assert.match(startupSetupSource, /Loading the latest resume readiness before starting your session\./)
  assert.match(startupSetupSource, /The selected resume could not be found\. Refresh your resume list and choose a ready resume again\./)
  assert.match(startupSetupSource, /Finish extraction\/indexing from the dashboard, then refresh\./)
  assert.match(startupSetupSource, /Open dashboard to finish resume setup/)
  assert.match(startupSetupSource, /if \(startDisabled\) {[\s\S]*cloudSessionStorageUnavailable[\s\S]*Please restart the backend and try again\./)
  assert.match(startupSetupSource, /disabled={startDisabled}/)
  assert.match(startupSetupSource, /const startIdempotencyKeyRef = useRef\(''\)/)
  assert.match(startupSetupSource, /desktop-session:/)
  assert.match(startupSetupSource, /catch \{[\s\S]*Cloud session storage is temporarily unavailable\. Please restart the backend and try again\./)
  assert.match(startupSetupSource, /await saiiaApi\.endInterviewSession\?\.\(session\.id\)\.catch\?\.\(\(\) => \{\}\)/)
  assert.match(startupSetupSource, /console\.info\('Intervu AI active interview session'/)
  assert.match(startupSetupSource, /onBack/)
  assert.match(startupSetupSource, /Start Session/)
  assert.match(startupSetupSource, /activeSessionId: session\.id/)
  assert.match(startupSetupSource, /sessionTitle: draft\.title/)
  assert.match(startupSetupSource, /targetRole: draft\.role/)
  assert.match(startupSetupSource, /companyName: draft\.company/)
  assert.match(startupSetupSource, /jobDescription: draft\.jobContext/)
  assert.match(diagnosticsSource, /onBack={\(\) => setStartupScreen\('session-choice'\)}/)
  assert.match(diagnosticsSource, /setStartupSessionConfig\(nextConfig\)[\s\S]*?setStartupScreen\('runtime'\)/)
  assert.match(diagnosticsSource, /onStartupSessionConfigChange\?\.\(nextConfig\)/)
  assert.match(diagnosticsSource, /onStartupSessionConfigChange\?\.\(null\)/)
  assert.match(appSource, /const \[startupSessionConfig, setStartupSessionConfig\] = useState\(null\)/)
  assert.match(appSource, /const startupSessionConfigRef = useRef\(null\)/)
  assert.match(appSource, /const applyStartupSessionConfig = \(nextConfig\) => {[\s\S]*?startupSessionConfigRef\.current = nextConfig[\s\S]*?setStartupSessionConfig\(nextConfig\)[\s\S]*?}/)
  assert.match(appSource, /onStartupSessionConfigChange={applyStartupSessionConfig}/)
  assert.match(appSource, /const activeStartupSessionConfig = startupSessionConfigRef\.current/)
  assert.match(appSource, /const activeSessionId = String\(activeStartupSessionConfig\?\.activeSessionId \|\| ''\)\.trim\(\)/)
  assert.match(appSource, /const requestId = Date\.now\(\) \+ Math\.random\(\)/)
  assert.match(appSource, /function getSafeGenerationSource\(mode, source\)/)
  assert.match(appSource, /if \(normalizedSource === 'chat'\)/)
  assert.match(appSource, /if \(normalizedSource === 'answer'\)/)
  assert.match(appSource, /if \(normalizedSource === 'analyze_screen' \|\| normalizedSource === 'screen'\)/)
  assert.match(appSource, /if \(normalizedMode === 'manual'\) \{\s+return 'answer'/)
  assert.match(appSource, /const requestSource = getSafeGenerationSource\(mode, source\)/)
  assert.match(appSource, /request_id: String\(requestId\)/)
  assert.match(appSource, /source: requestSource/)
  assert.match(appSource, /session_id: activeSessionId \|\| undefined/)
  assert.match(appSource, /const selectedResumeId = String\(activeStartupSessionConfig\?\.selectedResumeId \|\| ''\)\.trim\(\)/)
  assert.match(appSource, /const selectedResumeName = String\(activeStartupSessionConfig\?\.selectedResumeName \|\| ''\)\.trim\(\)/)
  assert.match(appSource, /activeStartupSessionConfig\?\.targetRole \|\| activeStartupSessionConfig\?\.role/)
  assert.match(appSource, /activeStartupSessionConfig\?\.companyName \|\| activeStartupSessionConfig\?\.company/)
  assert.match(appSource, /activeStartupSessionConfig\?\.jobDescription \|\| activeStartupSessionConfig\?\.jobContext/)
  assert.match(appSource, /profile: selectedResumeId \? \{\} : liveProfile/)
  assert.match(appSource, /selected_resume_id: selectedResumeId \|\| undefined/)
  assert.match(appSource, /target_role: targetRole \|\| undefined/)
  assert.match(appSource, /company_name: companyName \|\| undefined/)
  assert.match(appSource, /job_description: jobDescription \|\| undefined/)
  assert.match(appSource, /window\.saiia\?\.generateAnswer/)
  assert.match(appSource, /Intervu AI selected resume generation diagnostics/)
  assert.match(appSource, /activeSessionIdExists: Boolean\(activeSessionId\)/)
  assert.match(appSource, /generationRequestIncludesSessionId: Boolean\(generateRequestBody\.session_id\)/)
  assert.match(appSource, /generationRequestIncludesSelectedResumeId: Boolean\(generateRequestBody\.selected_resume_id\)/)
  const selectedResumeDiagnosticsBlock =
    appSource.match(/const selectedResumeDiagnostics = \{[\s\S]*?\n    \}/)?.[0] || ''
  assert.ok(selectedResumeDiagnosticsBlock, 'selectedResumeDiagnostics block should exist')
  assert.doesNotMatch(selectedResumeDiagnosticsBlock, /selectedResumeName/)
  assert.match(appSource, /Selected resume is not ready for generation\. Please finish resume setup or rebuild the index from the dashboard\./)
  assert.match(appSource, /Selected resume is not ready or does not contain enough project context for this answer\./)
  assert.match(appSource, /resume_context_source: generatePayload\.resume_context_source \|\| 'none'/)
  assert.match(appSource, /selected_resume_id_used: generatePayload\.selected_resume_id_used \?\? false/)
  assert.match(appSource, /selected_resume_chunk_count: generatePayload\.selected_resume_chunk_count \?\? 0/)
  assert.match(appSource, /selected_resume_candidate_name_available:[\s\S]*?generatePayload\.selected_resume_candidate_name_available \?\? false/)
  assert.match(appSource, /selected_resume_candidate_name_source: generatePayload\.selected_resume_candidate_name_source \|\| 'none'/)
  assert.match(appSource, /selected_resume_strict_mode: generatePayload\.selected_resume_strict_mode \?\? false/)
  assert.match(appSource, /selected_resume_context_used_in_prompt: generatePayload\.selected_resume_context_used_in_prompt \?\? false/)
  assert.match(appSource, /generic_fallback_blocked: generatePayload\.generic_fallback_blocked \?\? false/)
  assert.match(appSource, /profile_fallback_blocked: generatePayload\.profile_fallback_blocked \?\? false/)
  assert.match(appSource, /profile_context_suppressed_by_selected_resume:[\s\S]*?generatePayload\.profile_context_suppressed_by_selected_resume \?\? false/)
  assert.match(appSource, /final_context_priority: generatePayload\.final_context_priority \|\| 'none'/)
  assert.match(appSource, /job_context_included: generatePayload\.job_context_included \?\? Boolean\(companyName \|\| jobDescription\)/)
  assert.match(appSource, /target_role_included: generatePayload\.target_role_included \?\? Boolean\(targetRole\)/)
  assert.match(appSource, /project_intent_detected: generatePayload\.project_intent_detected \?\? false/)
  assert.match(appSource, /generationRequestIncludesSelectedResumeId: Boolean\(generateRequestBody\.selected_resume_id\)/)
  assert.match(appSource, /jobContextIncluded: Boolean\(companyName \|\| jobDescription\)/)
  assert.match(appSource, /targetRoleIncluded: Boolean\(targetRole\)/)
  assert.match(diagnosticsSource, /label="Context priority"/)
  assert.match(diagnosticsSource, /label="Job context request"/)
  assert.match(diagnosticsSource, /label="Target role request"/)
  assert.match(diagnosticsSource, /label="Job context in prompt"/)
  assert.match(diagnosticsSource, /label="Target role in prompt"/)
  assert.match(diagnosticsSource, /label="Project intent"/)
  assert.match(diagnosticsSource, /label="Selected resume strict"/)
  assert.match(diagnosticsSource, /label="Selected context in prompt"/)
  assert.match(diagnosticsSource, /label="Generic fallback blocked"/)
  assert.match(diagnosticsSource, /label="Profile fallback blocked"/)
  assert.match(diagnosticsSource, /label="Old profile suppressed"/)
  assert.match(diagnosticsSource, /label="Selected resume name"/)
  assert.match(diagnosticsSource, /label="Selected name source"/)
  assert.match(appSource, /selectedResumeIdExists: Boolean\(String\(startupSessionConfig\?\.selectedResumeId \|\| ''\)\.trim\(\)\)/)
  assert.match(diagnosticsSource, /label="Resume context source"/)
  assert.match(diagnosticsSource, /label="Selected resume request"/)
  assert.match(appSource, /applyStartupSessionConfig\(null\)/)
  assert.match(cssSource, /\.startup-setup-card\s*{[\s\S]*?width: 504px;[\s\S]*?height: 462px;/)
  assert.match(cssSource, /\.startup-setup-main\s*{[\s\S]*?overflow-y: auto;/)
})

test('startup login keeps long configuration errors in a bounded message area', () => {
  assert.match(startupSource, /const errorView = startupPollFailed[\s\S]*?getDesktopStartupErrorView\(authState\)/)
  assert.match(startupSource, /const errorText = errorView\.message/)
  assert.match(startupSource, /className={`startup-login-main\$\{errorText \? ' startup-login-main--error' : ''\}\$\{isOpeningBrowser \? ' startup-login-main--opening' : ''\}`}/)
  assert.match(startupSource, /<div className="startup-login-action-area">[\s\S]*<p className="startup-login-error" role="alert">/)
  assert.match(figmaLoginCssSource, /\.startup-login-action-area\s*{[\s\S]*?top: 281px;[\s\S]*?display: flex;/)
  assert.match(figmaLoginCssSource, /\.startup-login-error\s*{[\s\S]*?position: static;[\s\S]*?min-height: 36px;[\s\S]*?overflow: visible;/)
  assert.match(figmaLoginCssSource, /\.startup-login-action-area \.startup-login-button\s*{[\s\S]*?position: static;/)
  assert.doesNotMatch(figmaLoginCssSource, /\.startup-login-error\s*{[^}]*position: absolute;/)
})

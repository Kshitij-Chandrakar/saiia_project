const {
  app,
  BrowserWindow,
  desktopCapturer,
  globalShortcut,
  ipcMain,
  Menu,
  screen,
  shell,
  safeStorage,
  systemPreferences,
} = require('electron')
const { execFile } = require('child_process')
const fs = require('fs')
const path = require('path')
const {
  CALLBACK_URL,
  DesktopAuthSessionManager,
  createIpcSenderValidator,
} = require('./desktop_auth_session.cjs')

const hasSingleInstanceLock = app.requestSingleInstanceLock()
if (!hasSingleInstanceLock) {
  app.quit()
  process.exit(0)
}

registerDesktopAuthProtocol()

app.on('second-instance', (_event, argv) => {
  handleDesktopAuthCallbackFromArgv(argv)
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.show()
    mainWindow.focus()
  }
})

app.on('open-url', (event, url) => {
  event.preventDefault()
  handleDesktopAuthCallback(url)
})

let mainWindow
let overlayWindow
let isScreenSharing = false
let startupFlowComplete = false
let overlayVisible = false
let overlayOpacity = 1
let overlayBoundsState = null
let overlayBoundsSaveTimer = null
let lastExternalWindowSnapshot = null
let lastExternalCaptureTarget = null
let foregroundWindowPollTimer = null
let foregroundWindowPollInFlight = null
let desktopAuthSessionManager = null
let validateMainWindowIpcSender = null
let validateOverlayWindowIpcSender = null
let bufferedDesktopAuthCallbacks = []

const overlayState = {
  answer: '',
  error: '',
  status: '',
  transcript: '',
  questionHistory: {
    answer: { entries: [], currentIndex: -1 },
    screen: { entries: [], currentIndex: -1 },
  },
  questionHistoryNavigationCount: 0,
  fontSize: 14,
  provider: '',
  category: '',
  generationMs: null,
  totalPipelineMs: null,
  recording: false,
  manualProcessing: false,
  isManualGenerating: false,
  manualQuestionError: '',
  recordingStartedAt: null,
  audioPipelineStatus: 'idle',
  audioSourceWarning: false,
  autoMode: false,
  autoProcessing: false,
  ocrProcessing: false,
  ocrText: '',
  ocrConfidence: null,
  screenVisionProvider: '',
  screenVisionModel: '',
  screenCaptureTarget: 'active_window',
  screenWindowTitle: '',
  screenProcessName: '',
  screenImageWidth: 0,
  screenImageHeight: 0,
  rawScreenVisionText: '',
  screenCleanedText: '',
  extractedScreenQuestion: '',
  screenQuestionType: 'none',
  screenConfidence: null,
  screenCaptureMs: 0,
  screenVisionMs: 0,
  screenFallbackOcrUsed: false,
  screenScreenshotHidSaiiaWindows: false,
  screenRejectedUiNoise: false,
  screenUiNoiseRatio: 0,
  screenAnswerGenerated: false,
  screenAnswerText: '',
  screenCodeAnswer: '',
  screenCodeLanguage: '',
  screenAnswerDisplayedInPanel: false,
  screenAnswerCommittedToOverlay: false,
  screenPanelMode: 'preview',
  screenAnswerLoading: false,
  screenError: '',
  microphoneEnabled: false,
  systemAudioEnabled: false,
  activeAudioSource: 'none',
  systemAudioSupported: false,
  systemAudioDeviceName: '',
  autoModeStatus: 'off',
  autoModeSource: 'none',
  lastAutoTranscript: '',
  lastDetectedQuestion: '',
  autoRejectedReason: '',
  cooldownRemainingMs: 0,
  screenShareProtectionEnabled: true,
  overlayOpacity: 1,
  sessionStartedAt: Date.now(),
  privacyMessage:
    'Visibility during screen sharing depends on OS, meeting app, and whether the user shares full screen, window, or tab.',
}
const SCREEN_SOURCE_PREVIEW_SIZE = { width: 320, height: 200 }
const SCREEN_CAPTURE_MAX_DIMENSION = 2200
const OVERLAY_MARGIN_X = 40
const OVERLAY_MARGIN_TOP = 56
const OVERLAY_MARGIN_BOTTOM = 64
const OVERLAY_TARGET_WIDTH = 920
const OVERLAY_TARGET_HEIGHT = 560
const OVERLAY_MIN_WIDTH = 700
const OVERLAY_MIN_HEIGHT = 360
const OVERLAY_MIN_VISIBLE_WIDTH = 360
const OVERLAY_MIN_VISIBLE_HEIGHT = 76

const FOREGROUND_WINDOW_POLL_MS = 900
const LAST_EXTERNAL_TARGET_TTL_MS = 30000
const ANALYZE_SCREEN_HIDE_DELAY_MS = 220
const SCREEN_FULL_CAPTURE_ENABLED = String(process.env.SCREEN_FULL_CAPTURE_ENABLED || 'true').trim().toLowerCase() === 'true'
const SCREEN_FULL_CAPTURE_MAX_SCROLLS = Math.max(0, Number.parseInt(process.env.SCREEN_FULL_CAPTURE_MAX_SCROLLS || '4', 10) || 4)
const SCREEN_FULL_CAPTURE_WAIT_MS = Math.max(120, Number.parseInt(process.env.SCREEN_FULL_CAPTURE_WAIT_MS || '250', 10) || 250)
const SCREEN_FULL_CAPTURE_SCROLL_AMOUNT = Math.max(0.25, Math.min(1, Number.parseFloat(process.env.SCREEN_FULL_CAPTURE_SCROLL_AMOUNT || '0.75') || 0.75))
const SCREEN_FULL_CAPTURE_RESTORE_SCROLL = String(process.env.SCREEN_FULL_CAPTURE_RESTORE_SCROLL || 'true').trim().toLowerCase() === 'true'
const SCREEN_FULL_CAPTURE_PLATFORM_HINTS = /(leetcode|hackerrank|geeksforgeeks|problem|assessment|question|exam|quiz|mcq|constraints|example|chart|diagram|debug)/i
const SCREEN_FULL_CAPTURE_PROCESS_HINTS = /^(chrome|msedge|firefox|brave|opera|iexplore)$/i
const DESKTOP_AUTH_ENV_KEYS = new Set([
  'SUPABASE_URL',
  'VITE_SUPABASE_URL',
  'SUPABASE_ANON_KEY',
  'VITE_SUPABASE_ANON_KEY',
  'SAIIA_BACKEND_URL',
  'VITE_BACKEND_URL',
  'SAIIA_WEB_AUTH_URL',
  'VITE_SAIIA_WEB_AUTH_URL',
  'SAIIA_WEB_DASHBOARD_URL',
  'VITE_SAIIA_WEB_DASHBOARD_URL',
])

loadDesktopEnvFiles()

function loadDesktopEnvFiles() {
  const repoRoot = path.resolve(__dirname, '../..')
  const frontendRoot = path.resolve(__dirname, '..')
  ;[
    path.join(repoRoot, '.env'),
    path.join(frontendRoot, '.env.local'),
    path.join(frontendRoot, '.env'),
  ].forEach(loadDesktopEnvFile)
}

function loadDesktopEnvFile(filePath) {
  let raw
  try {
    raw = fs.readFileSync(filePath, 'utf8')
  } catch {
    return
  }

  raw.split(/\r?\n/).forEach((line) => {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) {
      return
    }
    const match = /^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/.exec(trimmed)
    if (!match) {
      return
    }
    const [, key, rawValue] = match
    if (!DESKTOP_AUTH_ENV_KEYS.has(key)) {
      return
    }
    if (Object.prototype.hasOwnProperty.call(process.env, key)) {
      return
    }
    process.env[key] = parseDesktopEnvValue(rawValue)
  })
}

function parseDesktopEnvValue(value) {
  const trimmed = String(value || '').trim()
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1)
  }
  return trimmed
}

function getDesktopAuthSessionPath() {
  return path.join(app.getPath('userData'), 'desktop-auth-session.bin')
}

function getDesktopAuthConfig() {
  return {
    supabaseUrl: process.env.SUPABASE_URL || process.env.VITE_SUPABASE_URL || '',
    supabaseAnonKey: process.env.SUPABASE_ANON_KEY || process.env.VITE_SUPABASE_ANON_KEY || '',
    webAuthUrl: getConfiguredWebAuthUrl(),
    backendUrl: process.env.SAIIA_BACKEND_URL || process.env.VITE_BACKEND_URL || 'http://localhost:8000',
  }
}

function getConfiguredWebAuthUrl() {
  return process.env.SAIIA_WEB_AUTH_URL || process.env.VITE_SAIIA_WEB_AUTH_URL || 'http://localhost:5173/auth/desktop-login'
}

function parseHttpUrl(rawUrl, label) {
  let parsed
  try {
    parsed = new URL(String(rawUrl || '').trim())
  } catch {
    throw new Error(`${label} must be a valid URL.`)
  }
  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error(`${label} must use http or https.`)
  }
  return parsed
}

function getDesktopDashboardUrl() {
  const configuredDashboardUrl = process.env.SAIIA_WEB_DASHBOARD_URL || process.env.VITE_SAIIA_WEB_DASHBOARD_URL || ''
  if (configuredDashboardUrl.trim()) {
    return parseHttpUrl(configuredDashboardUrl, 'Dashboard URL').toString()
  }
  const webAuthUrl = parseHttpUrl(getConfiguredWebAuthUrl(), 'Desktop web auth URL')
  return new URL('/auth/dashboard', webAuthUrl.origin).toString()
}

function getPackagedIndexPath() {
  return path.resolve(__dirname, '../dist/index.html')
}

function registerDesktopAuthProtocol() {
  if (process.defaultApp) {
    app.setAsDefaultProtocolClient('saiia', process.execPath, [path.resolve(process.argv[1] || '')])
    return
  }
  app.setAsDefaultProtocolClient('saiia')
}

function createDesktopAuthSessionManager() {
  const config = getDesktopAuthConfig()
  return new DesktopAuthSessionManager({
    ...config,
    redirectUri: CALLBACK_URL,
    sessionPath: getDesktopAuthSessionPath(),
    safeStorage,
    openExternal: (url) => shell.openExternal(url),
  })
}

function handleDesktopAuthCallback(rawUrl) {
  const value = String(rawUrl || '')
  if (!value.startsWith(CALLBACK_URL)) {
    return false
  }
  if (!desktopAuthSessionManager) {
    bufferedDesktopAuthCallbacks.push(value)
    return true
  }
  desktopAuthSessionManager.handleAuthCallback(value).catch((error) => {
    console.error('Desktop auth callback failed.', error?.message || 'Authentication failed.')
  })
  return true
}

function takeBufferedDesktopAuthCallbacks() {
  const callbacks = bufferedDesktopAuthCallbacks
  bufferedDesktopAuthCallbacks = []
  return callbacks
}

function handleDesktopAuthCallbackFromArgv(argv = []) {
  for (const arg of argv) {
    if (handleDesktopAuthCallback(arg)) {
      return true
    }
  }
  return false
}

function isOwnProcessWindow(snapshot) {
  return Number(snapshot?.processId || 0) === process.pid
}

function normalizeWindowText(value) {
  return String(value || '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
}

function isSaiiaLikeText(value) {
  return /(saiia|ai help|analyze screen|runtime panel|devtools|electron)/i.test(String(value || ''))
}

function isPreferredExternalProcess(processName) {
  return /^(chrome|msedge|firefox|brave|opera|zoom|teams|slack)$/i.test(String(processName || ''))
}

function isStrongQuestionWindowTitle(title) {
  return /(hackerrank|leetcode|geeksforgeeks|meet|zoom|question|problem|assessment|exam|quiz|coding|constraints|example|interview)/i.test(
    String(title || '')
  )
}

function shouldPreferStoredTarget(currentSnapshot, storedTarget) {
  if (!isUsableExternalSnapshot(currentSnapshot) || !storedTarget?.title) {
    return false
  }

  if (currentSnapshot.nativeWindowId) {
    return false
  }

  const currentProcess = String(currentSnapshot.processName || '')
  const storedProcess = String(storedTarget.processName || '')
  const currentLooksWeak = /^(code|cursor|devenv)$/i.test(currentProcess) || !isStrongQuestionWindowTitle(currentSnapshot.title)
  const storedLooksStrong = isStrongQuestionWindowTitle(storedTarget.title) || isPreferredExternalProcess(storedProcess)
  return currentLooksWeak && storedLooksStrong
}

function isUsableExternalSnapshot(snapshot) {
  if (!snapshot || !snapshot.title || isOwnProcessWindow(snapshot)) {
    return false
  }

  if (isSaiiaLikeText(snapshot.title) || isSaiiaLikeText(snapshot.processName)) {
    return false
  }

  return true
}

function buildCaptureTarget(snapshot, extras = {}) {
  if (!snapshot) {
    return null
  }

  return {
    id: extras.id || snapshot.id || '',
    title: String(extras.title || snapshot.title || '').trim(),
    name: String(extras.name || snapshot.name || snapshot.title || '').trim(),
    processName: String(extras.processName || snapshot.processName || '').trim(),
    nativeWindowId: String(extras.nativeWindowId || snapshot.nativeWindowId || '').trim(),
    bounds: snapshot.bounds || extras.bounds || null,
    updatedAt: Number(extras.updatedAt || snapshot.updatedAt || snapshot.capturedAt || Date.now()),
    source: String(extras.source || snapshot.source || '').trim(),
    reason: String(extras.reason || '').trim(),
  }
}

function rememberExternalCaptureTarget(snapshot, extras = {}) {
  const target = buildCaptureTarget(snapshot, extras)
  if (!isUsableExternalSnapshot(target)) {
    return null
  }

  lastExternalCaptureTarget = target
  return target
}

function getFreshLastExternalCaptureTarget() {
  if (!lastExternalCaptureTarget?.title) {
    return null
  }

  const ageMs = Date.now() - Number(lastExternalCaptureTarget.updatedAt || 0)
  if (ageMs > LAST_EXTERNAL_TARGET_TTL_MS) {
    return null
  }

  return {
    ...lastExternalCaptureTarget,
    ageMs,
  }
}

function createActiveWindowNotIdentifiedError(reason = 'active_window_not_identified') {
  const error = new Error('SAIIA could not identify the active question window.')
  error.code = 'active_window_not_identified'
  error.userAction = 'Focus the question window and retry.'
  error.retryable = true
  error.reason = reason
  return error
}

function isRejectedDesktopSourceName(sourceName) {
  return !sourceName || /(saiia|devtools|electron)/i.test(String(sourceName || ''))
}

function scoreExternalSourcePreference(sourceName) {
  const normalized = normalizeWindowText(sourceName)
  let score = 0
  if (/(hackerrank|leetcode|geeksforgeeks|google meet|meet|zoom|interview|problem|question|assessment|constraints|example)/i.test(sourceName)) {
    score += 40
  }
  if (/(chrome|msedge|firefox|brave|opera)/i.test(sourceName)) {
    score += 20
  }
  if (/(visual studio code|code)/i.test(sourceName)) {
    score -= 10
  }
  if (/window|screen/i.test(normalized) && normalized.length < 8) {
    score -= 5
  }
  return score
}

function scoreWindowSourceMatch(sourceName, targetTitle) {
  const source = normalizeWindowText(sourceName)
  const target = normalizeWindowText(targetTitle)

  if (!source || !target) {
    return 0
  }
  if (source === target) {
    return 100
  }
  if (target.startsWith(source) || source.startsWith(target)) {
    return 80
  }
  if (target.includes(source) || source.includes(target)) {
    return 70
  }

  const sourceTokens = new Set(source.split(/[^a-z0-9]+/).filter(Boolean))
  const targetTokens = new Set(target.split(/[^a-z0-9]+/).filter(Boolean))
  if (!sourceTokens.size || !targetTokens.size) {
    return 0
  }

  let overlap = 0
  sourceTokens.forEach((token) => {
    if (targetTokens.has(token)) {
      overlap += 1
    }
  })

  return overlap ? Math.round((overlap / Math.max(sourceTokens.size, targetTokens.size)) * 60) : 0
}

function sourceMatchesNativeWindow(sourceId, nativeWindowId) {
  const source = String(sourceId || '').trim()
  const nativeId = String(nativeWindowId || '').trim()
  return Boolean(source && nativeId && source.startsWith(`window:${nativeId}:`))
}

function redactWindowTitleForDiagnostics(value) {
  const text = String(value || '').trim()
  return text ? `[redacted:${text.length}]` : 'n/a'
}

function runForegroundWindowProbe() {
  const script = `
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class WinApi {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
  [StructLayout(LayoutKind.Sequential)]
  public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
}
"@
$hwnd = [WinApi]::GetForegroundWindow()
if ($hwnd -eq [IntPtr]::Zero) {
  "{}"
  exit 0
}
$titleBuilder = New-Object System.Text.StringBuilder 2048
[void][WinApi]::GetWindowText($hwnd, $titleBuilder, $titleBuilder.Capacity)
$processId = 0
[void][WinApi]::GetWindowThreadProcessId($hwnd, [ref]$processId)
$process = Get-Process -Id $processId -ErrorAction SilentlyContinue
$rect = New-Object WinApi+RECT
[void][WinApi]::GetWindowRect($hwnd, [ref]$rect)
[pscustomobject]@{
  title = $titleBuilder.ToString()
  nativeWindowId = $hwnd.ToInt64().ToString()
  processId = [int]$processId
  processName = if ($process) { $process.ProcessName } else { "" }
  left = $rect.Left
  top = $rect.Top
  right = $rect.Right
  bottom = $rect.Bottom
} | ConvertTo-Json -Compress
`.trim()

  return new Promise((resolve, reject) => {
    execFile(
      'powershell.exe',
      ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script],
      { windowsHide: true, maxBuffer: 1024 * 1024 },
      (error, stdout, stderr) => {
        if (error) {
          reject(error)
          return
        }

        const raw = String(stdout || '').trim()
        if (!raw) {
          resolve(null)
          return
        }

        try {
          const payload = JSON.parse(raw)
          const snapshot = {
            title: String(payload?.title || '').trim(),
            nativeWindowId: String(payload?.nativeWindowId || '').trim(),
            processId: Number(payload?.processId || 0),
            processName: String(payload?.processName || '').trim(),
            bounds: {
              left: Number(payload?.left || 0),
              top: Number(payload?.top || 0),
              right: Number(payload?.right || 0),
              bottom: Number(payload?.bottom || 0),
            },
            capturedAt: Date.now(),
          }
          resolve(snapshot)
        } catch (parseError) {
          reject(new Error(`Could not parse foreground window probe output. ${stderr || raw}`))
        }
      }
    )
  })
}

async function refreshForegroundWindowSnapshot(options = {}) {
  if (process.platform !== 'win32') {
    return null
  }

  if (!options.force && foregroundWindowPollInFlight) {
    return foregroundWindowPollInFlight
  }

  const probe = runForegroundWindowProbe()
    .then((snapshot) => {
      if (snapshot && snapshot.title && !isOwnProcessWindow(snapshot)) {
        lastExternalWindowSnapshot = snapshot
      }
      if (isUsableExternalSnapshot(snapshot)) {
        rememberExternalCaptureTarget(snapshot, {
          source: 'foreground_probe',
          reason: 'foreground_external_window',
        })
      }
      return snapshot
    })
    .catch((error) => {
      console.warn('Foreground window probe failed.', error)
      return null
    })

  if (options.force) {
    return probe
  }

  foregroundWindowPollInFlight = probe.finally(() => {
    foregroundWindowPollInFlight = null
  })

  return foregroundWindowPollInFlight
}

function startForegroundWindowTracking() {
  if (process.platform !== 'win32' || foregroundWindowPollTimer) {
    return
  }

  refreshForegroundWindowSnapshot().catch(() => {})
  foregroundWindowPollTimer = setInterval(() => {
    refreshForegroundWindowSnapshot().catch(() => {})
  }, FOREGROUND_WINDOW_POLL_MS)
}

function stopForegroundWindowTracking() {
  if (foregroundWindowPollTimer) {
    clearInterval(foregroundWindowPollTimer)
    foregroundWindowPollTimer = null
  }
}

function delay(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

function escapePowerShellString(value) {
  return String(value || '').replace(/'/g, "''")
}

function shouldUseFullProblemCapture(targetWindow) {
  if (!SCREEN_FULL_CAPTURE_ENABLED) {
    return false
  }

  const title = String(targetWindow?.title || '')
  const processName = String(targetWindow?.processName || '')
  return SCREEN_FULL_CAPTURE_PLATFORM_HINTS.test(title) || SCREEN_FULL_CAPTURE_PROCESS_HINTS.test(processName)
}

function runPowerShellJson(script) {
  return new Promise((resolve, reject) => {
    execFile(
      'powershell.exe',
      ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script],
      { windowsHide: true, maxBuffer: 1024 * 1024 },
      (error, stdout, stderr) => {
        if (error) {
          reject(error)
          return
        }

        const raw = String(stdout || '').trim()
        if (!raw) {
          resolve({})
          return
        }

        try {
          resolve(JSON.parse(raw))
        } catch (parseError) {
          reject(new Error(`Could not parse PowerShell output. ${stderr || raw}`))
        }
      }
    )
  })
}

async function sendWindowScrollKeys(targetWindow, keyToken, repeatCount = 1) {
  const targetTitle = String(targetWindow?.title || '')
  const bounds = targetWindow?.bounds || null
  if (!targetTitle || !repeatCount) {
    return { ok: false }
  }

  const safeTitle = escapePowerShellString(targetTitle)
  const safeKeyToken = escapePowerShellString(keyToken)
  const hasBounds = Number.isFinite(bounds?.left)
    && Number.isFinite(bounds?.top)
    && Number.isFinite(bounds?.right)
    && Number.isFinite(bounds?.bottom)
    && bounds.right > bounds.left
    && bounds.bottom > bounds.top
  const clickX = hasBounds ? Math.round(bounds.left + ((bounds.right - bounds.left) * 0.22)) : 0
  const clickY = hasBounds ? Math.round(bounds.top + ((bounds.bottom - bounds.top) * 0.42)) : 0
  const script = `
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class NativeInput {
  [DllImport("user32.dll")]
  public static extern bool SetCursorPos(int X, int Y);
  [DllImport("user32.dll")]
  public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtraInfo);
}
"@
$shell = New-Object -ComObject WScript.Shell
$title = '${safeTitle}'
$activated = $shell.AppActivate($title)
if (-not $activated) {
  [pscustomobject]@{ ok = $false; activated = $false } | ConvertTo-Json -Compress
  exit 0
}
Start-Sleep -Milliseconds 120
${hasBounds ? `
[NativeInput]::SetCursorPos(${clickX}, ${clickY}) | Out-Null
Start-Sleep -Milliseconds 60
[NativeInput]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 40
[NativeInput]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 120
`.trim() : ''}
for ($i = 0; $i -lt ${Math.max(1, repeatCount)}; $i++) {
  $shell.SendKeys('${safeKeyToken}')
  Start-Sleep -Milliseconds ${Math.max(120, SCREEN_FULL_CAPTURE_WAIT_MS)}
}
[pscustomobject]@{ ok = $true; activated = $true; clicked = ${hasBounds ? '$true' : '$false'} } | ConvertTo-Json -Compress
`.trim()

  return runPowerShellJson(script)
}

function getWindowVisibilitySnapshot(targetWindow) {
  if (!targetWindow || targetWindow.isDestroyed()) {
    return null
  }

  return {
    window: targetWindow,
    wasVisible: targetWindow.isVisible(),
    wasFocused: targetWindow.isFocused(),
  }
}

async function withSaiiaWindowsHidden(task) {
  const snapshots = [getWindowVisibilitySnapshot(mainWindow), getWindowVisibilitySnapshot(overlayWindow)].filter(Boolean)
  let hidWindows = false

  try {
    for (const snapshot of snapshots) {
      if (snapshot.wasVisible) {
        snapshot.window.hide()
        hidWindows = true
      }
    }
    if (hidWindows) {
      await delay(ANALYZE_SCREEN_HIDE_DELAY_MS)
    }
    const result = await task()
    return {
      ...result,
      hidSaiiaWindows: hidWindows,
    }
  } finally {
    for (const snapshot of snapshots) {
      if (!snapshot.wasVisible) {
        continue
      }
      if (snapshot.window.isDestroyed()) {
        continue
      }
      if (snapshot.window === overlayWindow && overlayVisible) {
        snapshot.window.showInactive()
      } else if (snapshot.window === mainWindow) {
        snapshot.window.show()
      } else {
        snapshot.window.show()
      }
    }
  }
}

function getOverlayBoundsStatePath() {
  return path.join(app.getPath('userData'), 'overlay-window-state.json')
}

function readOverlayBoundsState() {
  try {
    const raw = fs.readFileSync(getOverlayBoundsStatePath(), 'utf8')
    const parsed = JSON.parse(raw)
    if (
      parsed &&
      Number.isFinite(parsed.x) &&
      Number.isFinite(parsed.y) &&
      Number.isFinite(parsed.width) &&
      Number.isFinite(parsed.height)
    ) {
      return parsed
    }
  } catch {}

  return null
}

function queueOverlayBoundsSave(bounds) {
  if (!bounds) {
    return
  }

  overlayBoundsState = {
    x: Math.round(bounds.x),
    y: Math.round(bounds.y),
    width: Math.round(bounds.width),
    height: Math.round(bounds.height),
  }

  if (overlayBoundsSaveTimer) {
    clearTimeout(overlayBoundsSaveTimer)
  }

  overlayBoundsSaveTimer = setTimeout(() => {
    overlayBoundsSaveTimer = null
    try {
      fs.mkdirSync(path.dirname(getOverlayBoundsStatePath()), { recursive: true })
      fs.writeFileSync(getOverlayBoundsStatePath(), JSON.stringify(overlayBoundsState, null, 2))
    } catch (error) {
      console.error('Failed to persist overlay window position.', error)
    }
  }, 150)
}

function getOverlayDisplay(bounds) {
  if (bounds && Number.isFinite(bounds.x) && Number.isFinite(bounds.y)) {
    return screen.getDisplayMatching({
      x: bounds.x,
      y: bounds.y,
      width: bounds.width || OVERLAY_TARGET_WIDTH,
      height: bounds.height || OVERLAY_TARGET_HEIGHT,
    })
  }

  return screen.getDisplayNearestPoint(screen.getCursorScreenPoint())
}

function getDefaultOverlayBounds(display = screen.getPrimaryDisplay()) {
  const workArea = display.workArea
  const width = Math.min(
    OVERLAY_TARGET_WIDTH,
    Math.max(Math.min(OVERLAY_MIN_WIDTH, workArea.width - 16), workArea.width - OVERLAY_MARGIN_X * 2)
  )
  const height = Math.min(
    OVERLAY_TARGET_HEIGHT,
    Math.max(
      Math.min(OVERLAY_MIN_HEIGHT, workArea.height - 16),
      workArea.height - OVERLAY_MARGIN_TOP - OVERLAY_MARGIN_BOTTOM
    )
  )
  const x = Math.round(workArea.x + (workArea.width - width) / 2)
  const y = Math.round(
    Math.min(workArea.y + OVERLAY_MARGIN_TOP, workArea.y + Math.max(0, workArea.height - height))
  )

  return { x, y, width, height }
}

function clampOverlayBounds(bounds) {
  const fallbackDisplay = getOverlayDisplay(bounds)
  const workArea = fallbackDisplay.workArea
  const maxWidth = Math.max(320, workArea.width - 16)
  const maxHeight = Math.max(220, workArea.height - 16)
  const minWidth = Math.min(OVERLAY_MIN_WIDTH, maxWidth)
  const minHeight = Math.min(OVERLAY_MIN_HEIGHT, maxHeight)
  const width = Math.max(
    minWidth,
    Math.min(Number.isFinite(bounds?.width) ? bounds.width : OVERLAY_TARGET_WIDTH, maxWidth)
  )
  const height = Math.max(
    minHeight,
    Math.min(Number.isFinite(bounds?.height) ? bounds.height : OVERLAY_TARGET_HEIGHT, maxHeight)
  )
  const minX = workArea.x - width + OVERLAY_MIN_VISIBLE_WIDTH
  const maxX = workArea.x + workArea.width - OVERLAY_MIN_VISIBLE_WIDTH
  const minY = workArea.y
  const maxY = workArea.y + workArea.height - OVERLAY_MIN_VISIBLE_HEIGHT
  const nextX = Math.round(
    Math.min(maxX, Math.max(minX, Number.isFinite(bounds?.x) ? bounds.x : workArea.x))
  )
  const nextY = Math.round(
    Math.min(maxY, Math.max(minY, Number.isFinite(bounds?.y) ? bounds.y : workArea.y))
  )

  return {
    x: nextX,
    y: nextY,
    width: Math.round(width),
    height: Math.round(height),
  }
}

function getInitialOverlayBounds() {
  const savedBounds = readOverlayBoundsState()
  if (!savedBounds) {
    return getDefaultOverlayBounds(getOverlayDisplay())
  }

  return clampOverlayBounds(savedBounds)
}

function applyOverlayBounds(nextBounds, options = {}) {
  if (!overlayWindow || overlayWindow.isDestroyed() || !nextBounds) {
    return null
  }

  const clampedBounds = clampOverlayBounds(nextBounds)
  const currentBounds = overlayWindow.getBounds()
  const boundsChanged =
    currentBounds.x !== clampedBounds.x ||
    currentBounds.y !== clampedBounds.y ||
    currentBounds.width !== clampedBounds.width ||
    currentBounds.height !== clampedBounds.height

  if (boundsChanged) {
    overlayWindow.setBounds(clampedBounds, options.animate === true)
  }
  queueOverlayBoundsSave(clampedBounds)
  return clampedBounds
}

function resizeOverlayFromBottomRight(nextSize) {
  if (!overlayWindow || overlayWindow.isDestroyed()) {
    return null
  }

  const currentBounds = overlayWindow.getBounds()
  const display = screen.getDisplayMatching(currentBounds)
  const workArea = display.workArea
  const maxRight = workArea.x + workArea.width
  const maxBottom = workArea.y + workArea.height
  const maxWidth = Math.max(OVERLAY_MIN_WIDTH, maxRight - currentBounds.x)
  const maxHeight = Math.max(OVERLAY_MIN_HEIGHT, maxBottom - currentBounds.y)
  const requestedWidth = Number.isFinite(nextSize?.width) ? nextSize.width : currentBounds.width
  const requestedHeight = Number.isFinite(nextSize?.height) ? nextSize.height : currentBounds.height
  const requestedMinHeight = Number.isFinite(nextSize?.minHeight)
    ? Math.max(OVERLAY_MIN_HEIGHT, nextSize.minHeight)
    : OVERLAY_MIN_HEIGHT

  return applyOverlayBounds({
    ...currentBounds,
    width: Math.max(OVERLAY_MIN_WIDTH, Math.min(requestedWidth, maxWidth)),
    height: Math.max(requestedMinHeight, Math.min(requestedHeight, maxHeight)),
  })
}

function resetOverlayPosition() {
  const display = overlayWindow && !overlayWindow.isDestroyed()
    ? screen.getDisplayMatching(overlayWindow.getBounds())
    : getOverlayDisplay()
  const nextBounds = getDefaultOverlayBounds(display)
  return applyOverlayBounds(nextBounds)
}

function buildApplicationMenu() {
  const template = [
    {
      label: 'Overlay',
      submenu: [
        {
          label: 'Reset overlay position',
          click: () => {
            resetOverlayPosition()
          },
        },
      ],
    },
  ]

  Menu.setApplicationMenu(Menu.buildFromTemplate(template))
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

function broadcastToolbarAction(action, payload = {}) {
  const eventPayload = { action, payload }
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('toolbar:action', eventPayload)
  }
  if (overlayWindow && !overlayWindow.isDestroyed()) {
    overlayWindow.webContents.send('toolbar:action', eventPayload)
  }
}

function syncOverlayVisibility(visible) {
  if (!startupFlowComplete) {
    visible = false
  }
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

function completeStartupFlow() {
  startupFlowComplete = true
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.setMinimumSize(420, 260)
    mainWindow.setSize(620, 860)
    mainWindow.center()
  }
  syncOverlayVisibility(true)
  return { ok: true }
}

function resetStartupFlow() {
  startupFlowComplete = false
  syncOverlayVisibility(false)
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.setMinimumSize(426, 384)
    mainWindow.setSize(504, 462)
    mainWindow.center()
    mainWindow.show()
    mainWindow.focus()
  }
  return { ok: true }
}

function closeStartupWindow() {
  if (!startupFlowComplete) {
    globalShortcut.unregisterAll()
    if (overlayWindow && !overlayWindow.isDestroyed()) {
      overlayWindow.hide()
      overlayWindow.close()
    }
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.close()
    }
    app.quit()
    return { ok: true, quit: true }
  }

  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.close()
  }
  return { ok: true }
}

function toggleOverlayVisibility() {
  if (!startupFlowComplete) {
    syncOverlayVisibility(false)
    return
  }

  const isCurrentlyVisible = !!(
    overlayWindow &&
    !overlayWindow.isDestroyed() &&
    overlayWindow.isVisible()
  )
  syncOverlayVisibility(!isCurrentlyVisible)
}

function getScreenCaptureThumbnailSize() {
  const displays = screen.getAllDisplays()
  if (!displays.length) {
    return { width: 1600, height: 900 }
  }

  let maxWidth = 0
  let maxHeight = 0
  for (const display of displays) {
    maxWidth = Math.max(maxWidth, display.size?.width || 0)
    maxHeight = Math.max(maxHeight, display.size?.height || 0)
  }

  const width = maxWidth || 1600
  const height = maxHeight || 900
  const scale = Math.min(1, SCREEN_CAPTURE_MAX_DIMENSION / Math.max(width, height))

  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
  }
}

async function listScreenSources() {
  const sources = await desktopCapturer.getSources({
    types: ['screen', 'window'],
    fetchWindowIcons: false,
    thumbnailSize: SCREEN_SOURCE_PREVIEW_SIZE,
  })

  return sources
    .filter((source) => !source.thumbnail.isEmpty())
    .map((source) => ({
      id: source.id,
      name: source.name,
      kind: source.id.startsWith('screen:') ? 'screen' : 'window',
      thumbnailDataUrl: source.thumbnail.toDataURL(),
    }))
}

async function captureScreenSource(sourceId) {
  if (!sourceId || !String(sourceId).trim()) {
    throw new Error('No screen source was selected.')
  }

  const sources = await desktopCapturer.getSources({
    types: ['screen', 'window'],
    fetchWindowIcons: false,
    thumbnailSize: getScreenCaptureThumbnailSize(),
  })
  const source = sources.find((entry) => entry.id === sourceId)

  if (!source || source.thumbnail.isEmpty()) {
    throw new Error('Could not capture screen.')
  }

  return {
    id: source.id,
    name: source.name,
    kind: source.id.startsWith('screen:') ? 'screen' : 'window',
    imageDataUrl: source.thumbnail.toDataURL(),
  }
}

async function captureWindowThumbnailForTarget(targetWindow) {
  const captureStartedAt = Date.now()
  const sources = await desktopCapturer.getSources({
    types: ['window'],
    fetchWindowIcons: false,
    thumbnailSize: getScreenCaptureThumbnailSize(),
  })

  let bestMatch = null
  let bestScore = 0
  for (const source of sources) {
    if (!source || source.thumbnail.isEmpty()) {
      continue
    }
    const sourceName = String(source.name || '').trim()
    if (isRejectedDesktopSourceName(sourceName)) {
      continue
    }
    let score = scoreWindowSourceMatch(sourceName, targetWindow.title)
    if (targetWindow?.name) {
      score = Math.max(score, scoreWindowSourceMatch(sourceName, targetWindow.name))
    }
    if (targetWindow?.id && source.id === targetWindow.id) {
      score = Math.max(score, 120)
    }
    if (sourceMatchesNativeWindow(source.id, targetWindow?.nativeWindowId)) {
      score = Math.max(score, 200)
    }
    score += scoreExternalSourcePreference(sourceName)
    if (score > bestScore) {
      bestScore = score
      bestMatch = source
    }
  }

  if (!bestMatch || bestScore < 55) {
    throw new Error('Open the target question window first, then click Analyze Screen.')
  }

  return {
    id: bestMatch.id,
    name: bestMatch.name,
    kind: 'window',
    windowTitle: targetWindow.title,
    processName: targetWindow.processName || '',
    imageDataUrl: bestMatch.thumbnail.toDataURL(),
    captureMs: Date.now() - captureStartedAt,
  }
}

async function getBestExternalDesktopSourceCandidate() {
  const sources = await desktopCapturer.getSources({
    types: ['window'],
    fetchWindowIcons: false,
    thumbnailSize: { width: 1, height: 1 },
  })

  const freshTarget = getFreshLastExternalCaptureTarget()
  let bestMatch = null
  let bestScore = 0
  let tiedBest = false
  let candidateCount = 0
  let rejectedReason = ''

  for (const source of sources) {
    const sourceName = String(source?.name || '').trim()
    if (isRejectedDesktopSourceName(sourceName)) {
      rejectedReason = sourceName ? 'rejected:desktop_source_name' : 'rejected:empty_name'
      continue
    }

    candidateCount += 1
    let score = scoreExternalSourcePreference(sourceName)
    if (sourceMatchesNativeWindow(source.id, freshTarget?.nativeWindowId)) {
      score = Math.max(score, 200)
    }
    if (freshTarget?.title) {
      score += scoreWindowSourceMatch(sourceName, freshTarget.title)
    }
    if (freshTarget?.name) {
      score += Math.round(scoreWindowSourceMatch(sourceName, freshTarget.name) * 0.5)
    }

    if (score > bestScore) {
      bestScore = score
      bestMatch = source
      tiedBest = false
    } else if (score === bestScore && score > 0) {
      tiedBest = true
    }
  }

  if (!bestMatch) {
    return {
      target: null,
      source: null,
      reason: rejectedReason || 'no_external_desktop_source',
    }
  }

  if ((!freshTarget?.title && candidateCount !== 1) || tiedBest) {
    return {
      target: null,
      source: null,
      reason: candidateCount > 1 ? 'active_window_ambiguous' : 'no_external_desktop_source',
      candidateCount,
      ambiguous: candidateCount > 1 || tiedBest,
    }
  }

  const target = rememberExternalCaptureTarget(
    {
      title: bestMatch.name,
      processName: '',
      bounds: null,
      capturedAt: Date.now(),
    },
    {
      id: bestMatch.id,
      name: bestMatch.name,
      source: 'desktop_capturer',
      reason: freshTarget?.title ? 'desktop_source_matched_last_target' : 'desktop_source_best_external',
    }
  )

  return {
    target,
    source: bestMatch,
    reason: target?.reason || 'desktop_source_best_external',
  }
}

async function resolveCaptureTargetForAnalyze(options = {}) {
  const allowCachedFallback = options.allowCachedFallback !== false
  const allowDesktopFallback = options.allowDesktopFallback !== false
  const foregroundWindow = await refreshForegroundWindowSnapshot({ force: true })
  const currentActiveTitle = foregroundWindow?.title || ''
  const freshTarget = getFreshLastExternalCaptureTarget()

  if (allowCachedFallback && freshTarget?.title) {
    console.info('[AnalyzeScreen] target resolved', {
      current_active_window_title: redactWindowTitleForDiagnostics(currentActiveTitle),
      last_external_target_title: redactWindowTitleForDiagnostics(freshTarget.title),
      selected_capture_target_title: redactWindowTitleForDiagnostics(freshTarget.title),
      selected_capture_target_source: freshTarget.source || 'last_external_capture_target',
      target_selection_reason: 'last_external_window',
      target_age_ms: freshTarget.ageMs || 0,
      rejected_target_reason: foregroundWindow?.title ? 'current_active_is_saiia_or_not_preferred' : 'no_active_external_window',
    })
    return freshTarget
  }

  if (isUsableExternalSnapshot(foregroundWindow)) {
    const target = rememberExternalCaptureTarget(foregroundWindow, {
      source: 'foreground_probe',
      reason: 'foreground_non_saiia',
    })
    console.info('[AnalyzeScreen] target resolved', {
      current_active_window_title: redactWindowTitleForDiagnostics(currentActiveTitle),
      last_external_target_title: redactWindowTitleForDiagnostics(lastExternalCaptureTarget?.title),
      selected_capture_target_title: redactWindowTitleForDiagnostics(target?.title),
      selected_capture_target_source: target?.source || 'foreground_probe',
      target_selection_reason: target?.reason || 'foreground_non_saiia',
      target_age_ms: 0,
      rejected_target_reason: '',
    })
    return target
  }

  if (allowCachedFallback && shouldPreferStoredTarget(foregroundWindow, freshTarget)) {
    console.info('[AnalyzeScreen] target resolved', {
      current_active_window_title: redactWindowTitleForDiagnostics(currentActiveTitle),
      last_external_target_title: redactWindowTitleForDiagnostics(freshTarget?.title),
      selected_capture_target_title: redactWindowTitleForDiagnostics(freshTarget?.title),
      selected_capture_target_source: freshTarget?.source || 'last_external_capture_target',
      target_selection_reason: 'prefer_recent_question_window_over_weak_current_window',
      target_age_ms: freshTarget?.ageMs || 0,
      rejected_target_reason: `current_window_deprioritized:${foregroundWindow?.processName || 'unknown'}`,
    })
    return freshTarget
  }

  let desktopFallback = null
  if (allowDesktopFallback) {
    desktopFallback = await getBestExternalDesktopSourceCandidate()
    if (desktopFallback?.target?.title) {
      console.info('[AnalyzeScreen] target resolved', {
        current_active_window_title: redactWindowTitleForDiagnostics(currentActiveTitle),
        last_external_target_title: redactWindowTitleForDiagnostics(lastExternalCaptureTarget?.title),
        selected_capture_target_title: redactWindowTitleForDiagnostics(desktopFallback.target.title),
        selected_capture_target_source: desktopFallback.target.source || 'desktop_capturer',
        target_selection_reason: desktopFallback.reason || 'desktop_source_best_external',
        target_age_ms: 0,
        rejected_target_reason: foregroundWindow?.title ? 'current_active_is_saiia_or_invalid' : 'no_active_external_window',
      })
      return desktopFallback.target
    }
  }

  console.info('[AnalyzeScreen] target resolution failed', {
    current_active_window_title: redactWindowTitleForDiagnostics(currentActiveTitle),
    last_external_target_title: redactWindowTitleForDiagnostics(lastExternalCaptureTarget?.title),
    selected_capture_target_title: 'n/a',
    selected_capture_target_source: 'n/a',
    target_selection_reason: 'no_valid_target',
    target_age_ms: freshTarget?.ageMs || null,
    rejected_target_reason: desktopFallback?.reason || 'no_recent_external_target_or_desktop_source',
  })
  throw createActiveWindowNotIdentifiedError(desktopFallback?.reason || 'no_valid_target')
}

async function captureActiveWindowSource() {
  let preHideTarget = null
  try {
    preHideTarget = await resolveCaptureTargetForAnalyze({
      allowCachedFallback: false,
      allowDesktopFallback: false,
    })
  } catch {
    preHideTarget = null
  }

  return withSaiiaWindowsHidden(async () => {
    const frozenTarget = preHideTarget || (await resolveCaptureTargetForAnalyze())
    const targetWindow = frozenTarget
    return captureWindowThumbnailForTarget(targetWindow)
  })
}

async function captureActiveWindowSequence() {
  let preHideTarget = null
  try {
    preHideTarget = await resolveCaptureTargetForAnalyze({
      allowCachedFallback: false,
      allowDesktopFallback: false,
    })
  } catch {
    preHideTarget = null
  }

  return withSaiiaWindowsHidden(async () => {
    const frozenTarget = preHideTarget || (await resolveCaptureTargetForAnalyze())
    const targetWindow = frozenTarget
    const analyzeMode = shouldUseFullProblemCapture(targetWindow) ? 'full_problem' : 'visible_window'
    const captures = []
    const scrollPositions = [0]
    let duplicateCaptureStopped = false
    let bottomReached = false
    let restoredScrollPosition = false

    const firstCapture = await captureWindowThumbnailForTarget(targetWindow)
    captures.push({ ...firstCapture, scrollStep: 0 })

    if (analyzeMode === 'full_problem') {
      const scrollKey = SCREEN_FULL_CAPTURE_SCROLL_AMOUNT >= 0.5 ? '{PGDN}' : '{DOWN}'

      for (let index = 1; index <= SCREEN_FULL_CAPTURE_MAX_SCROLLS; index += 1) {
        const scrollResult = await sendWindowScrollKeys(targetWindow, scrollKey, 1)
        if (!scrollResult?.ok) {
          bottomReached = index > 1
          break
        }
        await delay(SCREEN_FULL_CAPTURE_WAIT_MS)
        const nextCapture = await captureWindowThumbnailForTarget(targetWindow)
        if (!nextCapture?.imageDataUrl || nextCapture.imageDataUrl === captures[captures.length - 1]?.imageDataUrl) {
          bottomReached = true
          duplicateCaptureStopped = true
          break
        }
        captures.push({ ...nextCapture, scrollStep: index })
        scrollPositions.push(index)
      }

      if (SCREEN_FULL_CAPTURE_RESTORE_SCROLL && captures.length > 1) {
        const restoreResult = await sendWindowScrollKeys(targetWindow, '{PGUP}', captures.length - 1)
        restoredScrollPosition = Boolean(restoreResult?.ok)
      }
    }

    return {
      ...firstCapture,
      captures,
      analyzeMode,
      fullCaptureEnabled: SCREEN_FULL_CAPTURE_ENABLED,
      scrollCaptureUsed: captures.length > 1,
      captureCount: captures.length,
      scrollPositions,
      duplicateCaptureStopped,
      bottomReached,
      restoredScrollPosition,
    }
  })
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 504,
    height: 462,
    minWidth: 426,
    minHeight: 384,
    autoHideMenuBar: true,
    transparent: true,
    frame: false,
    backgroundColor: '#00000000',
    hasShadow: false,
    titleBarStyle: 'hidden',
    trafficLightPosition: { x: -9999, y: -9999 },
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
  if (!startupFlowComplete) {
    return null
  }

  const initialBounds = getInitialOverlayBounds()
  overlayWindow = new BrowserWindow({
    x: initialBounds.x,
    y: initialBounds.y,
    width: initialBounds.width,
    height: initialBounds.height,
    minWidth: OVERLAY_MIN_WIDTH,
    minHeight: OVERLAY_MIN_HEIGHT,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    hasShadow: false,
    resizable: true,
    movable: true,
    focusable: true,
    show: false,
    backgroundColor: '#00000000',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  overlayWindow.setAlwaysOnTop(true, 'screen-saver')
  overlayWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })

  overlayWindow.setOpacity(overlayOpacity)
  queueOverlayBoundsSave(initialBounds)
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

  overlayWindow.on('move', () => {
    applyOverlayBounds(overlayWindow.getBounds())
  })

  overlayWindow.on('resize', () => {
    applyOverlayBounds(overlayWindow.getBounds())
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

app.on('ready', async () => {
  desktopAuthSessionManager = createDesktopAuthSessionManager()
  const bufferedCallbacks = takeBufferedDesktopAuthCallbacks()
  validateMainWindowIpcSender = createIpcSenderValidator({
    getExpectedWindow: () => mainWindow,
    BrowserWindow,
    devOrigin: process.env.VITE_DEV_SERVER_URL || 'http://localhost:5173',
    isPackaged: app.isPackaged,
    packagedIndexPath: getPackagedIndexPath(),
  })
  validateOverlayWindowIpcSender = createIpcSenderValidator({
    getExpectedWindow: () => overlayWindow,
    BrowserWindow,
    devOrigin: process.env.VITE_DEV_SERVER_URL || 'http://localhost:5173',
    isPackaged: app.isPackaged,
    packagedIndexPath: getPackagedIndexPath(),
  })
  await desktopAuthSessionManager.initialize().catch((error) => {
    console.error('Desktop auth session restore failed.', error?.message || 'Authentication restore failed.')
  })
  bufferedCallbacks.forEach((url) => handleDesktopAuthCallback(url))
  handleDesktopAuthCallbackFromArgv(process.argv)

  buildApplicationMenu()
  createMainWindow()
  startForegroundWindowTracking()

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
  globalShortcut.unregister('Control+Enter')
  globalShortcut.unregister('Control+Shift+Enter')
  const hideOk = globalShortcut.register('Control+H', () => {
    if (!startupFlowComplete) {
      return
    }
    toggleOverlayVisibility()
  })
  const aiAnswerOk = globalShortcut.register('Control+Enter', () => {
    if (!startupFlowComplete) {
      return
    }
    broadcastToolbarAction('ai-answer')
  })
  const analyzeScreenOk = globalShortcut.register('Control+Shift+Enter', () => {
    if (!startupFlowComplete) {
      return
    }
    broadcastToolbarAction('analyze-screen')
  })

  if (!hideOk) {
    console.error(
      'Failed to register Ctrl+H for overlay hide/show. Another app may already be using this shortcut.'
    )
  } else {
    console.log('Ctrl+H registered for overlay hide/show')
  }
  if (!aiAnswerOk) {
    console.error('Failed to register Ctrl+Enter for AI Answer.')
  }
  if (!analyzeScreenOk) {
    console.error('Failed to register Ctrl+Shift+Enter for Analyze Screen.')
  }

  app.on('activate', () => {
    if (mainWindow === null) {
      createMainWindow()
    }
    if (startupFlowComplete && overlayWindow === null) {
      createOverlayWindow()
    }
  })
})

function validateAuthIpc(event) {
  if (!validateMainWindowIpcSender) {
    throw new Error('Desktop auth IPC is not ready.')
  }
  validateMainWindowIpcSender(event)
}

function validateTrustedRendererIpc(event) {
  const errors = []
  for (const validate of [validateMainWindowIpcSender, validateOverlayWindowIpcSender]) {
    if (!validate) {
      continue
    }
    try {
      validate(event)
      return true
    } catch (error) {
      errors.push(error)
    }
  }
  throw errors[0] || new Error('Desktop IPC is not ready.')
}

ipcMain.handle('auth:get-state', (event) => {
  validateTrustedRendererIpc(event)
  return desktopAuthSessionManager.getSafeState()
})

ipcMain.handle('auth:start-login', async (event) => {
  validateAuthIpc(event)
  return desktopAuthSessionManager.startLogin()
})

ipcMain.handle('auth:logout', async (event) => {
  validateAuthIpc(event)
  const state = await desktopAuthSessionManager.logout()
  if (state.status === 'signed-out' || state.status === 'token-expired') {
    resetStartupFlow()
  }
  return state
})

ipcMain.handle('cloud:get-startup-context', (event) => {
  validateAuthIpc(event)
  return desktopAuthSessionManager.getStartupContext()
})

ipcMain.handle('cloud:refresh-startup-context', async (event) => {
  validateAuthIpc(event)
  return desktopAuthSessionManager.refreshStartupContext()
})

ipcMain.handle('cloud:list-resumes', async (event) => {
  validateAuthIpc(event)
  return desktopAuthSessionManager.listCloudResumes()
})

ipcMain.handle('generate:answer', async (event, body) => {
  validateAuthIpc(event)
  return desktopAuthSessionManager.generateAnswer(body)
})

ipcMain.handle('startup:complete', (event) => {
  validateAuthIpc(event)
  if (desktopAuthSessionManager.getSafeState().status !== 'connected') {
    return { ok: false, reason: 'auth-required' }
  }
  return completeStartupFlow()
})

ipcMain.handle('startup:close', (event) => {
  validateAuthIpc(event)
  return closeStartupWindow()
})

ipcMain.handle('dashboard:open', async (event) => {
  validateTrustedRendererIpc(event)
  const dashboardUrl = getDesktopDashboardUrl()
  await shell.openExternal(dashboardUrl)
  return { ok: true }
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
  if (!startupFlowComplete) {
    syncOverlayVisibility(false)
    return { visible: false }
  }

  toggleOverlayVisibility()
  return {
    visible: overlayVisible && !!(overlayWindow && overlayWindow.isVisible()),
  }
})

ipcMain.handle('overlay:reset-position', () => {
  const bounds = resetOverlayPosition()
  return { bounds }
})

ipcMain.handle('overlay:get-bounds', () => ({
  bounds: overlayWindow && !overlayWindow.isDestroyed() ? overlayWindow.getBounds() : null,
}))

ipcMain.handle('overlay:resize-bottom-right', (_event, nextSize) => ({
  bounds: resizeOverlayFromBottomRight(nextSize),
}))

ipcMain.handle('overlay:set-opacity', (_event, nextOpacity) => {
  const normalizedOpacity = Math.min(1, Math.max(0.4, Number(nextOpacity) || 1))
  overlayOpacity = normalizedOpacity
  overlayState.overlayOpacity = normalizedOpacity
  if (overlayWindow && !overlayWindow.isDestroyed()) {
    overlayWindow.setOpacity(normalizedOpacity)
  }
  broadcastOverlayState()
  return {
    overlayOpacity: normalizedOpacity,
  }
})

ipcMain.handle('toolbar:trigger', (_event, action, payload) => {
  if (!startupFlowComplete) {
    return { ok: false, reason: 'startup-incomplete' }
  }

  broadcastToolbarAction(action, payload)
  if (action === 'end-session') {
    app.quit()
  }
  return { ok: true }
})

ipcMain.handle('window:open-main-panel', () => {
  if (!mainWindow || mainWindow.isDestroyed()) {
    createMainWindow()
  }
  if (mainWindow) {
    mainWindow.show()
    mainWindow.focus()
  }
  return { ok: true }
})

ipcMain.handle('screen:list-sources', async () => listScreenSources())

ipcMain.handle('screen:capture', async (_event, sourceId) => captureScreenSource(sourceId))

ipcMain.handle('screen:capture-active-window', async () => captureActiveWindowSource())

ipcMain.handle('screen:capture-active-window-sequence', async () => captureActiveWindowSequence())

app.on('will-quit', () => {
  stopForegroundWindowTracking()
  if (overlayBoundsSaveTimer) {
    clearTimeout(overlayBoundsSaveTimer)
    overlayBoundsSaveTimer = null
  }
  if (overlayWindow && !overlayWindow.isDestroyed()) {
    queueOverlayBoundsSave(overlayWindow.getBounds())
  } else if (overlayBoundsState) {
    try {
      fs.mkdirSync(path.dirname(getOverlayBoundsStatePath()), { recursive: true })
      fs.writeFileSync(getOverlayBoundsStatePath(), JSON.stringify(overlayBoundsState, null, 2))
    } catch (error) {
      console.error('Failed to flush overlay window position.', error)
    }
  }
  globalShortcut.unregisterAll()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

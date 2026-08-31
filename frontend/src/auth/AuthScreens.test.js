import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'


const source = readFileSync(new URL('./AuthScreens.jsx', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const cssSource = readFileSync(new URL('./auth.css', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const appSource = readFileSync(new URL('../App.jsx', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const signupPageSource = source.match(/export function AuthSignupPage[\s\S]*?export function AuthLoginPage/)?.[0] || ''
const loginPageSource = source.match(/export function AuthLoginPage[\s\S]*?export function AuthForgotPasswordPage/)?.[0] || ''
const statusPageSource = source.match(/export function AuthStatusPage[\s\S]*?function RequireAuth/)?.[0] || ''
const dashboardPageSource = source.match(/export function AuthDashboardPage[\s\S]*?export function AuthResumePage/)?.[0] || ''
const resumePageSource = source.match(/export function AuthResumePage[\s\S]*?export function AuthLogoutPage/)?.[0] || ''
const statusLogoutSource = statusPageSource.match(/async function handleLogout\(\) \{[\s\S]*?\n  \}\n\n  return \(/)?.[0] || ''
const dashboardLogoutSource = dashboardPageSource.match(/async function handleLogout\(\) \{[\s\S]*?\n  \}\n\n  return \(/)?.[0] || ''
const resumeRefreshCatchSource = resumePageSource.match(/catch \(refreshError\) \{[\s\S]*?\}\s*catch \(confirmError\)/)?.[0] || ''
const resumeDeleteSource = resumePageSource.match(/async function handleDeleteResume\(targetResumeArg = null\) \{[\s\S]*?\n  \}\n\n  async function handleRebuildIndex/)?.[0] || ''
const openDesktopHandoffSource = source.match(/async function openDesktopHandoff[\s\S]*?\n\}/)?.[0] || ''
const sourceWithoutDesktopHandoff = source.replace(openDesktopHandoffSource, '')

assert.ok(signupPageSource, 'AuthSignupPage source slice should be found')
assert.ok(loginPageSource, 'AuthLoginPage source slice should be found')
assert.ok(statusPageSource, 'AuthStatusPage source slice should be found')
assert.ok(dashboardPageSource, 'AuthDashboardPage source slice should be found')
assert.ok(resumePageSource, 'AuthResumePage source slice should be found')
assert.ok(statusLogoutSource, 'AuthStatusPage handleLogout source slice should be found')
assert.ok(dashboardLogoutSource, 'AuthDashboardPage handleLogout source slice should be found')
assert.ok(resumeRefreshCatchSource, 'AuthResumePage refresh catch source slice should be found')
assert.ok(resumeDeleteSource, 'AuthResumePage handleDeleteResume source slice should be found')
assert.ok(openDesktopHandoffSource, 'openDesktopHandoff source slice should be found')


test('profile bootstrap behavior is shared by status and dashboard pages', () => {
  assert.match(source, /function useProfileBootstrap\(\{ backendUrl, sessionErrorMessage, disabled = false \}\)/)
  assert.equal((source.match(/async function handleBootstrapProfile/g) || []).length, 1)
  assert.match(source, /const bootstrapOperationRef = useRef\(0\)/)
  assert.match(source, /return \(\) => \{\s+bootstrapOperationRef\.current \+= 1\s+\}/)
  assert.match(statusPageSource, /useProfileBootstrap\(\{\s+backendUrl,\s+sessionErrorMessage: 'No active auth session was found\.',\s+disabled: logoutPending,/)
  assert.match(dashboardPageSource, /useProfileBootstrap\(\{\s+backendUrl,\s+sessionErrorMessage: 'Session expired or signed out\. Please log in again\.',\s+disabled: logoutPending,/)
})


test('bootstrap result and loading updates require active operation', () => {
  assert.match(source, /if \(bootstrapLoading \|\| disabled\) \{\s+return\s+\}/)
  assert.match(source, /const operationId = bootstrapOperationRef\.current \+ 1/)
  assert.match(source, /bootstrapOperationRef\.current = operationId/)
  assert.match(source, /setBootstrapLoading\(true\)[\s\S]*supabase\.auth\.getSession\(\)/)
  assert.match(source, /if \(bootstrapOperationRef\.current === operationId\) \{\s+setBootstrapResult\(result\)/)
  assert.match(source, /if \(bootstrapOperationRef\.current === operationId\) \{\s+setBootstrapLoading\(false\)/)
})


test('protected dashboard redirects signed-out users to login', () => {
  assert.match(source, /function RequireAuth\(\{ backendUrl, children \}\)/)
  assert.match(source, /supabase\.auth\.getSession\(\)/)
  assert.match(source, /setSignedOut\(true\)/)
  assert.match(source, /to=\{`\/auth\/login\?next=\$\{encodeURIComponent\(nextRoute\)\}`\}/)
  assert.match(source, /const LOGIN_REQUIRED_MESSAGE = 'Session expired or signed out\. Please log in\.'/)
  assert.match(source, /state=\{\{ authMessage: LOGIN_REQUIRED_MESSAGE, next: nextRoute \}\}/)
  assert.doesNotMatch(source, /authMessage: error/)
})


test('login redirects to dashboard by default after verification', () => {
  assert.match(source, /const DEFAULT_LOGIN_NEXT_ROUTE = '\/auth\/dashboard'/)
  assert.match(source, /const \[searchParams\] = useSearchParams\(\)/)
  assert.match(source, /const safeNextRoute = getSafeAuthNextRoute\(searchParams\.get\('next'\) \|\| location\.state\?\.next\)/)
  assert.match(source, /navigate\(safeNextRoute, \{ replace: true \}\)/)
})


test('signed-in users visiting login or signup redirect to dashboard', () => {
  assert.match(source, /function useRedirectAuthenticatedUser\(targetRoute = DEFAULT_LOGIN_NEXT_ROUTE\)/)
  assert.match(source, /const \{ data \} = await supabase\.auth\.getSession\(\)/)
  assert.match(source, /if \(data\.session\?\.access_token\) \{[\s\S]*if \(targetRoute\) \{[\s\S]*navigate\(targetRoute, \{ replace: true \}\)/)
  assert.match(signupPageSource, /const safeNextRoute = safeDesktopState[\s\S]*\? desktopLoginRoute\(safeDesktopState\)[\s\S]*: getSafeAuthNextRoute\(searchParams\.get\('next'\) \|\| location\.state\?\.next\)[\s\S]*const checkingSession = useRedirectAuthenticatedUser\(safeNextRoute\)/)
  assert.match(loginPageSource, /const safeNextRoute = getSafeAuthNextRoute\(searchParams\.get\('next'\) \|\| location\.state\?\.next\)[\s\S]*const checkingSession = useRedirectAuthenticatedUser\(safeDesktopState \? '' : safeNextRoute\)/)
  assert.match(signupPageSource, /if \(checkingSession\) \{[\s\S]*<p className="auth-message info">Checking session\.\.\.<\/p>/)
  assert.match(loginPageSource, /if \(checkingSession\) \{[\s\S]*<p className="auth-message info">Checking session\.\.\.<\/p>/)
})


test('desktop login handoff is isolated to the /auth/desktop-login entry path', () => {
  assert.match(appSource, /<Route path="\/auth\/desktop-login" element=\{<AuthDesktopLoginPage backendUrl=\{BACKEND_URL\} \/>\} \/>/)
  assert.match(appSource, /<Route path="\/auth\/login" element=\{<AuthLoginPage backendUrl=\{BACKEND_URL\} \/>\} \/>/)
  assert.match(appSource, /<Route path="\/auth\/signup" element=\{<AuthSignupPage backendUrl=\{BACKEND_URL\} \/>\} \/>/)
  assert.match(source, /const DESKTOP_CALLBACK_URL = 'saiia:\/\/auth\/callback'/)
  assert.equal(source.includes('const DESKTOP_STATE_PATTERN = /^[A-Za-z0-9._~-]{16,256}$/'), true)
  assert.match(source, /function desktopLoginRoute\(state\) \{[\s\S]*return `\/auth\/desktop-login\?state=\$\{encodeURIComponent\(state\)\}`/)
  assert.match(source, /function desktopSignupRoute\(state\) \{[\s\S]*return `\/auth\/signup\?desktop_state=\$\{encodeURIComponent\(state\)\}`/)
  assert.match(source, /export function AuthDesktopLoginPage\(\{ backendUrl \}\)/)
  assert.match(source, /const state = getSafeDesktopState\(searchParams\.get\('state'\)\)/)
  assert.match(source, /<AuthLoginPage backendUrl=\{backendUrl\} desktopState=\{state\} desktopError=\{error\} \/>/)
})


test('desktop handoff passes only handoff code and state to Electron callback URL', () => {
  assert.match(source, /async function openDesktopHandoff\(session, state, backendUrl\)/)
  assert.match(source, /createDesktopHandoff\(session\.access_token, session\.refresh_token, state, \{ backendUrl \}\)/)
  assert.match(source, /const callbackUrl = new URL\(DESKTOP_CALLBACK_URL\)/)
  assert.match(source, /callbackUrl\.searchParams\.set\('handoff_code', handoffCode\)/)
  assert.match(source, /callbackUrl\.searchParams\.set\('state', state\)/)
  assert.match(source, /window\.location\.href = callbackUrl\.toString\(\)/)
  assert.doesNotMatch(source.match(/async function openDesktopHandoff[\s\S]*?\n\}/)?.[0] || '', /access_token.*searchParams|refresh_token.*searchParams|session\.access_token.*searchParams|session\.refresh_token.*searchParams/)
})


test('desktop mode preserves email password and Google auth without changing normal website redirects', () => {
  assert.match(signupPageSource, /const safeDesktopState = getSafeDesktopState\(desktopState \|\| searchParams\.get\('desktop_state'\)\)/)
  assert.match(signupPageSource, /const safeNextRoute = safeDesktopState[\s\S]*\? desktopLoginRoute\(safeDesktopState\)[\s\S]*: getSafeAuthNextRoute/)
  assert.match(signupPageSource, /emailRedirectTo: getAuthRedirectUrl\(safeDesktopState\)/)
  assert.match(signupPageSource, /if \(safeDesktopState && data\.session\) \{[\s\S]*await openDesktopHandoff\(data\.session, safeDesktopState, backendUrl\)/)
  assert.match(loginPageSource, /if \(safeDesktopState\) \{[\s\S]*await openDesktopHandoff\(data\.session, safeDesktopState, backendUrl\)/)
  assert.match(loginPageSource, /fetchCurrentUser\(data\.session\.access_token, \{ backendUrl \}\)[\s\S]*navigate\(safeNextRoute, \{ replace: true \}\)/)
  assert.match(source, /async function startGoogleLogin\(desktopState = ''\) \{[\s\S]*provider: 'google'[\s\S]*redirectTo: getAuthRedirectUrl\(desktopState\)/)
  assert.match(signupPageSource, /async function handleGoogleLogin\(\) {[\s\S]*const \{ error \} = await startGoogleLogin\(safeDesktopState\)[\s\S]*form\.setError\(error\.message \|\| 'Google login could not be started\.'\)/)
  assert.match(loginPageSource, /async function handleGoogleLogin\(\) {[\s\S]*const \{ error \} = await startGoogleLogin\(safeDesktopState\)[\s\S]*form\.setError\(error\.message \|\| 'Google login could not be started\.'\)/)
  assert.match(signupPageSource, /onClick=\{handleGoogleLogin\}/)
  assert.match(loginPageSource, /onClick=\{handleGoogleLogin\}/)
})


test('protected dashboard redirect returns to dashboard after login', () => {
  assert.match(source, /const nextRoute = getSafeAuthNextRoute\(location\.pathname\)/)
  assert.match(source, /state=\{\{ authMessage: LOGIN_REQUIRED_MESSAGE, next: nextRoute \}\}/)
})


test('unsafe external auth next URLs are ignored by allowlist', () => {
  assert.match(source, /const SAFE_AUTH_NEXT_ROUTES = new Set\(\['\/auth\/dashboard', '\/auth\/status'\]\)/)
  assert.match(source, /return SAFE_AUTH_NEXT_ROUTES\.has\(route\) \? route : fallback/)
  assert.match(openDesktopHandoffSource, /window\.location\.href = callbackUrl\.toString\(\)/)
  assert.doesNotMatch(sourceWithoutDesktopHandoff, /window\.location\s*=|window\.location\.href\s*=|location\.href\s*=|new URL\(.*next/)
})


test('protected dashboard shows safe user identity and avoids token state', () => {
  assert.match(source, /export function AuthDashboardPage\(\{ backendUrl \}\)/)
  assert.match(source, /fetchCurrentUser\(data\.session\.access_token, \{ backendUrl \}\)/)
  assert.match(source, /fetchInterviewSessions,/)
  assert.match(source, /\{user\.email \|\| user\.user_id\}/)
  assert.match(source, /\{user\.role && <span>\{user\.role\}<\/span>\}/)
  assert.doesNotMatch(source, /setSessionToken|useState\(['"]unit-test-access-token|accessToken, setAccessToken/)
})


test('dashboard loads session history and transcript controls with separate loading, error, and empty states', () => {
  assert.match(dashboardPageSource, /const \[sessionHistory, setSessionHistory\] = useState\(\[\]\)/)
  assert.match(dashboardPageSource, /const \[sessionHistoryLoading, setSessionHistoryLoading\] = useState\(true\)/)
  assert.match(dashboardPageSource, /const \[sessionHistoryError, setSessionHistoryError\] = useState\(''\)/)
  assert.match(dashboardPageSource, /const \[openTranscriptSessionId, setOpenTranscriptSessionId\] = useState\(''\)/)
  assert.match(dashboardPageSource, /const \[transcriptEntries, setTranscriptEntries\] = useState\(\[\]\)/)
  assert.match(dashboardPageSource, /const \[transcriptLoading, setTranscriptLoading\] = useState\(false\)/)
  assert.match(dashboardPageSource, /const \[transcriptError, setTranscriptError\] = useState\(''\)/)
  assert.match(dashboardPageSource, /const \[openNotesSessionId, setOpenNotesSessionId\] = useState\(''\)/)
  assert.match(dashboardPageSource, /const \[sessionNotes, setSessionNotes\] = useState\(null\)/)
  assert.match(dashboardPageSource, /const \[notesLoading, setNotesLoading\] = useState\(false\)/)
  assert.match(dashboardPageSource, /const \[notesError, setNotesError\] = useState\(''\)/)
  assert.match(source, /function formatSessionTime\(value\)/)
  assert.match(source, /function formatSessionContextLine\(session\)/)
  assert.match(source, /function formatSessionDisplayContextLine\(session\)/)
  assert.match(source, /function formatTranscriptDisplayMetaLine\(entry\)/)
  assert.match(source, /function formatInterviewNotesMetaLine\(notes\)/)
  assert.match(source, /function triggerTextDownload\(filename, content, format\)/)
  assert.match(dashboardPageSource, /const controller = new AbortController\(\)/)
  assert.match(dashboardPageSource, /const \{ data, error: sessionError \} = await supabase\.auth\.getSession\(\)/)
  assert.match(dashboardPageSource, /fetchInterviewSessions\(data\.session\.access_token, \{/)
  assert.match(dashboardPageSource, /limit: 20,[\s\S]*page: 1,[\s\S]*signal,/)
  assert.match(dashboardPageSource, /Loading interview sessions\.\.\./)
  assert.match(dashboardPageSource, /sessionHistoryError \? \(/)
  assert.match(dashboardPageSource, /Could not load interview sessions\. Please try again\./)
  assert.match(dashboardPageSource, /Retry session history/)
  assert.match(dashboardPageSource, /No interview sessions yet\./)
  assert.match(dashboardPageSource, /aria-label="Interview session history"/)
  assert.match(dashboardPageSource, /session\.title \|\| session\.target_role \|\| session\.company_name \|\| 'Untitled session'/)
  assert.match(dashboardPageSource, /className="auth-session-history__title"/)
  assert.match(dashboardPageSource, /className="auth-session-history__meta">\{formatSessionDisplayContextLine\(session\)\}/)
  assert.match(dashboardPageSource, /className="auth-session-history__line">Status: \{session\.status \|\| 'unknown'\}/)
  assert.match(dashboardPageSource, /className="auth-session-history__line">Started: \{formatSessionTime\(session\.started_at\)\}/)
  assert.match(dashboardPageSource, /Ended: \{session\.ended_at \? formatSessionTime\(session\.ended_at\) : 'Not ended yet'\}/)
  assert.match(dashboardPageSource, /session\.job_description_preview \? \(/)
  assert.match(dashboardPageSource, /Context: \{session\.job_description_preview\}/)
  assert.match(dashboardPageSource, /handleTranscriptToggle\(session\.id\)/)
  assert.match(dashboardPageSource, /handleNotesGenerate\(session\.id\)/)
  assert.match(dashboardPageSource, /handleNotesToggle\(session\.id\)/)
  assert.match(dashboardPageSource, /handleTranscriptDownload\(session\.id, 'txt'\)/)
  assert.match(dashboardPageSource, /handleTranscriptDownload\(session\.id, 'md'\)/)
  assert.match(
    dashboardPageSource,
    /async function handleNotesToggle\(sessionId\) \{[\s\S]*setOpenNotesSessionId\(normalizedSessionId\)\s+setSessionNotes\(null\)\s+setNotesError\(''\)\s+setNotesLoading\(true\)/,
  )
  assert.match(
    dashboardPageSource,
    /async function handleNotesGenerate\(sessionId, forceRegenerate = false\) \{[\s\S]*setNotesGenerateKey\(normalizedSessionId\)\s+setOpenNotesSessionId\(normalizedSessionId\)\s+setSessionNotes\(null\)\s+setNotesError\(''\)\s+setNotesLoading\(true\)/,
  )
  assert.match(dashboardPageSource, /Generate AI Notes/)
  assert.match(dashboardPageSource, /View AI Notes/)
  assert.match(dashboardPageSource, /Loading AI notes\.\.\./)
  assert.match(dashboardPageSource, /No AI notes yet\. Generate AI Notes to create them\./)
  assert.match(dashboardPageSource, /Could not load AI notes\. Please try again\./)
  assert.match(dashboardPageSource, /Retry AI Notes/)
  assert.match(dashboardPageSource, /Regenerate AI Notes/)
  assert.match(dashboardPageSource, /formatInterviewNotesMetaLine\(sessionNotes\)/)
  assert.match(dashboardPageSource, /View transcript/)
  assert.match(dashboardPageSource, /Download \.txt/)
  assert.match(dashboardPageSource, /Download \.md/)
  assert.match(dashboardPageSource, /Loading transcript\.\.\./)
  assert.match(dashboardPageSource, /Could not load transcript entries\. Please try again\./)
  assert.match(dashboardPageSource, /No transcript entries yet\./)
  assert.match(dashboardPageSource, /Question:/)
  assert.match(dashboardPageSource, /Answer:/)
  assert.match(dashboardPageSource, /formatTranscriptDisplayMetaLine\(entry\)/)
  assert.match(cssSource, /\.auth-session-history__transcript-entry \.auth-session-history__line \{\s+white-space: pre-wrap;/)
  assert.match(cssSource, /\.auth-session-history__notes-markdown \{\s+margin: 0;\s+white-space: pre-wrap;/)
  assert.match(dashboardPageSource, /\) : sessionHistoryError \? \([\s\S]*Retry session history[\s\S]*\) : sessionHistory.length \? \([\s\S]*\) : \(/)
  assert.doesNotMatch(dashboardPageSource, /No target role'} - \{session\.company_name \|\| 'No company'/)
})


test('dashboard logout clears session path and returns to login', () => {
  assert.match(dashboardLogoutSource, /async function handleLogout\(\) \{[\s\S]*if \(!supabase \|\| logoutPending\) \{[\s\S]*return/)
  assert.match(dashboardLogoutSource, /setLogoutPending\(true\)[\s\S]*const \{ error: signOutError \} = await supabase\.auth\.signOut\(\)/)
  assert.match(dashboardLogoutSource, /if \(signOutError\) \{[\s\S]*setLogoutError\('Sign out failed\. Please try again\.'\)[\s\S]*setLogoutPending\(false\)[\s\S]*return[\s\S]*\}[\s\S]*invalidateBootstrap\(\)/)
  assert.match(dashboardLogoutSource, /navigate\('\/auth\/login', \{[\s\S]*state: \{ authMessage: 'Signed out\.' \}/)
})


test('dashboard logout failure is generic and preserves bootstrap state', () => {
  assert.match(dashboardPageSource, /const \[logoutError, setLogoutError\] = useState\(''\)/)
  assert.doesNotMatch(dashboardLogoutSource, /setLogoutError\(.*\.message/)
  assert.match(dashboardLogoutSource, /const \{ error: signOutError \} = await supabase\.auth\.signOut\(\)/)
  assert.match(dashboardLogoutSource, /catch \{\s+setLogoutError\('Sign out failed\. Please try again\.'\)\s+setLogoutPending\(false\)/)
  assert.doesNotMatch(dashboardLogoutSource, /setLogoutPending\(true\)\s+invalidateBootstrap\(\)/)
})


test('logout buttons are disabled while signout is pending', () => {
  assert.match(statusPageSource, /const \[logoutPending, setLogoutPending\] = useState\(false\)/)
  assert.match(dashboardPageSource, /const \[logoutPending, setLogoutPending\] = useState\(false\)/)
  assert.match(statusPageSource, /disabled=\{!supabase \|\| loading \|\| logoutPending\}/)
  assert.match(dashboardPageSource, /disabled=\{!supabase \|\| logoutPending\}/)
  assert.match(source, /logoutPending \? 'Signing out\.\.\.' : 'Logout'/)
})


test('status logout resolved-error is generic and preserves bootstrap state', () => {
  assert.match(statusLogoutSource, /const \{ error: signOutError \} = await supabase\.auth\.signOut\(\)/)
  assert.match(statusLogoutSource, /if \(signOutError\) \{[\s\S]*setUserError\('Sign out failed\. Please try again\.'\)[\s\S]*setLogoutPending\(false\)[\s\S]*return[\s\S]*\}[\s\S]*invalidateBootstrap\(\)/)
  assert.match(statusLogoutSource, /catch \{\s+setUserError\('Sign out failed\. Please try again\.'\)\s+setLoading\(false\)\s+setLogoutPending\(false\)/)
  assert.doesNotMatch(statusLogoutSource, /setUserError\(.*\.message/)
  assert.doesNotMatch(statusLogoutSource, /setLogoutPending\(true\)\s+setLoading\(true\)\s+setUserError\(''\)\s+invalidateBootstrap\(\)/)
})


test('desktop-local routes remain unprotected while auth dashboard is protected', () => {
  assert.match(appSource, /<Route path="\/auth\/dashboard" element=\{<AuthDashboardPage backendUrl=\{BACKEND_URL\} \/>\} \/>/)
  assert.match(appSource, /<Route path="\/auth\/resume" element=\{<AuthResumePage backendUrl=\{BACKEND_URL\} \/>\} \/>/)
  assert.match(appSource, /<Route path="\/" element=\{<MainWindow \/>\} \/>/)
  assert.match(appSource, /<Route path="\/profile-setup" element=\{<ProfileSetupForm \/>\} \/>/)
})


test('cloud resume page is protected and loads current plus review candidate state', () => {
  assert.match(resumePageSource, /<RequireAuth backendUrl=\{backendUrl\}>/)
  assert.match(resumePageSource, /const controller = new AbortController\(\)/)
  assert.match(resumePageSource, /fetchCurrentCloudResume\(token, \{ backendUrl, signal \}\)/)
  assert.match(resumePageSource, /fetchReviewCandidate\(token, \{ backendUrl, signal \}\)/)
  assert.match(resumePageSource, /if \(ignore\) \{[\s\S]*setCurrentResume/)
  assert.match(resumePageSource, /controller\.abort\(\)/)
  assert.match(resumePageSource, /current\.ready \? current\.resume : null/)
  assert.match(resumePageSource, /No active ready resume yet\./)
})


test('cloud resume page renders no active ready message only once', () => {
  assert.equal((resumePageSource.match(/No active ready resume yet\./g) || []).length, 1)
  assert.match(resumePageSource, /setMessage\(current\.ready \? 'A ready resume is active for cloud answers\.' : ''\)/)
})


test('cloud resume upload validates files and calls upload extract status flow', () => {
  assert.match(source, /const MAX_RESUME_FILE_BYTES = 5 \* 1024 \* 1024/)
  assert.match(source, /const SUPPORTED_RESUME_EXTENSIONS = new Set\(\['\.pdf', '\.docx', '\.txt'\]\)/)
  assert.match(source, /function validateCloudResumeFile\(file\)/)
  assert.match(resumePageSource, /const fileInputRef = useRef\(null\)/)
  assert.match(resumePageSource, /function clearSelectedResumeFile\(\) \{[\s\S]*setFile\(null\)[\s\S]*fileInputRef\.current\.value = ''/)
  assert.match(resumePageSource, /disabled=\{uploadDisabled\}/)
  assert.match(resumePageSource, /disabled=\{busy\}/)
  assert.match(resumePageSource, /ref=\{fileInputRef\}/)
  assert.match(resumePageSource, /uploadCloudResume\(token, file, \{ backendUrl \}\)/)
  assert.match(resumePageSource, /const uploadedStatus = await fetchCloudResumeStatus\(token, uploaded\.id, \{ backendUrl \}\)/)
  assert.match(resumePageSource, /if \(uploadedStatus\.status !== 'uploaded'\) \{[\s\S]*return/)
  assert.match(resumePageSource, /extractCloudResume\(token, uploaded\.id, \{ backendUrl \}\)/)
  assert.match(resumePageSource, /clearSelectedResumeFile\(\)[\s\S]*setPhase\('needs_review'\)/)
  assert.match(resumePageSource, /Extraction failed\. Try again or upload another file\./)
  assert.match(resumePageSource, /catch \(resumeError\) \{[\s\S]*setMessage\(''\)/)
})


test('cloud resume review form confirms edited normalized fields without raw resume text', () => {
  assert.match(source, /const CLOUD_PROFILE_FIELDS = \[/)
  assert.match(source, /\['full_name', 'Full name', 'input'\]/)
  assert.match(source, /\['achievements', 'Achievements', 'textarea'\]/)
  assert.match(resumePageSource, /CLOUD_PROFILE_FIELDS\.map\(\(\[field, label, kind\]\)/)
  assert.match(resumePageSource, /const \[confirmPending, setConfirmPending\] = useState\(false\)/)
  assert.match(resumePageSource, /const confirmControllerRef = useRef\(null\)/)
  assert.match(resumePageSource, /confirmControllerRef\.current\?\.abort\(\)/)
  assert.match(resumePageSource, /if \(confirmPending\) \{[\s\S]*return\s+\}/)
  assert.match(resumePageSource, /setConfirmPending\(true\)[\s\S]*confirmCloudResume/)
  assert.match(resumePageSource, /finally \{[\s\S]*setConfirmPending\(false\)/)
  assert.match(resumePageSource, /draftProfile && phase !== 'confirmed'/)
  assert.match(resumePageSource, /confirmPending \? 'Saving reviewed profile\.\.\.' : 'Confirm Reviewed Profile'/)
  assert.match(resumePageSource, /confirmCloudResume\([\s\S]*normalizeCloudProfile\(draftProfile\)/)
  assert.match(resumePageSource, /fetchCurrentCloudResume\(token, \{ backendUrl, signal: confirmController\.signal \}\)/)
  assert.match(resumePageSource, /Resume confirmed and activated\./)
  assert.match(resumePageSource, /catch \(confirmError\) \{[\s\S]*?setMessage\(''\)/)
  assert.doesNotMatch(source.match(/const CLOUD_PROFILE_FIELDS = \[[\s\S]*?\n\]/)?.[0] || '', /raw_resume_text/)
  assert.doesNotMatch(resumePageSource, /console\.log|setAccessToken|sessionToken/)
})


test('cloud resume page refreshes current state after confirmation', () => {
  assert.match(resumePageSource, /setPhase\('confirmed'\)/)
  assert.match(resumePageSource, /Resume confirmed and activated\./)
  assert.match(resumePageSource, /Resume confirmed\. Refresh to load active resume status\./)
  assert.match(resumePageSource, /confirmed\.ready && current\.ready/)
  assert.match(resumePageSource, /setCurrentResume\(current\.ready \? current\.resume : null\)/)
  assert.match(resumePageSource, /setResumeRecord\(\(currentRecord\) =>/)
  assert.match(resumeRefreshCatchSource, /Refresh to load active resume status/)
  assert.doesNotMatch(resumeRefreshCatchSource, /setCurrentResume\(null\)/)
  assert.doesNotMatch(resumeRefreshCatchSource, /Could not confirm/)
  assert.match(resumePageSource, /draftProfile && phase !== 'confirmed'/)
  assert.doesNotMatch(resumePageSource, /setCurrentResume\(.*confirmed|status: 'ready'|is_active: true/)
})


test('cloud resume page supports delete and rebuild lifecycle controls safely', () => {
  assert.match(source, /deleteCloudResume,/)
  assert.match(source, /rebuildCloudResumeIndex,/)
  assert.match(resumePageSource, /const \[deletePending, setDeletePending\] = useState\(false\)/)
  assert.match(resumePageSource, /const \[rebuildPending, setRebuildPending\] = useState\(false\)/)
  assert.match(resumePageSource, /async function handleDeleteResume\(targetResumeArg = null\)/)
  assert.match(resumePageSource, /const targetResume = targetResumeArg \|\| currentResume \|\| reviewCandidate \|\| resumeRecord/)
  assert.match(resumePageSource, /Delete this cloud resume \(\$\{resumeLabel\}\)\?/)
  assert.match(resumePageSource, /deleteCloudResume\(token, targetResume\.id, \{ backendUrl \}\)/)
  assert.match(resumePageSource, /if \(currentResume\?\.id === targetResume\.id\) \{[\s\S]*setCurrentResume\(null\)/)
  assert.match(resumePageSource, /if \(reviewCandidate\?\.id === targetResume\.id\) \{[\s\S]*setReviewCandidate\(null\)/)
  assert.match(resumeDeleteSource, /if \(resumeRecord\?\.id === targetResume\.id\) \{[\s\S]*setResumeRecord\(null\)[\s\S]*clearSelectedResumeFile\(\)/)
  assert.doesNotMatch(resumeDeleteSource, /setExtractionAttempt\(null\)[\s\S]*clearSelectedResumeFile\(\)/)
  assert.match(resumePageSource, /Resume deleted\./)
  assert.match(resumePageSource, /onClick=\{\(\) => handleDeleteResume\(currentResume\)\}/)
  assert.match(resumePageSource, /onClick=\{\(\) => handleDeleteResume\(reviewCandidate\)\}/)
  assert.match(resumePageSource, /onClick=\{\(\) => handleDeleteResume\(resumeRecord \|\| reviewCandidate\)\}/)
  assert.match(resumePageSource, /async function handleRebuildIndex\(\)/)
  assert.match(resumePageSource, /rebuildCloudResumeIndex\(token, currentResume\.id, \{ backendUrl \}\)/)
  assert.match(resumePageSource, /fetchCurrentCloudResume\(token, \{ backendUrl \}\)/)
  assert.match(resumePageSource, /Resume index rebuilt\./)
  assert.match(resumePageSource, /disabled=\{busy \|\| !currentResume\.is_active\}/)
  assert.match(resumePageSource, /deletePending \? 'Deleting resume\.\.\.' : 'Delete Resume'/)
  assert.match(resumePageSource, /rebuildPending \? 'Rebuilding index\.\.\.' : 'Rebuild Index'/)
})

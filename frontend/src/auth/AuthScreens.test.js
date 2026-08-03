import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'


const source = readFileSync(new URL('./AuthScreens.jsx', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const appSource = readFileSync(new URL('../App.jsx', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const signupPageSource = source.match(/export function AuthSignupPage[\s\S]*?export function AuthLoginPage/)?.[0] || ''
const loginPageSource = source.match(/export function AuthLoginPage[\s\S]*?export function AuthForgotPasswordPage/)?.[0] || ''
const statusPageSource = source.match(/export function AuthStatusPage[\s\S]*?function RequireAuth/)?.[0] || ''
const dashboardPageSource = source.match(/export function AuthDashboardPage[\s\S]*?export function AuthLogoutPage/)?.[0] || ''
const statusLogoutSource = statusPageSource.match(/async function handleLogout\(\) \{[\s\S]*?\n  \}\n\n  return \(/)?.[0] || ''
const dashboardLogoutSource = dashboardPageSource.match(/async function handleLogout\(\) \{[\s\S]*?\n  \}\n\n  return \(/)?.[0] || ''

assert.ok(signupPageSource, 'AuthSignupPage source slice should be found')
assert.ok(loginPageSource, 'AuthLoginPage source slice should be found')
assert.ok(statusPageSource, 'AuthStatusPage source slice should be found')
assert.ok(dashboardPageSource, 'AuthDashboardPage source slice should be found')
assert.ok(statusLogoutSource, 'AuthStatusPage handleLogout source slice should be found')
assert.ok(dashboardLogoutSource, 'AuthDashboardPage handleLogout source slice should be found')


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
  assert.match(source, /if \(data\.session\?\.access_token\) \{\s+navigate\(targetRoute, \{ replace: true \}\)/)
  assert.match(signupPageSource, /const safeNextRoute = getSafeAuthNextRoute\(searchParams\.get\('next'\) \|\| location\.state\?\.next\)[\s\S]*const checkingSession = useRedirectAuthenticatedUser\(safeNextRoute\)/)
  assert.match(loginPageSource, /const safeNextRoute = getSafeAuthNextRoute\(searchParams\.get\('next'\) \|\| location\.state\?\.next\)[\s\S]*const checkingSession = useRedirectAuthenticatedUser\(safeNextRoute\)/)
  assert.match(signupPageSource, /if \(checkingSession\) \{[\s\S]*<p className="auth-message info">Checking session\.\.\.<\/p>/)
  assert.match(loginPageSource, /if \(checkingSession\) \{[\s\S]*<p className="auth-message info">Checking session\.\.\.<\/p>/)
})


test('protected dashboard redirect returns to dashboard after login', () => {
  assert.match(source, /const nextRoute = getSafeAuthNextRoute\(location\.pathname\)/)
  assert.match(source, /state=\{\{ authMessage: LOGIN_REQUIRED_MESSAGE, next: nextRoute \}\}/)
})


test('unsafe external auth next URLs are ignored by allowlist', () => {
  assert.match(source, /const SAFE_AUTH_NEXT_ROUTES = new Set\(\['\/auth\/dashboard', '\/auth\/status'\]\)/)
  assert.match(source, /return SAFE_AUTH_NEXT_ROUTES\.has\(route\) \? route : fallback/)
  assert.doesNotMatch(source, /window\.location\s*=|location\.href\s*=|new URL\(.*next/)
})


test('protected dashboard shows safe user identity and avoids token state', () => {
  assert.match(source, /export function AuthDashboardPage\(\{ backendUrl \}\)/)
  assert.match(source, /fetchCurrentUser\(data\.session\.access_token, \{ backendUrl \}\)/)
  assert.match(source, /\{user\.email \|\| user\.user_id\}/)
  assert.match(source, /\{user\.role && <span>\{user\.role\}<\/span>\}/)
  assert.doesNotMatch(source, /setSessionToken|useState\(['"]unit-test-access-token|accessToken, setAccessToken/)
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
  assert.match(appSource, /<Route path="\/" element=\{<MainWindow \/>\} \/>/)
  assert.match(appSource, /<Route path="\/profile-setup" element=\{<ProfileSetupForm \/>\} \/>/)
})

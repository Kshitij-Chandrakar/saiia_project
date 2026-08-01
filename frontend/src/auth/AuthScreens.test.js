import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'


const source = readFileSync(new URL('./AuthScreens.jsx', import.meta.url), 'utf8')
const appSource = readFileSync(new URL('../App.jsx', import.meta.url), 'utf8')


test('bootstrap operation is invalidated on logout and unmount', () => {
  assert.match(source, /const bootstrapOperationRef = useRef\(0\)/)
  assert.match(source, /return \(\) => \{\s+bootstrapOperationRef\.current \+= 1\s+\}/)
  assert.match(source, /async function handleLogout\(\) \{[\s\S]*bootstrapOperationRef\.current \+= 1/)
})


test('bootstrap result and loading updates require active operation', () => {
  assert.match(source, /if \(bootstrapLoading\) \{\s+return\s+\}/)
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
  assert.match(source, /Session expired or signed out\. Please log in\./)
})


test('login redirects to dashboard by default after verification', () => {
  assert.match(source, /const DEFAULT_LOGIN_NEXT_ROUTE = '\/auth\/dashboard'/)
  assert.match(source, /const \[searchParams\] = useSearchParams\(\)/)
  assert.match(source, /navigate\(\s+getSafeAuthNextRoute\(searchParams\.get\('next'\) \|\| location\.state\?\.next\),\s+\{ replace: true \}\s+\)/)
})


test('protected dashboard redirect returns to dashboard after login', () => {
  assert.match(source, /const nextRoute = getSafeAuthNextRoute\(location\.pathname\)/)
  assert.match(source, /state=\{\{ authMessage: error \|\| 'Session expired or signed out\. Please log in\.', next: nextRoute \}\}/)
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
  assert.match(source, /async function handleLogout\(\) \{[\s\S]*supabase\.auth\.signOut\(\)/)
  assert.match(source, /navigate\('\/auth\/login', \{[\s\S]*state: \{ authMessage: 'Signed out\.' \}/)
})


test('desktop-local routes remain unprotected while auth dashboard is protected', () => {
  assert.match(appSource, /<Route path="\/auth\/dashboard" element=\{<AuthDashboardPage backendUrl=\{BACKEND_URL\} \/>\} \/>/)
  assert.match(appSource, /<Route path="\/" element=\{<MainWindow \/>\} \/>/)
  assert.match(appSource, /<Route path="\/profile-setup" element=\{<ProfileSetupForm \/>\} \/>/)
})

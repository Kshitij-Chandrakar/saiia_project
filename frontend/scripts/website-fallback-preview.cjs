// Local synthetic review only. No credentials, database or provider forwarding.
const http = require('node:http')
const fs = require('node:fs')
const path = require('node:path')
const dist = path.resolve(__dirname, '../../tmp/website-batch1-production')
const cases = {
  render: ['/auth/resume', 'Rendering failure'],
  startup: ['/auth/login', 'Entry-script failure'],
  onboarding: ['/auth/onboarding', 'Onboarding failure, then Retry'],
  logout: ['/auth/logout', 'Sign-out failure, then Retry'],
  unsubscribe: ['/unsubscribe?token=synthetic-review-link', 'Unsubscribe failure, then Retry'],
  missing: ['/unsubscribe', 'Unsubscribe after link loss'],
  login: ['/auth/login', 'Safe sign-in error (submit synthetic fields)'],
  guard: ['/auth/dashboard', 'Safe account-verification error'],
}
let selected = 'render'
let attempts = 0
let generation = 0
const user = { id: 'synthetic-owner', email: 'candidate@example.test' }
const token = Buffer.from('{}').toString('base64url') + '.' + Buffer.from(JSON.stringify({ sub: user.id, exp: 2524608000 })).toString('base64url') + '.synthetic'
const session = { access_token: token, refresh_token: 'synthetic-refresh', expires_at: 2524608000, expires_in: 360000000, token_type: 'bearer', user }
const mime = { '.html': 'text/html; charset=utf-8', '.js': 'application/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.ttf': 'font/ttf', '.jpg': 'image/jpeg' }
const csp = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self' http://127.0.0.1:5309; media-src 'self'; frame-src 'none'; form-action 'self'; base-uri 'self'"
const website = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1:5301')
  res.setHeader('Cache-Control', 'no-store')
  res.setHeader('Content-Security-Policy', csp)
  if (url.pathname === '/__review') {
    res.setHeader('Content-Type', 'text/html; charset=utf-8')
    return res.end(`<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>Batch 1 local review</title><body style="margin:40px;font:16px/1.7 Arial;background:#eef4ff;color:#10234f"><h1>Intervucopilot · Batch 1 review</h1><p>Synthetic local fixtures only. Choose one scenario at a time. Retry recovers locally.</p><ul>${Object.entries(cases).map(([key, value]) => `<li><a href="/__review/open?case=${key}">${value[1]}</a></li>`).join('')}</ul><p>For the JavaScript-disabled view, disable JavaScript in browser developer tools and reload any page. Re-enable it before continuing.</p><p>Return to <a href="/__review">this review index</a> to reset a scenario. No provider requests are forwarded. Stop with Ctrl+C in the preview process.</p>`)
  }
  if (url.pathname === '/__review/open') {
    selected = Object.hasOwn(cases, url.searchParams.get('case')) ? url.searchParams.get('case') : 'render'
    attempts = 0
    generation++
    res.writeHead(302, { Location: cases[selected][0] })
    return res.end()
  }
  if (url.pathname === '/__review/blocked-entry.js') { res.writeHead(404); return res.end() }
  if (url.pathname.startsWith('/api/')) {
    res.writeHead(503, { 'Content-Type': 'application/json' })
    return res.end(JSON.stringify({ detail: 'Synthetic preview only' }))
  }
  let file
  try { file = path.resolve(dist, '.' + decodeURIComponent(url.pathname)) } catch { res.writeHead(400); return res.end() }
  if (file !== dist && !file.startsWith(dist + path.sep)) { res.writeHead(403); return res.end() }
  if (fs.existsSync(file) && fs.statSync(file).isFile()) {
    res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream')
    return fs.createReadStream(file).pipe(res)
  }
  let html = fs.readFileSync(path.join(dist, 'index.html'), 'utf8')
  const signedIn = ['render', 'onboarding', 'logout', 'guard'].includes(selected)
  // Only synthetic state is inserted; real website storage is on another origin.
  html = html.replace('<head>', `<head><script>if(sessionStorage.getItem('review-generation')!==${JSON.stringify(String(generation))}){localStorage.removeItem('intervucopilot.website-logout-intent');${signedIn ? `localStorage.setItem('sb-127-auth-token',${JSON.stringify(JSON.stringify(session))});` : "localStorage.removeItem('sb-127-auth-token');"}sessionStorage.setItem('review-generation',${JSON.stringify(String(generation))});}</script>`)
  // A scenario entry resets browser-only fixture state; ordinary reload does not.
  if (selected === 'startup' && attempts++ === 0) html = html.replace(/src="\/assets\/[^" ]+\.js"/, 'src="/__review/blocked-entry.js"')
  res.setHeader('Content-Type', 'text/html; charset=utf-8')
  res.end(html)
})
const api = http.createServer((req, res) => {
  res.setHeader('Access-Control-Allow-Origin', 'http://127.0.0.1:5301')
  res.setHeader('Access-Control-Allow-Headers', 'authorization,content-type,apikey,x-client-info,x-supabase-api-version,idempotency-key')
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,PATCH,OPTIONS')
  res.setHeader('Cache-Control', 'no-store')
  if (req.method === 'OPTIONS') { res.writeHead(204); return res.end() }
  const pathname = new URL(req.url, 'http://127.0.0.1:5309').pathname
  let status = 200, value = {}
  if (pathname === '/auth/v1/logout') { status = attempts++ === 0 ? 500 : 204; value = { message: 'synthetic private signout error' } }
  else if (pathname === '/auth/v1/token') { status = 400; value = { error_code: 'unknown_code', message: 'synthetic private provider error' } }
  else if (pathname === '/api/auth/me') {
    status = selected === 'guard' ? 503 : 200
    value = selected === 'guard' ? { detail: 'synthetic private infrastructure error' } : { user_id: user.id, email: selected === 'render' ? { private: 'deliberate render fault' } : user.email }
  }
  else if (pathname === '/api/auth/profile/bootstrap') value = { profile_exists: true, settings_exists: true }
  else if (pathname === '/api/onboarding') {
    status = selected === 'onboarding' && attempts++ === 0 ? 503 : 200
    value = status === 503 ? { detail: 'synthetic private migration error' } : { onboarding_current_step: 2, onboarding_completed_at: null }
  }
  else if (pathname === '/api/email/unsubscribe') {
    status = selected === 'unsubscribe' && attempts++ === 0 ? 503 : 200
    value = status === 503 ? { detail: 'synthetic private storage error' } : { success: true }
  }
  else if (pathname === '/api/resumes/current') value = { ready: false, resume: null }
  else if (pathname === '/api/resumes/review-candidate') value = { has_candidate: false, resume: null }
  else if (['/api/resumes', '/api/interview-sessions', '/api/job-contexts'].includes(pathname)) value = { items: [], page: 1, limit: 20 }
  else { status = 503; value = { detail: 'synthetic fixture has no response for this operation' } }
  req.resume()
  res.writeHead(status, { 'Content-Type': 'application/json' })
  res.end(status === 204 ? '' : JSON.stringify(value))
})
website.listen(5301, '127.0.0.1')
api.listen(5309, '127.0.0.1')
console.log('Synthetic Batch 1 previews: http://127.0.0.1:5301/__review')
for (const server of [website, api]) server.on('error', error => { console.error(error.code); process.exitCode = 1; website.close(); api.close() })
process.on('SIGINT', () => { website.close(); api.close() })

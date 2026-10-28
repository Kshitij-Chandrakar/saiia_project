// Loopback-only review of the production build. All API responses are synthetic.
const http = require('node:http')
const fs = require('node:fs')
const path = require('node:path')
const dist = path.resolve(__dirname, '../../tmp/website-batch3-production')
const scenes = {
  missing: ['/missing-page', 'Branded page not found'],
  invalid: ['/auth/confirm', 'Missing secure link'],
  service: ['/auth/confirm?token_hash=synthetic&type=email', 'Verification service unavailable'],
  resume: ['/auth/resume', 'Delete confirmation: click Delete Resume'],
  draft: ['/auth/resume', 'Draft confirmation: extract, edit, close, then upload another TXT file'],
  onboarding: ['/auth/onboarding', 'Onboarding welcome without unsupported review claims'],
}
let scene = 'missing', generation = 0, deleted = false
const record = { id: 'synthetic-resume', original_filename: 'Synthetic practice resume.txt', status: 'ready', is_active: true }
const user = { id: 'review-owner', email: 'candidate@example.test' }
const token = Buffer.from('{}').toString('base64url') + '.' + Buffer.from(JSON.stringify({ sub: user.id, exp: 2524608000 })).toString('base64url') + '.synthetic'
const session = { access_token: token, refresh_token: 'synthetic-refresh', expires_at: 2524608000, expires_in: 3600, token_type: 'bearer', user }
const mime = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html; charset=utf-8', '.png': 'image/png', '.svg': 'image/svg+xml', '.ttf': 'font/ttf', '.jpg': 'image/jpeg' }
const site = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1:5321')
  res.setHeader('Cache-Control', 'no-store')
  res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self' http://127.0.0.1:5329; media-src 'self'; frame-src 'none'; base-uri 'self'")
  if (url.pathname === '/__review') {
    res.setHeader('Content-Type', 'text/html; charset=utf-8')
    return res.end(`<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>Batch 3 local review</title><body style="font:16px/1.7 Arial;color:#10234f;background:#eef4ff;margin:32px"><h1>Intervucopilot: Batch 3 review</h1><p>Open one scenario at a time in a new tab. Synthetic local fixtures only. No real account, upload, deletion or provider action occurs.</p><ul>${Object.entries(scenes).map(([key, value]) => `<li><a target="_blank" rel="noopener" href="/__review/open?scene=${key}">${value[1]}</a></li>`).join('')}</ul><p>Draft scenario: click Extract Again, edit a field and close. Click Upload Resume, choose a local test TXT file, then Upload and Extract. Keep editing cancels without losing the file. The simulated replacement upload fails deliberately; Retry processing then shows the Extract Again confirmation. No file leaves this computer.</p><p>Reset a scenario by opening its link again. Home uses the real local landing page. These previews do not establish remote hosting, provider or installed-app acceptance.</p>`)
  }
  if (url.pathname === '/__review/open') {
    scene = Object.hasOwn(scenes, url.searchParams.get('scene')) ? url.searchParams.get('scene') : 'missing'
    generation++; deleted = false
    res.writeHead(302, { Location: scenes[scene][0] }); return res.end()
  }
  if (url.pathname.startsWith('/api/')) { res.writeHead(503); return res.end('{}') }
  let file
  try { file = path.resolve(dist, '.' + decodeURIComponent(url.pathname)) } catch { res.writeHead(400); return res.end() }
  if (file !== dist && !file.startsWith(dist + path.sep)) { res.writeHead(403); return res.end() }
  if (fs.existsSync(file) && fs.statSync(file).isFile()) { res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); return fs.createReadStream(file).pipe(res) }
  let html = fs.readFileSync(path.join(dist, 'index.html'), 'utf8')
  html = html.replace('<head>', `<head><script>if(sessionStorage.getItem('branding-review-generation')!==${JSON.stringify(String(generation))}){localStorage.removeItem('intervucopilot.website-logout-intent');${['resume', 'draft', 'onboarding'].includes(scene) ? `localStorage.setItem('sb-127-auth-token',${JSON.stringify(JSON.stringify(session))});` : "localStorage.removeItem('sb-127-auth-token');"}sessionStorage.setItem('branding-review-generation',${JSON.stringify(String(generation))});}</script>`)
  res.setHeader('Content-Type', 'text/html; charset=utf-8'); res.end(html)
})
const api = http.createServer((req, res) => {
  res.setHeader('Access-Control-Allow-Origin', 'http://127.0.0.1:5321')
  res.setHeader('Access-Control-Allow-Headers', 'authorization,content-type,apikey,x-client-info,x-supabase-api-version,idempotency-key,x-idempotency-key')
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,DELETE,OPTIONS')
  if (req.method === 'OPTIONS') { res.writeHead(204); return res.end() }
  const p = new URL(req.url, 'http://127.0.0.1:5329').pathname
  req.resume() // Never retain synthetic upload bodies or credentials.
  let value = { items: [], page: 1, limit: 20 }, status = 200
  if (p === '/auth/v1/verify') { status = 503; value = { message: 'Synthetic service unavailable' } }
  else if (p === '/auth/v1/user') value = user
  else if (p === '/api/auth/me') value = { user_id: user.id, email: user.email }
  else if (p === '/api/auth/profile/bootstrap') value = { profile_exists: true, settings_exists: true }
  else if (p === '/api/onboarding') value = { onboarding_completed_at: scene === 'onboarding' ? null : 'synthetic-complete', onboarding_current_step: scene === 'onboarding' ? 1 : 5 }
  else if (p === '/api/account/subscription') value = {}
  else if (p === '/api/resumes/current') value = { ready: scene !== 'draft' && !deleted, resume: scene !== 'draft' && !deleted ? record : null }
  else if (p === '/api/resumes/review-candidate') value = { has_candidate: scene === 'draft' && !deleted, resume: scene === 'draft' && !deleted ? { ...record, status: 'uploaded', is_active: false } : null }
  else if (p === '/api/resumes' && req.method === 'GET') value = { items: deleted ? [] : [{ ...record, status: scene === 'draft' ? 'uploaded' : 'ready' }] }
  else if (p === '/api/resumes' && req.method === 'POST') { status = 503; value = {} }
  else if (p === '/api/resumes/synthetic-resume' && req.method === 'DELETE') { deleted = true; value = { deleted: true } }
  else if (p.endsWith('/extract')) value = { status: 'needs_review', extraction_attempt: 1, profile: { full_name: 'Synthetic Candidate' }, review_required: true }
  else if (req.method !== 'GET') { status = 405; value = {} }
  res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(value))
})
site.listen(5321, '127.0.0.1'); api.listen(5329, '127.0.0.1')
for (const server of [site, api]) server.on('error', error => { console.error(error.code); site.close(); api.close(); process.exitCode = 1 })
process.on('SIGINT', () => { site.close(); api.close() })
console.log('Synthetic Batch 3 review: http://127.0.0.1:5321/__review')

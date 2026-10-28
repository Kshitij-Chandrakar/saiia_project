// Loopback-only synthetic review. Never forwards a request to any provider.
const http = require('node:http')
const fs = require('node:fs')
const path = require('node:path')
const dist = path.resolve(__dirname, '../../tmp/website-batch2-production')
const scenes = {
  callback: ['/auth/callback?next=%2Fauth%2Fresume', 'Callback: wait 15 seconds, then release the response'],
  guard: ['/auth/resume', 'Protected route: wait 15 seconds, then retry or release'],
  unsubscribe: ['/unsubscribe?token=synthetic-review-link', 'Unsubscribe: progress at 10 seconds, uncertain at 15 seconds'],
  checkout: ['/auth/checkout', 'Checkout: wait 12 seconds, then release and recover the existing checkout'],
}
let scene = 'callback', generation = 0, hold = true
const waiting = new Set()
const user = { id: 'owner', email: 'candidate@example.test' }
const token = Buffer.from('{}').toString('base64url')+'.'+Buffer.from(JSON.stringify({ sub: user.id, exp: 2524608000 })).toString('base64url')+'.synthetic'
const session = { access_token: token, refresh_token: 'synthetic-refresh', expires_at: 2524608000, expires_in: 3600, token_type: 'bearer', user }
const mime = { '.js':'application/javascript', '.css':'text/css', '.html':'text/html; charset=utf-8', '.png':'image/png', '.svg':'image/svg+xml', '.ttf':'font/ttf', '.jpg':'image/jpeg' }
const site = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1:5311')
  res.setHeader('Cache-Control', 'no-store')
  res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self' http://127.0.0.1:5319; media-src 'self'; frame-src 'none'; base-uri 'self'")
  if (url.pathname === '/__review') {
    res.setHeader('Content-Type','text/html; charset=utf-8')
    return res.end(`<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>Batch 2 local review</title><body style="font:16px/1.7 Arial;color:#10234f;background:#eef4ff;margin:32px"><h1>Intervucopilot: Batch 2 review</h1><p>Synthetic local fixtures. Open ONE scenario at a time in a new tab. Keep this index open.</p><ul>${Object.entries(scenes).map(([key,v])=>`<li><a target="_blank" rel="noopener" href="/__review/open?scene=${key}">${v[1]}</a></li>`).join('')}</ul><button onclick="fetch('/__review/release').then(()=>this.textContent='Responses released')" style="padding:12px 20px">Release current responses</button><p>Releasing allows delayed responses to finish. If an unsubscribe or checkout request already timed out, return to its tab and use its manual Retry or Recover action. Nothing is sent to a real account or provider.</p><p>Use a fresh scenario link to reset. Stop a manually started preview with Ctrl+C.</p>`)
  }
  if (url.pathname === '/__review/open') {
    for (const entry of [...waiting]) entry.cancel()
    scene = Object.hasOwn(scenes, url.searchParams.get('scene')) ? url.searchParams.get('scene') : 'callback'
    generation++; hold = true
    res.writeHead(302, {Location:scenes[scene][0]});return res.end()
  }
  if (url.pathname === '/__review/release') {
    hold = false; for (const entry of [...waiting]) entry.finish()
    res.setHeader('Content-Type','application/json');return res.end('{"released":true}')
  }
  if (url.pathname.startsWith('/api/')) {res.writeHead(503, {'Content-Type':'application/json'});return res.end('{}')}
  let file
  try {file = path.resolve(dist,'.'+decodeURIComponent(url.pathname))} catch {res.writeHead(400);return res.end()}
  if (file !== dist && !file.startsWith(dist+path.sep)) {res.writeHead(403);return res.end()}
  if (fs.existsSync(file) && fs.statSync(file).isFile()) {res.setHeader('Content-Type',mime[path.extname(file)]||'application/octet-stream');return fs.createReadStream(file).pipe(res)}
  const value = {...session,expires_at:scene==='guard'?1:session.expires_at}
  let html = fs.readFileSync(path.join(dist,'index.html'),'utf8')
  html = html.replace('<head>',`<head><script>if(sessionStorage.getItem('progress-review-generation')!==${JSON.stringify(String(generation))}){localStorage.removeItem('intervucopilot.website-logout-intent');localStorage.setItem('sb-127-auth-token',${JSON.stringify(JSON.stringify(value))});sessionStorage.removeItem('billing.operation.owner');sessionStorage.setItem('progress-review-generation',${JSON.stringify(String(generation))});}</script>`)
  res.setHeader('Content-Type','text/html; charset=utf-8');res.end(html)
})
function answer(res,p) {
  if (res.destroyed) return
  let value
  if(p==='/auth/v1/token') value=session
  else if(p==='/api/auth/me') value={user_id:user.id,email:user.email}
  else if(p==='/api/auth/profile/bootstrap') value={profile_exists:true,settings_exists:true}
  else if(p==='/api/onboarding') value={onboarding_completed_at:'synthetic-complete',onboarding_current_step:5}
  else if(p==='/api/email/unsubscribe') value={success:true}
  else if(p==='/api/billing/current'||p==='/api/billing/status') value={operation_id:'existing-review-operation',state:'pending',name:'Plus',currency:'INR',amount_minor:'47082',interval:'month',total_count:12}
  else if(p==='/api/resumes/current') value={ready:false,resume:null}
  else if(p==='/api/resumes/review-candidate') value={has_candidate:false,resume:null}
  else value={items:[],page:1,limit:20}
  res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify(value))
}
const api = http.createServer((req,res)=>{
  res.setHeader('Access-Control-Allow-Origin','http://127.0.0.1:5311')
  res.setHeader('Access-Control-Allow-Headers','authorization,content-type,apikey,x-client-info,x-supabase-api-version,idempotency-key')
  res.setHeader('Access-Control-Allow-Methods','GET,POST,OPTIONS')
  if(req.method==='OPTIONS'){res.writeHead(204);return res.end()}
  const p=new URL(req.url,'http://127.0.0.1:5319').pathname
  req.resume()
  if(p.startsWith('/api/billing/') && req.method!=='GET'){res.writeHead(405);return res.end()}
  const wait = hold && ((scene==='callback'&&p==='/api/auth/me')||(scene==='guard'&&p==='/auth/v1/token')||(scene==='unsubscribe'&&p==='/api/email/unsubscribe')||(scene==='checkout'&&p==='/api/billing/current'))
  if(!wait)return answer(res,p)
  const entry={finish:()=>{waiting.delete(entry);answer(res,p)},cancel:()=>{waiting.delete(entry);res.destroy()}}
  waiting.add(entry);res.on('close',()=>waiting.delete(entry))
})
site.listen(5311,'127.0.0.1');api.listen(5319,'127.0.0.1')
for(const server of [site,api])server.on('error',error=>{console.error(error.code);site.close();api.close();process.exitCode=1})
process.on('SIGINT',()=>{for(const entry of [...waiting])entry.cancel();site.close();api.close()})
console.log('Synthetic Batch 2 review: http://127.0.0.1:5311/__review')

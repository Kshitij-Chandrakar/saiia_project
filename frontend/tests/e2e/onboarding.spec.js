import {test,expect} from '@playwright/test'
import {mkdir} from 'node:fs/promises'
import path from 'node:path'
const captures=path.resolve('../tmp/onboarding-five-screenshots')
async function mock(page,{step=1,completed=false,resume=false,signedIn=true,fail=false,settingsMissing=false,bootstrapFailure=false}={}) {
 const state={onboarding_current_step:step,onboarding_completed_at:completed?'completed':null}
 const writes=[],entryCalls=[]
 let missing=settingsMissing,setupFailure=bootstrapFailure
 await page.route('**/src/auth/supabaseClient.js*',route=>route.fulfill({contentType:'application/javascript',body:`window.__obSession=${signedIn?"{access_token:'synthetic',user:{id:'owner'}}":"null"};export const supabase={auth:{getSession:async()=>({data:{session:window.__obSession}}),onAuthStateChange:()=>({data:{subscription:{unsubscribe(){}}}}),signOut:async()=>{window.__obSession=null;return {error:null}}}};export function getSupabaseAuthConfig(){return {}};`}))
 await page.route('**/api/**',async route=>{
  const req=route.request(),url=new URL(req.url()),p=url.pathname
  if(p==='/api/auth/me'){entryCalls.push('verify');return route.fulfill({json:{user_id:'owner',email:'candidate@example.test'}})}
  if(p==='/api/auth/profile/bootstrap'){
   entryCalls.push('bootstrap');expect(req.postData()).toBeNull()
   if(setupFailure)return route.fulfill({status:503,json:{detail:'Account setup temporarily unavailable'}})
   missing=false;return route.fulfill({json:{profile_exists:true,settings_exists:true}})
  }
  if(p.startsWith('/api/onboarding')){
   entryCalls.push('onboarding')
   if(missing)return route.fulfill({status:409,json:{detail:'Account setup required'}})
   if(fail)return route.fulfill({status:503,json:{detail:'private backend failure'}})
   if(req.method()!=='GET'){writes.push({path:p,body:req.postDataJSON()});if(p.endsWith('/step'))state.onboarding_current_step=req.postDataJSON().current_step;else state.onboarding_completed_at='saved'}
   return route.fulfill({json:state})
  }
  if(p==='/api/resumes/current')return route.fulfill({json:{ready:resume,resume:resume?{id:'resume',original_filename:'existing-resume.pdf',is_active:true,status:'confirmed'}:null}})
  if(p==='/api/resumes'&&req.method()==='POST')return route.fulfill({json:{id:'uploaded',original_filename:'profile.txt',status:'uploaded'}})
  if(p==='/api/resumes')return route.fulfill({json:{items:[]}})
  if(p==='/api/job-contexts/extract')return route.fulfill({json:{company:'Example',position:'Engineer',job_description:'Extracted synthetic description',extraction_receipt_id:'receipt'}})
  if(p==='/api/job-contexts'&&req.method()==='POST')return route.fulfill({json:{job_context:{id:'job',company:'Example',position:'Engineer'}}})
  if(p==='/api/job-contexts')return route.fulfill({json:{items:[]}})
  if(p==='/api/interview-sessions'&&req.method()==='POST')return route.fulfill({json:{session:{id:'session',status:'active',target_role:'Engineer'}}})
  if(p==='/api/interview-sessions')return route.fulfill({json:{items:[],limit:20,page:1}})
  return route.fulfill({status:404,json:{detail:'Unmocked endpoint'}})
 })
 return {state,writes,entryCalls,recoverSetup:()=>{setupFailure=false}}
}
async function ready(page){await page.evaluate(()=>document.fonts.ready);await expect.poll(()=>page.locator('.ob-card img').evaluateAll(images=>images.every(i=>i.complete&&i.naturalWidth>0))).toBe(true)}
test('new user resumes saved steps, keeps existing resume, and finishes once',async({page})=>{
 const f=await mock(page,{resume:true});await page.goto('/auth/dashboard')
 await expect(page).toHaveURL(/auth\/onboarding/)
 await page.getByRole('button',{name:'Get Started',exact:true}).click()
 await expect(page.getByText('existing-resume.pdf')).toBeVisible()
 await page.reload();await expect(page.getByRole('heading',{name:'Add your CV or Resume'})).toBeVisible()
 await page.getByRole('button',{name:'Back',exact:true}).click();await page.getByRole('button',{name:'Get Started',exact:true}).click()
 for(let i=2;i<5;i++)await page.getByRole('button',{name:'Next',exact:true}).click()
 await page.getByRole('button',{name:'Continue to App',exact:true}).click()
 await expect(page).toHaveURL(/auth\/dashboard/);await expect(page.getByRole('heading',{name:'Welcome back!'})).toBeVisible()
 expect(f.writes.filter(r=>r.path.endsWith('/complete'))).toHaveLength(1)
 await page.reload();await expect(page.getByRole('heading',{name:'Welcome back!'})).toBeVisible()
})
test('Skip completes entire flow without resource creation',async({page})=>{
 const f=await mock(page,{step:3});await page.goto('/auth/onboarding');await page.getByRole('button',{name:'Skip',exact:true}).click()
 await expect(page).toHaveURL(/auth\/dashboard/);expect(f.state.onboarding_completed_at).toBe('saved');expect(f.writes).toHaveLength(1)
})
test('existing account bypasses onboarding',async({page})=>{await mock(page,{completed:true});await page.goto('/auth/dashboard');await expect(page.getByRole('heading',{name:'Welcome back!'})).toBeVisible();await expect(page.locator('.ob-card')).toHaveCount(0)})
test('unavailable schema shows safe retry without a dashboard flash',async({page})=>{await mock(page,{fail:true});await page.goto('/auth/dashboard');await expect(page.getByRole('alert')).toContainText('Onboarding is unavailable');await expect(page.getByRole('button',{name:'Retry onboarding'})).toBeVisible();await expect(page.getByRole('heading',{name:'Welcome back!'})).toHaveCount(0)})
test('unauthenticated user cannot enter onboarding',async({page})=>{await mock(page,{signedIn:false});await page.goto('/auth/onboarding');await expect(page).toHaveURL(/auth\/login/)})
for(const [width,height] of [[1440,900],[1366,768],[1280,720],[1024,768],[390,844],[360,800]])test(`five stages at ${width}x${height}`,async({page})=>{
 await page.setViewportSize({width,height});await page.emulateMedia({reducedMotion:'reduce'});await mock(page);await page.goto('/auth/onboarding');await mkdir(captures,{recursive:true})
 const errors=[];page.on('pageerror',e=>errors.push(e.message))
 for(let step=1;step<=5;step++){
  await ready(page);await expect(page.locator('.ob-progress li')).toHaveCount(5);await expect(page.locator('.ob-progress')).toHaveAttribute('aria-label',`Step ${step} of 5`)
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  const button=page.getByRole('button',{name:step===1?'Get Started':step===5?'Continue to App':'Next',exact:true})
  await button.scrollIntoViewIfNeeded();const box=await button.boundingBox();expect(box.x).toBeGreaterThanOrEqual(0);expect(box.y+box.height).toBeLessThanOrEqual(height+1)
  for(const control of await page.locator('.ob-header button,.ob-actions button').all()){const rect=await control.boundingBox();expect(rect.x).toBeGreaterThanOrEqual(0);expect(rect.x+rect.width).toBeLessThanOrEqual(width+1)}
  await page.screenshot({path:path.join(captures,`step-${step}-${width}x${height}.png`),fullPage:false})
  if(step<5)await button.click()
 }
 expect(errors).toEqual([])
})
test('keyboard, upload and context actions preserve data on Back',async({page})=>{
 await mock(page,{step:2});await page.goto('/auth/onboarding')
 await page.locator('input[type=file]').setInputFiles({name:'profile.txt',mimeType:'text/plain',buffer:Buffer.from('Synthetic resume fixture')})
 await expect(page.getByText('profile.txt')).toBeVisible();await page.getByRole('button',{name:'Next',exact:true}).click()
 await page.getByRole('button',{name:'Add Job Description',exact:true}).click();await page.getByLabel('Company',{exact:true}).fill('Example');await page.getByLabel('Role',{exact:true}).fill('Engineer');await page.getByLabel('Job description',{exact:true}).fill('Synthetic job context');await page.getByRole('button',{name:'Save context'}).click()
 await expect(page.getByText('Engineer',{exact:true})).toBeVisible();await page.getByRole('button',{name:'Back',exact:true}).click();await expect(page.getByText('profile.txt')).toBeVisible()
 await page.keyboard.press('Tab');await expect(page.locator(':focus')).toBeVisible()
})

test('failed navigation keeps step; rapid pending clicks cannot duplicate completion',async({page})=>{
 const f=await mock(page);await page.goto('/auth/onboarding')
 let failed=false
 await page.route('**/api/onboarding/step',async route=>{if(!failed){failed=true;return route.fulfill({status:503,json:{detail:'private'}})}f.state.onboarding_current_step=2;return route.fulfill({json:f.state})})
 await page.getByRole('button',{name:'Get Started',exact:true}).click();await expect(page.getByRole('alert')).toContainText('Unable to save');await expect(page.getByRole('heading',{name:'Welcome to Intervucopilot'})).toBeVisible()
 await page.getByRole('button',{name:'Get Started',exact:true}).click();await expect(page.getByRole('heading',{name:'Add your CV or Resume'})).toBeVisible()
 let sends=0,release
 const blocked=new Promise(resolve=>release=resolve)
 await page.route('**/api/onboarding/complete',async route=>{sends++;await blocked;f.state.onboarding_completed_at='saved';await route.fulfill({json:f.state})})
 const skip=page.getByRole('button',{name:'Skip',exact:true});await skip.click();await expect(skip).toBeDisabled();expect(sends).toBe(1);release();await expect(page).toHaveURL(/auth\/dashboard/)
})
test('context editor traps focus and document extraction requires explicit consent',async({page})=>{
 await mock(page,{step:3});await page.goto('/auth/onboarding');await page.getByRole('button',{name:'Upload Document',exact:true}).click()
 const dialog=page.getByRole('dialog');await expect(dialog).toBeVisible();await expect(page.locator('.ob-header')).toHaveAttribute('inert','')
 await expect(page.getByRole('button',{name:'Extract document'})).toBeDisabled()
 await page.getByLabel('Document',{exact:true}).setInputFiles({name:'job.txt',mimeType:'text/plain',buffer:Buffer.from('Synthetic job')})
 await page.getByRole('checkbox').check();await page.getByRole('button',{name:'Extract document'}).click()
 await expect(page.getByLabel('Job description',{exact:true})).toHaveValue('Extracted synthetic description')
 await page.getByRole('button',{name:'Cancel',exact:true}).focus();await page.keyboard.press('Tab');await expect(page.getByLabel('Company',{exact:true})).toBeFocused()
 await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0)
})
test('existing job and session load without recreating resources',async({page})=>{
 await mock(page,{step:3});let mutations=0
 await page.route('**/api/job-contexts',route=>{if(route.request().method()!=='GET')mutations++;return route.fulfill({json:{items:[{id:'existing-job',company:'Existing Company',position:'Existing Role',is_active:true}]}})})
 await page.route('**/api/interview-sessions?*',route=>route.fulfill({json:{items:[{id:'existing-session',company_name:'Existing Company',target_role:'Existing Role',status:'active'}]}}))
 await page.goto('/auth/onboarding');await expect(page.getByText('Existing Role',{exact:true})).toBeVisible();await page.getByRole('button',{name:'Next',exact:true}).click()
 await expect(page.getByText('Existing Company',{exact:true})).toBeVisible();await page.getByRole('button',{name:'Start Session',exact:true}).click();await expect(page.getByRole('status')).toContainText('existing session')
 await page.getByRole('button',{name:'Next',exact:true}).click();await expect(page.getByRole('heading',{name:'Get the best live-call experience'})).toBeVisible();expect(mutations).toBe(0)
})

test('desktop is step five across refresh, Back, Next and completion',async({page})=>{
 const f=await mock(page,{step:5});await page.goto('/auth/onboarding')
 await expect(page.getByRole('heading',{name:'Get the best live-call experience'})).toBeVisible()
 await expect(page.locator('.ob-progress li')).toHaveCount(5)
 await page.reload();await expect(page.locator('.ob-progress')).toHaveAttribute('aria-label','Step 5 of 5')
 await page.getByRole('button',{name:'Back',exact:true}).click()
 expect(f.state.onboarding_current_step).toBe(4)
 await expect(page.getByRole('heading',{name:'Everything starts with an interview session'})).toBeVisible()
 await page.getByRole('button',{name:'Next',exact:true}).click()
 await expect(page.getByRole('heading',{name:'Get the best live-call experience'})).toBeVisible()
 expect(f.state.onboarding_current_step).toBe(5)
 await page.getByRole('button',{name:'Continue to App',exact:true}).click()
 await expect(page).toHaveURL(/auth\/dashboard/)
 expect(f.state.onboarding_completed_at).toBe('saved')
 expect(f.writes.filter(r=>r.path.endsWith('/complete'))).toHaveLength(1)
})

for (const status of ['active', 'ended', 'abandoned', null]) test(`session status ${status} only reuses active sessions`,async({page})=>{
 await mock(page,{step:4});let creates=0
 await page.route('**/api/interview-sessions**',route=>{
  if(route.request().method()==='POST'){creates++;return route.fulfill({json:{session:{id:'new-session',status:'active',target_role:'New role'}}})}
  return route.fulfill({json:{items:status?[{id:'old-session',status,target_role:'Old role'}]:[]}})
 })
 await page.goto('/auth/onboarding');const start=page.getByRole('button',{name:'Start Session',exact:true});await expect(start).toBeEnabled();await start.click()
 if(status==='active'){await expect(page.getByRole('status')).toContainText('Your existing session is ready in Call Sessions.');expect(creates).toBe(0)}
 else {await expect(page.getByText('New role',{exact:true})).toBeVisible();expect(creates).toBe(1)}
 await start.click();expect(creates).toBe(status==='active'?0:1)
})
test('document replacement and editor cancellation require new consent',async({page})=>{
 await mock(page,{step:3});await page.goto('/auth/onboarding')
 const open=page.getByRole('button',{name:'Upload Document',exact:true})
 await open.click()
 const file=page.getByLabel('Document',{exact:true}),consent=page.getByRole('checkbox'),extract=page.getByRole('button',{name:'Extract document'})
 const doc=name=>({name,mimeType:'text/plain',buffer:Buffer.from('Synthetic document')})
 await file.setInputFiles(doc('A.txt'));await consent.check();await expect(extract).toBeEnabled()
 await file.setInputFiles(doc('B.txt'));await expect(consent).not.toBeChecked();await expect(extract).toBeDisabled()
 await consent.check();await expect(extract).toBeEnabled();await page.getByRole('button',{name:'Cancel',exact:true}).click()
 await open.click();await expect(consent).not.toBeChecked();await expect(file).toHaveValue('');await expect(extract).toBeDisabled()
 await file.setInputFiles(doc('A.txt'));await consent.check();await extract.click()
 await expect(page.getByRole('heading',{name:'Add Job Description',exact:true})).toBeVisible()
 await page.getByRole('button',{name:'Cancel',exact:true}).click();await open.click()
 await expect(consent).not.toBeChecked();await expect(file).toHaveValue('');await expect(extract).toBeDisabled()
 await file.setInputFiles(doc('B.txt'));await expect(extract).toBeDisabled();await consent.check();await expect(extract).toBeEnabled()
 await page.keyboard.press('Escape');await open.click();await expect(consent).not.toBeChecked();await expect(file).toHaveValue('')
})

for(const name of ['Upload Document','Add Company Notes','Add Job Description']) test(`editor restores focus to ${name} after Escape and Cancel`,async({page})=>{
 await mock(page,{step:3});await page.goto('/auth/onboarding')
 const trigger=page.getByRole('button',{name,exact:true})
 for(const close of ['Escape','Cancel']){
  await trigger.focus();await page.keyboard.press('Enter');await expect(page.getByRole('dialog')).toBeVisible()
  if(close==='Escape')await page.keyboard.press('Escape')
  else await page.getByRole('button',{name:'Cancel',exact:true}).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.locator('.ob-body')).not.toHaveAttribute('inert','')
  await expect(trigger).toBeFocused()
 }
})
test('successful context save restores its opening trigger after controls become usable',async({page})=>{
 await mock(page,{step:3});await page.goto('/auth/onboarding')
 const trigger=page.getByRole('button',{name:'Add Job Description',exact:true})
 await trigger.focus();await page.keyboard.press('Enter');await page.getByLabel('Company',{exact:true}).fill('Example')
 await page.getByRole('button',{name:'Save context',exact:true}).click()
 await expect(page.getByRole('dialog')).toHaveCount(0);await expect(trigger).toBeEnabled();await expect(trigger).toBeFocused()
})


test('missing settings are bootstrapped before the onboarding read on direct dashboard entry',async({page})=>{
 const f=await mock(page,{settingsMissing:true})
 await page.goto('/auth/dashboard')
 await expect(page.getByRole('heading',{name:'Welcome to Intervucopilot',exact:true})).toBeVisible()
 expect(f.state.onboarding_current_step).toBe(1)
 const read=f.entryCalls.indexOf('onboarding')
 expect(read).toBeGreaterThan(f.entryCalls.indexOf('bootstrap'))
 expect(f.entryCalls.slice(0,read)).toContain('verify')
})

test('failed entry bootstrap blocks onboarding until session-check retry succeeds',async({page})=>{
 const f=await mock(page,{settingsMissing:true,bootstrapFailure:true})
 await page.goto('/auth/dashboard')
 const retry=page.getByRole('button',{name:'Retry',exact:true})
 await expect(retry).toBeVisible()
 expect(f.entryCalls).not.toContain('onboarding')
 f.recoverSetup();await retry.click()
 await expect(page.getByRole('heading',{name:'Welcome to Intervucopilot',exact:true})).toBeVisible()
 expect(f.entryCalls.indexOf('onboarding')).toBeGreaterThan(f.entryCalls.lastIndexOf('bootstrap'))
})


for(const completed of [true,false]) test(`legacy account route redirects through dashboard gate (completed=${completed})`,async({page})=>{
 await mock(page,{completed});await page.goto('/auth/status')
 await expect(page).toHaveURL(completed?/auth\/dashboard$/:/auth\/onboarding$/)
 await expect(page.getByRole('heading',{name:completed?'Welcome back!':'Welcome to Intervucopilot',exact:true})).toBeVisible()
 await expect(page.getByRole('button',{name:'Prepare Profile',exact:true})).toHaveCount(0)
})

test('legacy account route sends signed-out users to login',async({page})=>{
 await mock(page,{signedIn:false});await page.goto('/auth/status')
 await expect(page).toHaveURL(/auth\/login/)
 await expect(page.getByRole('heading',{name:'Welcome back!',exact:true})).toBeVisible()
 await expect(page.getByRole('button',{name:'Prepare Profile',exact:true})).toHaveCount(0)
})

test('bootstrap recovery is branded, safe, responsive and supports logout',async({page})=>{
 await mock(page,{bootstrapFailure:true});await page.goto('/auth/dashboard')
 await expect(page.getByRole('heading',{name:"Account setup couldn't be completed",exact:true})).toBeFocused()
 await expect(page.getByText("We couldn't finish preparing your account. Please try again.",{exact:true})).toBeVisible()
 await expect(page.locator('.account-setup-recovery')).not.toContainText('temporarily unavailable')
 await mkdir(captures,{recursive:true})
 for(const [width,height] of [[1366,768],[390,844]]){
  await page.setViewportSize({width,height})
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  await page.screenshot({path:path.join(captures,`account-setup-recovery-${width}.png`)})
 }
 await page.locator('.account-setup-recovery').getByRole('button',{name:'Logout',exact:true}).click()
 await expect(page).toHaveURL(/auth\/login$/)
 await expect(page.getByRole('heading',{name:'Welcome back!',exact:true})).toBeVisible()
})

for(const route of ['/auth/login','/auth/signup'])test(`${route} has no misleading system-status link`,async({page})=>{
 await mock(page,{signedIn:false});await page.goto(route)
 await expect(page.getByRole('heading',{name:route.endsWith('login')?'Welcome back!':'Create your account',exact:true})).toBeVisible()
 await expect(page.getByRole('link',{name:/system status/i})).toHaveCount(0)
})


test('email verification setup failure recovers through dashboard and preserves explicit consent',async({page})=>{
 await mock(page)
 const consent={terms_accepted:true,privacy_accepted:true,marketing_email_opt_in:false,consent_source:'signup'}
 await page.addInitScript(consent=>localStorage.setItem('intervuai.pendingSignupConsent',JSON.stringify({email:'candidate@example.test',consent})),consent)
 await page.route('**/src/auth/AuthScreens.jsx*',async route=>{
  const response=await route.fetch()
  await route.fulfill({response,body:(await response.text()).replace(/const CONSENT_FEATURE_ENABLED = [^\n]+/,'const CONSENT_FEATURE_ENABLED = true;')})
 })
 await page.route('**/src/auth/supabaseClient.js*',route=>route.fulfill({contentType:'application/javascript',body:`
  const session={access_token:'synthetic',user:{id:'owner',email:'candidate@example.test'}};
  window.__verificationCalls=0;
  export const supabase={auth:{getSession:async()=>({data:{session}}),verifyOtp:async()=>{window.__verificationCalls++;return {data:{session},error:null}},onAuthStateChange:()=>({data:{subscription:{unsubscribe(){}}}})}};
  export function getSupabaseAuthConfig(){return {}};
 `}))
 let fail=true,writes=0
 await page.route('**/api/auth/profile/bootstrap',route=>{
  if(!route.request().postData()){expect(fail).toBe(false);return route.fulfill({json:{profile_exists:true,settings_exists:true}})}
  writes++;expect(route.request().postDataJSON()).toEqual(consent)
  return route.fulfill(fail?{status:503,json:{detail:'private setup details'}}:{json:{profile_exists:true,settings_exists:true}})
 })
 await page.goto('/auth/confirm?token_hash=synthetic&type=email')
 const proceed=page.getByRole('link',{name:'Continue to Dashboard',exact:true})
 await expect(proceed).toHaveAttribute('href','/auth/dashboard')
 await proceed.click()
 await expect(page.getByRole('heading',{name:"Account setup couldn't be completed",exact:true})).toBeVisible()
 expect(await page.evaluate(()=>localStorage.getItem('intervuai.pendingSignupConsent'))).not.toBeNull()
 fail=false;await page.getByRole('button',{name:'Retry',exact:true}).click()
 await expect(page).toHaveURL(/auth\/onboarding$/)
 expect(writes).toBe(3)
 expect(await page.evaluate(()=>window.__verificationCalls)).toBe(1)
 expect(await page.evaluate(()=>localStorage.getItem('intervuai.pendingSignupConsent'))).toBeNull()
 await expect(page.getByRole('button',{name:'Prepare Profile',exact:true})).toHaveCount(0)
})

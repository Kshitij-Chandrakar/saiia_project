import { test, expect } from '@playwright/test'
import { mkdir, readFile } from 'node:fs/promises'
import path from 'node:path'

const output = path.resolve('..', 'tmp/signup-check')
class SignupPage {
  constructor(page) { this.page=page; this.email=page.getByLabel('Email', {exact:true}); this.password=page.getByLabel('Password', {exact:true}); this.terms=page.getByRole('checkbox',{name:'I agree to the Terms & Conditions and Privacy Policy.'}); this.marketing=page.getByRole('checkbox',{name:'I want to receive promotional, discount, and product emails.'}); this.submit=page.getByRole('button',{name:'Create Account',exact:true}) }
  async goto() { await this.page.goto('/auth/signup'); await expect(this.submit).toBeEnabled() }
  async fill() { await this.email.fill('person@example.test'); await this.password.fill('sample-password') }
}
async function mockAuth(page, { enabled=true, desktop=false }={}) {
  await page.addInitScript(desktop => {
    window.__signupCalls=[]; window.__oauthCalls=[]; window.__bootstrap=[]; window.__session=null
    if(desktop) window.electronAPI={}
  },desktop)
  await page.route('**/src/auth/supabaseClient.js*', route => route.fulfill({contentType:'application/javascript',body:`
    export function getSupabaseAuthConfig(){return {}}; export const supabase = {auth:{getSession:async()=>({data:{session:window.__session}}),
      signUp:async args=>{window.__signupCalls.push(args);if(window.__pending)return new Promise(resolve=>window.__resolveSignup=resolve);return window.__result||{data:{session:null},error:null}},
      signInWithOAuth:async args=>{window.__oauthCalls.push(args);return {error:null}},
      onAuthStateChange:()=>({data:{subscription:{unsubscribe(){}}}})}};`}))
  await page.route('**/src/auth/AuthScreens.jsx*',async route=>{const response=await route.fetch();const body=(await response.text()).replace(/const CONSENT_FEATURE_ENABLED = [^\n]+/,`const CONSENT_FEATURE_ENABLED = ${enabled};`);await route.fulfill({response,body})})
  await page.route('**/api/auth/me',route=>route.fulfill({json:{user_id:'mock-user',email:'person@example.test'}}))
  await page.route('**/api/auth/profile/bootstrap', async route=>{ const consent=route.request().postDataJSON();await page.evaluate(x=>window.__bootstrap.push(x),consent);await route.fulfill({json:{user_id:'mock-user',profile_exists:true,settings_exists:true}}) })
}
test('Figma signup renders with local assets and no overflow at all five sizes',async({page})=>{
  await mockAuth(page);const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error') errors.push(m.text())});const failed=[];page.on('response',r=>{if(r.status()>=400)failed.push(r.url())}); await mkdir(output,{recursive:true})
  await page.emulateMedia({reducedMotion:'reduce'})
  for(const [width,height] of [[1440,1024],[1366,768],[768,1024],[390,844],[360,800]]){
    await page.setViewportSize({width,height});const signup=new SignupPage(page);await signup.goto();await page.evaluate(()=>document.fonts.ready)
    await expect(signup.email).toBeVisible();await expect(signup.password).toBeVisible();await expect(page.getByLabel('Full Name',{exact:true})).toHaveCount(0);await expect(page.getByLabel('Confirm Password',{exact:true})).toHaveCount(0)
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(width)
    await expect.poll(()=>page.locator('main img').evaluateAll(images=>images.every(i=>i.complete&&i.naturalWidth>0))).toBe(true)
    expect(await page.locator('main img').evaluateAll(images=>images.every(i=>!i.src.includes('figma.com')))).toBe(true)
    expect(await page.locator('main').evaluate(el=>[...el.querySelectorAll('*')].every(x=>x.getAnimations().length===0))).toBe(true)
    await page.screenshot({path:path.join(output,`signup-${width}x${height}.png`),fullPage:true,animations:'disabled'})
  }
  expect(errors).toEqual([]);expect(failed).toEqual([])
})
test('controls, consent validation, errors, pending guard and verification persistence',async({page})=>{
  await mockAuth(page);const signup=new SignupPage(page);await signup.goto()
  await expect(signup.terms).not.toBeChecked();await expect(signup.marketing).not.toBeChecked();await signup.marketing.check();await expect(signup.terms).not.toBeChecked();await signup.marketing.uncheck()
  await signup.email.fill('invalid');await signup.password.fill('123');await signup.submit.click();expect(await page.evaluate(()=>window.__signupCalls.length)).toBe(0)
  await signup.fill();await signup.submit.click();expect(await page.evaluate(()=>window.__signupCalls.length)).toBe(0)
  await signup.terms.check();await page.getByRole('button',{name:'Show password'}).click();await expect(signup.password).toHaveAttribute('type','text');await page.getByRole('button',{name:'Hide password'}).click()
  await page.evaluate(()=>{window.__pending=true});await signup.submit.click();await expect(page.getByRole('button',{name:'Creating...'})).toBeDisabled();await page.evaluate(()=>document.querySelector('form').requestSubmit());expect(await page.evaluate(()=>window.__signupCalls.length)).toBe(1)
  await page.evaluate(()=>window.__resolveSignup({data:{session:null},error:{message:'Mock signup unavailable'}}));await expect(page.getByRole('alert')).toHaveText('Mock signup unavailable');await expect(signup.email).toHaveValue('person@example.test')
  await page.evaluate(()=>{window.__pending=false;window.__result={data:{session:null},error:null}});await signup.submit.click();await expect(page.getByRole('dialog',{name:'Check your email'})).toContainText('Check your email to verify your account.');await page.getByRole('button',{name:'Got it',exact:true}).click()
  const pending=await page.evaluate(()=>JSON.parse(localStorage.getItem('intervuai.pendingSignupConsent')));expect(pending.consent.marketing_email_opt_in).toBe(false);expect(pending.consent.terms_accepted).toBe(true)
  await page.getByRole('link',{name:'Privacy Policy',exact:true}).last().click();await expect(page.getByRole('status').last()).toContainText('Privacy Policy is not published yet.');await expect(page.getByRole('status').last()).toBeVisible();await page.getByRole('button',{name:'Dismiss notice'}).click();expect(page.url()).toContain('/auth/signup')
  await page.getByRole('link',{name:'Sign in',exact:true}).click();await expect(page).toHaveURL(/\/auth\/login$/)
})
test('disabled consent gate blocks real signup, desktop retains its shell, login screenshots unchanged',async({page})=>{
  await mockAuth(page,{enabled:false});const signup=new SignupPage(page);await signup.goto();await signup.fill();await signup.terms.check();await signup.submit.click();await expect(page.getByRole('alert')).toContainText('consent setup');expect(await page.evaluate(()=>window.__signupCalls.length)).toBe(0)
  for(const [width,height] of [[1440,1024],[390,844]]){await page.setViewportSize({width,height});await page.emulateMedia({reducedMotion:'reduce'});await page.goto('/auth/login');await expect(page.getByRole('button',{name:'Sign In',exact:true})).toBeEnabled();await page.evaluate(()=>document.fonts.ready);await page.screenshot({path:path.join(output,`login-after-${width}.png`),fullPage:true,animations:'disabled'});expect(await readFile(path.join(output,`login-after-${width}.png`))).toEqual(await readFile(new URL(`./fixtures/login-before-${width}.png`,import.meta.url)))}
  await page.goto('/auth/signup?desktop_state=desktop-safe-state-123');await expect(page.getByRole('button',{name:'Sign Up',exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'Create your account',exact:true})).toHaveCount(0)
})


test('untouched marketing stays null and authenticated bootstrap remains schema-gated',async({page})=>{
  await mockAuth(page);const signup=new SignupPage(page);await signup.goto();await signup.fill();await signup.terms.check()
  await page.evaluate(()=>{window.__result={data:{session:{access_token:'mock-only',user:{email:'person@example.test'}}},error:null}})
  await page.route('**/api/auth/profile/bootstrap',route=>route.fulfill({status:503,json:{detail:'Consent schema is not ready.'}}))
  await signup.submit.click();await expect(page.getByRole('alert')).toContainText('Consent schema is not ready.')
  expect(await page.evaluate(()=>JSON.parse(localStorage.getItem('intervuai.pendingSignupConsent')).consent.marketing_email_opt_in)).toBeNull()
  await page.unroute('**/api/auth/profile/bootstrap')
  await page.route('**/api/auth/profile/bootstrap',async route=>{await page.evaluate(x=>window.__bootstrap.push(x),route.request().postDataJSON());await route.fulfill({json:{user_id:'mock-user',profile_exists:true,settings_exists:true}})})
  await signup.submit.click();await expect(page.getByRole('status')).toHaveText('Account created. Your consent preferences were saved.')
  expect(await page.evaluate(()=>window.__bootstrap[0].marketing_email_opt_in)).toBeNull()
  expect(await page.evaluate(()=>localStorage.getItem('intervuai.pendingSignupConsent'))).toBeNull()
})
test('verification callback persists existing signup consent and clears it only after bootstrap',async({page})=>{
  await mockAuth(page);const signup=new SignupPage(page);await signup.goto();await signup.fill();await signup.terms.check();await signup.submit.click();await expect(page.getByRole('dialog',{name:'Check your email'})).toContainText('Check your email to verify your account.');await page.getByRole('button',{name:'Got it',exact:true}).click()
  await page.route('**/src/auth/supabaseClient.js*',route=>route.fulfill({contentType:'application/javascript',body:`export function getSupabaseAuthConfig(){return {}}; export const supabase={auth:{verifyOtp:async()=>({data:{session:{access_token:'mock-only',user:{email:'person@example.test'}}}}),getSession:async()=>({data:{session:null}})}};`}))
  await page.goto('/auth/confirm?token_hash=mock-only&type=email&next=%2Fauth%2Fdashboard')
  await expect.poll(()=>page.evaluate(()=>window.__bootstrap.length)).toBe(1)
  expect(await page.evaluate(()=>window.__bootstrap[0].marketing_email_opt_in)).toBeNull()
  expect(await page.evaluate(()=>localStorage.getItem('intervuai.pendingSignupConsent'))).toBeNull()
  expect(page.url()).not.toContain('token_hash')
})
test('keyboard focus is visible and Google pending requests cannot duplicate',async({page})=>{
  await mockAuth(page);const signup=new SignupPage(page);await signup.goto();await signup.email.focus();await page.keyboard.press('Tab');await expect(signup.password).toBeFocused();await expect(signup.password).toHaveCSS('border-color','rgb(37, 99, 235)');await expect.poll(()=>signup.password.evaluate(el=>getComputedStyle(el).boxShadow)).toContain('4px')
  await signup.email.fill('person@example.test');await signup.terms.check()
  await page.evaluate(()=>{window.__oauthPending=true})
  await page.route('**/src/auth/supabaseClient.js*',route=>route.fulfill({contentType:'application/javascript',body:`export function getSupabaseAuthConfig(){return {}}; export const supabase={auth:{getSession:async()=>({data:{session:null}}),signInWithOAuth:async args=>{window.__oauthCalls.push(args);return new Promise(resolve=>window.__resolveOAuth=resolve)}}};`}))
  // Reload with the slow mock, then enter consent again; no real provider is contacted.
  await signup.goto();await signup.email.fill('person@example.test');await signup.terms.check();await page.getByRole('button',{name:'Sign in with Google'}).click();await expect(page.getByRole('button',{name:'Sign in with Google'})).toBeDisabled();expect(await page.evaluate(()=>window.__oauthCalls.length)).toBe(1);await page.evaluate(()=>window.__resolveOAuth({error:null}));await expect(page.getByRole('button',{name:'Sign in with Google'})).toBeEnabled()
})


test('already authenticated website signup respects the existing safe next redirect',async({page})=>{
  await mockAuth(page);await page.addInitScript(()=>{window.__session={access_token:'mock-only',user:{email:'person@example.test'}}});await page.goto('/auth/signup?next=%2Fauth%2Fstatus');await expect(page).toHaveURL(/\/auth\/status$/)
})
async function assertDesktopFits(page) {
  const geometry = await page.evaluate(() => {
    const root=document.documentElement
    const selectors=['.website-signup h1','.website-signup header p','.website-signup__google','.website-signup__divider span','.website-signup__field','.website-signup__consents label','.website-signup__submit','.website-signup footer p','.website-signup nav','.website-signup__features','#signup-password-help','.website-signup__mascot','.website-signup__status','.website-signup__brand','.website-signup__messages [role="alert"]']
    return {width:root.clientWidth,height:root.clientHeight,scrollWidth:root.scrollWidth,scrollHeight:root.scrollHeight,
      boxes:selectors.flatMap(selector=>[...document.querySelectorAll(selector)].map(el=>{const r=el.getBoundingClientRect();return {selector,left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height}})),
      overflow:[...document.querySelectorAll('.website-signup,.website-signup__credentials,.website-signup__content,.website-signup form')].map(el=>{const s=getComputedStyle(el);return [s.overflowX,s.overflowY]}),zoom:getComputedStyle(document.querySelector('.website-signup')).zoom}
  })
  expect(geometry.zoom).toBe('1');expect(geometry.scrollHeight).toBeLessThanOrEqual(geometry.height+1);expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.width)
  for(const box of geometry.boxes){expect(box.width,box.selector).toBeGreaterThan(0);expect(box.height,box.selector).toBeGreaterThan(0);expect(box.left,box.selector).toBeGreaterThanOrEqual(0);expect(box.top,box.selector).toBeGreaterThanOrEqual(0);expect(box.right,box.selector).toBeLessThanOrEqual(geometry.width+1);expect(box.bottom,box.selector).toBeLessThanOrEqual(geometry.height+1)}
  for(const pair of geometry.overflow)expect(pair).toEqual(['visible','visible'])
}
test('desktop signup fits every control without clipping at normal zoom, including errors',async({page})=>{
  await mockAuth(page);await page.emulateMedia({reducedMotion:'reduce'});const folder=path.resolve('..','tmp/signup-viewport-check');await mkdir(folder,{recursive:true})
  for(const [width,height] of [[1440,900],[1366,768],[1280,720],[1536,864]]){
    await page.setViewportSize({width,height});const signup=new SignupPage(page);await signup.goto();await page.evaluate(()=>document.fonts.ready);await expect.poll(()=>page.locator('main img').evaluateAll(images=>images.every(i=>i.complete&&i.naturalWidth>0))).toBe(true)
    await assertDesktopFits(page);await page.screenshot({path:path.join(folder,`signup-${width}x${height}.png`),fullPage:false,animations:'disabled'})
    await signup.email.fill('person@example.test');await page.getByRole('button',{name:'Sign in with Google'}).click();await expect(page.getByRole('alert')).toContainText('must agree');await assertDesktopFits(page)
    await signup.password.fill('sample-password');await page.getByRole('button',{name:'Show password'}).click();await expect(signup.password).toHaveAttribute('type','text');await page.getByRole('button',{name:'Hide password'}).click();await signup.terms.check();await signup.marketing.check();await expect(signup.marketing).toBeChecked();await expect(signup.terms).toBeChecked();await signup.marketing.uncheck()
    await page.evaluate(()=>window.__result={data:{session:null},error:{message:'Account creation is temporarily unavailable. Please try again.'}});await signup.submit.click();await expect(page.getByRole('alert')).toContainText('temporarily unavailable');await assertDesktopFits(page);await page.screenshot({path:path.join(folder,`signup-error-${width}x${height}.png`),fullPage:false,animations:'disabled'})
    await page.goto('/auth/login');await expect(page.getByRole('button',{name:'Sign In',exact:true})).toBeEnabled();await page.evaluate(()=>document.fonts.ready);const after=await page.screenshot({path:path.join(folder,`login-after-${width}x${height}.png`),fullPage:false,animations:'disabled'});expect(after).toEqual(await readFile(new URL(`./fixtures/login-viewport-before-${width}x${height}.png`,import.meta.url)))
  }
})
test('desktop mascot float stays within viewport and mobile can scroll naturally',async({page})=>{
  await mockAuth(page);await page.setViewportSize({width:1280,height:720});const signup=new SignupPage(page);await signup.goto();await page.evaluate(()=>document.fonts.ready)
  await page.evaluate(()=>{for(const el of document.querySelectorAll('main *'))for(const animation of el.getAnimations()){animation.pause();animation.currentTime=animation.effect.getTiming().iterations===Infinity?3000:1000}});await assertDesktopFits(page)
  await page.setViewportSize({width:390,height:844});await page.emulateMedia({reducedMotion:'reduce'});await signup.goto();await page.evaluate(()=>document.fonts.ready);expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(390);expect(await page.evaluate(()=>document.documentElement.scrollHeight)).toBeGreaterThan(844);await page.screenshot({path:path.resolve('..','tmp/signup-viewport-check/signup-mobile.png'),fullPage:true,animations:'disabled'});await signup.fill();await signup.terms.check();await signup.submit.click();await expect(page.getByRole('dialog',{name:'Check your email'})).toContainText('Check your email to verify your account.');await page.getByRole('button',{name:'Got it',exact:true}).click();await page.goto('/auth/login');await expect(page.getByRole('button',{name:'Sign In',exact:true})).toBeEnabled();await page.evaluate(()=>document.fonts.ready);const after=await page.screenshot({path:path.resolve('..','tmp/signup-viewport-check/login-after-390x844.png'),fullPage:false,animations:'disabled'});expect(after).toEqual(await readFile(new URL('./fixtures/login-viewport-before-390x844.png',import.meta.url)))
})


test('signup matches login visual controls and preserves its mascot at desktop and mobile sizes',async({page})=>{
  await mockAuth(page);await page.emulateMedia({reducedMotion:'reduce'});const folder=path.resolve('..','tmp/signup-login-match');await mkdir(folder,{recursive:true})
  const styles=async prefix=>page.evaluate(prefix=>{const read=selector=>{const el=document.querySelector(selector),s=getComputedStyle(el);return {font:s.fontFamily,fontSize:s.fontSize,height:s.height,color:s.color,background:s.backgroundColor,border:s.borderColor,radius:s.borderRadius}};return {input:read(`.${prefix}__input input`),google:read(`.${prefix}__google`),heading:read(`.${prefix} h1`),width:document.querySelector('form').getBoundingClientRect().width,columns:getComputedStyle(document.querySelector('main')).gridTemplateColumns}},prefix)
  for(const [width,height] of [[1440,900],[1366,768],[1280,720],[1536,864],[390,844],[360,800]]){
    await page.setViewportSize({width,height});await page.goto('/auth/login');await expect(page.getByRole('button',{name:'Sign In',exact:true})).toBeEnabled();await page.evaluate(()=>document.fonts.ready);const login=await styles('website-login');const screenshot=await page.screenshot({path:path.join(folder,`login-after-${width}x${height}.png`),fullPage:false,animations:'disabled'});expect(screenshot).toEqual(await readFile(new URL(`./fixtures/login-match-before-${width}x${height}.png`,import.meta.url)))
    const signup=new SignupPage(page);await signup.goto();await page.evaluate(()=>document.fonts.ready);await expect.poll(()=>page.locator('main img').evaluateAll(images=>images.every(i=>i.complete&&i.naturalWidth>0))).toBe(true);const appearance=await styles('website-signup');expect(appearance.input).toEqual(login.input);expect(appearance.google).toEqual(login.google);expect(appearance.heading).toEqual(login.heading);expect(appearance.width).toBe(login.width);if(width>900){expect(appearance.columns).toEqual(login.columns);await assertDesktopFits(page)}
    await expect(page.getByRole('link',{name:'Intervucopilot home'})).toBeVisible();await expect(page.getByRole('img',{name:'Friendly Intervucopilot robot opening a door, walking out and saying Welcome'})).toHaveAttribute('data-phase','complete');expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(width);await page.screenshot({path:path.join(folder,`signup-after-${width}x${height}.png`),fullPage:false,animations:'disabled'})
  }
})
async function beginOAuth(page, marketing=null, email='') {
  await mockAuth(page);const signup=new SignupPage(page);await signup.goto();await signup.email.fill(email)
  const google=page.getByRole('button',{name:'Sign in with Google'});await google.click();await expect(page.getByRole('alert')).toContainText('Terms');expect(await page.evaluate(()=>window.__oauthCalls.length)).toBe(0)
  await signup.terms.check();if(marketing!==null){await signup.marketing.check();if(!marketing)await signup.marketing.uncheck()}
  await google.click();await expect.poll(()=>page.evaluate(()=>window.__oauthCalls.length)).toBe(1)
  const url=new URL(await page.evaluate(()=>window.__oauthCalls[0].options.redirectTo));expect(url.searchParams.get('signup_attempt')).toBeTruthy();url.searchParams.delete('next')
  await page.addInitScript(()=>{window.__session={access_token:'mock-only',user:{id:'mock-user',email:'verified@example.test'}}});return url
}
for(const [marketing,email] of [[null,''],[true,'invalid'],[false,'different@example.test']])test(`Google without credentials ${marketing}/${email}`,async({page})=>{
  const url=await beginOAuth(page,marketing,email);await page.goto(url.href);await expect(page.getByText('Your consent preferences were saved.')).toBeVisible()
  expect(await page.evaluate(()=>window.__bootstrap.length)).toBe(1);expect(await page.evaluate(()=>window.__bootstrap[0])).toEqual({terms_accepted:true,privacy_accepted:true,marketing_email_opt_in:marketing,consent_source:'signup',consent_version:'c10.6a-v1'})
  expect(await page.evaluate(()=>sessionStorage.getItem('intervuai.googleSignupAttempt'))).toBeNull();await page.reload();await expect(page.getByText(/Signup preferences were not saved/)).toBeVisible();expect(await page.evaluate(()=>window.__bootstrap.length)).toBe(0)
})
test('ordinary login ignores signup choices',async({page})=>{await beginOAuth(page,true);await page.goto('/auth/callback');await expect(page.getByText('Signed in as person@example.test.')).toBeVisible();expect(await page.evaluate(()=>window.__bootstrap.length)).toBe(0)})
test('failed persistence retries with authenticated ownership',async({page})=>{
  const url=await beginOAuth(page,false);await page.route('**/api/auth/profile/bootstrap',r=>r.fulfill({status:503,json:{detail:'not ready'}}));await page.goto(url.href);await expect(page.getByText(/Signup preferences were not saved/)).toBeVisible()
  expect(await page.evaluate(()=>sessionStorage.getItem('intervuai.googleSignupAttempt'))).not.toBeNull();await page.unroute('**/api/auth/profile/bootstrap')
  await page.route('**/api/auth/profile/bootstrap',async r=>{expect(r.request().headers().authorization).toBe('Bearer mock-only');const body=r.request().postDataJSON();expect(body.user_id).toBeUndefined();await page.evaluate(x=>window.__bootstrap.push(x),body);await r.fulfill({json:{user_id:'mock-user'}})})
  await page.getByRole('button',{name:'Retry saving signup preferences'}).click();await expect(page.getByText('Your consent preferences were saved.')).toBeVisible();expect(await page.evaluate(()=>window.__bootstrap.length)).toBe(1)
})
for(const reason of ['cancelled','expired','missing-session'])test(`OAuth ${reason} safely discards consent`,async({page})=>{
  const url=await beginOAuth(page);if(reason==='cancelled')url.searchParams.set('error','access_denied');if(reason==='expired')await page.evaluate(()=>{const key='intervuai.googleSignupAttempt';const x=JSON.parse(sessionStorage.getItem(key));x.createdAt-=600001;sessionStorage.setItem(key,JSON.stringify(x))});if(reason==='missing-session')await page.addInitScript(()=>{window.__session=null})
  await page.goto(url.href);await expect(page.getByText(/Signup preferences were not saved/)).toBeVisible();expect(await page.evaluate(()=>window.__bootstrap.length)).toBe(0);expect(await page.evaluate(()=>sessionStorage.getItem('intervuai.googleSignupAttempt'))).toBeNull()
})
test('Intervucopilot fits desktop and mobile',async({page})=>{
  await mockAuth(page);await page.emulateMedia({reducedMotion:'reduce'});await mkdir(output,{recursive:true})
  for(const [width,height]of [[1366,768],[1280,720],[390,844]]){await page.setViewportSize({width,height});await new SignupPage(page).goto();await page.evaluate(()=>document.fonts.ready);const brand=page.getByRole('link',{name:'Intervucopilot home'});await expect(brand).toHaveText('Intervucopilot');expect(await brand.evaluate(el=>{const r=el.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&el.scrollWidth<=el.clientWidth+1})).toBe(true);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:path.join(output,`signup-brand-${width}x${height}.png`),fullPage:false,animations:'disabled'})}
})

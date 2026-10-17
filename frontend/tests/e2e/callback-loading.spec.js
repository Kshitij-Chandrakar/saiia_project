import { test, expect } from '@playwright/test'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'

async function mock(page, { failure = false, desktop = false } = {}) {
  await page.addInitScript(({failure, desktop}) => {
    if (desktop) window.electronAPI = {}
    window.__failure = failure
    window.__calls = 0
    window.__release = null
    window.__pending = new Promise(resolve => window.__release = resolve)
  }, {failure, desktop})
  await page.route('**/src/auth/supabaseClient.js*', route => route.fulfill({contentType:'application/javascript',body:`
    export const supabase={auth:{
      getSession:async()=>{window.__calls++;await window.__pending;return {data:{session:window.__failure?null:{access_token:'synthetic-only',user:{id:'synthetic-user'}}},error:null}},
      onAuthStateChange:()=>({data:{subscription:{unsubscribe(){}}}})
    }};export function getSupabaseAuthConfig(){return {}};
  `}))
  await page.route('**/api/**', route => {
    if(new URL(route.request().url()).pathname==='/api/onboarding') return route.fulfill({json:{onboarding_current_step:1,onboarding_completed_at:'completed'}})
    if(new URL(route.request().url()).pathname==='/api/auth/me') return route.fulfill({json:{user_id:'synthetic-user',email:'candidate@example.test'}})
    return route.fulfill({json:{items:[],ready:false,resume:null,has_candidate:false}})
  })
}

const pending = page => page.getByRole('dialog',{name:'Signing you in…',exact:true})

test('loading overflow and scroll restoration at desktop, tablet and short mobile sizes', async ({page}) => {
  await mock(page)
  for (const [width,height] of [[1366,768],[1280,720],[768,1024],[390,844],[390,260]]) {
    await page.setViewportSize({width,height}); await page.goto('/auth/callback'); await expect(pending(page)).toBeVisible()
    const metrics=await page.evaluate(()=>{
      const root=document.documentElement,body=document.body,card=document.querySelector('dialog')
      return {width:innerWidth,height:innerHeight,rootWidth:root.clientWidth,rootScroll:root.scrollHeight,bodyOverflow:getComputedStyle(body).overflow,rootOverflow:getComputedStyle(root).overflow,cardHeight:card.clientHeight,cardScroll:card.scrollHeight,cardWidth:card.clientWidth,cardScrollWidth:card.scrollWidth}
    })
    if(height>=301+32) expect(metrics.cardScroll).toBe(metrics.cardHeight)
    else expect(metrics.cardScroll).toBeGreaterThan(metrics.cardHeight)
    expect(metrics.bodyOverflow).toBe('hidden'); expect(metrics.rootOverflow).toBe('hidden')
    expect(metrics.cardScrollWidth).toBe(metrics.cardWidth)
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
    const box=await pending(page).boundingBox()
    expect(box.y).toBeGreaterThanOrEqual(16); expect(box.y+box.height).toBeLessThanOrEqual(height-16)
    await page.mouse.wheel(0,500); expect(await page.evaluate(()=>scrollY)).toBe(0)
    if(height===260) {
      await pending(page).getByText('Please wait',{exact:true}).scrollIntoViewIfNeeded()
      expect(await pending(page).evaluate(el=>el.scrollTop)).toBeGreaterThan(0)
      expect(await page.evaluate(()=>scrollY)).toBe(0)
    }
    await page.screenshot({path:path.resolve(`../tmp/callback-loading/overflow-fixed-${width}x${height}.png`)})
    await page.evaluate(()=>{window.__failure=true;window.__release()})
    await expect(pending(page)).toHaveCount(0)
    expect(await page.evaluate(()=>document.body.style.overflow)).toBe('')
    expect(await page.evaluate(()=>document.documentElement.style.overflow)).toBe('')
    await page.getByRole('link',{name:'Back to sign in'}).click()
    await expect(page.getByRole('heading',{name:'Welcome back!',exact:true})).toBeVisible()
    if(height===260) {
      await page.mouse.wheel(0,500)
      await expect.poll(()=>page.evaluate(()=>scrollY)).toBeGreaterThan(0)
    }
  }
})

test('cleanup restores pre-existing scroll styles without unlocking another owner', async ({page}) => {
  await mock(page,{failure:true})
  await page.goto('/auth/login'); await expect(page.getByRole('heading',{name:'Welcome back!',exact:true})).toBeVisible()
  await page.evaluate(()=>{
    document.documentElement.style.overflow='clip'; document.body.style.overflow='hidden'; document.body.style.paddingRight='7px'
    history.pushState({},'', '/auth/callback'); dispatchEvent(new PopStateEvent('popstate'))
  })
  await expect(pending(page)).toBeVisible(); await page.evaluate(()=>window.__release())
  await expect(pending(page)).toHaveCount(0)
  expect(await page.evaluate(()=>({root:document.documentElement.style.overflow,body:document.body.style.overflow,padding:document.body.style.paddingRight}))).toEqual({root:'clip',body:'hidden',padding:'7px'})
})

test('pending modal, inert shared login, no dismissal, one verification, safe success', async ({page}) => {
  await mock(page); await page.goto('/auth/callback?next=%2Fauth%2Fresume')
  await expect(pending(page)).toBeVisible(); await expect(pending(page)).toBeFocused()
  await expect(page.getByRole('heading',{name:'Auth Status'})).toHaveCount(0)
  expect(await page.locator('.website-login').count()).toBe(1)
  expect(await page.locator('#website-login-email').inputValue()).toBe('')
  await page.keyboard.press('Tab'); await expect(pending(page)).toBeFocused()
  await page.keyboard.press('Escape'); await page.mouse.click(5,5); await expect(pending(page)).toBeVisible()
  expect(await page.evaluate(()=>window.__calls)).toBe(1)
  expect(await page.evaluate(()=>getComputedStyle(document.querySelector('dialog')).opacity)).toBe('1')
  expect(await page.evaluate(()=>getComputedStyle(document.querySelector('.website-callback__spinner')).animationName)).toBe('website-callback-spin')
  await page.evaluate(()=>window.__release()); await expect(page).toHaveURL(/\/auth\/resume$/)
  await expect(page.getByRole('heading',{name:'Resumes',level:1})).toBeVisible()
  expect(await page.evaluate(()=>document.body.style.overflow)).not.toBe('hidden')
})

for (const next of ['', '?next=https%3A%2F%2Fevil.example', '?next=%2F%2Fevil.example', '?next=%2Fauth%2Flogin']) {
  test(`safe fallback for ${next || 'no next'}`, async ({page}) => {
    await mock(page); await page.goto(`/auth/callback${next}`); await expect(pending(page)).toBeVisible()
    await page.evaluate(()=>window.__release()); await expect(page).toHaveURL(/\/auth\/dashboard$/)
  })
}

test('terminal failure stops motion, releases scroll lock, and keeps safe recovery destination', async ({page}) => {
  await mock(page,{failure:true}); await page.goto('/auth/callback?next=%2Fauth%2Fsessions')
  await expect(pending(page)).toBeVisible(); await page.evaluate(()=>window.__release())
  await expect(pending(page)).toHaveCount(0)
  await expect(page.getByRole('link',{name:'Back to sign in'})).toBeFocused()
  const background = page.locator('.website-callback > [aria-hidden="true"]')
  await expect(background).toHaveJSProperty('inert',true)
  for (let index=0; index<5; index++) {
    await page.keyboard.press('Tab')
    expect(await background.evaluate(node=>node.contains(document.activeElement))).toBe(false)
  }
  await page.locator('.website-login input[type="email"]').evaluate(node=>node.focus())
  expect(await background.evaluate(node=>node.contains(document.activeElement))).toBe(false)
  await expect(page.locator('.website-callback__spinner')).toHaveCount(0)
  expect(await page.evaluate(()=>document.body.style.overflow)).not.toBe('hidden')
  await expect(page.getByRole('link',{name:'Back to sign in'})).toHaveAttribute('href','/auth/login?next=%2Fauth%2Fsessions')
  await page.getByRole('link',{name:'Back to sign in'}).click(); await expect(page).toHaveURL(/\/auth\/login\?next=%2Fauth%2Fsessions$/)
  await expect(page.getByRole('heading',{name:'Welcome back!',exact:true})).toBeVisible()
})

test('provider cancellation is neutral even with an existing session', async ({page}) => {
  await mock(page); await page.goto('/auth/callback?error=access_denied&error_description=sensitive-detail')
  await expect(page.getByRole('heading',{name:'Unable to finish sign-in'})).toBeVisible()
  await expect(page.locator('.website-callback__card')).not.toContainText('sensitive-detail')
  expect(await page.evaluate(()=>window.__calls)).toBe(0)
})

test('backend verification failure shows generic recovery, never expiry or raw errors', async ({page}) => {
  await mock(page)
  await page.route('**/api/auth/me', route => route.fulfill({status:503,json:{detail:'sensitive provider diagnostic'}}))
  await page.goto('/auth/callback'); await expect(pending(page)).toBeVisible(); await page.evaluate(()=>window.__release())
  await expect(page.getByRole('heading',{name:'Unable to finish sign-in'})).toBeVisible()
  await expect(page.locator('.website-callback__card')).not.toContainText('sensitive provider diagnostic')
  await expect(page.locator('.website-callback__card')).not.toContainText('expired')
})

test('navigation during pending work releases the modal and ignores a late result', async ({page}) => {
  await mock(page); await page.goto('/auth/callback?next=%2Fauth%2Fresume'); await expect(pending(page)).toBeVisible()
  // Same-document router navigation exercises effect cleanup while the provider is pending.
  await page.evaluate(()=>{history.pushState({},'', '/auth/login');dispatchEvent(new PopStateEvent('popstate'))})
  await expect(pending(page)).toHaveCount(0); expect(await page.evaluate(()=>document.body.style.overflow)).not.toBe('hidden')
  await page.evaluate(()=>{window.__failure=true;window.__release()})
  await expect(page.getByRole('heading',{name:'Welcome back!',exact:true})).toBeVisible(); await expect(page).toHaveURL(/\/auth\/login$/)
})

test('refreshing the callback retains a safe destination and no expiry notice', async ({page}) => {
  await mock(page); await page.goto('/auth/callback?next=%2Fauth%2Fsessions'); await expect(pending(page)).toBeVisible()
  await page.reload(); await expect(pending(page)).toBeVisible(); expect(await page.evaluate(()=>window.__calls)).toBe(1)
  await page.evaluate(()=>window.__release()); await expect(page).toHaveURL(/\/auth\/sessions$/)
  await expect(page.getByRole('heading',{name:'Call Sessions',level:1})).toBeVisible()
})

test('desktop callback keeps existing presentation', async ({page}) => {
  await mock(page,{desktop:true}); await page.goto('/auth/callback')
  await expect(page.getByRole('heading',{name:'Auth Status'})).toBeVisible(); await expect(pending(page)).toHaveCount(0)
  await page.evaluate(()=>window.__release()); await expect(page.getByText('Signed in as candidate@example.test.',{exact:true})).toBeVisible()
})

test('responsive reference geometry, reduced motion and recorded pending-to-success transition', async ({browser}) => {
  const output=path.resolve('../tmp/callback-loading'); await mkdir(output,{recursive:true})
  for (const [width,height] of [[1366,768],[1280,720],[768,1024],[390,844]]) {
    const context=await browser.newContext({viewport:{width,height},baseURL:'http://127.0.0.1:5173',recordVideo:width===1366?{dir:output,size:{width,height}}:undefined})
    const page=await context.newPage(); await mock(page); await page.goto('/auth/callback?next=%2Fauth%2Fresume')
    await expect(pending(page)).toBeVisible()
    const box=await pending(page).boundingBox(); expect(box.width).toBe(Math.min(370,width-32)); expect(box.height).toBe(301)
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
    await page.screenshot({path:path.join(output,`pending-${width}.png`)})
    const animation=await page.locator('.website-callback__spinner').evaluate(el=>el.getAnimations()[0].currentTime)
    await expect.poll(()=>page.locator('.website-callback__spinner').evaluate(el=>el.getAnimations()[0].currentTime)).toBeGreaterThan(animation+300)
    await page.emulateMedia({reducedMotion:'reduce'}); await expect(page.locator('.website-callback__spinner')).toHaveCSS('animation-name','none')
    if(width===390) await page.screenshot({path:path.join(output,'reduced-motion.png')})
    await page.emulateMedia({reducedMotion:'no-preference'}); await page.evaluate(()=>window.__release()); await expect(page.getByRole('heading',{name:'Resumes',level:1})).toBeVisible()
    const video=page.video(); await context.close(); if(video)await video.saveAs(path.join(output,'callback-transition.webm'))
  }
})

async function pendingSignupCallback(page, { attempt = false, pending = true, failure = false } = {}) {
  const consent = {terms_accepted:true,privacy_accepted:true,marketing_email_opt_in:false,consent_source:'signup',consent_version:'c10.6a-v1'}
  await page.addInitScript(({attempt,pending,consent}) => {
    if(pending)localStorage.setItem('intervuai.pendingSignupConsent',JSON.stringify({email:'candidate@example.test',consent}))
    if(attempt)sessionStorage.setItem('intervuai.googleSignupAttempt',JSON.stringify({attempt:'synthetic-attempt',createdAt:Date.now(),consent}))
  }, {attempt,pending,consent})
  await page.route('**/src/auth/AuthScreens.jsx*',async route=>{
    const response=await route.fetch()
    const body=(await response.text()).replace(/const CONSENT_FEATURE_ENABLED = [^\n]+/,'const CONSENT_FEATURE_ENABLED = true;')
    await route.fulfill({response,body})
  })
  await page.route('**/src/auth/supabaseClient.js*',route=>route.fulfill({contentType:'application/javascript',body:`
    export const supabase={auth:{getSession:async()=>({data:{session:{access_token:'synthetic',user:{id:'owner',email:'candidate@example.test'}}}}),onAuthStateChange:()=>({data:{subscription:{unsubscribe(){}}}})}};export function getSupabaseAuthConfig(){return {}};
  `}))
  let bootstraps=0,ready=!pending
  await page.route('**/api/**',async route=>{
    const endpoint=new URL(route.request().url()).pathname
    if(endpoint==='/api/auth/me')return route.fulfill({json:{user_id:'owner',email:'candidate@example.test'}})
    if(endpoint==='/api/auth/profile/bootstrap'){
      bootstraps++;expect(route.request().postDataJSON()).toEqual(consent)
      if(failure)return route.fulfill({status:503,json:{detail:'private bootstrap failure'}})
      ready=true;return route.fulfill({json:{profile_exists:true,settings_exists:true}})
    }
    if(endpoint==='/api/onboarding')return route.fulfill(ready?{json:{onboarding_current_step:1,onboarding_completed_at:pending?null:'completed'}}:{status:503,json:{detail:'Missing settings'}})
    return route.fulfill({json:{items:[],ready:false,resume:null,has_candidate:false}})
  })
  return {count:()=>bootstraps,route:'/auth/callback'+(attempt?'?signup_attempt=synthetic-attempt':'')}
}
test('email callback without signup_attempt bootstraps before onboarding and clears pending consent',async({page})=>{
  const f=await pendingSignupCallback(page)
  await page.goto(f.route)
  await expect(page.getByRole('heading',{name:'Welcome to Intervucopilot',exact:true})).toBeVisible()
  await expect(page).toHaveURL(/auth\/onboarding$/)
  expect(f.count()).toBe(1)
  expect(await page.evaluate(()=>localStorage.getItem('intervuai.pendingSignupConsent'))).toBeNull()
})
test('signup_attempt callback uses only its existing bootstrap operation',async({page})=>{
  const f=await pendingSignupCallback(page,{attempt:true})
  await page.goto(f.route)
  await expect(page.getByRole('heading',{name:'Welcome to Intervucopilot',exact:true})).toBeVisible()
  expect(f.count()).toBe(1)
  expect(await page.evaluate(()=>sessionStorage.getItem('intervuai.googleSignupAttempt'))).toBeNull()
  expect(await page.evaluate(()=>localStorage.getItem('intervuai.pendingSignupConsent'))).not.toBeNull()
})
test('ordinary callback without pending consent reaches existing dashboard without a consent write',async({page})=>{
  const f=await pendingSignupCallback(page,{pending:false})
  await page.goto(f.route)
  await expect(page.getByRole('heading',{name:'Welcome back!',exact:true})).toBeVisible()
  expect(f.count()).toBe(0)
})
test('email callback bootstrap failure keeps pending data and does not enter onboarding',async({page})=>{
  const f=await pendingSignupCallback(page,{failure:true})
  await page.goto(f.route)
  await expect(page.getByText('Sign in could not be verified. Please try again.',{exact:true})).toBeVisible()
  await expect(page).toHaveURL(/auth\/callback$/)
  expect(f.count()).toBe(1)
  expect(await page.evaluate(()=>localStorage.getItem('intervuai.pendingSignupConsent'))).not.toBeNull()
  await expect(page.getByRole('heading',{name:'Welcome to Intervucopilot',exact:true})).toHaveCount(0)
})

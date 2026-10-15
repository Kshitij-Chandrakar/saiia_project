import { test, expect } from '@playwright/test'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'

const output = path.resolve('../tmp/session-notice')

async function mock(page, { signedIn = true, sessionError = null, initializing = false } = {}) {
  await page.addInitScript(({signedIn,sessionError,initializing}) => {
    const remembered = sessionStorage.getItem('synthetic-authenticated')
    window.__session = (remembered === null ? signedIn : remembered === 'true') ? {access_token:'synthetic-only',user:{id:'synthetic-user'}} : null
    window.__sessionError = sessionStorage.getItem('synthetic-session-error') ? {code:sessionStorage.getItem('synthetic-session-error')} : sessionError; window.__initializing = initializing
    window.__listeners = []; window.__passwordCalls = 0; window.__oauthCalls = []
    window.__ready = new Promise(resolve=>window.__finishInitialization=()=>{window.__initializing=false;resolve()})
  }, {signedIn,sessionError,initializing})
  await page.route('**/src/auth/supabaseClient.js*', route => route.fulfill({contentType:'application/javascript',body:`
    const provider = new BroadcastChannel('synthetic-auth-events');
    window.__emit = (event,session,broadcast=true) => {
      window.__session=session;
      sessionStorage.setItem('synthetic-authenticated',String(Boolean(session)));
      for(const callback of [...window.__listeners]) callback(event,session);
      if(broadcast)provider.postMessage({event,authenticated:Boolean(session)});
    };
    provider.onmessage=({data})=>window.__emit(data.event,data.authenticated?{access_token:'synthetic-only',user:{id:'synthetic-user'}}:null,false);
    export const supabase={auth:{
      getSession:async()=>{if(window.__initializing)await window.__ready;return {data:{session:window.__sessionError?null:window.__session},error:window.__sessionError}},
      onAuthStateChange:callback=>{window.__listeners.push(callback);return {data:{subscription:{unsubscribe(){window.__listeners=window.__listeners.filter(x=>x!==callback)}}}}},
      signOut:async()=>{if(window.__logoutFailure)return {error:{message:'Synthetic failure'}};window.__emit('SIGNED_OUT',null);return {error:null}},
      signInWithPassword:async()=>{window.__passwordCalls++;const session={access_token:'synthetic-only',user:{id:'synthetic-user'}};window.__emit('SIGNED_IN',session);return {data:{session},error:null}},
      signInWithOAuth:async options=>{window.__oauthCalls.push(options);return {error:null}}
    }}; export function getSupabaseAuthConfig(){return {}};
  `}))
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url())
    if(url.pathname==='/api/auth/me')return route.fulfill({json:{user_id:'synthetic-user',email:'candidate@example.test',role:'authenticated'}})
    if(url.pathname==='/api/resumes/current')return route.fulfill({json:{ready:false,resume:null}})
    if(url.pathname==='/api/resumes/review-candidate')return route.fulfill({json:{has_candidate:false,resume:null}})
    return route.fulfill({json:{items:[],page:1,limit:20}})
  })
}

class SessionNotice {
  constructor(page) { this.page=page }
  dialog(name='You’ve been signed out') { return this.page.getByRole('dialog',{name,exact:true}) }
  async open(route='/auth/dashboard') {
    await this.page.goto(route)
    await expect(this.page.getByRole('heading',{name:route==='/auth/resume'?'Resumes':route==='/auth/sessions'?'Call Sessions':'Dashboard',level:1})).toBeVisible()
    await expect(this.page.getByRole('button',{name:'Logout',exact:true})).toBeVisible()
  }
  async lose() { await this.page.evaluate(()=>window.__emit('SIGNED_OUT',null)); await expect(this.dialog()).toBeVisible() }
}

test('unknown loss, deduplication, inert background, keyboard dismissal, focus and one-time consumption', async ({page}) => {
  await mock(page); const notice=new SessionNotice(page); await notice.open('/auth/sessions')
  await page.evaluate(()=>{window.__emit('SIGNED_OUT',null);window.__emit('SIGNED_OUT',null);window.__emit('SIGNED_OUT',null)})
  const dialog=notice.dialog(); await expect(dialog).toBeVisible(); await expect(page.getByRole('dialog')).toHaveCount(1)
  await expect(dialog).toContainText('Please sign in again to continue.')
  await expect(dialog).not.toContainText('inactivity'); await expect(dialog).not.toContainText('SESSION EXPIRED')
  await expect(page.getByText('Session expired or signed out. Please log in.',{exact:true})).toHaveCount(0)
  const action=dialog.getByRole('button',{name:'Sign in again',exact:true}); await expect(action).toBeFocused()
  await page.keyboard.press('Tab'); await expect(action).toBeFocused(); await page.keyboard.press('Shift+Tab'); await expect(action).toBeFocused()
  expect(await page.evaluate(()=>document.body.style.overflow)).toBe('hidden')
  await page.mouse.click(5,5); await expect(dialog).toBeVisible()
  expect(await page.evaluate(()=>history.state.usr.sessionLoss)).toBeUndefined()
  await action.click(); await expect(dialog).toHaveCount(0); await expect(page.getByLabel('Email Address',{exact:true})).toBeFocused()
  expect(await page.evaluate(()=>window.__passwordCalls)).toBe(0); expect(await page.evaluate(()=>window.__oauthCalls)).toEqual([])
  expect(await page.evaluate(()=>document.body.style.overflow)).not.toBe('hidden')
  await page.getByRole('button',{name:'Privacy Policy',exact:true}).click(); await expect(dialog).toHaveCount(0)
  await page.reload(); await expect(page.getByRole('heading',{name:'Welcome back!',exact:true})).toBeVisible(); await expect(dialog).toHaveCount(0)
  await page.getByRole('link',{name:'Create free account',exact:true}).click(); await page.goBack(); await expect(dialog).toHaveCount(0)
  await expect(page).toHaveURL(/next=%2Fauth%2Fsessions/)
  await page.getByLabel('Email Address',{exact:true}).fill('candidate@example.test'); await page.getByLabel('Password',{exact:true}).fill('synthetic-password')
  await page.getByRole('button',{name:'Sign In',exact:true}).click(); await expect(page).toHaveURL(/\/auth\/sessions$/)
  await expect(page.getByRole('heading',{name:'Call Sessions',level:1})).toBeVisible()
})

test('provider-confirmed expiry uses truthful wording; Escape focuses email', async ({page}) => {
  await mock(page,{signedIn:false,sessionError:{code:'session_expired'}})
  await page.goto('/auth/dashboard'); const dialog=new SessionNotice(page).dialog('Session expired')
  await expect(dialog).toBeVisible(); await expect(dialog).toContainText('Your session has expired. Please sign in again to continue.')
  await expect(dialog).not.toContainText('inactivity')
  await page.keyboard.press('Escape'); await expect(dialog).toHaveCount(0); await expect(page.getByLabel('Email Address',{exact:true})).toBeFocused()
})

test('account page observes unexpected loss and preserves its safe return route', async ({page}) => {
  await mock(page); await page.goto('/auth/status')
  await expect(page.getByText('candidate@example.test',{exact:true})).toBeVisible()
  const notice=new SessionNotice(page); await notice.lose()
  await expect(page).toHaveURL(/next=%2Fauth%2Fstatus/)
  await notice.dialog().getByRole('button',{name:'Sign in again',exact:true}).click()
  await page.getByLabel('Email Address',{exact:true}).fill('candidate@example.test'); await page.getByLabel('Password',{exact:true}).fill('synthetic-password')
  await page.getByRole('button',{name:'Sign In',exact:true}).click(); await expect(page).toHaveURL(/\/auth\/status$/)
  await expect(page.getByText('candidate@example.test',{exact:true})).toBeVisible()
})

test('account page distinguishes an explicit provider expiry from an ordinary unauthenticated visit', async ({page}) => {
  await mock(page,{signedIn:false}); await page.goto('/auth/status')
  await expect(page.getByText('No active auth session was found.',{exact:true})).toBeVisible(); await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.evaluate(()=>sessionStorage.setItem('synthetic-session-error','session_expired')); await page.reload()
  await expect(new SessionNotice(page).dialog('Session expired')).toBeVisible()
})

test('ordinary login, first-time protected visit and URL reason flags never produce a popup', async ({page}) => {
  await mock(page,{signedIn:false})
  for(const route of ['/auth/login','/auth/login?reason=expired&next=https://outside.example','/auth/login?reason=inactivity&next=//outside.example','/auth/resume']) {
    await page.goto(route); await expect(page.getByRole('heading',{name:'Welcome back!',exact:true})).toBeVisible()
    await expect(page.getByRole('dialog')).toHaveCount(0)
  }
})

test('initialization and successful refresh never announce expiry', async ({page}) => {
  await mock(page,{initializing:true}); await page.goto('/auth/dashboard')
  await expect(page.getByRole('status').filter({hasText:'Loading dashboard…'})).toBeVisible()
  await page.evaluate(()=>window.__emit('INITIAL_SESSION',null,false)); await expect(page).toHaveURL(/\/auth\/dashboard$/)
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.evaluate(()=>{window.__session={access_token:'synthetic-only',user:{id:'synthetic-user'}};window.__finishInitialization()})
  await expect(page.getByRole('heading',{name:'Dashboard',level:1})).toBeVisible()
  await expect(page.getByRole('button',{name:'Logout',exact:true})).toBeVisible()
  await page.evaluate(()=>window.__emit('TOKEN_REFRESHED',{access_token:'refreshed-synthetic-only',user:{id:'synthetic-user'}}))
  await expect(page.getByRole('heading',{name:'Dashboard',level:1})).toBeVisible(); await expect(page.getByRole('dialog')).toHaveCount(0)
})

for (const status of [401,403,503]) test(`API ${status} remains an actionable verification error, never expiry`, async ({page}) => {
  await mock(page)
  await page.route('**/api/auth/me',route=>route.fulfill({status,json:{detail:'Synthetic verification failure'}}))
  await page.goto('/auth/dashboard'); await expect(page.getByText('Synthetic verification failure',{exact:true})).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0); await expect(page).toHaveURL(/\/auth\/dashboard$/)
  await page.unroute('**/api/auth/me'); await page.getByRole('button',{name:'Retry session check',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Dashboard',level:1})).toBeVisible()
  await expect(page.getByRole('button',{name:'Logout',exact:true})).toBeVisible()
})

test('retryable session recovery errors are not sign-out events', async ({page}) => {
  await mock(page,{sessionError:{code:'network_error'}}); await page.goto('/auth/dashboard')
  await expect(page.getByText('Could not verify your session. Please try again.',{exact:true})).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.evaluate(()=>window.__sessionError=null); await page.getByRole('button',{name:'Retry session check',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Dashboard',level:1})).toBeVisible()
  await expect(page.getByRole('button',{name:'Logout',exact:true})).toBeVisible()
})

test('intentional and failed logout; cross-tab intentional logout stays neutral', async ({page,context}) => {
  await mock(page); const second=await context.newPage(); await mock(second)
  await new SessionNotice(page).open(); await new SessionNotice(second).open('/auth/resume')
  await page.evaluate(()=>window.__logoutFailure=true); await page.getByRole('button',{name:'Logout',exact:true}).click()
  await expect(page.getByText('Sign out failed. Please try again.',{exact:true})).toBeVisible()
  await expect(second.getByRole('heading',{name:'Resumes',level:1})).toBeVisible()
  await page.evaluate(()=>window.__logoutFailure=false); await page.getByRole('button',{name:'Logout',exact:true}).click()
  for(const tab of [page,second]) { await expect(tab).toHaveURL(/\/auth\/login/); await expect(tab.getByRole('heading',{name:'Welcome back!',exact:true})).toBeVisible(); await expect(tab.getByRole('dialog')).toHaveCount(0) }
})

test('restored session closes an obsolete prompt and a fresh loss can open a new one', async ({page}) => {
  await mock(page); const notice=new SessionNotice(page); await notice.open('/auth/resume'); await notice.lose()
  await page.evaluate(()=>window.__emit('SIGNED_IN',{access_token:'restored-synthetic-only',user:{id:'synthetic-user'}}))
  await expect(page.getByRole('heading',{name:'Resumes',level:1})).toBeVisible(); await expect(page.getByRole('dialog')).toHaveCount(0)
  await notice.lose(); await expect(notice.dialog()).toBeVisible()
})

test('logging in after intentional logout does not suppress a new unexpected loss', async ({page}) => {
  await mock(page); const notice=new SessionNotice(page); await notice.open()
  await page.getByRole('button',{name:'Logout',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Welcome back!',exact:true})).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.getByLabel('Email Address',{exact:true}).fill('candidate@example.test'); await page.getByLabel('Password',{exact:true}).fill('synthetic-password')
  await page.getByRole('button',{name:'Sign In',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Dashboard',level:1})).toBeVisible()
  await notice.lose(); await expect(notice.dialog()).toBeVisible()
})

for(const origin of ['/auth/status','/auth/logout'])test(`intentional logout through ${origin} suppresses the other tab's notice`, async ({page,context}) => {
  await mock(page); const second=await context.newPage(); await mock(second); await new SessionNotice(second).open()
  await page.goto(origin)
  if(origin==='/auth/status')await page.getByRole('button',{name:'Logout',exact:true}).click()
  await expect(second).toHaveURL(/\/auth\/login/)
  await expect(second.getByRole('heading',{name:'Welcome back!',exact:true})).toBeVisible()
  await expect(second.getByRole('dialog')).toHaveCount(0)
})

test('Google sign-in retains safe next; unsafe login and logout destinations stay rejected', async ({page}) => {
  await mock(page); const notice=new SessionNotice(page); await notice.open('/auth/resume'); await notice.lose()
  await notice.dialog().getByRole('button',{name:'Sign in again',exact:true}).click()
  await page.getByRole('button',{name:'Sign in with Google',exact:true}).click()
  const requests=await page.evaluate(()=>window.__oauthCalls)
  expect(requests).toHaveLength(1); expect(new URL(requests[0].options.redirectTo).searchParams.get('next')).toBe('/auth/resume')
  for(const next of ['https://outside.example','//outside.example','/auth/login','/auth/logout']) {
    await page.goto('/auth/login?next='+encodeURIComponent(next)); await page.getByLabel('Email Address',{exact:true}).fill('candidate@example.test'); await page.getByLabel('Password',{exact:true}).fill('synthetic-password')
    await page.getByRole('button',{name:'Sign In',exact:true}).click(); await expect(page).toHaveURL(/\/auth\/dashboard$/)
    await page.getByRole('button',{name:'Logout',exact:true}).click(); await expect(page.getByRole('heading',{name:'Welcome back!',exact:true})).toBeVisible()
  }
})

test('Figma geometry, asset, reduced motion and screenshots at four viewports', async ({page}) => {
  await mock(page); await mkdir(output,{recursive:true}); const notice=new SessionNotice(page)
  for(const [width,height] of [[1366,768],[1280,720],[768,1024],[390,844]]) {
    await page.setViewportSize({width,height}); await notice.open(); await notice.lose()
    const dialog=notice.dialog(); await page.evaluate(()=>document.fonts.ready)
    await expect.poll(()=>dialog.evaluate(d=>d.getAnimations().every(a=>a.playState==='finished'))).toBe(true)
    const geometry=await dialog.evaluate(d=>{const r=d.getBoundingClientRect(),img=d.querySelector('img'),button=d.querySelector('button');return {width:r.width,height:r.height,x:r.x,y:r.y,image:[img.getBoundingClientRect().width,img.getBoundingClientRect().height],imageLoaded:img.complete&&img.naturalWidth>0,button:[button.getBoundingClientRect().width,button.getBoundingClientRect().height],padding:getComputedStyle(d).padding,borderRadius:getComputedStyle(d).borderRadius}})
    expect(geometry.width).toBe(350);expect(geometry.height).toBe(384);expect(geometry.padding).toBe('32px');expect(geometry.borderRadius).toBe('12px');expect(geometry.image).toEqual([36,36]);expect(geometry.imageLoaded).toBe(true);expect(geometry.button).toEqual([286,48])
    expect(geometry.x).toBeCloseTo((width-350)/2);expect(geometry.y).toBeCloseTo((height-384)/2)
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(width)
    await page.screenshot({path:path.join(output,`signed-out-${width}.png`),fullPage:false})
    await dialog.getByRole('button',{name:'Sign in again',exact:true}).click()
    await page.evaluate(()=>window.__emit('SIGNED_IN',{access_token:'synthetic-only',user:{id:'synthetic-user'}}))
  }
  await page.emulateMedia({reducedMotion:'reduce'}); await notice.open(); await notice.lose()
  await expect(notice.dialog()).toHaveCSS('animation-name','none'); await page.screenshot({path:path.join(output,'reduced-motion.png')})
  await page.keyboard.press('Escape'); await page.evaluate(()=>{window.__session=null;sessionStorage.setItem('synthetic-authenticated','false');sessionStorage.setItem('synthetic-session-error','session_expired')})
  await page.goto('/auth/dashboard'); await expect(notice.dialog('Session expired')).toBeVisible()
  await page.screenshot({path:path.join(output,'expired-390.png')})
})

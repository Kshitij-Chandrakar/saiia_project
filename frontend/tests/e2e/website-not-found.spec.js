import { test, expect } from '@playwright/test'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'
const output = path.resolve('..', 'tmp/website-404')
async function mockAuth(page) {
  await page.route('**/src/auth/supabaseClient.js*', route => route.fulfill({contentType:'application/javascript',body:`export function getSupabaseAuthConfig(){return {}};export const supabase={auth:{getSession:async()=>({data:{session:null}}),onAuthStateChange:()=>({data:{subscription:{unsubscribe(){}}}})}}`}))
}
test('unknown route renders compact accessible card and survives refresh', async ({page}) => {
  await mockAuth(page)
  await page.emulateMedia({reducedMotion:'reduce'})
  const errors=[]
  page.on('pageerror',e=>errors.push(e.message))
  page.on('console',m=>{if(m.type()==='error')errors.push(m.text())})
  page.on('response',r=>{if(r.url().includes('/src/assets/')&&r.status()>=400)errors.push('Failed illustration')})
  await mkdir(output,{recursive:true})
  for(const [width,height] of [[1366,768],[1280,720],[390,844],[360,800]]) {
    await page.setViewportSize({width,height})
    const response=await page.goto('/missing-website-page')
    expect(response.status()).toBe(200) // Vite SPA fallback, not an HTTP 404.
    await expect(page.getByRole('heading',{name:'Page not found',exact:true})).toBeFocused()
    await expect(page).toHaveTitle('Page not found | Intervucopilot')
    await page.evaluate(async()=>{await document.fonts.ready;await Promise.all([...document.images].map(i=>i.decode()))})
    const geometry=await page.getByRole('main').evaluate(main=>{
      const card=main.querySelector('section'),r=card.getBoundingClientRect(),img=card.querySelector('img')
      return {width:r.width,height:r.height,ratio:img.getBoundingClientRect().width/img.getBoundingClientRect().height,loaded:img.complete&&img.naturalWidth>0,contained:[...card.querySelectorAll('span,img,h1,p,a,button')].every(e=>{const b=e.getBoundingClientRect();return b.top>=0&&b.bottom<=innerHeight&&b.left>=0&&b.right<=innerWidth}),overflow:document.documentElement.scrollWidth>innerWidth}
    })
    expect(geometry.loaded).toBe(true);expect(geometry.contained).toBe(true);expect(geometry.overflow).toBe(false);expect(geometry.ratio).toBe(1)
    if(width>900)expect({width:geometry.width,height:geometry.height}).toEqual({width:370,height:432})
    await page.screenshot({path:path.join(output,`${width}x${height}.png`),fullPage:false})
  }
  await page.reload();await expect(page.getByRole('heading',{name:'Page not found'})).toBeVisible()
  await page.evaluate(()=>document.body.style.zoom='2')
  const back=page.getByRole('button',{name:'Go back',exact:true});await back.scrollIntoViewIfNeeded()
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  await page.getByRole('link',{name:'Back to home'}).focus();await expect(page.getByRole('link',{name:'Back to home'})).toBeFocused()
  await page.evaluate(()=>document.body.style.zoom='1');await back.click();await expect(page).toHaveURL(/\/$/)
  expect(errors).toEqual([])
})
test('home action uses landing route and internal Go back retains known route', async ({page})=>{
 await mockAuth(page)
 await page.goto('/auth/login')
 // Same router navigation as an internal application link, without a document reload.
 await page.evaluate(()=>{history.pushState({key:'test-internal'},'', '/unknown-internal');dispatchEvent(new PopStateEvent('popstate'))})
 await expect(page.getByRole('heading',{name:'Page not found'})).toBeVisible()
 await page.getByRole('button',{name:'Go back',exact:true}).click();await expect(page).toHaveURL(/\/auth\/login$/)
 await page.goto('/unknown-direct');await page.getByRole('link',{name:'Back to home'}).click();await expect(page).toHaveURL(/\/$/)
 await expect(page.getByRole('heading',{name:'Page not found'})).toHaveCount(0)
})
test('valid routes keep their own auth and recovery rendering',async({page})=>{
 await mockAuth(page)
 for(const route of ['/auth/login','/auth/signup','/auth/dashboard','/auth/callback','/auth/confirm','/auth/reset-password']){
 await page.goto(route);await expect(page.getByRole('main')).not.toHaveClass(/website-not-found/);await expect(page.getByRole('heading',{name:'Page not found',exact:true})).toHaveCount(0)
 }
})

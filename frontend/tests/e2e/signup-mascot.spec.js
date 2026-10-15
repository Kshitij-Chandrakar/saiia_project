import { test, expect } from '@playwright/test'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'
const output=path.resolve('..','tmp/signup-mascot')
async function mock(page) {
 await page.route('**/src/auth/supabaseClient.js*',r=>r.fulfill({contentType:'application/javascript',body:`export function getSupabaseAuthConfig(){return {}}; export const supabase={auth:{getSession:async()=>({data:{session:null}}),onAuthStateChange:()=>({data:{subscription:{unsubscribe(){}}}}),signUp:async()=>({data:{session:null},error:null}),signInWithOAuth:async()=>({error:null})}}`}))
}
async function ready(page) { await page.goto('/auth/signup');await expect(page.locator('.signup-mascot-scene')).toHaveAttribute('data-assets-loaded','true');await page.evaluate(()=>document.fonts.ready) }
test('actual entrance has hinge opening, alternating gait, stable greeting, and no form replay',async({browser})=>{
 await mkdir(output,{recursive:true});const context=await browser.newContext({viewport:{width:1366,height:768},recordVideo:{dir:output,size:{width:1366,height:768}}});const page=await context.newPage();await mock(page);const errors=[];page.on('pageerror',e=>errors.push(e.message))
 await page.clock.install({time:new Date('2026-10-08T12:00:00Z')});await page.clock.pauseAt(new Date('2026-10-08T12:01:00Z'));await ready(page);const scene=page.locator('.signup-mascot-scene')
 await page.clock.runFor(750);await expect(scene).toHaveAttribute('data-phase','waiting');expect(await scene.locator('[data-door]').evaluate(e=>e.style.transform)).toBe('rotateY(0deg)');await expect(scene.locator('[data-bubble]')).toHaveAttribute('opacity','0');await page.screenshot({path:path.join(output,'frame-0750.png')})
 await page.clock.runFor(550);await expect(scene).toHaveAttribute('data-phase','opening');expect(await scene.locator('[data-door]').evaluate(e=>e.style.transform)).not.toBe('rotateY(0deg)');await page.screenshot({path:path.join(output,'frame-1300.png')})
 await page.clock.runFor(350);await expect(scene).toHaveAttribute('data-phase','walking');const first=await scene.locator('[data-sprite]').getAttribute('viewBox');const travel=await scene.locator('[data-robot]').getAttribute('transform');await page.screenshot({path:path.join(output,'frame-1650.png')})
 await page.clock.runFor(300);expect(await scene.locator('[data-sprite]').getAttribute('viewBox')).not.toBe(first);expect(await scene.locator('[data-robot]').getAttribute('transform')).not.toBe(travel);await page.screenshot({path:path.join(output,'frame-1950.png')})
 await page.clock.runFor(150);await expect(scene).toHaveAttribute('data-frame','4');await page.screenshot({path:path.join(output,'frame-2100-opposite-contact.png')});await page.clock.runFor(850);await expect(scene.locator('[data-bubble]')).toHaveAttribute('opacity','0');await page.screenshot({path:path.join(output,'frame-2950.png')});await page.clock.runFor(1100);await expect(scene).toHaveAttribute('data-phase','complete');await expect(scene.locator('text')).toHaveText('Welcome');await expect(scene.locator('[data-bubble]')).toHaveAttribute('opacity','1');await page.screenshot({path:path.join(output,'frame-4050.png')})
 const stable=await scene.locator('[data-robot]').getAttribute('transform');await page.getByLabel('Email',{exact:true}).fill('person@example.test');await page.getByLabel('Password',{exact:true}).fill('sample-password');await page.getByRole('button',{name:'Show password'}).click();await page.getByRole('checkbox').first().check();await page.clock.runFor(2000);await expect(scene).toHaveAttribute('data-phase','complete');expect(await scene.locator('[data-robot]').getAttribute('transform')).toBe(stable)
 await page.getByRole('link',{name:'Sign in',exact:true}).click();await expect(scene).toHaveCount(0);await page.goto('/auth/signup');await expect(scene).toHaveAttribute('data-phase','waiting');expect(errors).toEqual([]);await context.close()
})
test('final scene fits all viewports with reduced motion and no page overflow',async({page})=>{
 await mock(page);await page.emulateMedia({reducedMotion:'reduce'});await mkdir(output,{recursive:true})
 for(const [width,height] of [[1440,900],[1366,768],[1280,720],[1536,864],[390,844],[360,800]]){
  await page.setViewportSize({width,height});await ready(page);await expect(page.locator('.signup-mascot-scene')).toHaveAttribute('data-phase','complete');await expect(page.locator('[data-bubble]')).toHaveAttribute('opacity','1')
  const metrics=await page.evaluate(()=>{const root=document.documentElement;const scene=document.querySelector('.signup-mascot-scene').getBoundingClientRect();const hero=document.querySelector('.website-signup__hero').getBoundingClientRect();return {scrollWidth:root.scrollWidth,scrollHeight:root.scrollHeight,width:root.clientWidth,height:root.clientHeight,contained:scene.left>=hero.left&&scene.right<=hero.right&&scene.top>=hero.top&&scene.bottom<=hero.bottom}})
  expect(metrics.scrollWidth).toBeLessThanOrEqual(width);if(width>900)expect(metrics.scrollHeight).toBeLessThanOrEqual(height+1);expect(metrics.contained).toBe(true);await page.screenshot({path:path.join(output,`final-${width}x${height}.png`),fullPage:false})
 }
})
test('failed motion assets provide a static fallback without blocking signup',async({page})=>{
 await mock(page);await page.route('**/robot-walk-atlas.png',r=>r.abort());await page.goto('/auth/signup');await expect(page.locator('.signup-mascot-scene')).toHaveAttribute('data-phase','fallback');await expect(page.locator('.signup-mascot-scene text')).toHaveText('Welcome');await page.getByLabel('Email',{exact:true}).fill('person@example.test');await expect(page.getByLabel('Email',{exact:true})).toHaveValue('person@example.test')
})
test('records the actual entrance at normal speed with usable controls',async({browser})=>{
 await mkdir(output,{recursive:true});const context=await browser.newContext({viewport:{width:1366,height:768},recordVideo:{dir:output,size:{width:1366,height:768}}});const page=await context.newPage();await mock(page);const errors=[];page.on('pageerror',e=>errors.push(e.message));await ready(page)
 const scene=page.locator('.signup-mascot-scene');await expect(scene).toHaveAttribute('data-phase','waiting');await expect(scene.locator('[data-robot]')).toHaveAttribute('opacity','0')
 await page.getByLabel('Email',{exact:true}).fill('person@example.test');await page.getByRole('checkbox').last().check()
 await expect(scene).toHaveAttribute('data-phase','opening');await page.screenshot({path:path.join(output,'real-opening.png')});await expect(scene).toHaveAttribute('data-phase','walking');await page.screenshot({path:path.join(output,'real-first-step.png')})
 await expect(scene).toHaveAttribute('data-phase','complete',{timeout:6000});await page.screenshot({path:path.join(output,'real-final.png')});await page.getByLabel('Email',{exact:true}).fill('');await page.getByRole('button',{name:'Create Account',exact:true}).click();await expect(scene).toHaveAttribute('data-phase','complete');expect(errors).toEqual([])
 const video=page.video();await context.close();const {copyFile}=await import('node:fs/promises');await copyFile(await video.path(),path.join(output,'entrance-real-time.webm'))
 const review=await browser.newContext({viewport:{width:1366,height:768}});const playback=await review.newPage()
 await playback.route('**/mascot-recording.webm',r=>r.fulfill({contentType:'video/webm',path:path.join(output,'entrance-real-time.webm')}))
 await playback.goto('http://127.0.0.1:5173/auth/signup');await playback.setContent('<video muted autoplay style="width:1366px;height:768px" src="http://127.0.0.1:5173/mascot-recording.webm"></video>')
 expect(await playback.locator('video').evaluate(v=>v.playbackRate)).toBe(1)
 for(const time of [1.3,1.8,2.3,2.8,3.3,4.5]){await expect.poll(()=>playback.locator('video').evaluate(v=>v.currentTime)).toBeGreaterThanOrEqual(time);await playback.screenshot({path:path.join(output,`playback-${time}.png`)})}
 await review.close()

})
test('leaving signup cancels pending work; SPA re-entry starts once',async({page})=>{
 await mock(page);await page.clock.install({time:new Date('2026-10-08T12:00:00Z')});await page.clock.pauseAt(new Date('2026-10-08T12:01:00Z'));await ready(page);await page.clock.runFor(400)
 await page.evaluate(()=>{window.__oldScene=document.querySelector('.signup-mascot-scene');window.__oldElapsed=window.__oldScene.dataset.elapsed})
 await page.getByRole('link',{name:'Sign in',exact:true}).click();await page.clock.runFor(2000);expect(await page.evaluate(()=>window.__oldScene.dataset.elapsed===window.__oldElapsed)).toBe(true)
 await page.getByRole('link',{name:'Create free account'}).click();await expect(page.locator('.signup-mascot-scene')).toHaveAttribute('data-assets-loaded','true');await page.clock.runFor(400);await expect(page.locator('.signup-mascot-scene')).toHaveAttribute('data-phase','waiting');await page.clock.runFor(4000);await expect(page.locator('.signup-mascot-scene')).toHaveAttribute('data-phase','complete')
})
test('late assets start at door opening, never halfway through the walk',async({page})=>{
 await mock(page);let release;const gate=new Promise(resolve=>{release=resolve});await page.route('**/robot-walk-atlas.png',async route=>{await gate;await route.continue()})
 await page.clock.install({time:new Date('2026-10-08T12:00:00Z')});await page.clock.pauseAt(new Date('2026-10-08T12:01:00Z'));await page.goto('/auth/signup',{waitUntil:'domcontentloaded'});const scene=page.locator('.signup-mascot-scene');await expect(scene).toBeVisible();await page.clock.runFor(5000);await expect(scene).toHaveAttribute('data-phase','waiting');release();await expect(scene).toHaveAttribute('data-assets-loaded','true');await page.clock.runFor(32);await expect(scene).toHaveAttribute('data-phase','opening');expect(Number(await scene.getAttribute('data-elapsed'))).toBeLessThan(1100)
})

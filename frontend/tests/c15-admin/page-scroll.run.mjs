import {chromium,expect} from '@playwright/test';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
const accounts=JSON.parse(await readFile(path.join(process.env.LOCALAPPDATA,'IntervucopilotC15Local/logins.json'),'utf8'));
const output='../docs/evidence/c15-admin-page-scroll-20261106';await mkdir(output,{recursive:true});
const browser=await chromium.launch(),results=[];
try {
 for(const role of ['super_admin','admin']) {
  const context=await browser.newContext();const page=await context.newPage();page.setDefaultTimeout(15000);
  await page.goto('http://127.0.0.1:5400/auth/login?next=/auth/admin');await page.getByLabel('Email Address',{exact:true}).fill(accounts.users[role].email);await page.getByLabel('Password',{exact:true}).fill(accounts.password);await page.getByRole('button',{name:'Sign In',exact:true}).click();await expect(page.getByRole('heading',{name:'Customers',level:1,exact:true})).toBeVisible();
  for(const [width,height] of [[1366,768],[390,560]]) {
   await page.setViewportSize({width,height});
   for(const section of role==='super_admin'?['overview','users','campaigns','memberships','coupons','audit','commercial']:['overview','users','campaigns']) {
    await page.goto('http://127.0.0.1:5400/auth/admin'+(section==='commercial'?'/subscriptions':'?view='+section));
    const port=page.locator('#admin-content');await expect(page.locator('.ac-desktop-sidebar nav')).toHaveCount(1);await expect(port).toBeVisible();
    expect(await port.evaluate(el=>getComputedStyle(el).overscrollBehaviorY)).toBe('none');
    expect(await page.evaluate(()=>getComputedStyle(document.documentElement).overscrollBehaviorY)).toBe('none');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    const settled=()=>port.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
    const bounds=await port.boundingBox();await page.mouse.move(bounds.x+Math.min(150,bounds.width/2),bounds.y+Math.min(100,bounds.height/2));
    const max=await port.evaluate(el=>el.scrollHeight-el.clientHeight);
    if(max>0){await page.mouse.wheel(0,200);await expect.poll(()=>port.evaluate(el=>el.scrollTop)).toBeGreaterThan(0);}
    const snapshot=()=>page.evaluate(()=>{const main=document.querySelector('#admin-content'),header=document.querySelector('.ac-page-header').getBoundingClientRect(),text=main.firstElementChild?.getBoundingClientRect(),sidebar=document.querySelector('.ac-desktop-sidebar').getBoundingClientRect();return{window:scrollY,scroll:main.scrollTop,header:header.y,text:text?.y,sidebar:sidebar.y};});
    for(const edge of ['top','bottom']) {
     await port.evaluate((el,edge)=>{el.scrollTop=edge==='top'?0:el.scrollHeight;},edge);await page.mouse.wheel(0,edge==='top'?-2000:2000);await settled();
     const before=await snapshot();
     for(let i=0;i<5;i++){await page.mouse.wheel(0,edge==='top'?-700:700);await settled();expect(await snapshot()).toEqual(before);}
    }
    expect(await page.evaluate(()=>scrollY)).toBe(0);
    if(['memberships','audit','overview'].includes(section))await page.screenshot({path:`${output}/${role}-${section}-${width}.png`});
    results.push({role,section,width,height,scroll_range:max,normal_scroll:max>0?'verified':'content_fits',both_edges_stable:true});
   }
  }
  await context.close();
 }
 await writeFile(output+'/results.json',JSON.stringify(results,null,2));console.log('PASS',results.length,'actual-route section/viewport checks.');
}finally{await browser.close();}

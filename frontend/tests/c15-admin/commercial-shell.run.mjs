import { startPlan, resumeDraft } from '../catalog/fixtures/workspace.js';
import { chromium, expect } from '@playwright/test';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const accounts=JSON.parse(await readFile(path.join(process.env.LOCALAPPDATA,'IntervucopilotC15Local/logins.json'),'utf8'));
const output=fileURLToPath(new URL('../../../docs/evidence/c15-commercial-shell-20261105',import.meta.url));await mkdir(output,{recursive:true});
const results=[];const browser=await chromium.launch();
try{
 for(const role of ['super_admin','admin','customer']){
  const context=await browser.newContext({viewport:{width:1440,height:900}});const page=await context.newPage();page.setDefaultTimeout(15000);
  await page.goto('http://127.0.0.1:5400/auth/login?next=/auth/admin');await page.getByLabel('Email Address',{exact:true}).fill(accounts.users[role].email);await page.getByLabel('Password',{exact:true}).fill(accounts.password);await page.getByRole('button',{name:'Sign In',exact:true}).click();
  await expect(page.locator(role === 'customer' ? '.wd-account-email strong' : '.ac-desktop-sidebar .ac-account strong')).toHaveAttribute('title',accounts.users[role].email);
  if(role==='super_admin'){
   await expect(page.getByRole('heading',{name:'Customers',exact:true,level:1})).toBeVisible();
   await page.getByRole('link',{name:'Commercial configuration',exact:true}).first().click();
   await expect(page.getByRole('heading',{name:'Commercial configuration',level:1,exact:true})).toBeVisible();
   await expect(page.getByRole('heading',{name:'Start a plan',level:2,exact:true})).toBeVisible();
   for(const [width,height] of [[1440,900],[1366,768],[390,844]]){
    await page.setViewportSize({width,height});
    if(width===390){await page.getByRole('button',{name:'Open navigation',exact:true}).click();await expect(page.getByRole('dialog',{name:'Administration navigation'}).getByRole('link',{name:'Commercial configuration',exact:true})).toHaveAttribute('aria-current','page');await page.keyboard.press('Escape');}
    else await expect(page.locator('.ac-desktop-sidebar').getByRole('link',{name:'Commercial configuration',exact:true})).toHaveAttribute('aria-current','page');
    expect(await page.locator('.website-dashboard').count()).toBe(0);expect(await page.locator('h1').count()).toBe(1);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    const header=await page.locator('.ac-page-header').boundingBox();await page.locator('#admin-content').evaluate(e=>e.scrollTop=e.scrollHeight);expect((await page.locator('.ac-page-header').boundingBox()).y).toBe(header.y);await page.locator('#admin-content').evaluate(e=>e.scrollTop=0);
    await page.screenshot({path:path.join(output,`commercial-${width}.png`)});results.push({role,width,shared_shell:true,stable_header:true,no_page_overflow:true});
   }
   await page.setViewportSize({width:1440,height:900});await page.reload();await expect(page.getByRole('button',{name:'New plan',exact:true})).toBeVisible();
   await page.locator('.ac-desktop-sidebar').getByRole('button',{name:'Overview',exact:true}).click();await expect(page.getByRole('heading',{name:'Overview',level:1,exact:true})).toBeVisible();await page.goBack();await expect(page.getByRole('heading',{name:'Commercial configuration',level:1,exact:true})).toBeVisible();await page.goForward();await expect(page.getByRole('heading',{name:'Overview',level:1,exact:true})).toBeVisible();await page.goBack();
   await startPlan(page);await page.getByLabel('Plan code',{exact:true}).fill('shell-check-'+Date.now());await page.getByLabel('Display name',{exact:true}).fill('Local admin shell check');
   await page.locator('.ac-desktop-sidebar').getByRole('button',{name:'Customers',exact:true}).click();const blocker=page.getByRole('dialog',{name:'Leave this draft?',exact:true});await expect(blocker).toBeVisible();await blocker.getByRole('button',{name:'Stay',exact:true}).click();await expect(blocker).not.toBeVisible();await expect(page.getByLabel('Display name',{exact:true})).toHaveValue('Local admin shell check');results.push({role,back_forward_reload_stay:true});await page.locator('.ca-document-heading').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(output,'commercial-editor.png')});
   await page.getByLabel('Change reason',{exact:true}).fill('Synthetic shared shell acceptance');await expect(page.getByLabel('Change reason',{exact:true})).toHaveValue('Synthetic shared shell acceptance');const saveResponse=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().includes('/api/admin/catalog/plans/'));await page.getByRole('button',{name:'Save draft',exact:true}).click();const saveResult=await saveResponse;await page.screenshot({path:path.join(output,'save-check.png')});if(saveResult.status()===503){
    expect((await saveResult.json()).detail.code).toBe('catalog_database_unavailable');await expect(page.getByRole('alert')).toContainText('Draft storage is unavailable');await expect(page.getByLabel('Change reason',{exact:true})).toHaveValue('Synthetic shared shell acceptance');
    results.push({role,actual_storage:'unavailable',code:'catalog_database_unavailable',edits_preserved:true,save_acceptance:'not_claimed',unchanged_activation:true});
    await page.getByRole('button',{name:'Continue editing',exact:true}).click();await page.locator('.ac-desktop-sidebar').getByRole('button',{name:'Customers',exact:true}).click();await blocker.getByRole('button',{name:'Discard and leave',exact:true}).click();await expect(page.getByRole('heading',{name:'Customers',exact:true,level:1})).toBeVisible();
    await page.getByRole('link',{name:'Commercial configuration',exact:true}).first().click();
   }else{
    expect(saveResult.ok()).toBeTruthy();await expect(page.getByRole('status')).toContainText('Draft saved.',{timeout:20000});
   await page.getByText('Troubleshooting: draft details',{exact:true}).click();const id=await page.locator('.ca-ids code').first().innerText();results.push({role,actual_draft_saved:id,stay_preserves_edits:true});
   await page.getByRole('button',{name:'Preview saved draft',exact:true}).click();await expect(page.getByRole('dialog',{name:'Subscription review',exact:true})).toBeVisible();await page.getByRole('button',{name:'Close subscription review',exact:true}).click();
   await page.getByLabel('Display name',{exact:true}).fill('Unsaved draft change');await page.locator('.ac-desktop-sidebar').getByRole('button',{name:'Customers',exact:true}).click();await expect(blocker).toBeVisible();await blocker.getByRole('button',{name:'Discard and leave',exact:true}).click();await expect(page.getByRole('heading',{name:'Customers',exact:true,level:1})).toBeVisible();
   await page.getByRole('link',{name:'Commercial configuration',exact:true}).first().click();await resumeDraft(page);await page.getByLabel('Open a draft by ID',{exact:true}).fill(id);await page.getByRole('button',{name:'Open draft',exact:true}).click();await expect(page.getByLabel('Display name',{exact:true})).toHaveValue('Local admin shell check');
   results.push({role,actual_preview_open_save_reopen:true,discard_does_not_overwrite_saved:true});

   }
  }else{
   await page.goto('http://127.0.0.1:5400/auth/admin/subscriptions');await expect(page.getByRole('heading',{name:'Page not found',exact:true})).toBeVisible();expect(await page.getByRole('button',{name:'New plan',exact:true}).count()).toBe(0);results.push({role,direct_route_denied:true});
  }
  await context.close();
 }
}finally{await browser.close();await writeFile(path.join(output,'actual-results.json'),JSON.stringify(results,null,2));}
console.log('PASS',results.length,'actual commercial shell checks');

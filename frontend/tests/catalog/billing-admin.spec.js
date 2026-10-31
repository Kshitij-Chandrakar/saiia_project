import {test,expect} from '@playwright/test';
import {mkdir,readFile} from 'node:fs/promises';
const account='10000000-0000-4000-8000-000000000002',target='10000000-0000-4000-8000-000000000003';
const snapshot={revision:'synthetic-revision',operations:[{id:target,state:'confirmed',provider_state:'active',cancel_requested:true,amount_minor:'47082',currency:'INR'}],notifications:[{id:target,kind:'billing_payment',state:'unknown',attempts:1,delivery_events:[{type:'email.delivery_delayed',provider_event_at:'2026-10-27T00:00:00Z',processed_at:'2026-10-27T00:01:00Z',failure_category:null}]}],commands:[]};
async function fixture(page,access={read:true,manage:true},stale=false){
  await page.route('**/api/admin/billing/**',async route=>{
    const request=route.request();
    if(request.url().endsWith('/access'))return route.fulfill({json:access});
    if(request.method()==='GET')return route.fulfill({json:snapshot});
    const data=request.postDataJSON();
    if(data.review)return route.fulfill({json:{action:data.action,target:data.target,operation_id:data.operation_id,review_id:target,revision:'synthetic-revision'}});
    return route.fulfill(stale?{status:409,json:{error:'conflict'}}:{json:{id:data.operation_id,state:'requested'}});
  });
  await page.goto('/');
}
test('server permission denial hides private billing data',async({page})=>{await fixture(page,{read:false,manage:false});await expect(page.getByText('Billing permission denied.')).toBeVisible();await expect(page.getByLabel('Account ID')).toHaveCount(0);});
test('read role sees accurate unknown status without mutation controls',async({page})=>{await fixture(page,{read:true,manage:false});await page.getByLabel('Account ID').fill(account);await page.getByRole('button',{name:'Inspect billing'}).click();await expect(page.getByText(/confirmation unknown/)).toBeVisible();await expect(page.getByText(/Payment confirmation.*unknown/)).toBeVisible();await expect(page.getByText(/email.delivery_delayed.*provider event/)).toBeVisible();await expect(page.getByRole('button',{name:'Review reconciliation request'})).toHaveCount(0);});
test('exact-target confirmation, requested status and desktop/mobile rendering',async({page})=>{
 await fixture(page);await page.getByLabel('Account ID').fill(account);await page.getByRole('button',{name:'Inspect billing'}).click();await page.getByRole('button',{name:'Review reconciliation request'}).click();await expect(page.getByRole('dialog')).toContainText(target);
 await mkdir('../tmp/c12-resend-callbacks/screenshots',{recursive:true});
 for(const [name,width,height] of [['desktop',1366,768],['mobile',390,844]]){await page.setViewportSize({width,height});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:`../tmp/c12-resend-callbacks/screenshots/admin-${name}.png`,fullPage:true});}
 await page.getByRole('button',{name:'Confirm request',exact:true}).click();await expect(page.getByRole('status')).toContainText('Operation requested');
 await page.evaluate(()=>window.syntheticBillingLogout());await expect(page.getByLabel('Account ID')).toHaveCount(0);await expect(page.getByText(target)).toHaveCount(0);
});
test('stale state requires inspection again',async({page})=>{await fixture(page,undefined,true);await page.getByLabel('Account ID').fill(account);await page.getByRole('button',{name:'Inspect billing'}).click();await page.getByRole('button',{name:'Review reconciliation request'}).click();await page.getByRole('button',{name:'Confirm request',exact:true}).click();await expect(page.getByRole('status')).toContainText('State changed');});
test('email HTML previews render at mobile width',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 for(const kind of ['billing_payment','billing_renewal','billing_cancellation','billing_access_end']){
  const html=await readFile(`../tmp/c12-billing-email-admin/previews/${kind}.html`,'utf8');
  await page.setContent(html);await expect(page.getByRole('heading',{name:kind==='billing_payment'?'Payment received':kind==='billing_renewal'?'Your subscription is renewed':'Intervucopilot',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:`../tmp/c12-resend-callbacks/screenshots/${kind}.png`,fullPage:true});
 }
});

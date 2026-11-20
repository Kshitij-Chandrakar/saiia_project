import { chromium, expect } from '@playwright/test';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
const accounts=JSON.parse(await readFile(path.join(process.env.LOCALAPPDATA,'IntervucopilotC15Local/logins.json'),'utf8'));
const output='../docs/evidence/c15-membership-workflow-20261106';await mkdir(output,{recursive:true});
const browser=await chromium.launch();const results=[];
async function login(page,role) {
 page.setDefaultTimeout(15000);
 await page.goto('http://127.0.0.1:5400/auth/login?next=/auth/admin');
 await page.getByLabel('Email Address',{exact:true}).fill(accounts.users[role].email);
 await page.getByLabel('Password',{exact:true}).fill(accounts.password);
 await page.getByRole('button',{name:'Sign In',exact:true}).click();
 await expect(page.getByRole('heading',{level:1,name:'Customers',exact:true})).toBeVisible();
 await page.goto('http://127.0.0.1:5400/auth/admin?view=memberships');
}
try {
 const context=await browser.newContext({viewport:{width:1440,height:900}});const page=await context.newPage();
 await login(page,'super_admin');
 await expect(page.getByRole('heading',{name:'People with admin access',exact:true})).toBeVisible();
 await expect(page.getByRole('region',{name:'Administrators records'})).toContainText(accounts.users.admin.id);
 await page.screenshot({path:output+'/desktop.png'});
 await page.getByRole('button',{name:'Add administrator',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'Add administrator',exact:true});
 await expect(dialog.getByRole('button',{name:'Review change',exact:true})).toBeDisabled();
 await dialog.getByRole('searchbox',{name:'User email or Account ID'}).fill(accounts.users.customer.email);
 await dialog.getByRole('button',{name:'Find user',exact:true}).click();
 await dialog.getByRole('button',{name:new RegExp('Select this account')}).click();
 await expect(dialog).toContainText(accounts.users.customer.id);
 await page.screenshot({path:output+'/choose-access.png'});
 const deniedReview=page.waitForResponse(response=>response.url().endsWith('/api/admin/memberships/review'));
 await dialog.getByRole('button',{name:'Review change',exact:true}).click();
 expect((await deniedReview).status()).toBe(403);
 await expect(page.getByRole('dialog',{name:'Verify sensitive access',exact:true})).toBeVisible();
 await page.keyboard.press('Escape');
 await expect(dialog).toBeVisible();
 await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
 await expect(page.getByRole('button',{name:'Add administrator',exact:true})).toBeFocused();
 const staffRow=page.getByRole('row').filter({hasText:accounts.users.admin.id});
 await staffRow.getByRole('button',{name:/Change access for/}).click();
 await expect(page.getByRole('dialog')).toContainText(accounts.users.admin.id);
 await expect(page.getByLabel('Access level',{exact:true})).toHaveValue('admin');
 await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).not.toBeVisible();
 await expect(staffRow.getByRole('button',{name:/Change access for/})).toBeFocused();
 await page.getByText('Appoint a successor',{exact:false}).first().click();
 await expect(page.getByLabel('Successor Account ID',{exact:true})).toBeVisible();
 await page.getByText('Recovery and safeguards',{exact:true}).click();
 await expect(page.getByText('Emergency recovery is unavailable',{exact:false})).toBeVisible();
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.screenshot({path:output+'/mobile.png'});
 results.push({actual_local:true,lookup_matches:true,row_change_prefills:true,cancel_escape_restore_focus:true,mobile_no_page_overflow:true,grants_executed:0});
 // Isolated mutation fixtures exercise UI sequencing without granting any role.
 let reviews=0,confirms=0,failReview=true,failConfirm=true,operation=null;
 await page.route('**/api/admin/memberships/review',async route=>{
  reviews++;const data=route.request().postDataJSON();expect(data.target).toBe(accounts.users.customer.id);
  expect(data.operation_id).toBeTruthy(); if(operation !== null) expect(data.operation_id).toBe(operation);operation=data.operation_id;
  if(failReview){failReview=false;await route.fulfill({status:503,json:{}});return;}
  await route.fulfill({json:{review_id:'11111111-1111-4111-8111-111111111111',expires_at:new Date(Date.now()+240000).toISOString()}});
 });
 await page.route('**/api/admin/memberships/confirm',async route=>{
  confirms++;expect(route.request().postDataJSON()).toEqual({review_id:'11111111-1111-4111-8111-111111111111',confirm:true});
  if(failConfirm){failConfirm=false;await route.fulfill({status:503,json:{}});return;}
  await route.fulfill({json:{outcome:'confirmed'}});
 });
 await page.getByRole('button',{name:'Add administrator',exact:true}).click();
 const flow=page.getByRole('dialog');
 await flow.getByRole('searchbox').fill('missing@example.invalid');await flow.getByRole('button',{name:'Find user',exact:true}).click();
 await expect(flow.getByRole('status')).toContainText('No matching account');
 await flow.getByRole('searchbox').fill(accounts.users.customer.email);await flow.getByRole('searchbox').press('Enter');
 await flow.getByRole('button',{name:/Select this account/}).click();
 await flow.getByLabel('Access level',{exact:true}).selectOption('super_admin');
 await flow.getByRole('button',{name:'Review change',exact:true}).click();
 await expect(flow.getByRole('alert')).toContainText('not confirmed');
 await expect(flow.getByLabel('Access level',{exact:true})).toHaveValue('super_admin');
 expect(confirms).toBe(0);
 await flow.getByRole('button',{name:'Review change',exact:true}).click();
 await expect(page.getByRole('dialog',{name:'Review access change',exact:true})).toBeVisible();
 await expect(flow).toContainText('Super admin');expect(confirms).toBe(0);
 await page.screenshot({path:output+'/review-mobile-fixture.png'});
 await page.setViewportSize({width:1440,height:900});await page.screenshot({path:output+'/review-desktop-fixture.png'});
 await flow.getByRole('button',{name:'Confirm access change',exact:true}).click();
 await expect(flow.getByRole('alert')).toContainText('not confirmed');
 await expect(flow.getByRole('button',{name:'Confirm access change',exact:true})).toBeEnabled();
 await flow.getByRole('button',{name:'Confirm access change',exact:true}).click();
 await expect(flow).not.toBeVisible();expect(reviews).toBe(2);expect(confirms).toBe(2);
 results.push({isolated_ui_fixtures:true,review_before_confirm:true,failed_review_preserves_edits:true,same_operation_retry:true,failed_confirmation_preserves_receipt:true,no_backend_grants:true});
 await context.close();
 const denied=await browser.newContext();const admin=await denied.newPage();await login(admin,'admin');
 await expect(admin.getByRole('heading',{name:'Page not found',exact:true})).toBeVisible();
 await expect(admin.getByRole('button',{name:'Add administrator',exact:true})).toHaveCount(0);
 results.push({normal_admin_denied:true});await denied.close();
 await writeFile(output+'/results.json',JSON.stringify(results,null,2));console.log('PASS: actual lookup/navigation/isolation; fixture review-confirm/recovery. No grants executed.');
} finally {await browser.close();}

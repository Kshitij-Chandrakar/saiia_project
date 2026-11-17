import {chromium,expect} from '@playwright/test';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
const accounts=JSON.parse(await readFile(path.join(process.env.LOCALAPPDATA,'IntervucopilotC15Local/logins.json'),'utf8'));
const output='../docs/evidence/c15-admin-dismiss-red-20261106';await mkdir(output,{recursive:true});
const browser=await chromium.launch(),checks=[];
async function check(button,name){await expect(button).toBeVisible();await button.hover();await expect(button).toHaveCSS('background-color','rgb(180, 35, 24)');await expect(button).toHaveCSS('color','rgb(255, 255, 255)');await button.focus();await expect(button).toHaveCSS('background-color','rgb(180, 35, 24)');checks.push(name);}
try{const page=await browser.newPage({viewport:{width:1366,height:768}});await page.goto('http://127.0.0.1:5400/auth/login?next=/auth/admin');await page.getByLabel('Email Address',{exact:true}).fill(accounts.users.super_admin.email);await page.getByLabel('Password',{exact:true}).fill(accounts.password);await page.getByRole('button',{name:'Sign In',exact:true}).click();await expect(page.getByRole('heading',{name:'Customers',level:1,exact:true})).toBeVisible();
await page.goto('http://127.0.0.1:5400/auth/admin?view=memberships');await page.getByRole('button',{name:'Add administrator',exact:true}).click();const cancel=page.getByRole('dialog').getByRole('button',{name:'Cancel',exact:true});await check(cancel,'membership Cancel');await page.screenshot({path:output+'/membership.png'});await cancel.click();await expect(page.getByRole('dialog')).not.toBeVisible();
await page.getByRole('button',{name:'Verify access',exact:true}).click();const close=page.getByRole('button',{name:'Close verification',exact:true});await check(close,'verification close');await close.click();
await page.goto('http://127.0.0.1:5400/auth/admin?view=coupons');await page.getByRole('button',{name:'Create inert coupon draft',exact:true}).click();await check(page.getByRole('button',{name:'Cancel draft',exact:true}),'coupon Cancel draft');await page.getByRole('button',{name:'Cancel draft',exact:true}).click();
await page.goto('http://127.0.0.1:5400/auth/admin/subscriptions');await page.getByRole('button',{name:'New plan',exact:true}).click();await page.getByRole('button',{name:'Start from scratch',exact:true}).click();await check(page.getByRole('button',{name:'Close draft',exact:true}),'commercial Close draft');
await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:'Open navigation',exact:true}).click();await check(page.getByRole('button',{name:'Close navigation',exact:true}),'mobile navigation close');await page.screenshot({path:output+'/mobile.png'});await page.getByRole('button',{name:'Close navigation',exact:true}).click();
await writeFile(output+'/results.json',JSON.stringify(checks,null,2));console.log('PASS',checks);}
finally{await browser.close();}

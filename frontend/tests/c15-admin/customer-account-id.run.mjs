import { chromium, expect } from '@playwright/test';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
const accounts=JSON.parse(await readFile(path.join(process.env.LOCALAPPDATA,'IntervucopilotC15Local/logins.json'),'utf8'));
const output='../docs/evidence/c15-customer-account-id-20261106';await mkdir(output,{recursive:true});
const browser=await chromium.launch();const results=[];
try {
 for(const role of ['super_admin','admin']) {
  const context=await browser.newContext();const page=await context.newPage();
  await page.goto('http://127.0.0.1:5400/auth/login?next=/auth/admin');
  await page.getByLabel('Email Address',{exact:true}).fill(accounts.users[role].email);
  await page.getByLabel('Password',{exact:true}).fill(accounts.password);
  await page.getByRole('button',{name:'Sign In',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Customers',level:1,exact:true})).toBeVisible();
  const region=page.getByRole('region',{name:'Customers records',exact:true});
  const row=region.getByRole('row').filter({has:page.getByText(accounts.users.customer.email,{exact:true})});
  await expect(row.locator('td').first()).toContainText('Account ID: '+accounts.users.customer.id);
  for(const width of [1440,390]) {
   await page.setViewportSize({width,height:width===390?844:900});
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
   await expect(row.getByRole('button',{name:'Inspect metadata',exact:true})).toBeAttached();
   await page.screenshot({path:`${output}/${role}-${width}.png`});
  }
  results.push({role,account_id_matches:true,no_page_overflow:true});await context.close();
 }
 await writeFile(`${output}/results.json`,JSON.stringify(results,null,2));console.log('PASS: both roles; desktop/mobile Account ID matches existing customer identity.');
} finally {await browser.close();}

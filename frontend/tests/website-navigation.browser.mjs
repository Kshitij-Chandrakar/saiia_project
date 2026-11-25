import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch();
try {
 for(const width of [1440,390]) {
  const page=await browser.newPage({viewport:{width,height:900}});
  await page.goto('http://localhost:5173');
  await expect(page.locator('#website-startup')).toHaveCount(0);
  await page.evaluate(()=>{window.navigationCheck='preserved'});
  let documents=0;page.on('request',r=>{if(r.isNavigationRequest()&&r.frame()===page.mainFrame())documents++});
  await page.locator('a[href="/auth/login"]:visible').first().click();
  await expect(page).toHaveURL(/\/auth\/login$/);
  expect(await page.evaluate(()=>window.navigationCheck)).toBe('preserved');
  expect(documents).toBe(0);
  await expect(page.locator('#website-startup')).toHaveCount(0);
  await page.goBack();await expect(page).toHaveURL('http://localhost:5173/');
  await page.getByRole('article',{name:'Free plan'}).getByRole('link',{name:'Get started'}).click();
  await expect(page).toHaveURL(/\/auth\/signup$/);
  expect(await page.evaluate(()=>window.navigationCheck)).toBe('preserved');
  await page.getByRole('link',{name:'Sign in',exact:true}).click();
  await expect(page).toHaveURL(/\/auth\/login$/);
  await page.getByRole('link',{name:'Intervucopilot home'}).click();
  await expect(page).toHaveURL('http://localhost:5173/');
  expect(documents).toBe(0);
  await expect(page.locator('#website-startup')).toHaveCount(0);
  console.log('PASS '+width+': home/sign-in/back without reload or startup screen');await page.close();
 }
 const slow=await browser.newPage();let release;const barrier=new Promise(r=>release=r);
 await slow.route('**/src/main.jsx*',async route=>{await barrier;await route.continue()});
 await slow.goto('http://localhost:5173',{waitUntil:'commit'});
 await expect(slow.locator('#website-startup')).toBeHidden();
 await expect(slow.locator('#website-startup')).toBeVisible({timeout:5000});
 release();await expect(slow.locator('#website-startup')).toHaveCount(0,{timeout:15000});await slow.close();
 const failed=await browser.newPage();await failed.route('**/src/main.jsx*',r=>r.abort());await failed.goto('http://localhost:5173');await expect(failed.locator('#startup-title')).toContainText('couldn');await expect(failed.locator('#website-startup')).toBeVisible();await failed.close();
 console.log('PASS slow-load recovery and failed-module recovery');
} finally {await browser.close()}

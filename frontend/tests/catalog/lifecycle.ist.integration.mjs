// Opt-in running isolated demo only. No production identity or configuration.
import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch();
const context=await browser.newContext({timezoneId:'America/Los_Angeles',viewport:{width:1366,height:768}});
const page=await context.newPage();
try {
  await page.goto('http://127.0.0.1:5187/__demo/as/admin');
  await expect(page.getByText(/Isolated demo.*disposable data/)).toBeVisible();
  const button=name=>page.getByRole('button',{name,exact:true});
  await button('Import approved Pro draft').click();
  await page.getByLabel('Plan code',{exact:true}).fill('ist-test-'+crypto.randomUUID().slice(0,8));
  await page.getByLabel('Display name',{exact:true}).fill('Isolated IST conversion test');
  await page.getByText('Policy references',{exact:true}).click();
  await page.getByLabel('Subscription policy',{exact:true}).fill('synthetic.lifecycle');
  await page.getByLabel('Subscriber migration policy',{exact:true}).fill('synthetic.migration');
  await button('Prices').click();
  for(const n of [1,2]) {
    const group=page.getByRole('group',{name:`Price ${n}`,exact:true});
    await group.getByText('Policy references',{exact:true}).click();
    await group.getByLabel('Tax policy',{exact:true}).fill('synthetic.tax');
    await group.getByLabel('Rounding policy',{exact:true}).fill('synthetic.rounding');
  }
  await page.getByLabel('Change reason',{exact:true}).fill('Isolated IST conversion check; do not publish');
  await button('Save draft').click();await button('Preview saved draft').click();
  await button('Close subscription review').click();
  await page.getByLabel('Offer starts at (IST)',{exact:true}).fill('2026-10-23T21:43:26');
  await page.getByLabel('Offer ends at (IST, optional)',{exact:true}).fill('2026-10-23T22:00');
  await page.getByLabel('Lifecycle reason',{exact:true}).fill('IST conversion check only; no publication');
  const request=page.waitForRequest(r=>r.url().endsWith('/preview') && r.postDataJSON()?.scope==='publication_review');
  await button('Review for publication').click();const sent=(await request).postDataJSON();
  expect(sent.intent.valid_from).toBe('2026-10-23T16:13:26.000Z');
  expect(sent.intent.valid_until).toBe('2026-10-23T16:30:00.000Z');
  const dialog=page.getByRole('dialog',{name:'Subscription review',exact:true});
  await expect(dialog).toBeVisible();await expect(dialog).toContainText('09:43:26 pm IST');
  await expect(dialog).toContainText('10:00:00 pm IST');
  await page.screenshot({path:'../tmp/subscription-demo/subscription-review-desktop.png'});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:'../tmp/subscription-demo/subscription-review-mobile.png'});
  const bounds=await dialog.boundingBox();expect(bounds.x).toBeGreaterThanOrEqual(0);expect(bounds.x+bounds.width).toBeLessThanOrEqual(390);
  await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
  // Invalid ordering must not send another publication preview.
  await page.getByLabel('Offer ends at (IST, optional)',{exact:true}).fill('2026-10-23T20:00');
  let previewRequests=0;
  page.on('request',r=>{if(r.url().endsWith('/preview'))previewRequests++;});
  await button('Review for publication').click();
  await expect(page.getByRole('alert')).toContainText('An optional end must be later');
  expect(previewRequests).toBe(0);
  await button('Close subscription review').click();
  await page.getByLabel('Offer ends at (IST, optional)',{exact:true}).fill('');
  await page.getByRole('region',{name:'Offer lifecycle',exact:true}).screenshot({path:'../tmp/subscription-demo/ist-fields-desktop.png'});
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('region',{name:'Offer lifecycle',exact:true}).screenshot({path:'../tmp/subscription-demo/ist-fields-mobile.png'});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  const catalog=await page.evaluate(async()=>await(await fetch('/api/catalog')).json());
  expect(catalog.offers).toHaveLength(3);
  console.log('PASS: IST input in Los Angeles browser -> real JWT/API/native SQL policy preview -> IST confirmation; invalid end blocked; no publication; three offers preserved.');
} finally {await browser.close();}

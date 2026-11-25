// Opt-in actual localhost -> read-only preview -> native PostgreSQL. No route mocks.
import { chromium, expect } from '@playwright/test';
import fs from 'node:fs';
const browser = await chromium.launch({headless:true});
const page = await browser.newPage({viewport:{width:1366,height:768}});
try {
  const response = await page.request.get('http://localhost:5173/api/catalog');
  expect(response.status()).toBe(200);
  const data = await response.json();
  expect(data.offers.map(o=>o.name).sort()).toEqual(['Free','Plus','Pro']);
  expect(data.offers.every(o=>o.purchasable===false)).toBe(true);
  await page.goto('http://localhost:5173/#pricing');
  const pricing=page.getByRole('region',{name:'Your next opportunity starts here.',exact:true});
  await expect(pricing.getByRole('article')).toHaveCount(3);
  const plus=pricing.getByRole('article',{name:'Plus plan'}),pro=pricing.getByRole('article',{name:'Pro plan'});
  await expect(plus).toContainText('\u20b9399');
  await expect(pro).toContainText('\u20b9899');
  await expect(plus).toContainText('10 Clipboard saves / month');
  await expect(pricing.getByRole('button',{name:'Checkout coming soon'})).toHaveCount(2);
  for (const button of await pricing.getByRole('button',{name:'Checkout coming soon'}).all()) await expect(button).toBeDisabled();
  fs.mkdirSync('../tmp/catalog-preview',{recursive:true});
  await pricing.screenshot({path:'../tmp/catalog-preview/localhost-monthly.png'});
  await pricing.getByRole('button',{name:'Yearly',exact:true}).click();
  await expect(plus).toContainText('\u20b92,999');
  await expect(pro).toContainText('\u20b96,499');
  await expect(plus).toContainText('Approximately \u20b9250/month');
  await expect(pro).toContainText('Approximately \u20b9542/month');
  await expect(plus).toContainText('Save 37%');
  await expect(pro).toContainText('Save 39%');
  await pricing.screenshot({path:'../tmp/catalog-preview/localhost-yearly.png'});
  const free=pricing.getByRole('article',{name:'Free plan'});
  await free.getByRole('button',{name:'About Clipboard',exact:true}).focus();
  await expect(free.getByRole('tooltip').filter({hasText:'Clipboard lets'})).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(free.getByRole('tooltip').filter({hasText:'Clipboard lets'})).not.toBeVisible();
  await page.setViewportSize({width:390,height:844});
  await pricing.getByRole('button',{name:'Monthly',exact:true}).click();
  await pricing.screenshot({path:'../tmp/catalog-preview/localhost-mobile.png'});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  for(const [method,path] of [['POST','/api/catalog'],['GET','/api/admin/catalog/offers'],['GET','/api/generate'],['GET','/api/catalog/']]) {
    const result=await page.request.fetch('http://127.0.0.1:5188'+path,{method});
    expect(result.status()).toBe(404);
  }
  console.log('PASS: localhost -> public-only service -> native PostgreSQL; three plans, monthly/yearly, savings, tooltips, mobile, disabled checkout, write/admin/AI denial.');
} finally { await browser.close(); }

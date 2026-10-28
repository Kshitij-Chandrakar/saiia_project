import {test,expect} from '@playwright/test';
import {approvedFreeDraft,approvedPaidDraft} from '../../src/auth/catalogV2.js';
const project=d=>({...d.terms,contract_version:d.contract_version,registry_version:d.registry_version,plan:d.plan,offer_version_id:d.draft_id,version:'1',visibility_revision:'1',fingerprint:'a'.repeat(64),purchasable:false,checkout_state:'unavailable'});
test('public pricing handles loading, empty, unavailable and explicit retry without sample fallback',async({page})=>{
 let release;const barrier=new Promise(resolve=>release=resolve);let status='loading';
 await page.route('**/api/catalog',async r=>{if(status==='loading')await barrier;if(status==='unavailable')return r.fulfill({status:503,json:{detail:{code:'catalog_unavailable'}}});return r.fulfill({json:{catalog_revision:'1',offers:[]}});});
 await page.goto('/#pricing');await expect(page.getByText('Loading published plans\u2026',{exact:true})).toBeVisible();
 status='empty';release();await expect(page.getByText('No published plans are available yet.',{exact:true})).toBeVisible();
 status='unavailable';await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await expect(page.getByText('Plans are temporarily unavailable.',{exact:true})).toBeVisible();
 await expect(page.getByRole('article',{name:'Plus plan'})).toHaveCount(0);
 status='empty';await page.getByRole('button',{name:'Try again',exact:true}).click();await expect(page.getByText('No published plans are available yet.',{exact:true})).toBeVisible();
});
test('published cards use server versions, independent periods and unavailable support; refresh removes retired offers',async({page})=>{
 const offers=[approvedFreeDraft(),approvedPaidDraft('plus'),approvedPaidDraft('pro')].map(project);let current=offers;
 await page.route('**/api/catalog',r=>r.fulfill({json:{catalog_revision:current.length===3?'4':'5',offers:current,payable_prices:Object.fromEntries(offers.flatMap(o=>o.prices.map(p=>[p.price_id,{currency:'INR',exponent:'2',total_amount_minor:({'39900':'47082','299900':'353882','89900':'106082','649900':'766882'})[p.amount_minor]}])))}}));
 await page.goto('/#pricing');const plus=page.getByRole('article',{name:'Plus plan'});
 await expect(plus).toContainText('5 hours Auto Mode / month');await expect(plus).toContainText('10 Clipboard saves / month');
 await expect(plus.getByRole('button',{name:'Checkout coming soon',exact:true})).toBeDisabled();
 await expect(plus).toHaveAttribute('data-offer-id',offers[1].offer_version_id);
 await expect(plus.getByText('Coming soon',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Yearly',exact:true}).click();await expect(plus).toContainText('per year + 18% GST');await expect(plus).toContainText('Total: \u20b93,538.82');await expect(page.locator('.cp-saving')).toHaveCount(0);
 await expect(plus).toContainText('5 hours Auto Mode / month');
 current=offers.filter(o=>o.name!=='Pro');await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await expect(page.getByRole('article',{name:'Pro plan'})).toHaveCount(0);
});

test('shared unlimited claims disappear when an admin limits one displayed offer',async({page})=>{
 const offers=[approvedFreeDraft(),approvedPaidDraft('plus')].map(project);
 offers[1].allowances.find(a=>a.meter==='audio.transcribed').mode='limited';
 await page.route('**/api/catalog',r=>r.fulfill({json:{catalog_revision:'6',offers}}));
 await page.goto('/#pricing');const strip=page.getByRole('region',{name:'Included in every plan'});
 await expect(strip).toBeVisible();await expect(strip).not.toContainText('Unlimited manual audio');
 await expect(strip).toContainText('All available AI models');
});

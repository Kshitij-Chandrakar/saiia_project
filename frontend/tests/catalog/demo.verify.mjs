// Real browser -> loopback bridge -> JWT -> services -> disposable native SQL.
// No Playwright route mocks, token output or production configuration.
import {chromium,expect} from '@playwright/test';
import {writeFile,mkdir} from 'node:fs/promises';
const base='http://127.0.0.1:5187';
await mkdir('../tmp/subscription-demo',{recursive:true});
for(let i=0;i<100;i++) {
  try{if((await fetch(base+'/__demo')).ok)break;}catch{}
  if(i===99)throw Error('Demo did not start');
  await new Promise(resolve=>setTimeout(resolve,200));
}
const browser=await chromium.launch();
const page=await browser.newPage({viewport:{width:1440,height:1000}});
let firstCreate;
page.on('request',request=>{
  if(!firstCreate && request.method()==='POST' && /\/plans\/[^/]+\/drafts$/.test(new URL(request.url()).pathname))firstCreate=request.postDataJSON().document;
});
const result={environment:'Isolated demo',plans:[],verification:[]};
const button=name=>page.getByRole('button',{name,exact:true});
async function review(action='publish') {
  await button('Preview saved draft').click();
  await button('Close subscription review').click();
  await page.getByLabel('Publication action',{exact:true}).selectOption(action);
  await page.getByLabel('Offer starts at (IST)',{exact:true}).fill('2026-01-01T00:00');
  await page.getByLabel('Lifecycle reason',{exact:true}).fill('Isolated demo verification');
  await button('Review for publication').click();
  await expect(page.getByRole('dialog',{name:'Subscription review',exact:true})).toBeVisible();
  await button('Confirm review').click();
  await button(action==='publish'?'Publish reviewed offer':'Replace reviewed offer').click();
  await button(action==='publish'?'Confirm publication':'Confirm replacement').click();
  await expect(page.getByRole('heading',{name:action==='publish'?/Published offer.*version 1/:/Published offer.*version 2/})).toBeVisible();
}
try {
  await page.goto(base+'/__demo/as/admin');
  await expect(button('Import approved Free draft')).toBeEnabled();
  for(const name of ['Free','Plus','Pro','Disposable demo offer']) {
    if(name!=='Free')await page.goto(base+'/auth/admin/subscriptions');
    const template=name==='Disposable demo offer'?'Pro':name;
    await button(`Import approved ${template} draft`).click();
    await page.getByLabel('Plan code',{exact:true}).fill('isolated-'+template.toLowerCase()+'-'+crypto.randomUUID().slice(0,8));
    await page.getByLabel('Display name',{exact:true}).fill(name);
    await page.getByLabel('Change reason',{exact:true}).fill('Isolated demo approved import');
    await button('Save draft').click();
    await expect(button('Save changes')).toBeVisible();
    const id=await page.getByLabel('Open a draft by ID',{exact:true}).inputValue();
    await button('Close draft').click();
    await page.getByLabel('Open a draft by ID',{exact:true}).fill(id);
    await button('Open draft').click();
    await expect(page.getByLabel('Display name',{exact:true})).toHaveValue(name);
    await page.getByText('Policy references',{exact:true}).click();
    await page.getByLabel('Subscription policy',{exact:true}).fill('synthetic.lifecycle');
    await page.getByLabel('Subscriber migration policy',{exact:true}).fill('synthetic.migration');
    if(template==='Free') {
      await button('Features & limits').click();
      await page.getByLabel('Limit policy reference',{exact:true}).fill('synthetic.storage');
    } else {
      await button('Prices').click();
      for(const n of [1,2]) {
        const group=page.getByRole('group',{name:`Price ${n}`,exact:true});
        await group.getByText('Policy references',{exact:true}).click();
        await group.getByLabel('Tax policy',{exact:true}).fill('synthetic.tax');
        await group.getByLabel('Rounding policy',{exact:true}).fill('synthetic.rounding');
      }
    }
    await page.getByLabel('Change reason',{exact:true}).fill('Isolated demo policy references');
    await button('Save changes').click();await button('Open draft').click();
    await review();
    const catalog=await page.evaluate(async()=>await(await fetch('/api/catalog')).json());
    const offer=catalog.offers.find(o=>o.name===name);
    expect(offer).toBeTruthy();
    result.plans.push({name,draft_id:id,offer_id:offer.offer_version_id});
    if(name==='Disposable demo offer') {
      result.disposable_first=offer.offer_version_id;
      await button('Create a new draft version').click();
      await page.getByLabel('Description',{exact:true}).fill('Isolated demo replacement, safe to retire');
      await page.getByLabel('Change reason',{exact:true}).fill('Isolated demo replacement');
      await button('Save draft').click();await review('replace');
      const updated=await page.evaluate(async()=>await(await fetch('/api/catalog')).json());
      result.disposable_replacement=updated.offers.find(o=>o.name===name).offer_version_id;
      expect(updated.offers.some(o=>o.offer_version_id===offer.offer_version_id)).toBe(false);
      await button('Retire this offer').click();await button('Confirm retirement').click();
      await expect(page.getByRole('heading',{name:/Retired offer/})).toBeVisible();
    }
  }
  result.verification.push('Four real UI imports/saves/reopens/previews/reviews/publications; disposable replacement and retirement');
  // Reuse an observed, accepted UI request as valid input; no response mocking.
  const deniedDocument=structuredClone(firstCreate);
  deniedDocument.draft_id=crypto.randomUUID();
  deniedDocument.plan={plan_id:crypto.randomUUID(),code:'isolated-denied-'+crypto.randomUUID().slice(0,8)};
  await page.goto(base+'/#pricing');
  const pricing=page.getByRole('region',{name:'Your next opportunity starts here.',exact:true});
  await expect(pricing.getByRole('article')).toHaveCount(3);
  await expect(pricing.getByRole('article',{name:'Free plan'})).toContainText('No payment required');
  for(const [name,price] of [['Plus','₹399'],['Pro','₹899']])await expect(pricing.getByRole('article',{name:name+' plan'})).toContainText(price);
  for(const name of ['Plus','Pro'])await expect(pricing.getByRole('article',{name:name+' plan'}).getByRole('button',{name:'Checkout coming soon'})).toBeDisabled();
  await expect(pricing.getByRole('article',{name:'Free plan'}).locator('s')).toHaveText('Introducing Sketch');
  for(const [name,quantity] of [['Free','5'],['Plus','10'],['Pro','unlimited']]) {
    const card=pricing.getByRole('article',{name:name+' plan'});
    await card.getByRole('button',{name:'About Clipboard',exact:true}).click();
    await expect(card.getByRole('tooltip').filter({hasText:'Clipboard lets'})).toContainText(quantity);
    await page.keyboard.press('Escape');
    await card.getByRole('button',{name:'About Introducing Sketch',exact:true}).focus();
    await expect(card.getByRole('tooltip').filter({hasText:'Sketch turns'})).toBeVisible();
    await page.keyboard.press('Escape');
  }
  await pricing.screenshot({path:'../tmp/subscription-demo/monthly-desktop.png'});
  await pricing.getByRole('button',{name:'Yearly',exact:true}).click();
  await expect(pricing.getByRole('article',{name:'Plus plan'})).toContainText('₹2,999');
  await expect(pricing.getByRole('article',{name:'Plus plan'})).toContainText('Save 37%');
  await expect(pricing.getByRole('article',{name:'Pro plan'})).toContainText('₹6,499');
  await expect(pricing.getByRole('article',{name:'Pro plan'})).toContainText('Save 39%');
  await pricing.screenshot({path:'../tmp/subscription-demo/yearly-desktop.png'});
  await page.setViewportSize({width:390,height:844});
  await pricing.screenshot({path:'../tmp/subscription-demo/yearly-mobile.png'});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  result.verification.push('Three main cards preserved; monthly/yearly money, savings, information controls, disabled checkout, mobile overflow');
  await page.goto(base+'/__demo/as/ordinary');
  await expect(button('Import approved Free draft')).toHaveCount(0);
  await expect(page.getByRole('heading',{name:'Page not found',exact:true})).toBeVisible();
  const denial=await page.evaluate(async document=>{
    const {session}=await(await fetch('/__demo/session')).json();
    const r=await fetch('/api/admin/catalog/plans/'+document.plan.plan_id+'/drafts',{method:'POST',headers:{Authorization:'Bearer '+session.access_token,'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({document,reason:'Isolated ordinary denial check'})});
    return {status:r.status,error:await r.json()};
  },deniedDocument);
  expect(denial).toEqual({status:403,error:{detail:{code:'catalog_permission_denied'}}});
  result.verification.push('Ordinary synthetic account: existing 404 page; backend mutation HTTP 403');
  await page.goto(base+'/__demo/as/admin');
  await page.setViewportSize({width:1440,height:1000});
  await expect(button('Import approved Free draft')).toBeEnabled();
  await page.screenshot({path:'../tmp/subscription-demo/admin-desktop.png',fullPage:true});
  await writeFile('../tmp/subscription-demo-results.json',JSON.stringify(result,null,2));
  console.log('PASS: isolated browser lifecycle, pricing and ordinary-user denial. Safe IDs saved to tmp/subscription-demo-results.json');
} catch(error) {
  await page.screenshot({path:'../tmp/subscription-demo/failure.png',fullPage:true});
  throw error;
} finally {await browser.close();}

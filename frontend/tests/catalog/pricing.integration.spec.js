import {test,expect} from '@playwright/test';
const config=process.env.CATALOG_BROWSER_NATIVE ? JSON.parse(process.env.CATALOG_BROWSER_NATIVE) : null;
test('approved imports through JWT native policy publication to landing pricing',async({page},info)=>{
  test.setTimeout(180000);
  test.skip(!config,'Requires disposable native pricing runner');
  await page.route('**/src/auth/supabaseClient.js*',r=>r.fulfill({contentType:'application/javascript',body:`export const supabase={auth:{getSession:async()=>({data:{session:{access_token:${JSON.stringify(config?.token)},user:{id:'10000000-0000-4000-8000-000000000001'}}}}),onAuthStateChange:()=>({data:{subscription:{unsubscribe(){}}}})}};export function getSupabaseAuthConfig(){return {}};`}));
  await page.route('**/api/**',async r=>{const response=await r.fetch({url:config.url+new URL(r.request().url()).pathname});await r.fulfill({response});});
  const button=name=>page.getByRole('button',{name,exact:true});
  async function review(action='publish') {
    await button('Preview saved draft').click();
  await button('Close subscription review').click();
    await page.getByLabel('Publication action',{exact:true}).selectOption(action);
    await page.getByLabel('Offer starts at (IST)',{exact:true}).fill('2026-01-01T00:00');
    await page.getByLabel('Lifecycle reason',{exact:true}).fill('Synthetic catalog acceptance');
    await button('Review for publication').click();
    await expect(page.getByRole('dialog',{name:'Subscription review',exact:true})).toBeVisible();
    await button('Confirm review').click();
    await button(action==='publish'?'Publish reviewed offer':'Replace reviewed offer').click();
    await button(action==='publish'?'Confirm publication':'Confirm replacement').click();
    await expect(page.getByRole('heading',{name:action==='replace'?/Published offer.*version 2/:/Published offer.*version 1/})).toBeVisible();
  }
  for (const name of ['Free','Plus','Pro']) {
    await page.goto('/auth/admin/subscriptions');
    await button(`Import approved ${name} draft`).click();
    await expect(button(`Import approved ${name} draft`)).toBeDisabled();
    // Save incomplete approved terms first, reopen, then edit through the workspace.
    await page.getByLabel('Change reason',{exact:true}).fill('Synthetic approved import');
    await button('Save draft').click();await expect(button('Save changes')).toBeVisible();
    await button('Open draft').click();await expect(page.getByLabel('Display name',{exact:true})).toHaveValue(name);
    if (name !== 'Free') {
      await button('Usage & presentation').click();
      await expect(page.getByLabel('Allowance clipboard.new_saves',{exact:true})).toHaveValue(name==='Plus'?'limited':'unlimited');
      await expect(page.getByLabel('Resume storage capacity',{exact:true})).toHaveValue(name==='Plus'?'limited':'unlimited');
      if(name==='Plus') {
        await page.getByLabel('Resume storage capacity',{exact:true}).selectOption('unlimited');
        await expect(page.getByLabel('Maximum stored resumes',{exact:true})).toHaveCount(0);
        await page.getByLabel('Resume storage capacity',{exact:true}).selectOption('limited');
        await page.getByLabel('Maximum stored resumes',{exact:true}).fill('5');
        await button('Remove support.email').click();
        await page.getByLabel('Add a service benefit',{exact:true}).selectOption('support.email');
      }
      await button('Identity').click();
    }

    await page.getByText('Policy references',{exact:true}).click();
    await page.getByLabel('Subscription policy',{exact:true}).fill('synthetic.lifecycle');
    await page.getByLabel('Subscriber migration policy',{exact:true}).fill('synthetic.migration');
    if (name==='Free') {
      await button('Features & limits').click();
      await page.getByLabel('Limit policy reference',{exact:true}).fill('synthetic.storage');
    } else {
      await button('Prices').click();
      for (const n of [1,2]) {
        const group=page.getByRole('group',{name:`Price ${n}`,exact:true});
        await group.getByText('Policy references',{exact:true}).click();
        await group.getByLabel('Tax policy',{exact:true}).fill('synthetic.tax');
        await group.getByLabel('Rounding policy',{exact:true}).fill('synthetic.rounding');
      }
    }
    await page.getByLabel('Change reason',{exact:true}).fill('Synthetic policy references');
    await button('Save changes').click();await button('Open draft').click();
    await review();
  }
  await page.goto('/#pricing');
  const pricing=page.getByRole('region',{name:'Your next opportunity starts here.',exact:true});
  await expect(pricing.getByRole('article')).toHaveCount(3);
  await expect(pricing.getByRole('article',{name:'Plus plan'})).toContainText('\u20b9399');
  await expect(pricing.getByRole('article',{name:'Pro plan'})).toContainText('\u20b9899');
  await expect(pricing.getByRole('article',{name:'Plus plan'})).toContainText('10 Clipboard saves / month');
  await expect(pricing.getByRole('article',{name:'Pro plan'})).toContainText('Coming soon');
  await expect(pricing.getByRole('button',{name:'Checkout coming soon'})).toHaveCount(2);
  await expect(pricing.getByRole('article',{name:'Free plan'}).locator('s')).toHaveText('Introducing Sketch');
  const pricingBounds=await pricing.boundingBox();
  const faqBounds=await page.getByText('Questions, answered.',{exact:true}).boundingBox();
  expect(faqBounds.y).toBeGreaterThan(pricingBounds.y+pricingBounds.height);
  await page.setViewportSize({width:1440,height:1000});await pricing.screenshot({path:info.outputPath('pricing-monthly-desktop.png')});
  await pricing.getByRole('button',{name:'Yearly',exact:true}).click();
  await expect(pricing.getByRole('article',{name:'Plus plan'})).toContainText('\u20b92,999');
  await expect(pricing.getByRole('article',{name:'Plus plan'})).toContainText('per year + 18% GST');
  await expect(pricing.getByRole('article',{name:'Plus plan'})).toContainText('Total: \u20b93,538.82');
  await expect(pricing.getByRole('article',{name:'Pro plan'})).toContainText('per year + 18% GST');
  await expect(pricing.getByRole('article',{name:'Pro plan'})).toContainText('Total: \u20b97,668.82');
  await pricing.screenshot({path:info.outputPath('pricing-yearly-desktop.png')});
  await page.setViewportSize({width:390,height:844});await pricing.screenshot({path:info.outputPath('pricing-yearly-mobile.png')});
  await pricing.getByRole('button',{name:'Monthly',exact:true}).click();await pricing.screenshot({path:info.outputPath('pricing-monthly-mobile.png')});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  const free=pricing.getByRole('article',{name:'Free plan'});
  await free.getByRole('button',{name:'About Clipboard',exact:true}).focus();
  await expect(free.getByRole('tooltip').filter({hasText:'Clipboard lets'})).toBeVisible();
  await page.keyboard.press('Escape');await expect(free.getByRole('tooltip').filter({hasText:'Clipboard lets'})).not.toBeVisible();
  await free.getByRole('button',{name:'About Clipboard',exact:true}).click();await expect(free.getByRole('tooltip').filter({hasText:'Clipboard lets'})).toBeVisible();
  await expect(free.getByRole('button',{name:'Preview Clipboard unavailable',exact:true})).toHaveCount(0);
  // Replace/retire through the actual API-backed workspace, then revisit the
  // catalog section. The public endpoint has no cache/fallback sample catalog.
  await page.goto('/auth/admin/subscriptions');
  const catalog=await page.evaluate(async()=>await (await fetch('/api/catalog')).json());
  const pro=catalog.offers.find(o=>o.name==='Pro');
  await page.getByLabel('Open an offer by ID',{exact:true}).fill(pro.offer_version_id);
  await button('Open offer').click();await button('Create a new draft version').click();
  await page.getByLabel('Description',{exact:true}).fill('Synthetic replacement description');
  await page.getByLabel('Change reason',{exact:true}).fill('Synthetic replacement');
  await button('Save draft').click();await review('replace');
  const replacement=await page.evaluate(async()=>await (await fetch('/api/catalog')).json());
  expect(replacement.offers.find(o=>o.name==='Pro').description).toBe('Synthetic replacement description');
  await button('Retire this offer').click();await button('Confirm retirement').click();
  await expect(page.getByRole('heading',{name:/Retired offer/})).toBeVisible();
  await page.goto('/#pricing');await expect(page.getByRole('article',{name:'Pro plan'})).toHaveCount(0);
  await expect(page.getByRole('article',{name:'Plus plan'})).toBeVisible();
});

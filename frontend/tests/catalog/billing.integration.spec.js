import {test,expect} from '@playwright/test';
import {mkdir} from 'node:fs/promises';
const native = process.env.BILLING_BROWSER_NATIVE?JSON.parse(process.env.BILLING_BROWSER_NATIVE):null;
test.use({trace:'off'});

test('review, captured payment, reload recovery and account refresh',async({page})=>{
  test.skip(!native,'Requires disposable C12 runner');
  await page.route('**/api/billing/**',async route=>{
    const url = new URL(route.request().url());
    const response = await route.fetch({url:native.url+url.pathname+url.search});
    await route.fulfill({response});
  });
  await page.route('**/api/account/subscription',async route=>{
    const response=await route.fetch({url:native.url+'/api/account/subscription'});
    await route.fulfill({response});
  });
  await page.route('**/api/catalog',async route=>{
    const response=await route.fetch({url:native.url+'/api/catalog'});
    await route.fulfill({response});
  });
  await page.route('**/__synthetic_pay',async route=>{
    const response = await route.fetch({url:native.url+'/__synthetic_pay'});
    await route.fulfill({response});
  });
  await page.route('**/src/main.jsx*',route=>route.fulfill({contentType:'application/javascript',body:"import '/tests/catalog/fixtures/billing.jsx'"}));
  await page.addInitScript(data=>{
    window.syntheticSession={user:{id:data.account},access_token:data.token};
    window.Razorpay=class{
      constructor(options){this.options=options;}
      on(){}
      close(){}
      async open(){
        if(window.dismissCheckout){this.options.modal.ondismiss();return;}
        const result=await fetch('/__synthetic_pay',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({order_id:this.options.subscription_id})});
        this.options.handler(await result.json());
      }
    };
  },native);
  await page.goto('/');
  await expect(page.getByRole('article',{name:'Plus plan'})).toBeVisible();
  await mkdir('../tmp/c12-gst',{recursive:true});
  for(const [width,height] of [[1366,768],[390,844]]) {
    await page.setViewportSize({width,height});
    for(const yearly of [false,true]) {
      await page.getByRole('button',{name:yearly?'Yearly':'Monthly',exact:true}).click();
      const plus=page.getByRole('article',{name:'Plus plan'}),pro=page.getByRole('article',{name:'Pro plan'}),free=page.getByRole('article',{name:'Free plan'});
      await expect(plus.getByText(yearly?'₹2,999':'₹399',{exact:true})).toBeVisible();
      await expect(plus.getByText(yearly?'per year + 18% GST':'per month + 18% GST',{exact:true})).toBeVisible();
      await expect(plus.getByText(yearly?'Total: ₹3,538.82':'Total: ₹470.82',{exact:true})).toBeVisible();
      await expect(pro.getByText(yearly?'Total: ₹7,668.82':'Total: ₹1,060.82',{exact:true})).toBeVisible();
      await expect(free.getByText('₹0',{exact:true})).toBeVisible();
      await expect(free).not.toContainText('GST');
      await expect(page.locator('.cp-saving')).toHaveCount(0);
      await expect(plus).not.toContainText('₹71.82');
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
      await page.screenshot({path:`../tmp/c12-gst/${yearly?'yearly':'monthly'}-${width}x${height}.png`,fullPage:true});
    }
  }
  await page.setViewportSize({width:1366,height:768});
  await page.getByRole('button',{name:'Monthly',exact:true}).click();
  await page.locator(`a[href*="price=${native.price}"]`).click();
  await expect(page.getByRole('heading',{name:'Plus',exact:true})).toBeVisible();
  await expect(page.getByText('₹470.82',{exact:true})).toBeVisible();
  await expect(page.getByText('₹71.82',{exact:true})).toBeVisible();
  await expect(page.getByText('12 billing cycles',{exact:true})).toBeVisible();
  await page.getByRole('checkbox').check();
  await page.evaluate(()=>{window.dismissCheckout=true;});
  await page.getByRole('button',{name:'Accept terms and pay'}).click();
  await expect(page.getByText(/Checkout closed/)).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button',{name:'Accept terms and pay'})).toBeVisible();
  await page.getByRole('checkbox').check();
  await page.getByRole('button',{name:'Accept terms and pay'}).click();
  await expect(page.getByText('Payment confirmed. Your account plan has been updated.')).toBeVisible();
  await expect(page.getByText('Current account plan: Plus')).toBeVisible();
  await page.reload();
  await expect(page.getByText('Payment confirmed. Your account plan has been updated.')).toBeVisible();
  await mkdir('../tmp/c12-browser',{recursive:true});
  await page.screenshot({path:'../tmp/c12-browser/confirmed.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'../tmp/c12-browser/mobile.png',fullPage:true});
  await page.evaluate(()=>window.syntheticLogout());
  await expect(page.getByText(/Sign in to review/)).toBeVisible();
  await expect(page.getByRole('heading',{name:'Plus',exact:true})).toHaveCount(0);
});

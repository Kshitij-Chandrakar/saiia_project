// Opt-in manual demo; real catalog and protected reads, no API mocks or saves.
import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch();const page=await browser.newPage({viewport:{width:1366,height:768}});
try {
  const writes=[];
  page.on('request',r=>{if(r.url().includes('/api/') && ['POST','PATCH','DELETE'].includes(r.method()))writes.push(r.method());});
  await page.goto('http://127.0.0.1:5187/__demo/as/admin');
  await expect(page.getByText(/Isolated demo.*disposable data/)).toBeVisible();
  const list=page.getByRole('region',{name:'Published offers',exact:true});
  for(const name of ['Free','Plus','Pro'])await expect(list.getByRole('button',{name:`Open ${name} offer`,exact:true})).toBeEnabled();
  await list.screenshot({path:'../tmp/subscription-demo/published-offers-desktop.png'});
  await list.getByRole('button',{name:'Open Plus offer',exact:true}).click();
  await expect(page.getByRole('heading',{name:/Published offer.*version/})).toBeVisible();
  await list.getByRole('button',{name:'Create draft version for Plus',exact:true}).click();
  await expect(page.getByLabel('Display name',{exact:true})).toHaveValue('Plus');
  await expect(page.getByRole('button',{name:'Save draft',exact:true})).toBeEnabled();
  await page.getByRole('button',{name:'Prices',exact:true}).click();
  const amounts=await page.getByLabel('Price amount',{exact:true}).evaluateAll(inputs=>inputs.map(input=>input.value));
  console.log('Persisted Plus opened and copied to an unsaved successor; prices:',amounts.join(', '));
  await page.getByRole('button',{name:'Close draft',exact:true}).click();
  await page.setViewportSize({width:390,height:844});
  await expect(list.getByRole('button',{name:'Open Plus offer',exact:true})).toBeEnabled();
  await list.screenshot({path:'../tmp/subscription-demo/published-offers-mobile.png'});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  expect(writes).toHaveLength(0);
  await page.goto('http://127.0.0.1:5187/__demo/as/ordinary');
  await expect(page.getByRole('heading',{name:'Page not found',exact:true})).toBeVisible();
  await expect(page.getByRole('region',{name:'Published offers',exact:true})).toHaveCount(0);
  console.log('PASS: real JWT/native demo list -> protected Open -> local draft version -> Close; zero API writes, no mobile overflow, ordinary-user 404.');
}finally{await browser.close();}

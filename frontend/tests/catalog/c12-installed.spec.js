import {test,expect,_electron as electron,chromium} from '@playwright/test';
import {mkdir,writeFile,readFile} from 'node:fs/promises';
import path from 'node:path';
const config=JSON.parse(process.env.C12_ACCEPTANCE_CONFIG || 'null');
test('isolated installed production main/preload and C12 billing states',async()=>{
 test.skip(!config,'Isolated native runner is required');
 const steps=[];
 const record=async name=>{steps.push(name);await writeFile(path.join(config.evidence,'observations.json'),JSON.stringify({steps},null,2));};
 const control=async(action,data={})=>{
  const response=await fetch('http://127.0.0.1:5296/__c12__/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-C12-Fixture':config.nonce},body:JSON.stringify(data)});
  expect(response.ok).toBe(true);return response.json();
 };
 const environment=()=>{const value={...process.env,C12_ACCEPTANCE_USER_DATA:config.userData};delete value.ELECTRON_RUN_AS_NODE;delete value.C12_ACCEPTANCE_CONFIG;return value;};
 let app,page,browser,primaryFailure;
 const launch=async token=>{
  const env=environment();if(token)env.C12_ACCEPTANCE_SESSION=JSON.stringify({access_token:token,refresh_token:token===config.firstToken?'synthetic-first':'synthetic-second',expires_at:Math.floor(Date.now()/1000)+3600});
  app=await electron.launch({executablePath:config.executable,args:[],env});page=await app.firstWindow();
  expect(await app.evaluate(({app})=>({packaged:app.isPackaged,name:app.getName(),profile:app.getPath('userData')}))).toEqual({packaged:true,name:'Intervucopilot C12 Acceptance',profile:config.userData});
  await expect(page).toHaveURL(/^file:/);
  await page.getByRole('tab',{name:'Create',exact:true}).click({timeout:30000});
 };
 try{
  await mkdir(config.evidence,{recursive:true});
  await launch(config.firstToken);
  const diagnostic=await page.evaluate(async()=>({auth:await window.electronAPI.getAuthState(),subscription:await window.electronAPI.getSubscription()}));await writeFile(path.join(config.evidence,'diagnostic.json'),JSON.stringify(diagnostic,null,2));
  await expect(page.getByText('Current plan: Free',{exact:true})).toBeVisible({timeout:30000});
  expect((await control('free_gate')).denied).toBeTruthy();await record('Free display and backend quota denial');
  await page.getByRole('button',{name:'Buy Credits',exact:true}).click();
  await expect.poll(()=>app.evaluate(()=>global.c12OpenedUrls)).toEqual(['http://127.0.0.1:5297/#pricing']);
  browser=await chromium.launch();const tab=await browser.newPage();
  await tab.route('**/*',route=>{const url=new URL(route.request().url());return ['127.0.0.1','localhost'].includes(url.hostname)?route.continue():route.abort();});
  await tab.goto('http://127.0.0.1:5297/#pricing');await expect(tab.locator('#pricing')).toBeVisible();await expect(tab.getByRole('heading',{name:'Plus',exact:true})).toBeVisible();
  await tab.screenshot({path:path.join(config.evidence,'upgrade-website.png'),fullPage:true});await browser.close();browser=null;
  await record('Upgrade opens the configured loopback website; real pricing section renders');
  const before=await page.evaluate(()=>window.electronAPI.getSubscription());
  await control('paid');await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
  await expect(page.getByText('Current plan: Plus',{exact:true})).toBeVisible({timeout:25000});
  const paid=await page.evaluate(()=>window.electronAPI.getSubscription());expect(paid.auto.allowance).not.toEqual(before.auto.allowance);
  await page.screenshot({path:path.join(config.evidence,'paid-installed.png')});await record('Trusted synthetic payment updates plan and authoritative allowance');
  await app.close();app=null;await launch();
  await expect(page.getByText('Current plan: Plus',{exact:true})).toBeVisible({timeout:30000});
  expect(await page.evaluate(()=>window.electronAPI.getSubscription())).toEqual(paid);await record('Encrypted session restart and fresh backend retrieval');
  await control('unavailable',{value:true});await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
  await expect(page.getByText('Current plan temporarily unavailable',{exact:true})).toBeVisible({timeout:20000});
  expect((await page.evaluate(()=>window.electronAPI.getSubscription())).ok).toBe(false);await record('Backend unavailable shows unavailable, not stale paid authority');
  await control('unavailable',{value:false});await control('expire');await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
  await expect(page.getByText('Current plan: Free',{exact:true})).toBeVisible({timeout:20000});await record('Approved paid-period expiry returns to Free');
  await control('hold');await page.evaluate(()=>{window.c12Pending=window.electronAPI.getSubscription();});
  await page.evaluate(()=>window.electronAPI.logoutAuth());await control('release');
  expect((await page.evaluate(()=>window.c12Pending)).ok).toBe(false);
  await expect(page.getByText('Current plan: Plus',{exact:true})).toHaveCount(0);await record('Logout fences the in-flight prior-account response');
  await app.close();app=null;await launch(config.secondToken);
  await expect(page.getByText('Current plan: Free',{exact:true})).toBeVisible({timeout:30000});
  await page.screenshot({path:path.join(config.evidence,'second-account.png')});await record('Different verified synthetic account has isolated Free state');
  const stored=await readFile(path.join(config.userData,'desktop-auth-session.bin'));
  expect(stored.includes(Buffer.from(config.secondToken))).toBe(false);await record('Session file is encrypted, not plaintext token storage');
 }catch(error){primaryFailure=error;throw error;}finally{
  let cleanupFailure;
  for(const close of [()=>control('release'),()=>app?.close(),()=>browser?.close()]){
   try{await close();}catch(error){cleanupFailure??=error;}
  }
  if(!primaryFailure&&cleanupFailure)throw cleanupFailure;
 }
});

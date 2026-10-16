import {test,expect,_electron} from '@playwright/test'
import {mkdir,writeFile} from 'node:fs/promises'
import path from 'node:path'

for (const outcome of ['signed-out','token-expired','failure']) test(`logout ${outcome} after a tab unmount reaches the parent exactly once on success`, async ({page}) => {
 await openSetup(page,null,false,'choice')
 await page.evaluate(()=>{
  window.saiia.listInterviewSessions=async()=>({items:[{id:'cached-session',status:'ended',company_name:'Synthetic cached company',target_role:'Synthetic role',started_at:'2026-10-01T10:00:00Z'}]})
 })
 await page.getByRole('tab',{name:'Past Sessions',exact:true}).click()
 await expect(page.getByText('Synthetic cached company',{exact:true})).toBeVisible()
 await page.getByRole('button',{name:'Account menu'}).click()
 await page.evaluate(outcome=>{window.logoutPending=true;window.logoutFail=outcome==='failure';window.logoutResult=outcome},outcome)
 await page.getByRole('menuitem',{name:'Log out',exact:true}).click()
 await expect(page.getByRole('menuitem',{name:'Signing out...',exact:true})).toBeDisabled()
 await page.getByRole('tab',{name:'Create',exact:true}).click()
 await expect(page.getByRole('menu')).toHaveCount(0)
 await page.evaluate(()=>window.finishLogout())
 if (outcome==='failure') {
  await page.getByRole('tab',{name:'Past Sessions',exact:true}).click()
  await expect(page.getByText('Synthetic cached company',{exact:true})).toBeVisible()
  expect(await page.evaluate(()=>window.signedOutCount||0)).toBe(0)
 } else {
  await expect(page.getByRole('heading',{name:'Signed out',exact:true})).toBeVisible()
  await expect(page.getByText('Synthetic cached company',{exact:true})).toHaveCount(0)
  expect(await page.evaluate(()=>window.signedOutCount)).toBe(1)
 }
 expect(await page.evaluate(()=>window.logoutCalls)).toBe(1)
})
async function openSetup(page, balance=null, blocked=false, screen='setup'){
 page.on('pageerror',e=>console.log(e.message));page.on('console',m=>{if(m.type()==='error')console.log(m.text())});
 await page.route('**/src/main.jsx*',r=>r.fulfill({contentType:'application/javascript',body:`import React from '/node_modules/.vite/deps/react.js';import ReactDOM from'/node_modules/.vite/deps/react-dom_client.js';import Setup from '/src/components/StartupSessionSetupScreen.jsx';import Choice from '/src/components/StartupSessionChoiceScreen.jsx';import '/src/index.css';import '/src/styles/glass.css';window.calls=[];window.quotaChecks=0;window.saiia={getCloudStartupContext:async()=>{window.quotaChecks++;await new Promise((r,j)=>{window.quotaFinish=r;window.quotaReject=j})},refreshCloudStartupContext:async()=>{window.quotaChecks++;await new Promise((r,j)=>{window.quotaFinish=r;window.quotaReject=j})},listCloudResumes:async()=>({items:window.resumeItems||[{id:'resume-1',display_name:'Ready resume.pdf',can_generate:true}],error:window.resumeError||''}),createInterviewSession:async(body)=>{window.calls.push(body);if(window.fail)return {error:'Please retry'};if(window.pending)await new Promise(r=>window.finish=r);return {session:{id:'mock-session',status:'active'}}},endInterviewSession:async()=>{},openDashboard:async()=>{window.dashboardCalls=(window.dashboardCalls||0)+1;return {ok:true}},logoutAuth:async()=>{window.logoutCalls=(window.logoutCalls||0)+1;if(window.logoutPending)await new Promise(r=>window.finishLogout=r);if(window.logoutFail)throw new Error('mock-only');return {status:window.logoutResult||'signed-out'}}};window.electronAPI={completeStartup:async()=>({ok:true}),closeStartupWindow:async()=>{window.closeCalled=true},collapseStartupWindow:async()=>({ok:true}),restoreStartupWindow:async()=>({ok:true})};ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(function Harness(){const[email,setEmail]=React.useState(window.testEmail??'person@example.test');const[authenticated,setAuthenticated]=React.useState(true);window.setMenuEmail=setEmail;if(!authenticated)return React.createElement('h1',null,'Signed out');return React.createElement(${screen==='choice'?'Choice':'Setup'},{key:email,onSignedOut:()=>{window.signedOut=true;window.signedOutCount=(window.signedOutCount||0)+1;setAuthenticated(false)},onBack:()=>window.back=true,onStartSession:c=>window.config=c,authenticatedEmail:email,remainingMinutes:${balance?.remaining ?? 'null'},totalMinutes:${balance?.total ?? 'null'}});}));`}));
 await page.setViewportSize(screen==='choice'?{width:504,height:462}:{width:421,height:484});await page.goto('/');if(screen==='choice')return;if(blocked)await expect(page.getByRole('button',{name:'Start Session',exact:true})).toBeDisabled();else await expect(page.getByRole('button',{name:'Start Session',exact:true})).toBeEnabled()
}
test('compact setup scrolls centrally, validates company, retains fields and starts once',async({page})=>{
 await openSetup(page);await mkdir(path.resolve('..','tmp/session-setup'),{recursive:true});await page.evaluate(()=>document.fonts.ready);expect(await page.getByRole('main').evaluate(m=>[m.previousElementSibling,m.parentElement.querySelector('header'),m.nextElementSibling].every(e=>{const r=e.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight&&r.right<=innerWidth}))).toBe(true);await page.screenshot({path:'../tmp/session-setup/top.png'});
 const bounds=await page.getByRole('main').evaluate(m=>({height:innerHeight,width:innerWidth,scroll:m.scrollHeight>m.clientHeight,docOverflow:document.documentElement.scrollWidth>innerWidth}));expect(bounds).toEqual({height:484,width:421,scroll:true,docOverflow:false});
 await page.getByRole('button',{name:'Start Session',exact:true}).click();await expect(page.getByRole('alert')).toHaveText('Enter a company name.');await expect(page.getByRole('textbox',{name:'Company'})).toBeFocused();expect(await page.evaluate(()=>window.calls.length)).toBe(0);
 await page.getByRole('textbox',{name:'Session title'}).fill('Test interview');await page.getByRole('textbox',{name:'Company'}).fill('   ');await page.getByRole('button',{name:'Start Session',exact:true}).click();expect(await page.evaluate(()=>window.calls.length)).toBe(0);
 await page.getByRole('textbox',{name:'Company'}).fill(' Acme ');await page.getByRole('textbox',{name:'Position'}).fill('Engineer');await page.getByRole('combobox',{name:'Select a resume'}).selectOption('resume-1');await page.getByRole('textbox',{name:'Job description / context Optional'}).fill('Mock context');await page.screenshot({path:'../tmp/session-setup/bottom.png'});
 await page.evaluate(()=>window.fail=true);await page.getByRole('button',{name:'Start Session',exact:true}).click();await expect(page.getByRole('main').getByRole('status')).toHaveText('Please retry');await expect(page.getByRole('textbox',{name:'Session title'})).toHaveValue('Test interview');
 await page.evaluate(()=>{window.fail=false;window.pending=true});await page.getByRole('button',{name:'Start Session',exact:true}).click();await expect(page.getByRole('button',{name:'Starting...'})).toBeDisabled();expect(await page.evaluate(()=>window.calls.length)).toBe(2);await page.evaluate(()=>window.finish());await expect.poll(()=>page.evaluate(()=>window.config?.activeSessionId)).toBe('mock-session');expect(await page.evaluate(()=>window.calls.at(-1))).toMatchObject({title:'Test interview',company_name:'Acme',target_role:'Engineer',selected_resume_id:'resume-1',job_description:'Mock context'});
})
test('setup navigation and native API controls remain separate',async({page})=>{await openSetup(page);await page.getByRole('button',{name:'Cancel session setup',exact:true}).click();expect(await page.evaluate(()=>window.back)).toBe(true);await page.getByRole('button',{name:'Collapse session setup',exact:true}).click();await page.getByRole('button',{name:'Restore session setup',exact:true}).click();await expect(page.getByRole('heading',{name:'Create New Session'})).toBeVisible();await page.getByLabel('Account menu').click();await expect(page.getByRole('menuitem',{name:'Dashboard',exact:true})).toBeVisible();await page.getByRole('button',{name:'Close window',exact:true}).click();expect(await page.evaluate(()=>window.closeCalled)).toBe(true)})

test('real Electron setup content size and native collapse/restore IPC',async()=>{
 const env={...process.env};delete env.ELECTRON_RUN_AS_NODE
 const app=await _electron.launch({args:[process.cwd(), '--user-data-dir='+path.resolve('..','tmp','setup-electron-'+Date.now())],env,timeout:20000})
 try {
  const page=await app.firstWindow();await page.waitForFunction(()=>Boolean(window.electronAPI?.resizeStartupWindow))
  expect(await page.evaluate(()=>window.electronAPI.resizeStartupWindow('setup'))).toMatchObject({ok:true})
  const metrics=await app.evaluate(({BrowserWindow,screen})=>{const w=BrowserWindow.getAllWindows().find(w=>w.webContents.getURL().includes('5173'));return {content:w.getContentSize(),bounds:w.getBounds(),zoomFactor:w.webContents.getZoomFactor(),displayScale:screen.getDisplayMatching(w.getBounds()).scaleFactor}})
  metrics.renderer=await page.evaluate(()=>({width:innerWidth,height:innerHeight,devicePixelRatio}))
  await mkdir(path.resolve('..','tmp/session-setup'),{recursive:true});await writeFile('../tmp/session-setup/native-metrics.json',JSON.stringify(metrics,null,2))
  const size=await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows().find(w=>w.webContents.getURL().includes('5173')).getContentSize())
  // Windows display scaling rounds native bounds by up to two DIPs.
  expect(Math.abs(size[0]-421)).toBeLessThanOrEqual(2);expect(Math.abs(size[1]-484)).toBeLessThanOrEqual(2)
  // The isolated native profile is signed out: first verify the real guard.
  expect(await page.evaluate(()=>window.electronAPI.collapseStartupWindow())).toMatchObject({ok:false,reason:'auth-required'})
  // Unmount startup auth listeners before mocking identity so they cannot resize to the home screen.
  await page.evaluate(()=>{history.pushState({},'', '/auth/confirm');dispatchEvent(new PopStateEvent('popstate'))})
  await expect(page.getByRole('heading',{name:'Secure link unavailable'})).toBeVisible()
  // Mock only the safe identity summary in this isolated test process; no real login.
  await app.evaluate((_, modulePath) => {
    const Manager = process.mainModule.require(modulePath).DesktopAuthSessionManager
    const original = Manager.prototype.getSafeState
    Manager.prototype.getSafeState = function () { return {...original.call(this),status:'connected'} }
  }, path.resolve('electron/desktop_auth_session.cjs'))
  expect(await page.evaluate(()=>window.electronAPI.collapseStartupWindow())).toMatchObject({ok:true})
  expect(await page.evaluate(()=>window.electronAPI.restoreStartupWindow())).toMatchObject({ok:true})
  const restored=await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows().find(w=>w.webContents.getURL().includes('5173')).getContentSize())
  expect(Math.abs(restored[0]-421)).toBeLessThanOrEqual(2);expect(Math.abs(restored[1]-484)).toBeLessThanOrEqual(2)
 } finally { await app.close() }
})

test('quota checking, missing balance and safe retry never block session authorization',async({page})=>{
 await openSetup(page);await expect(page.getByRole('status')).toHaveText('Checking\u2026');await page.evaluate(()=>window.quotaFinish());await expect(page.getByRole('status')).toContainText('Time unavailable');await page.getByRole('button',{name:'Retry',exact:true}).click();await expect(page.getByRole('status')).toHaveText('Checking\u2026');expect(await page.evaluate(()=>window.quotaChecks)).toBe(2);await page.evaluate(()=>window.quotaFinish());await expect(page.getByRole('status')).toContainText('Time unavailable');await expect(page.getByRole('button',{name:'Start Session',exact:true})).toBeEnabled()
})
test('supplied real-balance props render loaded time and Automatic keeps runtime routing',async({page})=>{
 await openSetup(page,{remaining:7,total:10});await expect(page.getByRole('status')).toContainText('7 / 10 min');await expect(page.getByRole('combobox',{name:'AI Model'})).toHaveValue('runtime');await expect(page.getByRole('option',{name:'Automatic'})).toHaveCount(1);expect(await page.evaluate(()=>window.quotaChecks)).toBe(0)
})
for(const scale of [1,1.25])test(`logical layout and bounded JD at device scale ${scale}`,async({browser})=>{
 const context=await browser.newContext({deviceScaleFactor:scale});const page=await context.newPage();try{
 await openSetup(page);await page.evaluate(()=>window.quotaFinish());await page.evaluate(()=>document.fonts.ready);await mkdir(path.resolve('..','tmp/session-setup'),{recursive:true});await page.screenshot({path:`../tmp/session-setup/top-scale-${scale}.png`});const main=page.getByRole('main');await main.evaluate(m=>m.scrollTop=m.scrollHeight/2);await page.screenshot({path:`../tmp/session-setup/middle-scale-${scale}.png`});await page.getByRole('textbox',{name:'Job description / context Optional'}).fill('Long mock context. '.repeat(300));await main.evaluate(m=>m.scrollTop=m.scrollHeight);await page.screenshot({path:`../tmp/session-setup/bottom-scale-${scale}.png`});const geometry=await page.getByRole('textbox',{name:'Job description / context Optional'}).evaluate(e=>({height:e.getBoundingClientRect().height,resize:getComputedStyle(e).resize,overflow:e.scrollHeight>e.clientHeight}));expect(geometry).toEqual({height:110,resize:'none',overflow:true});expect(await page.evaluate(()=>({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,horizontal:document.documentElement.scrollWidth>innerWidth}))).toEqual({width:421,height:484,dpr:scale,horizontal:false});await expect(page.getByRole('combobox',{name:'Select a resume'})).toHaveValue('');
 }finally{await context.close()}
})

test('quota request failure is unavailable rather than an invented zero balance',async({page})=>{
 await openSetup(page);await page.evaluate(()=>window.quotaReject(new Error('mock-only')));await expect(page.getByRole('status')).toContainText('Time unavailable');await expect(page.getByRole('status')).not.toContainText('0 min');await page.getByRole('button',{name:'Retry',exact:true}).click();await expect(page.getByRole('status')).toHaveText('Checking\u2026');await page.evaluate(()=>window.quotaFinish());await expect(page.getByRole('status')).toContainText('Time unavailable')
})
test('resume empty, failed, not-ready and long selected filenames remain usable',async({page})=>{
 await page.addInitScript(()=>{window.resumeItems=[];window.resumeError='Unable to load resumes.'});await openSetupWithBlockedResume(page);await expect(page.getByText('Unable to load resumes.',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'Start Session',exact:true})).toBeDisabled();await page.evaluate(()=>window.resumeError='');await page.getByRole('button',{name:'Refresh',exact:true}).click();await expect(page.getByText('No uploaded resumes found. Upload a resume from the web dashboard first.',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'Open dashboard to upload resume'})).toBeVisible();
 await page.evaluate(()=>window.resumeItems=[{id:'long',display_name:'Long filename '.repeat(30)+'.pdf',can_generate:false,readiness_reason:'processing'}]);await page.getByRole('button',{name:'Refresh',exact:true}).click();await page.getByRole('combobox',{name:'Select a resume'}).selectOption('long');await expect(page.getByRole('button',{name:'Start Session',exact:true})).toBeDisabled();await page.getByRole('combobox',{name:'Select a resume'}).focus();await page.keyboard.press('ArrowUp');await page.keyboard.press('Enter');await expect(page.getByRole('combobox',{name:'Select a resume'})).toHaveValue('');expect(await page.getByRole('main').evaluate(m=>m.scrollWidth<=m.clientWidth)).toBe(true)
})
async function openSetupWithBlockedResume(page){
 // Reuse the same isolated harness while permitting the expected disabled start state.
 await openSetup(page, null, true)
}

for(const screen of ['setup','choice'])test(`shared ${screen} account menu matches branding and keyboard/outside behavior`,async({page})=>{
 await openSetup(page,null,false,screen);const trigger=page.getByRole('button',{name:'Account menu',exact:true});await trigger.focus();await page.keyboard.press('Enter');const menu=page.getByRole('menu',{name:'Account actions'});await expect(menu).toBeVisible();await expect(menu.getByText('Intervucopilot',{exact:true})).toBeVisible();await expect(menu.getByText('person@example.test',{exact:true})).toBeVisible();await expect(menu.getByRole('menuitem')).toHaveCount(2);await expect(menu.getByRole('menuitem',{name:'Dashboard',exact:true})).toBeFocused();await page.keyboard.press('ArrowDown');await expect(menu.getByRole('menuitem',{name:'Log out',exact:true})).toBeFocused();await page.keyboard.press('Home');await expect(menu.getByRole('menuitem',{name:'Dashboard',exact:true})).toBeFocused();await page.keyboard.press('Escape');await expect(menu).toHaveCount(0);await expect(trigger).toBeFocused();await trigger.click();expect(await menu.evaluate(e=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.bottom<=innerHeight})).toBe(true);await mkdir(path.resolve('..','tmp/startup-menu'),{recursive:true});await page.evaluate(()=>document.fonts.ready);await page.screenshot({path:`../tmp/startup-menu/${screen}-open.png`});await page.getByRole('heading',{name:'Intervucopilot',exact:true}).click();await expect(menu).toHaveCount(0);await trigger.click();await menu.getByRole('menuitem',{name:'Dashboard',exact:true}).click();await expect(menu).toHaveCount(0);expect(await page.evaluate(()=>window.dashboardCalls)).toBe(1);await trigger.click();await page.evaluate(()=>window.logoutPending=true);await menu.getByRole('menuitem',{name:'Log out',exact:true}).click();await expect(menu.getByRole('menuitem',{name:'Signing out...'})).toBeDisabled();expect(await page.evaluate(()=>window.logoutCalls)).toBe(1);await page.evaluate(()=>window.finishLogout());await expect.poll(()=>page.evaluate(()=>window.signedOut)).toBe(true);await expect(menu).toHaveCount(0)
})

test('long account emails, account changes and logout failures stay safe',async({page})=>{
 const email='long.account.'.repeat(20)+'@example.test';await page.addInitScript(email=>window.testEmail=email,email);await openSetup(page);await page.getByRole('textbox',{name:'Company'}).fill('Preserved company');const trigger=page.getByRole('button',{name:'Account menu'});await trigger.click();const menu=page.getByRole('menu',{name:'Account actions'});await expect(menu.getByText(email,{exact:true})).toHaveAttribute('title',email);expect(await menu.evaluate(e=>e.getBoundingClientRect().right<=innerWidth)).toBe(true);await page.keyboard.press('Escape');await expect(page.getByRole('textbox',{name:'Company'})).toHaveValue('Preserved company');await trigger.click();await page.evaluate(()=>window.logoutFail=true);await menu.getByRole('menuitem',{name:'Log out',exact:true}).click();await expect(menu.getByRole('alert')).toHaveText('We could not sign you out. Please try again.');await expect(menu.getByRole('menuitem',{name:'Log out',exact:true})).toBeEnabled();await page.evaluate(()=>window.setMenuEmail('new.account@example.test'));await expect(menu).toHaveCount(0);await trigger.click();await expect(menu.getByText('new.account@example.test',{exact:true})).toBeVisible();await expect(menu.getByText(email,{exact:true})).toHaveCount(0);await page.evaluate(()=>window.setMenuEmail(''));await expect(page.getByRole('button',{name:'Account menu'})).toHaveCount(0);await expect(menu).toHaveCount(0)
})

test('signed-out and browser-handoff startup branding stays local and exposes no account menu',async({page})=>{
 await page.route('**/src/main.jsx*',r=>r.fulfill({contentType:'application/javascript',body:`import React from '/node_modules/.vite/deps/react.js';import ReactDOM from '/node_modules/.vite/deps/react-dom_client.js';import Login from '/src/components/StartupLoginScreen.jsx';import '/src/index.css';import '/src/styles/glass.css';window.saiia={getCloudStartupContext:async()=>({auth:{status:window.authStatus||'signed-out'}}),startAuthLogin:async()=>{window.authStatus='signing-in';return {status:'signing-in'}}};ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(Login));`}));await page.setViewportSize({width:426,height:420});await page.goto('/');await expect(page.getByRole('heading',{name:'Welcome to Intervucopilot'})).toBeVisible();await expect(page.getByRole('button',{name:/Login with Intervucopilot/})).toBeVisible();await expect(page.getByRole('button',{name:'Account menu'})).toHaveCount(0);await page.evaluate(()=>document.fonts.ready);await mkdir(path.resolve('..','tmp/startup-menu'),{recursive:true});await page.screenshot({path:'../tmp/startup-menu/login.png'});await page.getByRole('button',{name:/Login with Intervucopilot/}).click();await expect(page.getByText('We\u2019re securely connecting you to Intervucopilot Sign In.',{exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'Intervucopilot',exact:true})).toBeVisible();await expect(page.getByRole('menu')).toHaveCount(0);await page.screenshot({path:'../tmp/startup-menu/browser-handoff.png'});
})

import { test, expect } from '@playwright/test'

async function openChoice(page, name = 'Free', auto = { mode: 'limited', allowance: '600', used: '60', reserved: '30', unit_scale: 1 }) {
  await page.setViewportSize({ width: 428, height: 280 })
  await page.addInitScript(({name, auto}) => {
    window.saiia = {}
    window.subscriptionResult = { ok: true, plan: { name }, auto }
    window.electronAPI = {
      getSubscription: async () => window.subscriptionResult,
      openUpgrade: async () => { window.pricingCalls = (window.pricingCalls || 0) + 1; return { ok: !window.pricingFails } },
      onSubscriptionInvalidated: callback => { window.invalidate = callback; return () => {} },
    }
  }, {name, auto})
  await page.route('**/src/main.jsx*', route => route.fulfill({ contentType: 'application/javascript', body: `
    import React from '/node_modules/.vite/deps/react.js';
    import ReactDOM from '/node_modules/.vite/deps/react-dom_client.js';
    import Choice from '/src/components/StartupSessionChoiceScreen.jsx';
    import '/src/index.css'; import '/src/styles/glass.css';window.dispatchEvent(new Event('intervucopilot:mounted'));
    ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(function Harness() {
      const [email, setEmail] = React.useState('first@example.test'); window.setEmail = setEmail;
      return React.createElement(Choice, {authenticatedEmail:email, onCreateSession:()=>window.started=(window.started||0)+1});
    }));` }))
  await page.goto('/')
  await expect(page.getByRole('status')).toHaveText(`Current plan: ${name}`)
}

for (const name of ['Free', 'Plus', 'Pro']) test(`${name} uses compact plan actions and the existing session flow`, async ({page}) => {
  await openChoice(page, name, name === 'Pro' ? {mode:'unlimited'} : name === 'Plus' ? {mode:'limited',allowance:'18000',used:'0',reserved:'0',unit_scale:1} : undefined)
  const start = page.getByRole('button', {name:name === 'Free' ? 'Free Session 8.5 min' : `${name} Start Session`, exact:true})
  await expect(start).toBeVisible()
  await start.click()
  expect(await page.evaluate(()=>window.started)).toBe(1)
  await expect(page.getByRole('button',{name:'Buy Credits',exact:true})).toHaveCount(name === 'Free' ? 1 : 0)
  await expect(page.getByRole('button',{name:'Upgrade to Pro',exact:true})).toHaveCount(name === 'Plus' ? 1 : 0)
  await page.evaluate(()=>document.fonts.ready)
  await page.screenshot({path:`../tmp/startup-choice-${name.toLowerCase()}.png`})
  expect(await page.locator('.startup-choice-session-actions').evaluate(el=>el.getBoundingClientRect().bottom <= innerHeight)).toBe(true)
  if (name !== 'Pro') {
    await page.getByRole('button',{name:name === 'Free' ? 'Buy Credits' : 'Upgrade to Pro',exact:true}).click()
    expect(await page.evaluate(()=>window.pricingCalls)).toBe(1)
    await page.evaluate(()=>window.pricingFails=true)
    await page.getByRole('button',{name:name === 'Free' ? 'Buy Credits' : 'Upgrade to Pro',exact:true}).click()
    await expect(page.getByText('Unable to open the website. Please try again.')).toBeVisible()
  } else await expect(page.getByLabel('Unlimited Auto time')).toBeVisible()
  await page.evaluate(()=>document.fonts.ready)
  expect(await page.locator('.startup-choice-card').evaluate(el=>el.scrollWidth <= el.clientWidth)).toBe(true)
  if (name === 'Plus') {
    expect(await page.getByRole('status').evaluate(el=>el.getBoundingClientRect().bottom <= document.querySelector('.startup-choice-message').getBoundingClientRect().top)).toBe(true)
  }
})

test('balance reserves, exhaustion, focus refresh and account invalidation remain truthful', async ({page}) => {
  await openChoice(page)
  await expect(page.getByLabel('8.5 of 10 Auto minutes remaining')).toBeVisible()
  await page.evaluate(()=>{window.subscriptionResult={ok:true,plan:{name:'Free'},auto:{mode:'limited',allowance:'600000000',used:'600000000',reserved:'1000000',unit_scale:1000000}};window.dispatchEvent(new Event('focus'))})
  await expect(page.getByRole('button',{name:'Free Session 0 min',exact:true})).toBeVisible()
  await page.evaluate(()=>{window.subscriptionResult={ok:true,plan:{name:'Plus'},auto:{mode:'limited',allowance:'18000',used:'0',reserved:'0',unit_scale:1}};window.dispatchEvent(new Event('focus'))})
  await expect(page.getByRole('button',{name:'Plus Start Session',exact:true})).toBeVisible()
  await expect(page.getByLabel('300 of 300 Auto minutes remaining')).toBeVisible()
  await page.evaluate(()=>{window.invalidate();window.subscriptionResult={ok:false};window.setEmail('second@example.test')})
  await expect(page.getByRole('status')).toHaveText('Current plan temporarily unavailable')
  await expect(page.getByRole('button',{name:'Plus Start Session',exact:true})).toHaveCount(0)
  await expect(page.getByRole('button',{name:'Start Session',exact:true})).toBeVisible()
  await expect(page.getByLabel('Time availability unavailable')).toBeVisible()
  await page.getByRole('tab',{name:'Past Sessions',exact:true}).click()
  await expect(page.getByText('No past sessions yet. Start a session from the Create tab.')).toBeVisible()
})

test('loading and renamed plans never pretend to be Free; narrow layout stays usable', async ({page}) => {
  await openChoice(page)
  await page.evaluate(()=>{window.invalidate();window.subscriptionResult={ok:true,plan:{name:'Custom plan'},auto:null};window.dispatchEvent(new Event('focus'))})
  await expect(page.getByRole('status')).toHaveText('Current plan: Custom plan. Auto allowance unavailable')
  await expect(page.getByRole('button',{name:'Free Session',exact:true})).toHaveCount(0)
  await expect(page.getByRole('button',{name:'Start Session',exact:true})).toBeVisible()
  await page.setViewportSize({width:360,height:360})
  expect(await page.locator('.startup-choice-card').evaluate(el=>el.scrollWidth <= el.clientWidth)).toBe(true)
  await page.evaluate(()=>{window.electronAPI.getSubscription=()=>new Promise(()=>{});window.setEmail('pending@example.test')})
  await expect(page.getByRole('status')).toHaveText('Loading current plan...')
  await expect(page.getByRole('button',{name:'Buy Credits',exact:true})).toHaveCount(0)
})


test('history shares the compact shell without answer buttons and keeps dashboard navigation', async ({page}) => {
  await openChoice(page)
  const shell = await page.locator('.startup-choice-tabs').evaluate(el=>({width:el.getBoundingClientRect().width,background:getComputedStyle(el).backgroundColor,font:getComputedStyle(el.firstElementChild).fontSize}))
  await page.evaluate(()=>{
    window.saiia.listInterviewSessions=async()=>({items:[
      {id:'one',status:'ended',company_name:'A very long company name that must stay inside its row',target_role:'Senior software engineer with a long role title',started_at:'2026-11-02T10:00:00Z'},
      {id:'two',status:'ended',company_name:'Google',target_role:'Engineer',started_at:'2026-10-27T10:00:00Z'},
      {id:'three',status:'abandoned',company_name:'Example',started_at:'2026-10-21T10:00:00Z'}
    ]})
    window.electronAPI.openDashboard=async()=>{window.dashboardCalls=(window.dashboardCalls||0)+1;return {ok:true}}
  })
  await page.setViewportSize({width:428,height:514})
  await page.getByRole('tab',{name:'Past Sessions',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Recent sessions',exact:true})).toBeVisible()
  await expect(page.getByRole('button',{name:'View answers',exact:true})).toHaveCount(0)
  expect(await page.locator('.startup-choice-tabs').evaluate(el=>({width:el.getBoundingClientRect().width,background:getComputedStyle(el).backgroundColor,font:getComputedStyle(el.firstElementChild).fontSize}))).toEqual(shell)
  expect(await page.locator('.startup-choice-history-list').evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true)
  expect(await page.getByRole('button',{name:'View All Sessions',exact:true}).evaluate(el=>el.getBoundingClientRect().bottom<=innerHeight)).toBe(true)
  await page.screenshot({path:'../tmp/startup-choice-history.png'})
  await page.getByRole('button',{name:'View All Sessions',exact:true}).click()
  expect(await page.evaluate(()=>window.dashboardCalls)).toBe(1)
  await page.setViewportSize({width:360,height:514})
  expect(await page.locator('.startup-choice-card').evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true)
  await page.getByRole('tab',{name:'Create',exact:true}).click()
  await expect(page.getByRole('button',{name:'Free Session 8.5 min',exact:true})).toBeVisible()
})

test('history loading, retry and empty states fit the shared shell', async ({page}) => {
  await openChoice(page)
  await page.evaluate(()=>{window.saiia.listInterviewSessions=()=>new Promise(resolve=>window.resolveHistory=resolve)})
  await page.setViewportSize({width:428,height:514})
  await page.getByRole('tab',{name:'Past Sessions',exact:true}).click()
  await expect(page.getByText('Loading past sessions...', {exact:true})).toBeVisible()
  await page.evaluate(()=>window.resolveHistory({error:'Cloud unavailable'}))
  await expect(page.getByRole('alert')).toContainText('We could not load your past sessions.')
  await page.evaluate(()=>{window.saiia.listInterviewSessions=async()=>({items:[]})})
  await page.getByRole('button',{name:'Try again',exact:true}).click()
  await expect(page.getByText('No past sessions yet. Start a session from the Create tab.')).toBeVisible()
  await expect(page.getByRole('button',{name:'View All Sessions',exact:true})).toBeVisible()
})

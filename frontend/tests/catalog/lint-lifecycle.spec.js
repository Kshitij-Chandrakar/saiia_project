import { test, expect } from '@playwright/test'

async function fixture(page, body) {
  await page.addInitScript(() => { window.electronAPI = {} })
  page.on('pageerror', error => console.log('Fixture page error:', error.message))
  page.on('console', message => { if (message.type() === 'error') console.log('Fixture console:', message.text()) })
  await page.route('**/*', route => {
    const url = new URL(route.request().url())
    return url.hostname === '127.0.0.1' ? route.continue() : route.abort()
  })
  await page.route('**/src/main.jsx*', route => route.fulfill({
    contentType: 'application/javascript',
    body: `import React from '/node_modules/.vite/deps/react.js';
      import ReactDOM from '/node_modules/.vite/deps/react-dom_client.js';
      ${body}`,
  }))
  await page.goto('/')
}

test('pending startup auth uses latest parent callback without repeating the request', async ({ page }) => {
  await fixture(page, `import Login from '/src/components/StartupLoginScreen.jsx';
    window.loads=0;window.callbacks=[];
    window.saiia={getCloudStartupContext:()=>{window.loads++;return new Promise(r=>window.finishAuth=r)}};
    function Harness(){const [version,setVersion]=React.useState(0);window.rerender=()=>setVersion(v=>v+1);
      return React.createElement(Login,{onAuthenticated:()=>window.callbacks.push(version)})}
    ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(Harness));`)
  await expect.poll(() => page.evaluate(() => window.loads)).toBe(1)
  await page.evaluate(() => window.rerender())
  await page.evaluate(() => window.finishAuth({ status: 'connected' }))
  await expect.poll(() => page.evaluate(() => window.callbacks)).toEqual([1])
  expect(await page.evaluate(() => window.loads)).toBe(1)
})

test('setup account change fences old resume response without render-driven reloads', async ({ page }) => {
  await fixture(page, `import Setup from '/src/components/StartupSessionSetupScreen.jsx';
    window.models=0;window.resumeRequests=[];
    window.saiia={getCloudStartupContext:async()=>({}),
      listAnswerModels:async()=>{window.models++;return {items:[],admission:'legacy'}},
      listCloudResumes:()=>new Promise(r=>window.resumeRequests.push(r))};
    function Harness(){const [email,setEmail]=React.useState('first@example.test');
      const [version,setVersion]=React.useState(0);window.rerender=()=>setVersion(v=>v+1);window.switchAccount=()=>setEmail('second@example.test');
      return React.createElement(Setup,{authenticatedEmail:email,initialConfig:{title:String(version)}})}
    ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(Harness));`)
  await expect.poll(() => page.evaluate(() => window.resumeRequests.length)).toBe(1)
  await page.evaluate(() => window.rerender())
  expect(await page.evaluate(() => window.models)).toBe(1)
  expect(await page.evaluate(() => window.resumeRequests.length)).toBe(1)
  await page.evaluate(() => window.switchAccount())
  await expect.poll(() => page.evaluate(() => window.resumeRequests.length)).toBe(2)
  await page.evaluate(() => window.resumeRequests[1]({ items: [{ id: 'new', display_name: 'new-current.pdf', can_generate: true }] }))
  await expect(page.getByRole('option', { name: 'new-current.pdf - Ready' })).toHaveCount(1)
  await page.evaluate(() => window.resumeRequests[0]({ items: [{ id: 'old', display_name: 'old-private.pdf', can_generate: true }] }))
  await expect(page.getByRole('option', { name: /old-private/ })).toHaveCount(0)
  await expect(page.getByRole('option', { name: 'new-current.pdf - Ready' })).toHaveCount(1)
})

import { before, after, test } from 'node:test'
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createServer } from 'vite'
import { chromium, _electron } from '@playwright/test'

const root = resolve(import.meta.dirname,'../..')
const catalog = JSON.parse(execFileSync(process.env.SAIIA_TEST_PYTHON || 'python',['-c',
  'import json;from app.answer_models import model_catalog;from app.config import settings;print(json.dumps(dict(items=model_catalog(settings),admission="enabled",error="")))'],
  { cwd: resolve(root,'backend'), encoding:'utf8' }))
let server,browser,url

test('legacy creation conflict can retry without an unavailable model selector', async () => {
  const page = await pageWith({ ...catalog, admission: 'legacy' }, {
    creationResult: { code: 'session_conflict', error: 'Session conflict. Retry.' },
  })
  await ready(page)
  await page.getByRole('button', { name: 'Start Session' }).click()
  await page.waitForFunction(() => window.created.length === 1)
  await page.getByText('Session conflict. Retry.', { exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Start Session' }).isDisabled(), false)
  await page.evaluate(() => { delete window.creationResult })
  await page.getByRole('button', { name: 'Start Session' }).click()
  await page.waitForFunction(() => window.started.length === 1)
  await page.close()
})
before(async () => {
  server=await createServer({ root:resolve(root,'frontend'), server:{host:'127.0.0.1',port:0}, logLevel:'error' })
  await server.listen()
  url=server.resolvedUrls.local[0]+'tests/fixtures/session-model-setup.html'
  browser=await chromium.launch({headless:true})
  await mkdir(resolve(root,'tmp/session-model-phase4'),{recursive:true})
})
after(async () => { await browser?.close();await server?.close() })
async function pageWith(value=catalog, extra={}) {
  const page=await browser.newPage({viewport:{width:421,height:484}})
  await page.addInitScript(({value,extra}) => { window.fixtureCatalog=value;Object.assign(window,extra) },{value,extra})
  await page.goto(url)
  await page.getByRole('button',{name:/AI Model/}).waitFor()
  return page
}
async function ready(page) { await page.waitForFunction(() => window.catalogCalls>0);await page.waitForTimeout(50) }

test('backend order/default, local logos, keyboard, viewport bounds and internal scrolling',async () => {
  const page=await pageWith();await ready(page)
  const trigger=page.getByRole('button',{name:/AI Model/})
  await trigger.focus();await trigger.press('ArrowDown')
  const options=page.getByRole('option')
  assert.deepEqual(await options.locator('strong').allTextContents(),catalog.items.map(m=>m.display_name))
  assert.equal(await options.filter({hasText:catalog.items.find(m=>m.default).display_name}).getAttribute('aria-selected'),'true')
  const box=await page.getByRole('listbox').boundingBox()
  assert.ok(box.x>=0 && box.y>=0 && box.x+box.width<=421 && box.y+box.height<=484)
  assert.equal(await page.getByRole('listbox').evaluate(el=>el.parentElement===document.body),true)
  await page.screenshot({path:resolve(root,'tmp/session-model-phase4/dropdown.png')})
  await page.keyboard.press('Home');await page.keyboard.press('Enter')
  assert.ok((await trigger.textContent()).includes(catalog.items[0].display_name))
  await trigger.press('Space');await page.keyboard.press('Escape')
  assert.equal(await trigger.evaluate(el=>el===document.activeElement),true)
  assert.equal(await page.getByRole('listbox').count(),0)
  await page.close()
})

test('enabled creation sends stable key, ignores credential availability and uses authoritative response; fresh setup resets',async () => {
  const page=await pageWith({...catalog,items:catalog.items.map(m=>({...m,credentials_configured:false}))});await ready(page)
  const chosen=catalog.items.find(m=>m.default)
  await page.evaluate(key=>{window.creationDelay=true;window.creationResult={session:{id:'authoritative',status:'active',selected_model_key:key,model_selection_kind:'model_bound'}}},catalog.items[0].key)
  await page.getByRole('button',{name:'Start Session'}).evaluate(button=>{button.click();button.click()})
  await page.waitForFunction(()=>window.created.length===1)
  assert.equal(await page.getByRole('button',{name:/AI Model/}).isDisabled(),true)
  await page.evaluate(()=>window.releaseCreation())
  await page.waitForFunction(()=>window.started.length===1)
  const sent=await page.evaluate(()=>window.created[0])
  assert.equal(sent.body.selected_model_key,chosen.key)
  assert.equal(sent.options.expectedModelAdmission,'enabled')
  assert.equal(await page.evaluate(()=>window.started[0].selectedModelKey),catalog.items[0].key)
  await page.evaluate(()=>window.renderSetup());await ready(page)
  assert.ok((await page.getByRole('button',{name:/AI Model/}).textContent()).includes(chosen.display_name))
  await page.close()
})

test('disabled mode submits no binding; admission closed cannot create',async () => {
  const page=await pageWith({...catalog,admission:'legacy'});await ready(page)
  assert.equal(await page.getByRole('button',{name:/AI Model/}).isDisabled(),true)
  await page.getByRole('button',{name:'Start Session'}).click()
  await page.waitForFunction(()=>window.created.length===1)
  assert.equal(await page.evaluate(()=>Object.hasOwn(window.created[0].body,'selected_model_key')),false)
  await page.close()
  const closed=await pageWith({...catalog,admission:'closed'});await ready(closed)
  assert.equal(await closed.getByRole('button',{name:'Start Session'}).isDisabled(),true)
  assert.equal(await closed.getByRole('button',{name:/AI Model/}).isDisabled(),true)
  await closed.screenshot({path:resolve(root,'tmp/session-model-phase4/admission-closed.png')})
  await closed.close()
})

test('loading failure Retry recovers; stale choice refresh requires explicit valid selection',async () => {
  const page=await pageWith({items:[],error:'Unavailable'});await ready(page)
  assert.equal(await page.getByRole('button',{name:'Start Session'}).isDisabled(),true)
  await page.evaluate(c=>{window.fixtureCatalog=c},catalog)
  await page.locator('#setup-model-description').getByRole('button',{name:'Retry'}).click();await ready(page)
  await page.evaluate(c=>{window.fixtureCatalog={...c,items:c.items.filter(m=>!m.default)};window.creationResult={code:'model_selection_stale',error:'Model choices changed.'}},catalog)
  await page.getByRole('button',{name:'Start Session'}).click()
  await page.waitForFunction(()=>window.catalogCalls===3)
  assert.equal(await page.getByRole('button',{name:'Start Session'}).isDisabled(),true)
  await page.getByRole('button',{name:/AI Model/}).click()
  assert.equal(await page.getByRole('option').count(),catalog.items.length-1)
  await page.getByRole('option').first().click()
  assert.equal(await page.getByRole('button',{name:'Start Session'}).isDisabled(),false)
  await page.close()
})

test('configured unfamiliar model and unknown logo need no frontend list changes',async () => {
  const custom={key:'groq:future-test',display_name:'Future model',description:'Neutral text model',logo_key:'unfamiliar',selectable:true,default:true}
  const page=await pageWith({...catalog,items:[custom,...catalog.items.map(m=>({...m,default:false}))]});await ready(page)
  await page.getByRole('button',{name:/AI Model/}).click()
  const option=page.getByRole('option').first()
  assert.equal(await option.locator('strong').textContent(),'Future model')
  assert.equal(await option.locator('img').count(),0)
  assert.equal(await option.locator('svg').count()>0,true)
  await page.keyboard.press('Escape')
  await page.close()
})


test('large configured catalog scrolls internally without clipping the window',async () => {
  const items=Array.from({length:20},(_,i)=>({...catalog.items[i%catalog.items.length],key:'configured:'+i,default:i===0}))
  const page=await pageWith({...catalog,items});await ready(page)
  await page.getByRole('button',{name:/AI Model/}).click()
  assert.ok(await page.getByRole('listbox').evaluate(el=>el.scrollHeight>el.clientHeight))
  await page.keyboard.press('End')
  assert.equal(await page.getByRole('option').last().evaluate(el=>el===document.activeElement),true)
  const box=await page.getByRole('listbox').boundingBox()
  assert.ok(box.y>=0 && box.y+box.height<=484)
  await page.close()
})


test('late catalog response after setup reset cannot overwrite the fresh default',async () => {
  const page=await pageWith(catalog,{catalogDelay:true})
  await page.waitForFunction(()=>Boolean(window.releaseCatalog))
  await page.evaluate(c=>{ window.fixtureCatalog={...c,items:[...c.items].reverse().map((m,i)=>({...m,default:i===0}))};window.catalogDelay=false;window.renderSetup() },catalog)
  await ready(page)
  const name=catalog.items.at(-1).display_name
  await page.waitForFunction(name=>document.querySelector('.setup-model-trigger').textContent.includes(name),name)
  await page.evaluate(()=>window.releaseCatalog())
  await page.waitForTimeout(50)
  assert.ok((await page.getByRole('button',{name:/AI Model/}).textContent()).includes(name))
  await page.close()
})

test('actual isolated Electron renderer at setup dimensions renders the same bounded popup',async () => {
  const testEnv={...process.env,PHASE4_TEST_URL:url,PHASE4_TEST_USER_DATA:resolve(root,'tmp/session-model-phase4/electron-profile')};delete testEnv.ELECTRON_RUN_AS_NODE
  const app=await _electron.launch({args:[resolve(root,'frontend/tests/fixtures/session-model-electron.cjs')],
    env:testEnv})
  try {
    const page=await app.firstWindow()
    await page.waitForFunction(()=>typeof window.renderSetup==='function')
    await page.evaluate(c=>{window.fixtureCatalog=c;window.renderSetup()},catalog)
    await ready(page)
    assert.deepEqual(await page.evaluate(()=>({width:innerWidth,height:innerHeight})),{width:421,height:484})
    await page.getByRole('button',{name:/AI Model/}).click()
    const box=await page.getByRole('listbox').boundingBox()
    assert.ok(box.x>=0 && box.y>=0 && box.x+box.width<=421 && box.y+box.height<=484)
    await page.screenshot({path:resolve(root,'tmp/session-model-phase4/electron-dropdown.png')})
  } finally {await app.close()}
})


test('company and existing resume-readiness validation remain enforced',async () => {
  const page=await pageWith(catalog,{fixtureResumes:[{id:'resume-not-ready',display_name:'Uploaded resume',can_generate:false,readiness_reason:'processing'}]});await ready(page)
  await page.getByLabel('Company',{exact:false}).fill('')
  await page.getByRole('button',{name:'Start Session'}).click()
  assert.equal(await page.locator('#setup-company-error').textContent(),'Enter a company name.')
  assert.equal(await page.evaluate(()=>window.created.length),0)
  await page.getByLabel('Company',{exact:false}).fill('Example')
  await page.locator('.startup-setup-resume select').selectOption('resume-not-ready')
  assert.equal(await page.getByRole('button',{name:'Start Session'}).isDisabled(),true)
  await page.close()
})

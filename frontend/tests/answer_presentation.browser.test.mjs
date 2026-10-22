import {before,after,test} from 'node:test'
import assert from 'node:assert/strict'
import {resolve,join} from 'node:path'
import {tmpdir} from 'node:os'
import {mkdtemp} from 'node:fs/promises'
import {createServer} from 'vite'
import {chromium,expect} from '@playwright/test'
let server,browser,url
before(async()=>{
 server=await createServer({root:resolve(import.meta.dirname,'..'),cacheDir:await mkdtemp(join(tmpdir(),'saiia-presentation-vite-')),optimizeDeps:{include:['@dagrejs/dagre']},server:{host:'127.0.0.1',port:0},logLevel:'error'})
 await server.listen();url=server.resolvedUrls.local[0];browser=await chromium.launch({headless:true})
})
after(async()=>{await browser?.close();await server?.close()})
for(const width of [420,620])test(`main, overlay and history safely present canonical Markdown at ${width}px`,async()=>{
 const page=await browser.newPage({viewport:{width,height:860}})
 await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort())
 try{
  await page.goto(url+'tests/fixtures/answer-presentation.html');await page.waitForFunction(()=>typeof window.setPresentation==='function')
  await page.evaluate(()=>window.setPresentation({text:'**Purpose',streaming:true}))
  for(const area of ['#main','#overlay'])await expect(page.locator(area+' .answer-text')).toContainText('**Purpose')
  await page.evaluate(()=>window.setPresentation({text:'**Purpose**\n\nFirst explanation.\n\n1. First step.\n2. Second step.\n\n```python\ndef identity(value):\n    return value',streaming:true}))
  for(const area of ['#main','#overlay']){
   await expect(page.locator(area+' strong')).toHaveText('Purpose')
   await expect(page.locator(area+' .answer-text')).not.toContainText('**Purpose**')
   await expect(page.locator(area+' ol > li')).toHaveText(['First step.','Second step.'])
   await expect(page.locator(area+' pre code')).toHaveText('def identity(value):\n    return value')
  }
  await page.evaluate(()=>window.finishPresentation())
  await page.locator('#history select').selectOption('synthetic-saved')
  for(const area of ['#main','#overlay','#history']){
   await expect(page.locator(area+' strong')).toHaveText('Purpose')
   await expect(page.locator(area+' ol > li')).toHaveText(['Establish requirements.','Compare tradeoffs.'])
   await expect(page.locator(area+' .answer-text')).not.toContainText('First explanation')
   assert.equal(await page.locator(area+' .answer-text').textContent(),await page.locator('#main .answer-text').textContent())
  }
  const malicious='<img src="https://invalid.example/a" onerror="window.executed=true"> <script>window.executed=true</script> [link](javascript:alert(1))\n\n`max_queue_size` and *useful emphasis*.\n\n- Bound memory.\n- Preserve failure handling.\n\nA numbered sentence 1. stays 2. one paragraph. Compute 2 * 3 * 4.'
  await page.evaluate(text=>window.setPresentation({text,streaming:false}),malicious)
  for(const area of ['#main','#overlay']){
   await expect(page.locator(area+' .answer-text')).toContainText('<script>window.executed=true</script>')
   assert.equal(await page.locator(area+' .answer-text img,'+area+' .answer-text script,'+area+' .answer-text a').count(),0)
   await expect(page.locator(area+' em')).toHaveText('useful emphasis')
   await expect(page.locator(area+' code')).toHaveText('max_queue_size')
   await expect(page.locator(area+' ul > li')).toHaveText(['Bound memory.','Preserve failure handling.'])
   await expect(page.locator(area+' .answer-text')).toContainText('Compute 2 * 3 * 4.')
   await expect(page.locator(area+' ol')).toHaveCount(0)
  }
  assert.equal(await page.evaluate(()=>window.executed),undefined)
 }finally{await page.close()}
})

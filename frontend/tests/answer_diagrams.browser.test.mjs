import {before,after,test} from 'node:test'
import assert from 'node:assert/strict'
import {resolve} from 'node:path'
import {createServer} from 'vite'
import {chromium,expect} from '@playwright/test'
import { createHash } from 'node:crypto'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { mkdtemp } from 'node:fs/promises'
let server,browser,url
const sid='30000000-0000-4000-8000-000000000001',tid='40000000-0000-4000-8000-000000000001',rev='v1:'+createHash('sha256').update('["Design a queue", "API sends tasks to Queue."]').digest('hex')
const graph={status:'ready',nodes:[{id:'api',label:'API',kind:'service'},{id:'queue',label:'Queue',kind:'queue'}],edges:[{source:'api',target:'queue',label:'tasks'}]}
const descriptor={session_id:sid,transcript_id:tid,source_revision:rev,eligible:true,generation_enabled:true}
// Discover the worker dependency before navigation; cold Vite reoptimization
// otherwise reloads the fixture during its first generation request.
before(async()=>{server=await createServer({root:resolve(import.meta.dirname,'..'),cacheDir:await mkdtemp(join(tmpdir(),'saiia-diagram-vite-')),optimizeDeps:{include:['@dagrejs/dagre']},server:{host:'127.0.0.1',port:0},logLevel:'error'});await server.listen();url=server.resolvedUrls.local[0];browser=await chromium.launch({headless:true})})
after(async()=>{await browser?.close();await server?.close()})
async function pageFor(handler,query=''){
 const page=await browser.newPage();await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort())
 await page.exposeFunction('diagramRequest',handler);await page.goto(url+'tests/fixtures/answer-diagrams.html'+query);return page
}
for(const width of [420,620]) test(`click-only generation and local SVG at ${width}px`,async()=>{
 let calls=0,release,started,navigations=0
 const gate=new Promise(r=>{started=r})
 const page=await pageFor(async(action)=>{
  if(action==='resolve')return {ok:true,data:descriptor}
  if(action==='read')return {ok:true,data:{state:'absent'}}
  calls++;started();await new Promise(r=>{release=r});return {ok:true,data:{state:'ready',graph}}
 })
 page.on('framenavigated',frame=>{if(frame===page.mainFrame())navigations++})
 try{
  await page.setViewportSize({width,height:860});await expect(page.getByRole('button',{name:'Generate diagram',exact:true})).toBeVisible();assert.equal(calls,0)
  await page.getByRole('button',{name:'Generate diagram',exact:true}).click();await gate
  await expect(page.getByRole('status')).toContainText('Generating diagram');assert.equal(calls,1)
  release();await expect(page.getByRole('img',{name:'Architecture from the completed answer'})).toBeVisible()
  assert.equal(navigations,0,'generation must not reload the test page')
  await expect(page.locator('svg text')).toHaveText(['tasks','API','Queue'])
  await expect(page.locator('#canonical-answer')).toHaveText('API sends tasks to Queue.')
  assert.equal(await page.locator('foreignObject,svg image,svg script').count(),0)
  assert.ok(await page.locator('.diagram-scroll').evaluate(el=>el.clientWidth<=window.innerWidth))
  await page.screenshot({path:join(tmpdir(),`saiia-diagram-${width}.png`)})
  await page.getByText('Components and relationships (text alternative)').click();await expect(page.getByText('API \u2192 Queue: tasks')).toBeVisible()
 }finally{await page.close()}
})
test('late generation cannot attach to a new answer; logout clears delivery',async()=>{
 let release,started;const gate=new Promise(r=>{started=r})
 const page=await pageFor(async(action,payload)=>{
  if(action==='resolve')return {ok:true,data:payload.request_id==='second'?{...descriptor,eligible:false}:descriptor}
  if(action==='read')return {ok:true,data:{state:'absent'}}
  started();await new Promise(r=>{release=r});return {ok:true,data:{state:'ready',graph}}
 })
 try{
  await page.getByRole('button',{name:'Generate diagram',exact:true}).click();await gate
  await page.evaluate(sid=>window.changeDiagramSource({session_id:sid,request_id:'second'}),sid)
  await expect(page.getByRole('status')).toContainText('Available for verified')
  release();await expect(page.locator('svg')).toHaveCount(0)
  await page.evaluate(()=>window.invalidateDiagram());await expect(page.getByRole('status')).toContainText('unavailable')
 }finally{await page.close()}
})
test('saved history restores diagram without generation',async()=>{
 const calls=[]
 const page=await pageFor(async(action)=>{calls.push(action)
  if(action==='history')return {ok:true,data:{items:[{id:tid,question_text:'Design a queue',answer_text:'API sends tasks to Queue.'}]}}
  if(action==='resolve')return {ok:true,data:{...descriptor,generation_enabled:false}}
  return {ok:true,data:{state:'ready',graph}}
 },'?history')
 try{await page.getByRole('combobox').selectOption(tid);await expect(page.getByRole('img')).toBeVisible();assert.deepEqual(calls,['history','resolve','read'])}finally{await page.close()}
})
test('layout timeout terminates worker and retains text alternative',async()=>{
 const page=await browser.newPage();let terminated=0
 await page.exposeFunction('workerTerminated',()=>{terminated++})
 await page.addInitScript(()=>{window.Worker=class{postMessage(){} terminate(){window.workerTerminated()}}})
 await page.exposeFunction('diagramRequest',async action=>({ok:true,data:action==='resolve'?descriptor:{state:'ready',graph}}))
 await page.goto(url+'tests/fixtures/answer-diagrams.html')
 try{await expect(page.getByRole('status')).toContainText('Visual layout unavailable');assert.equal(terminated,1);await expect(page.getByText('Components and relationships (text alternative)')).toBeVisible()}finally{await page.close()}
})
test('a canonical revision mismatch never offers generation',async()=>{
 const calls=[]
 const page=await pageFor(async action=>{calls.push(action);return {ok:true,data:{...descriptor,source_revision:'v1:'+'b'.repeat(64)}}})
 try{await expect(page.getByRole('status')).toContainText('Available for verified');assert.deepEqual(calls,['resolve']);await expect(page.getByRole('button',{name:'Generate diagram',exact:true})).toHaveCount(0)}finally{await page.close()}
})
test('logout during generation rejects late ready graph',async()=>{
 let release,started;const gate=new Promise(r=>{started=r})
 const page=await pageFor(async action=>{
  if(action==='resolve')return {ok:true,data:descriptor}
  if(action==='read')return {ok:true,data:{state:'absent'}}
  started();await new Promise(r=>{release=r});return {ok:true,data:{state:'ready',graph}}
 })
 try{await page.getByRole('button',{name:'Generate diagram',exact:true}).click();await gate;await page.evaluate(()=>window.invalidateDiagram());release();await expect(page.getByRole('status')).toContainText('unavailable');await expect(page.locator('svg')).toHaveCount(0);await expect(page.locator('.answer-preview')).toHaveText('API sends tasks to Queue.')}finally{await page.close()}
})
for(const width of [420,620]) test(`recognizable component symbols at ${width}px`,async()=>{
 const kinds=['client','service','database','storage','queue','cache','external']
 const symbols={status:'ready',nodes:kinds.map(kind=>({id:kind,label:{client:'User',service:'API service',database:'Database',storage:'Object storage',queue:'Message queue',cache:'Cache',external:'External system'}[kind],kind})),edges:kinds.slice(1).map((kind,i)=>({source:kinds[i],target:kind,label:'Data flow'}))}
 const page=await pageFor(async action=>({ok:true,data:action==='resolve'?descriptor:{state:'ready',graph:symbols}}))
 try{
  await page.setViewportSize({width,height:860})
  await expect(page.locator('.diagram-node')).toHaveCount(7)
  await expect(page.locator('[data-kind="client"] circle')).toHaveCount(1)
  await expect(page.locator('[data-kind="database"] ellipse')).toHaveCount(1)
  await expect(page.locator('[data-kind="storage"] ellipse')).toHaveCount(1)
  await expect(page.locator('[data-kind="queue"] rect')).toHaveCount(3)
  await expect(page.locator('[data-kind="cache"] .diagram-node-detail')).toHaveCount(1)
  await expect(page.locator('[data-kind="external"] .diagram-node-shape path')).toHaveCount(1)
  for(const kind of kinds){
   const node=page.locator(`.diagram-node[data-kind="${kind}"]`)
   await node.scrollIntoViewIfNeeded();await expect(node).toBeVisible()
   if(width===420)await node.screenshot({path:join(tmpdir(),`saiia-diagram-symbol-${kind}.png`)})
  }
  assert.equal(await page.locator('foreignObject,svg image,svg script').count(),0)
  assert.ok(await page.locator('.diagram-scroll').evaluate(el=>el.clientWidth<=window.innerWidth&&el.scrollHeight>el.clientHeight))
 }finally{await page.close()}
})


for(const state of ['pending','unavailable'])test(`source ${state} stops without polling or generation error`,async()=>{
 let calls=0
 const page=await pageFor(async action=>{calls++;assert.equal(action,'resolve');return {ok:true,data:{session_id:sid,state,eligible:false,reason:state==='pending'?'source_pending':'schema_unavailable'}}})
 try{
  await expect(page.getByRole('status')).toContainText(state==='pending'?'Waiting for the saved answer':'Diagram unavailable')
  await page.evaluate(()=>window.changeDiagramSource({session_id:'30000000-0000-4000-8000-000000000001',request_id:'first'}))
  await expect(page.getByRole('status')).toContainText(state==='pending'?'Waiting for the saved answer':'Diagram unavailable')
  assert.equal(calls,1)
  await expect(page.getByRole('button',{name:'Generate diagram',exact:true})).toHaveCount(0)
  await expect(page.locator('#canonical-answer')).toHaveText('API sends tasks to Queue.')
 }finally{await page.close()}
})

test('disabled generation restores an existing saved diagram',async()=>{
 let generations=0
 const page=await pageFor(async action=>{
  if(action==='resolve')return {ok:true,data:{...descriptor,generation_enabled:false}}
  if(action==='read')return {ok:true,data:{state:'ready',graph}}
  generations++;throw Error('must not generate')
 })
 try{await expect(page.getByRole('img',{name:'Architecture from the completed answer'})).toBeVisible();await expect(page.getByRole('button',{name:'Generate diagram',exact:true})).toHaveCount(0);assert.equal(generations,0)}finally{await page.close()}
})


test('a full filtered history page still allows navigation to valid later entries',async()=>{
 const pages=[]
 const page=await pageFor(async(action,payload)=>{
  if(action==='history') {
   pages.push(payload.page)
   return {ok:true,data:payload.page===1?{items:[],has_more:true}:{items:[{id:tid,question_text:'Design a queue',answer_text:'API sends tasks to Queue.'}],has_more:false}}
  }
  if(action==='resolve')return {ok:true,data:{...descriptor,generation_enabled:false}}
  return {ok:true,data:{state:'ready',graph}}
 },'?history')
 try {
  await expect(page.getByRole('button',{name:'More answers'})).toBeEnabled()
  await page.getByRole('button',{name:'More answers'}).click()
  await expect(page.getByRole('combobox').locator('option')).toHaveCount(2)
  await page.getByRole('combobox').selectOption(tid)
  await expect(page.getByRole('img')).toBeVisible()
  await expect(page.getByRole('button',{name:'More answers'})).toBeDisabled()
  assert.deepEqual(pages,[1,2])
 }finally{await page.close()}
})

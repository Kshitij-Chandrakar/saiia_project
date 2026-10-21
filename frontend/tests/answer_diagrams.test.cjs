const { test } = require('node:test')
const assert = require('node:assert/strict')
const { AnswerDiagrams, registerAnswerDiagramIpc } = require('../electron/answer_diagrams.cjs')
const { DesktopAuthSessionManager } = require('../electron/desktop_auth_session.cjs')
const sid='30000000-0000-4000-8000-000000000001', tid='40000000-0000-4000-8000-000000000001'
const payload={session_id:sid,transcript_id:tid,source_revision:'v1:'+'a'.repeat(64),operation_id:tid}
function setup(fetchImpl) {
 const manager=new DesktopAuthSessionManager({fetchImpl,backendUrl:'http://127.0.0.1:1',logger:{}})
 manager.session={access_token:'synthetic-only'}; manager.user={user_id:'synthetic-owner'}; manager.status='connected'
 manager._hasFreshVerification=()=>true
 const bridge=new AnswerDiagrams(()=>manager)
 return {manager,bridge}
}
test('main-only IPC validates before reaching authenticated boundary',async()=>{
 let handler, called=false
 registerAnswerDiagramIpc({handle:(name,fn)=>{assert.equal(name,'answer-diagram:request');handler=fn}},
  event=>{if(event.sender!=='main')throw Error('denied')},{request:()=>{called=true}})
 assert.throws(()=>handler({sender:'overlay'},'generate',payload),/denied/); assert.equal(called,false)
 handler({sender:'main'},'generate',payload); assert.equal(called,true)
})
test('allowlists reject renderer text, identity, model and bad revisions',async()=>{
 const {bridge}=setup(()=>{throw Error('must not fetch')})
 for(const extra of [{user_id:'forged'},{answer_text:'forged'},{model:'forged'},{source_revision:'display-2'}])
  await assert.rejects(bridge.request('generate',{...payload,...extra}),/invalid_diagram_request/)
})
test('authenticated backend and private projection',async()=>{
 const {bridge}=setup(async(url,options)=>{
  assert.equal(options.headers.Authorization,'Bearer synthetic-only')
  assert.equal(url,`http://127.0.0.1:1/api/interview-sessions/${sid}/transcript-entries/${tid}/diagram`)
  assert.deepEqual(JSON.parse(options.body),{source_revision:payload.source_revision,operation_id:tid})
  return {ok:true,status:200,json:async()=>({state:'failed',source_revision:payload.source_revision,attempt:1,operation_id:tid,retry_allowed:true,token:'MUST NOT CROSS',failure_code:'refused'})}
 })
 const result=await bridge.request('generate',payload)
 assert.equal(result.data.retry_allowed,true); assert.ok(!JSON.stringify(result).includes('MUST NOT CROSS'))
})
test('logout invalidates pending delivery before requesting cancellation',async()=>{
 let release,started,cancelled=false
 const begun=new Promise(resolve=>{started=resolve})
 const {bridge}=setup(async(url)=>{
  if(url.endsWith('/cancel')) {cancelled=true;return {ok:true,status:200,json:async()=>({state:'cancelled'})}}
  started(); return await new Promise(resolve=>{release=()=>resolve({ok:true,status:200,json:async()=>({state:'processing',operation_id:tid})})})
 })
 const pending=bridge.request('generate',payload);await begun
 bridge.cancelAll(); assert.equal(cancelled,true);release()
 assert.deepEqual(await pending,{ok:false,error:'stale_operation'});assert.equal(bridge.pending.size,0)
})
test('auth generation change rejects a delayed response',async()=>{
 const {manager,bridge}=setup(async()=>{manager.sessionGeneration+=1;return {ok:true,status:200,json:async()=>({state:'failed'})}})
 assert.equal((await bridge.request('read',payload)).error,'stale_operation')
})
test('actual preload invokes registered main-only diagram channel and unsubscribes',async()=>{
 const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path')
 const exposed={},listeners=new Map();let handler
 const {bridge}=setup(async()=>({ok:true,status:200,json:async()=>({state:'absent'})}))
 registerAnswerDiagramIpc({handle:(_name,fn)=>{handler=fn}},event=>{assert.equal(event.sender,'main')},bridge)
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../electron/preload.cjs'),'utf8'),{
  require:name=>{assert.equal(name,'electron');return {contextBridge:{exposeInMainWorld:(key,value)=>{exposed[key]=value}},
   ipcRenderer:{invoke:(channel,...args)=>{assert.equal(channel,'answer-diagram:request');return handler({sender:'main'},...args)},on:(channel,fn)=>listeners.set(channel,fn),removeListener:(channel)=>listeners.delete(channel)}}}
 })
 assert.equal((await exposed.electronAPI.answerDiagram('read',payload)).data.state,'absent')
 let invalidated=0;const unsubscribe=exposed.electronAPI.onAnswerDiagramInvalidated(()=>invalidated++)
 listeners.get('answer-diagram:invalidate')();assert.equal(invalidated,1);unsubscribe();assert.equal(listeners.size,0)
})
test('diagram rendering is absent from overlay modules and snapshots',()=>{
 const fs=require('node:fs'),path=require('node:path')
 for(const file of ['components/OverlayWindow.jsx','components/AnswerPanel.jsx','overlay_snapshot.js']){
  const source=fs.readFileSync(path.join(__dirname,'../src',file),'utf8')
  assert.ok(!/DiagramSection|answerDiagram|diagramSource|source_revision/.test(source),file)
 }
})
test('wrong source revision cannot cross the bridge',async()=>{
 const {bridge}=setup(async()=>({ok:true,status:200,json:async()=>({state:'failed',source_revision:'v1:'+'b'.repeat(64)})}))
 assert.equal((await bridge.request('read',payload)).error,'stale_source')
})


test('concurrent and remounted source lookups coalesce; unavailable schema is cached safely',async()=>{
 let calls=0,release,started;const gate=new Promise(r=>started=r)
 const {bridge}=setup(async()=>{calls++;started();await new Promise(r=>release=r);return {ok:true,status:200,json:async()=>({session_id:sid,eligible:false,state:'unavailable',reason:'schema_unavailable'})}})
 const query={session_id:sid,request_id:'synthetic-saved'}
 const a=bridge.request('resolve',query),b=bridge.request('resolve',query);await gate;release()
 const [one,two]=await Promise.all([a,b]);assert.deepEqual(one,two);assert.equal(calls,1)
 assert.equal(one.data.reason,'schema_unavailable');await bridge.request('resolve',query);assert.equal(calls,1)
 await bridge.request('resolve',{...query,request_id:'next-answer'});assert.equal(calls,1)
 bridge.cancelAll();const next=bridge.request('resolve',query);await new Promise(resolve=>setImmediate(resolve));release();await next;assert.equal(calls,2)
})

test('genuine service errors remain errors and can recover; pending does not become permanent cache',async()=>{
 let calls=0
 const {bridge}=setup(async()=>{calls++;return calls===1?{ok:false,status:503,json:async()=>({detail:{code:'unavailable'}})}:{ok:true,status:200,json:async()=>({session_id:sid,eligible:false,state:'pending',reason:'source_pending'})}})
 const query={session_id:sid,request_id:'synthetic-saved'}
 assert.deepEqual(await bridge.request('resolve',query),{ok:false,error:'unavailable'})
 assert.equal((await bridge.request('resolve',query)).data.state,'pending')
 await bridge.request('resolve',query);assert.equal(calls,3)
})

test('source UI gate needs explicit durable completion, not just a request ID',async()=>{
 const {completedDiagramSource}=await import('../src/diagram_source_revision.js')
 const entry={id:'synthetic',status:'complete',question:'Synthetic',fullAnswer:'Canonical',metadata:{savedRequestId:'synthetic',savedSessionId:sid}}
 assert.equal(completedDiagramSource(entry,'Canonical','answer',false),null)
 entry.metadata.answerSaved=true
 assert.equal(completedDiagramSource(entry,'Canonical','answer',true),null)
 assert.equal(completedDiagramSource({...entry,status:'generating'},'Canonical','answer',false),null)
 assert.equal(completedDiagramSource(entry,'Canonical','screen',false),null)
 assert.equal(completedDiagramSource(entry,'Other','answer',false),null)
 assert.equal(completedDiagramSource(entry,'Canonical','answer',false).request_id,'synthetic')
})


test('failed and throwing operations release slots beyond sixteen distinct sources',async()=>{
 const {manager,bridge}=setup(async()=>({ok:false,status:503,json:async()=>({})}))
 for(let i=1;i<=20;i++) {
  const item={...payload,transcript_id:`40000000-0000-4000-8000-${String(i).padStart(12,'0')}`}
  assert.equal((await bridge.request('generate',item)).ok,false)
  assert.equal(bridge.pending.size,0)
 }
 manager._backendJson=async()=>{throw Error('synthetic network failure')}
 assert.equal((await bridge.request('generate',payload)).error,'unavailable')
 assert.equal(bridge.pending.size,0)
 bridge.cancelAll(); assert.equal(bridge.pending.size,0)
})

test('old failure cannot release a newer same-key pending operation',async()=>{
 const {manager,bridge}=setup(async()=>{})
 let release; let started
 const begun=new Promise(resolve=>{started=resolve})
 manager._backendJson=async()=>{started();return await new Promise(resolve=>{release=resolve})}
 const old=bridge.request('generate',payload);await begun
 const newer={...payload}
 bridge.pending.set(`${sid}:${tid}`,newer)
 release({ok:false,status:503,payload:{}})
 assert.equal((await old).ok,false)
 assert.equal(bridge.pending.get(`${sid}:${tid}`).operation_id,newer.operation_id)
 manager._backendJson=async()=>({ok:true,status:200,payload:{state:'cancelled'}})
 bridge.cancelAll(); assert.equal(bridge.pending.size,0)
})

test('canonical history uses admitted code-point bounds without truncation',async()=>{
 let entry={id:tid,question_text:'Q'.repeat(4000),answer_text:String.fromCodePoint(0x1f600).repeat(24000)}
 const {bridge}=setup(async()=>({ok:true,status:200,json:async()=>({items:[entry]})}))
 let result=await bridge.request('history',{session_id:sid})
 assert.equal(result.ok,true);assert.equal(result.data.items[0].answer_text,entry.answer_text)
 const {canonicalRevision}=await import('../src/diagram_source_revision.js')
 assert.match(await canonicalRevision(entry.question_text,entry.answer_text,false),/^v1:/)
 entry={...entry,answer_text:entry.answer_text+'x'}
 assert.equal((await bridge.request('history',{session_id:sid})).ok,false)
 await assert.rejects(canonicalRevision(entry.question_text,entry.answer_text,false),/unverified_source/)
 entry={...entry,question_text:'Q'.repeat(4001),answer_text:'valid'}
 assert.equal((await bridge.request('history',{session_id:sid})).ok,false)
})

// Isolated in-memory PostgreSQL via the repository's already-installed PGlite.
// No Supabase URL, credentials, network connection or package installation.
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { PGlite } from '@electric-sql/pglite'
import { createHash } from 'node:crypto'
const db = new PGlite()
const owner='00000000-0000-4000-8000-000000000001', other='00000000-0000-4000-8000-000000000002'
const historical='30000000-0000-4000-8000-000000000001'
await db.exec(`
 create role anon; create role authenticated; create role service_role bypassrls;
 create schema auth; create schema extensions;
 create function extensions.gen_random_uuid() returns uuid language sql as 'select gen_random_uuid()';
 create function auth.uid() returns uuid language sql as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
 create function auth.role() returns text language sql as $$select current_setting('request.jwt.claim.role',true)$$;
 create function public.set_updated_at() returns trigger language plpgsql as $$begin new.updated_at=now(); return new; end$$;
 create table auth.users(id uuid primary key);
 create table public.resumes(id uuid primary key,user_id uuid references auth.users(id));
 create table public.job_contexts(id uuid primary key,user_id uuid references auth.users(id));
 grant usage on schema auth,extensions to authenticated,service_role;
 insert into auth.users values ('${owner}'),('${other}');
`)
for (const name of ['20260828120000_add_interview_session_lifecycle.sql','20260828153000_fix_interview_session_idempotency_rpc.sql']) {
 await db.exec(await readFile(new URL(`../../supabase/migrations/${name}`,import.meta.url),'utf8'))
}
for (const name of ['20260829103000_add_interview_session_transcript_storage.sql',
 '20260829170000_lock_down_transcript_entry_inserts.sql','20261011120000_add_permanent_transcript_deletion.sql',
 '20261018120000_add_session_model_selection.sql','20261018150000_add_session_generation_turns.sql','20261018180000_add_session_model_bindings.sql']) {
 await db.transaction(async tx=>tx.exec(await readFile(new URL(`../../supabase/migrations/${name}`,import.meta.url),'utf8')))
}

await db.exec(`insert into public.interview_sessions(id,user_id,title) values ('${historical}','${owner}','synthetic')`)
const sid=historical
const create=async(id,source='answer')=>(await db.query(`select * from public.create_interview_session_transcript_entry($1,$2,$3,$4,'Design a queue','API sends tasks to Queue.', 'technical','openai','synthetic',1,'{"answer_type":"system_design","provenance":"managed_generation"}')`,[owner,sid,id,source])).rows[0].transcript_entry_id
const stamp=async(tid,user=owner)=>(await db.query(`select public.stamp_answer_source($1,$2,$3,'Design a queue','API sends tasks to Queue.','system_design') as ok`,[user,sid,tid])).rows[0].ok
const historyPayload={question:'Design a queue',result:{answer:'API sends tasks to Queue.',answer_type:'system_design',generate_source:'auto'}}
const historicalOp=async(operation,token=null,payload=null)=>(await db.query("select public.session_generation_turn($1,$2,$3,'verified-history','hash',0,null,$4,$5) as result",[operation,owner,sid,token,payload])).rows[0].result
const historicalClaim=await historicalOp('claim')
await historicalOp('checkpoint',historicalClaim.token,historyPayload); await historicalOp('complete',historicalClaim.token)
await db.exec(await readFile(new URL('../../supabase/migrations/20261021120000_add_answer_sources.sql',import.meta.url),'utf8'))
for (const [question,answer] of [['Design a queue','API sends tasks to Queue.'],['Quotes " and newline\n','Unicode \u03bb \ud83d\ude00, slash / and \\']]) {
 const actual=(await db.query('select public.answer_source_revision($1,$2) as revision',[question,answer])).rows[0].revision
 const expected='v1:'+createHash('sha256').update(`[${JSON.stringify(question)}, ${JSON.stringify(answer)}]`).digest('hex')
 assert.equal(actual,expected,'server/client revision parity')
}
assert.equal((await db.query('select provenance from public.interview_answer_sources')).rows[0].provenance,'managed_generation','verified pre-migration history is eligible')
await db.exec('delete from public.interview_session_transcript_entries')
const tid=await create('unmanaged')
assert.equal((await db.query('select count(*)::int as n from public.interview_answer_sources')).rows[0].n,0,'client metadata cannot forge provenance')
assert.equal(await stamp(tid,other),false)
assert.equal(await stamp(tid),true)
const revision=(await db.query('select source_revision from public.interview_answer_sources')).rows[0].source_revision
assert.match(revision,/^v1:[a-f0-9]{64}$/)
assert.equal(await stamp(await create('screen','analyze_screen')),false)
await db.query("update public.interview_session_transcript_entries set answer_text='changed' where id=$1",[tid])
assert.equal((await db.query('select count(*)::int as n from public.interview_answer_sources')).rows[0].n,0)
const data={question:'Design a queue',result:{answer:'API sends tasks to Queue.',answer_type:'system_design',generate_source:'auto'}}
const op=async(operation,token=null,payload=null)=>(await db.query("select public.session_generation_turn($1,$2,$3,'managed','hash',0,null,$4,$5) as result",[operation,owner,sid,token,payload])).rows[0].result
const claim=await op('claim')
await op('checkpoint',claim.token,data)
await op('complete',claim.token)
assert.equal((await db.query('select provenance from public.interview_answer_sources')).rows[0].provenance,'managed_generation')
await db.exec(`delete from public.interview_session_transcript_entries`)
assert.equal((await db.query('select count(*)::int as n from public.interview_answer_sources')).rows[0].n,0)
console.log('6A SQL: spoofing, ownership, Screen exclusion, canonical invalidation, managed completion and cascade passed; paused migration excluded')
await db.exec(await readFile(new URL('../../supabase/migrations/20261021130000_add_answer_diagrams.sql',import.meta.url),'utf8'))
const dt=await create('diagram-source'); await stamp(dt)
const rev=(await db.query('select source_revision from public.interview_answer_sources where transcript_id=$1',[dt])).rows[0].source_revision
const oid='50000000-0000-4000-8000-000000000001', oid2='50000000-0000-4000-8000-000000000002'
const diagram=async(operation,{token=null,graph=null,model='gpt-4.1-mini',code=null,id=oid,user=owner,revision=rev,transcript=dt}={})=>
 (await db.query('select public.answer_diagram_operation($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) as result',
 [operation,user,sid,transcript,revision,id,token,graph,model,code])).rows[0].result
assert.equal((await diagram('claim',{user:other})).error,'source_not_found')
assert.equal((await diagram('claim',{revision:'stale'})).error,'stale_source')
let d=await diagram('claim'); assert.equal(d.claimed,true)
assert.equal((await diagram('claim',{id:oid2})).claimed,undefined,'duplicate click shares operation')
await diagram('fail',{token:d.token,code:'provider_failed'})
d=await diagram('retry',{id:oid2}); assert.equal(d.claimed,true); assert.equal(d.attempt,2)
assert.equal((await diagram('checkpoint',{token:oid,graph:{status:'ready'}})).error,'stale_operation')
await diagram('checkpoint',{id:oid2,token:d.token,graph:{status:'ready',nodes:[],edges:[]}})
await db.query("update public.interview_answer_diagrams set lease_until=clock_timestamp()-interval '1 second' where transcript_id=$1",[dt])
assert.equal((await diagram('read')).state,'checkpoint','checkpoint survives lease expiry for save-only recovery')
await diagram('finalize',{id:oid2,token:d.token})
assert.equal((await diagram('claim')).state,'ready','saved replay never claims')
assert.equal((await diagram('retry')).state,'ready')
assert.equal((await diagram('cancel',{id:oid2})).state,'ready','cancellation after finalization preserves the saved result')
await db.exec(`set request.jwt.claim.sub='${other}'; set role authenticated`)
assert.equal((await db.query('select count(*)::int as n from public.interview_answer_sources')).rows[0].n,0,'source RLS excludes other owners')
await assert.rejects(db.query("select public.stamp_answer_source($1,$2,$3,'q','a','system_design')",[owner,sid,dt]),/permission denied/)
await db.exec('reset role')
await db.exec('delete from public.interview_session_transcript_entries')
assert.equal((await diagram('finalize',{id:oid2,token:d.token})).error,'source_not_found','returning worker cannot resurrect deleted source')
assert.equal((await db.query('select count(*)::int as n from public.interview_answer_diagrams')).rows[0].n,0)
const uncertain=await create('uncertain'); await stamp(uncertain)
d=await diagram('claim',{transcript:uncertain})
await db.exec("update public.interview_answer_diagrams set lease_until=clock_timestamp()-interval '1 second'")
assert.equal((await diagram('claim',{transcript:uncertain})).state,'uncertain')
assert.equal((await diagram('checkpoint',{transcript:uncertain,token:d.token,graph:{status:'ready'}})).error,'stale_operation')
const cancelled=await create('cancel-before-claim'); await stamp(cancelled)
assert.equal((await diagram('cancel',{transcript:cancelled})).state,'cancelled')
assert.equal((await diagram('claim',{transcript:cancelled})).claimed,undefined,'cancel overtaking a delayed claim prevents generation')
const checkpointCancel=await create('cancel-checkpoint'); await stamp(checkpointCancel)
let checkpointWorker=await diagram('claim',{transcript:checkpointCancel})
await diagram('checkpoint',{transcript:checkpointCancel,token:checkpointWorker.token,graph:{status:'ready'}})
assert.equal((await diagram('cancel',{transcript:checkpointCancel})).graph,null)
assert.equal((await diagram('finalize',{transcript:checkpointCancel,token:checkpointWorker.token})).error,'stale_operation')
const changed=await create('changed'); await stamp(changed)
d=await diagram('claim',{transcript:changed})
await diagram('checkpoint',{transcript:changed,token:d.token,graph:{status:'ready'}})
await db.query("update public.interview_session_transcript_entries set answer_text='changed canonical answer' where id=$1",[changed])
assert.equal((await diagram('finalize',{transcript:changed,token:d.token})).error,'ineligible_source')
await db.exec(`update public.interview_sessions set status='ended',ended_at=clock_timestamp()-interval '6 minutes' where id='${sid}'`)
await db.query('select public.delete_interview_session_transcript_entries($1,$2)',[owner,sid])
assert.equal((await diagram('finalize',{transcript:uncertain,token:d.token})).error,'source_not_found')
assert.equal((await db.query('select count(*)::int as n from public.interview_answer_diagrams')).rows[0].n,0,'Clear Transcript cascades checkpoints and tombstones')
await db.exec('set role authenticated')
await assert.rejects(db.query('select * from public.interview_answer_diagrams'),/permission denied/)
await db.exec('reset role')
const seed=async(session)=>{
 await db.query('insert into public.interview_sessions(id,user_id,title) values($1,$2,$3)',[session,owner,'synthetic cascade'])
 const entry=(await db.query("select * from public.create_interview_session_transcript_entry($1,$2,'cascade','answer','Design a queue','API sends tasks to Queue.','technical','openai','synthetic',1,'{}')",[owner,session])).rows[0].transcript_entry_id
 await db.query("select public.stamp_answer_source($1,$2,$3,'Design a queue','API sends tasks to Queue.','system_design')",[owner,session,entry])
 const source=(await db.query('select source_revision from public.interview_answer_sources where transcript_id=$1',[entry])).rows[0].source_revision
 await db.query("select public.answer_diagram_operation('claim',$1,$2,$3,$4,$5,null,null,'gpt-4.1-mini',null)",[owner,session,entry,source,oid])
}
const cascadedSession='30000000-0000-4000-8000-000000000003'
await seed(cascadedSession)
await db.query('delete from public.interview_sessions where id=$1',[cascadedSession])
assert.equal((await db.query('select count(*)::int as n from public.interview_answer_diagrams')).rows[0].n,0,'session deletion cascades live operations')
await seed('30000000-0000-4000-8000-000000000004')
assert.equal((await db.query('select count(*)::int as n from public.interview_answer_diagrams')).rows[0].n,1)
await db.exec(`delete from auth.users where id='${owner}'`)
assert.equal((await db.query('select count(*)::int as n from public.interview_answer_diagrams')).rows[0].n,0)
console.log('6B SQL: duplicate claim, ownership, retry bound, stale fence, checkpoint recovery, ready replay, deletion/finalization ordering, expired uncertainty and account cascade passed')
await db.close()

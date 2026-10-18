// Isolated in-memory PostgreSQL via the repository's already-installed PGlite.
// No Supabase URL, credentials, network connection or package installation.
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { PGlite } from '../../tmp/transcript-delete-db/node_modules/@electric-sql/pglite/dist/index.js'
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
 '20261018120000_add_session_model_selection.sql','20261018150000_add_session_generation_turns.sql']) {
 await db.transaction(async tx=>tx.exec(await readFile(new URL(`../../supabase/migrations/${name}`,import.meta.url),'utf8')))
}
await db.exec(`insert into public.interview_sessions(id,user_id,title) values ('${historical}','${owner}','test')`)
const sid=historical
const payload={question:'private question',request:{question:'private question'},result:{answer:'private answer',provider:'groq',model:'openai/gpt-oss-120b',generation_ms:1,generate_source:'auto',selected_model_key:'gemini-3.5-flash-lite',actual_provider:'groq'}}
const op=async(operation,id='turn-1',token=null,attempt=0,data=null,user=owner,hash='hash',supersedes=null)=>{
 const result=(await db.query('select public.session_generation_turn($1,$2,$3,$4,$5,$6,$7,$8,$9) as result',
  [operation,user,sid,id,hash,attempt,supersedes,token,data])).rows[0].result
 return result
}
await db.exec("set role service_role")
let first=await op('claim','turn-1',null,0,{request:{question:'private question'}})
assert.equal(first.state,'claimed')
assert.equal((await op('claim')).state,'processing')
assert.equal((await op('claim','turn-1',null,0,null,owner,'other')).error,'payload_conflict')
assert.equal((await op('checkpoint','turn-1',other,0,payload)).error,'stale_attempt')
await op('checkpoint','turn-1',first.token,0,payload)
assert.equal((await op('claim')).state,'checkpoint')
await op('complete','turn-1',first.token)
await op('complete','turn-1',first.token)
assert.equal((await op('claim')).state,'completed')
assert.equal((await db.query('select count(*)::int as n from public.interview_session_transcript_entries')).rows[0].n,1)
assert.equal((await db.query('select metadata from public.interview_session_transcript_entries')).rows[0].metadata.actual_provider,'groq')
const second=await op('claim','turn-2')
await op('checkpoint','turn-2',second.token,0,payload)
await op('complete','turn-2',second.token)
assert.equal((await db.query('select count(*)::int as n from public.interview_session_transcript_entries')).rows[0].n,2)
let failed=await op('claim','failed')
await op('fail','failed',failed.token)
assert.equal((await op('claim','failed')).state,'failed')
const retry=await op('claim','failed',null,1)
assert.equal(retry.state,'claimed')
assert.equal((await op('checkpoint','failed',failed.token,0,payload)).error,'stale_attempt')
assert.equal((await op('claim','turn-1',null,0,null,other)).error,'session_not_found')
const abandoned=await op('claim','crashed')
await db.query("update public.session_generation_turns set lease_until=clock_timestamp()-interval '1 second' where request_id='crashed'")
assert.equal((await op('claim','crashed')).state,'uncertain')
assert.equal((await op('claim','crashed',null,1)).error,'attempt_conflict')
assert.equal((await op('checkpoint','crashed',abandoned.token,0,payload)).error,'stale_attempt')
const cancelled=await op('claim','cancelled')
await op('checkpoint','cancelled',cancelled.token,0,payload)
await op('cancel','cancelled',cancelled.token)
assert.equal((await op('complete','cancelled',cancelled.token)).error,'stale_attempt')
const old=await op('claim','superseded')
await op('claim','new',null,0,null,owner,'hash','superseded')
assert.equal((await op('checkpoint','superseded',old.token,0,payload)).error,'stale_attempt')
await db.exec('reset role;set role authenticated')
await assert.rejects(db.query('select * from public.session_generation_turns'),/permission denied/)
await assert.rejects(op('claim','forged'),/permission denied/)
await db.exec('reset role')
await db.query("update public.interview_sessions set status='ended',ended_at=clock_timestamp()-interval '6 minutes' where id=$1",[sid])
assert.equal((await db.query("select count(*)::int as n from public.session_generation_turns where state<>'completed' and payload is not null")).rows[0].n,0)
await db.exec('set role service_role')
await db.query('select public.delete_interview_session_transcript_entries($1,$2)',[owner,sid])
assert.equal((await db.query('select count(*)::int as n from public.session_generation_turns where payload is not null')).rows[0].n,0)
assert.equal((await db.query("select state from public.session_generation_turns where request_id='turn-1'")).rows[0].state,'deleted')
await db.exec('reset role')
await db.close()
console.log('PASS: generation claim/fence/retry/checkpoint/replay/expiry/uncertain/ownership/deletion; real isolated PostgreSQL-in-WASM')

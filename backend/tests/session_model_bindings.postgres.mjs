// Isolated in-memory PostgreSQL via the repository's already-installed PGlite.
// No Supabase URL, credentials, network connection or package installation.
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { PGlite } from '@electric-sql/pglite'
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
await db.exec(`insert into public.interview_sessions(id,user_id,title,status,ended_at) values ('${historical}','${owner}','historical','ended',now());
 create table public.interview_session_transcript_entries(session_id uuid,model text,metadata jsonb);
 insert into public.interview_session_transcript_entries values ('${historical}','old-model','{"model":"old-model"}');`)
const before=(await db.query('select * from public.interview_session_transcript_entries')).rows
await db.transaction(async tx => tx.exec(await readFile(new URL('../../supabase/migrations/20261018120000_add_session_model_selection.sql',import.meta.url),'utf8')))
assert.equal((await db.query('select selected_model_key from public.interview_sessions')).rows[0].selected_model_key,null)
assert.deepEqual((await db.query('select * from public.interview_session_transcript_entries')).rows,before)

// Simulate a real Phase 2 binding before the additive migration, without rewriting it.
await db.exec("create or replace function public.session_model_routing_ready() returns boolean language sql stable as 'select true';set role service_role; select set_config('request.jwt.claim.role','service_role',false)")
const historicalBound=(await db.query("select * from public.create_interview_session_with_model($1,'old-bound','oldhash',null,null,'old',null,null,null,'gpt-5.6-luna')",[owner])).rows[0].interview_session_id
await db.exec('reset role')
await db.exec(await readFile(new URL('../../supabase/migrations/20261018180000_add_session_model_bindings.sql',import.meta.url),'utf8'))
assert.equal((await db.query('select selected_model_binding from public.interview_sessions where id=$1',[historicalBound])).rows[0].selected_model_binding,null)
assert.deepEqual((await db.query('select * from public.interview_session_transcript_entries')).rows,before)
const binding={version:1,provider:'groq',api_model:'example-compatible-model',profile:'groq-chat',effort:'',output_limit:65536}
const key='groq:example-compatible-model'
const rpc=(id,b=binding,user=owner,hash='hash')=>db.query("select * from public.create_interview_session_with_binding($1,$2,$3,null,null,'test',null,null,null,$4,$5)",[user,id,hash,key,b])
await db.exec("create or replace function public.session_model_routing_ready() returns boolean language sql stable as 'select false';set role service_role")
await assert.rejects(rpc('closed'),/not available/)
await db.exec("reset role;create or replace function public.session_model_routing_ready() returns boolean language sql stable as 'select true';set role service_role")
const sid=(await rpc('new')).rows[0].interview_session_id
assert.equal((await rpc('new')).rows[0].replayed,true)
assert.deepEqual((await db.query('select selected_model_binding from public.interview_sessions where id=$1',[sid])).rows[0].selected_model_binding,binding)
await assert.rejects(rpc('new',{...binding,output_limit:1000}),/conflict/)
await assert.rejects(rpc('bad',{...binding,profile:'openai-reasoning'}),/binding|check/)
await assert.rejects(db.query('update public.interview_sessions set selected_model_binding=$1 where id=$2',[{...binding,api_model:'different'},sid]),/immutable/)
await db.exec("reset role;set role authenticated;select set_config('request.jwt.claim.sub','"+owner+"',false);select set_config('request.jwt.claim.role','authenticated',false)")
await assert.rejects(rpc('forged'),/permission denied/)
await assert.rejects(db.query("insert into public.interview_sessions(user_id,selected_model_key,selected_model_binding) values ($1,$2,$3)",[owner,key,binding]),/backend creation/)
await assert.rejects(db.query('update public.interview_sessions set selected_model_binding=$1 where id=$2',[{...binding,effort:'high'},sid]),/immutable/)
await db.query("update public.interview_sessions set status='ended',ended_at=now() where id=$1",[sid])
assert.equal((await db.query('select status from public.interview_sessions where id=$1',[sid])).rows[0].status,'ended')
await db.exec("select set_config('request.jwt.claim.sub','"+other+"',false)")
assert.equal((await db.query('select * from public.interview_sessions where id=$1',[sid])).rows.length,0)
await db.exec('reset role')
await db.close()
console.log('PASS: arbitrary configured binding, additive migration, RPC replay/profile conflict, immutability, ownership, grants, lifecycle, closed gate and unchanged historical rows/transcripts')

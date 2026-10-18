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
const rpc=(key,model=null,hash='hash',user=owner)=>db.query(`select * from public.create_interview_session_with_model($1,$2,$3,null,null,'test',null,null,null,$4)`,[user,key,hash,model])
const old=(key,user=owner)=>db.query(`select * from public.create_interview_session_with_idempotency($1,$2,'hash',null,null,'legacy',null,null,null)`,[user,key])
await db.exec("set role service_role; select set_config('request.jwt.claim.role','service_role',false)")
const legacy=(await old('old')).rows[0].interview_session_id
assert.equal((await old('old')).rows[0].replayed,true)
await assert.rejects(rpc('not-ready','gemini-3.5-flash-lite'),/not available/)
await db.exec('reset role')
// Test future enabled RPC behavior ONLY inside this disposable database.
await db.exec('create or replace function public.session_model_routing_ready() returns boolean language sql stable set search_path=pg_catalog as $$select true$$')
await db.exec("set role service_role; select set_config('request.jwt.claim.role','service_role',false)")
let bound
for (const [i,model] of ['gpt-5.6-luna','gpt-5.6-terra','gpt-oss-120b','gemini-3.5-flash-lite','gemini-3.6-flash'].entries()) {
 const result=(await rpc(`model-${i}`,model)).rows[0]
 bound=result.interview_session_id
 assert.equal((await db.query('select selected_model_key from public.interview_sessions where id=$1',[bound])).rows[0].selected_model_key,model)
 assert.equal((await rpc(`model-${i}`,model)).rows[0].replayed,true)
}
await assert.rejects(rpc('model-4','gpt-5.6-luna'),/idempotency key conflict/)
await assert.rejects(rpc('invalid','https://arbitrary-model'),/model_key_check/)
await assert.rejects(db.query('update public.interview_sessions set selected_model_key=$1 where id=$2',['gpt-5.6-luna',bound]),/immutable/)
await assert.rejects(db.query('update public.interview_sessions set selected_model_key=$1 where id=$2',['gpt-5.6-luna',historical]),/immutable/)
await assert.rejects(db.query('update public.interview_sessions set user_id=$1 where id=$2',[other,bound]),/immutable/)
await db.exec("reset role; set role authenticated; select set_config('request.jwt.claim.role','authenticated',false)")
await db.query("select set_config('request.jwt.claim.sub',$1,false)",[other])
assert.equal((await db.query('select * from public.interview_sessions where id=$1',[bound])).rows.length,0)
assert.equal((await db.query("update public.interview_sessions set status='ended',ended_at=now() where id=$1 returning id",[bound])).rows.length,0)
await db.query("select set_config('request.jwt.claim.sub',$1,false)",[owner])
await assert.rejects(rpc('forged','gpt-5.6-luna'),/permission denied/)
await assert.rejects(old('forged-old'),/permission denied/)
await assert.rejects(db.query('update public.interview_sessions set selected_model_key=null where id=$1',[bound]),/immutable/)
await assert.rejects(db.query("insert into public.interview_sessions(user_id,selected_model_key) values ($1,'gpt-5.6-luna')",[owner]),/backend creation/)
assert.equal((await db.query("update public.interview_sessions set status='ended',ended_at=now() where id=$1 returning selected_model_key",[bound])).rows[0].selected_model_key,'gemini-3.6-flash')
await db.exec('reset role')
// Restore the real shipped closed gate and verify future rows still cannot be admitted.
await db.exec('create or replace function public.session_model_routing_ready() returns boolean language sql stable set search_path=pg_catalog as $$select false$$')
await db.exec("set role service_role; select set_config('request.jwt.claim.role','service_role',false)")
await assert.rejects(rpc('disabled-again','gpt-5.6-luna'),/not available/)
await db.exec('reset role')
assert.deepEqual((await db.query('select * from public.interview_session_transcript_entries')).rows,before)
assert.equal((await db.query('select selected_model_key from public.interview_sessions where id=$1',[legacy])).rows[0].selected_model_key,null)
await db.close()
console.log('PASS: local migration, five keys, replay/conflict, gates, RLS, RPC/direct-write tampering, lifecycle and historical metadata')

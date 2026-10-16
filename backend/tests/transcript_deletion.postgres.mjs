// Isolated PostgreSQL-compatible database; never connects to Supabase.
// npm install --prefix tmp/transcript-delete-db @electric-sql/pglite --no-save --package-lock=false
// node backend/tests/transcript_deletion.postgres.mjs
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { PGlite } from '../../tmp/transcript-delete-db/node_modules/@electric-sql/pglite/dist/index.js'
const db = new PGlite()
const owner='00000000-0000-4000-8000-000000000001', other='00000000-0000-4000-8000-000000000002'
const selected='30000000-0000-4000-8000-000000000001', second='30000000-0000-4000-8000-000000000002'
await db.exec(`
  create role anon; create role authenticated; create role service_role bypassrls;
  create schema auth; create schema extensions;
  create function extensions.gen_random_uuid() returns uuid language sql as 'select gen_random_uuid()';
  create function auth.uid() returns uuid language sql as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
  create table auth.users(id uuid primary key);
  create table public.interview_sessions(id uuid primary key,user_id uuid references auth.users(id),status text,ended_at timestamptz,title text);
  grant usage on schema auth to authenticated;
  grant select on public.interview_sessions to authenticated;
  create table public.interview_session_ai_notes(session_id uuid references public.interview_sessions(id),notes_markdown text);
  create table public.interview_session_ask_ai_messages(session_id uuid references public.interview_sessions(id),message_text text);
  insert into auth.users values ('${owner}'),('${other}');
  insert into public.interview_sessions values ('${selected}','${owner}','active',null,'Preserved session'),('${second}','${owner}','active',null,'Other session');
`)
for(const name of ['20260829103000_add_interview_session_transcript_storage.sql','20260829170000_lock_down_transcript_entry_inserts.sql','20261011120000_add_permanent_transcript_deletion.sql']) {
  const sql = await readFile(new URL(`../../supabase/migrations/${name}`,import.meta.url),'utf8')
  // Match the migration runner: it owns the transaction, not the SQL file.
  if (name.startsWith('20261011120000')) assert.doesNotMatch(sql, /^\s*(?:begin|commit)\s*;/im)
  await db.transaction(tx => tx.exec(sql))
}
const create=id=>db.query(`select * from public.create_interview_session_transcript_entry($1,$2,'retry-1','chat','Saved question','Saved answer',null,null,null,null,'{}')`,[owner,id])
const clear=(user=owner,id=selected)=>db.query('select public.delete_interview_session_transcript_entries($1,$2) as count',[user,id])
await create(selected);await create(second)
await db.exec(`insert into public.interview_session_ai_notes values ('${selected}','Retained notes');insert into public.interview_session_ask_ai_messages values ('${selected}','Retained conversation');`)
await assert.rejects(clear(),/five minutes/)
await db.exec(`update public.interview_sessions set status='ended',ended_at=clock_timestamp()-interval '4 minutes' where id='${selected}'`)
await assert.rejects(clear(),/five minutes/)
await assert.rejects(clear(other),/not found/)
await db.exec(`update public.interview_sessions set ended_at=clock_timestamp()-interval '6 minutes' where id='${selected}'`)
const before=(await db.query('select * from public.interview_sessions order by id')).rows
assert.equal((await clear()).rows[0].count,1)
assert.equal((await clear()).rows[0].count,0)
await assert.rejects(create(selected),/closed/)
assert.deepEqual((await db.query('select * from public.interview_sessions order by id')).rows,before)
assert.equal((await db.query('select * from public.interview_session_ai_notes')).rows[0].notes_markdown,'Retained notes')
assert.equal((await db.query('select * from public.interview_session_ask_ai_messages')).rows[0].message_text,'Retained conversation')
assert.equal((await db.query('select session_id from public.interview_session_transcript_entries')).rows[0].session_id,second)
for(const role of ['anon','authenticated']) {
  await db.exec(`set role ${role}`)
  await assert.rejects(clear(),/permission denied/)
  await db.exec('reset role')
}
await db.exec(`set role authenticated;select set_config('request.jwt.claim.sub','${owner}',false)`)
assert.equal((await db.query('select * from public.interview_session_transcript_entries where session_id=$1',[selected])).rows.length,0)
assert.equal((await db.query('select * from public.interview_session_transcript_entries')).rows.length,1)
await assert.rejects(db.query('delete from public.interview_session_transcript_entries'),/permission denied/)
await db.exec(`select set_config('request.jwt.claim.sub','${other}',false)`)
assert.equal((await db.query('select * from public.interview_session_transcript_entries')).rows.length,0)
await db.exec('reset role')
// A transaction begun inside the grace window cannot insert after its deadline.
await db.transaction(async tx=>{
  await tx.exec(`update public.interview_sessions set status='ended',ended_at=now()-interval '5 minutes'+interval '100 milliseconds' where id='${second}'`)
  await new Promise(resolve=>setTimeout(resolve,200))
  await assert.rejects(tx.query(`select * from public.create_interview_session_transcript_entry($1,$2,'late-retry','chat','Question','Answer',null,null,null,null,'{}')`,[owner,second]),/closed/)
})
await db.close()
console.log('PASS: ownership, active/grace restrictions, repeat deletion, stale write fence, retained session/notes/chat, other session, restricted RPC grants.')

// C11.2C real SQL in an in-memory PostgreSQL WASM instance. No URLs or keys.
// Optional --pg-bin PATH creates its OWN native cluster for multi-session tests.
// It never accepts a connection URL or attaches to an existing database.
import assert from 'node:assert/strict'
import { spawn, spawnSync } from 'node:child_process'
import { access, mkdtemp, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'node:net'
import { PGlite } from '@electric-sql/pglite'

const root = fileURLToPath(new URL('../../', import.meta.url))
const args = process.argv.slice(2)
const option = name => {
  const index = args.indexOf(name)
  return index < 0 ? null : args[index + 1]
}
assert(args.every((a, i) => i % 2 ? true : ['--python', '--pg-bin'].includes(a)), 'unknown arguments')
assert.equal(args.length % 2, 0, 'options need explicit values')
const python = option('--python') ?? 'python'
const fixtureRun = spawnSync(python, ['-c', `
import json, runpy, sys
sys.path.insert(0, 'backend')
from app.commercial import catalog_contract as c
test = runpy.run_path('backend/tests/test_catalog_contract.py')
raw = test['document']()
raw['state'] = 'draft'
draft = c.CatalogDraft.model_validate(raw)
preview = dict(raw, state='previewed')
snapshot = c.create_snapshot(preview, offer_version_id=test['OFFER'], version=1)
print(json.dumps(dict(draft=draft.model_dump(mode='json'), canonical=snapshot.canonical_json(), fingerprint=snapshot.fingerprint)))
`], { cwd: root, encoding: 'utf8', windowsHide: true })
assert.equal(fixtureRun.status, 0, 'configured Python/Pydantic fixture generation failed: ' + fixtureRun.stderr)
const fixture = JSON.parse(fixtureRun.stdout)
const quote = value => value == null ? 'null' : `'${String(value).replaceAll("'", "''")}'`
const json = value => `${quote(JSON.stringify(value))}::jsonb`
const plan = fixture.draft.plan.plan_id, draft = fixture.draft.draft_id
const offer = JSON.parse(fixture.canonical).offer_version_id
const price = JSON.parse(fixture.canonical).terms.prices[0].price_id
const manager = '10000000-0000-4000-8000-000000000001'
const ordinary = '10000000-0000-4000-8000-000000000002'
const mutation = (revision, document, reason = 'synthetic edit') =>
  `select public.catalog_save_draft(${quote(draft)},${quote(plan)},${revision},${json(document)},${quote(reason)})`
const actor = id => `set session authorization authenticator; set role authenticated;
  select set_config('request.jwt.claim.sub',${quote(id)},false);`
let reset = 'reset session authorization; reset role;'
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

let db, directory, pgArgs, pgEnv, serverMayExist = false
const pgBin = option('--pg-bin')
const binary = name => join(resolve(pgBin), name + (process.platform === 'win32' ? '.exe' : ''))
const pg = (name, arguments_, input) => {
  const run = spawnSync(binary(name), arguments_, { input, encoding: 'utf8', env: pgEnv, windowsHide: true, timeout: 30000 })
  if (run.status !== 0) throw new Error(`${name} failed: ${run.stderr || run.error?.message}`)
  return run.stdout
}
let groups = 0
const passed = message => { groups++; console.log('PASS:', message) }
try {
  if (pgBin) {
    // Some portable server packages omit psql: fail before creating a cluster.
    for (const name of ['initdb','pg_ctl','psql']) await access(binary(name))
    // No inherited libpq connection/auth settings, and no existing data directory.
    pgEnv = {
      ...Object.fromEntries(Object.entries(process.env).filter(([key]) => !/^PG/i.test(key))),
      PGOPTIONS: '-c lock_timeout=10000 -c statement_timeout=15000 -c idle_in_transaction_session_timeout=20000',
      PGCONNECT_TIMEOUT: '5',
    }
    directory = await mkdtemp(join(tmpdir(), 'c112c-disposable-'))
    const socket = createServer()
    await new Promise(resolve => socket.listen(0, '127.0.0.1', resolve))
    const port = socket.address().port
    await new Promise(resolve => socket.close(resolve))
    pg('initdb', ['-D', join(directory, 'data'), '-U', 'catalog_test_owner', '-A', 'trust', '--no-locale', '-E', 'UTF8'])
    serverMayExist = true
    pg('pg_ctl', ['-D', join(directory, 'data'), '-l', join(directory, 'server.log'), '-o', `-h 127.0.0.1 -p ${port}`, '-w', 'start'])
    pgArgs = ['-X', '-q', '-A', '-t', '-v', 'ON_ERROR_STOP=1', '-h', '127.0.0.1', '-p', String(port), '-U', 'catalog_test_owner', '-d', 'postgres']
    // Each exec/query is an independent native connection. Multi-statement SQL
    // maintains session identity only within its single invocation.
    db = {
      exec: async sql => pg('psql', pgArgs, sql),
      query: async sql => ({ rows: JSON.parse(pg('psql', pgArgs, `select coalesce(json_agg(q),'[]') from (${sql}) q;`)) }),
    }
  } else db = new PGlite()
  const rows = async sql => (await db.query(sql)).rows
  const denied = async (sql, pattern = /permission denied|denied|immutable|conflict|constraint|mismatch|must|invalid|unsupported|out of range/i) => {
    await assert.rejects(db.exec(sql), pattern)
    // A failed statement may leave a role/transaction active on PGlite.
    await db.exec(`rollback; ${reset}`)
  }
  const maintenance = (await rows('select session_user as name'))[0].name
  reset = `set session authorization "${maintenance.replaceAll('"','""')}"; reset role;`
  console.log('Database:', await rows('select version() as version'))
  await db.exec(`
    create role anon; create role authenticated; create role service_role bypassrls;
    create role authenticator login noinherit; create role direct_login login noinherit;
    grant anon,authenticated,service_role to authenticator;
    grant authenticated to direct_login;
    create schema auth; create table auth.users(id uuid primary key);
    create function auth.uid() returns uuid language sql stable as
      $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
    grant usage on schema auth,public to anon,authenticated,service_role;
    -- Simulate Supabase's permissive defaults: migration must revoke these.
    alter default privileges in schema public grant all on tables to anon,authenticated,service_role;
    alter default privileges in schema public grant execute on functions to anon,authenticated,service_role;
    insert into auth.users values (${quote(manager)}),(${quote(ordinary)});
  `)
  await db.exec(await readFile(new URL('../../supabase/migrations/20261022120000_catalog_storage_foundation.sql', import.meta.url), 'utf8'))
  assert.equal((await rows(`select count(*)::int as n from public.catalog_plans`))[0].n, 0)
  assert.equal((await rows(`select count(*)::int as n from public.subscription_admin_permissions`))[0].n, 0)
  passed('migration applied on isolated synthetic Supabase-role baseline; no subjects/offers seeded')

  const tables = ['subscription_admin_permissions','catalog_plans','catalog_drafts','catalog_draft_revisions',
    'catalog_offer_versions','catalog_price_versions','catalog_visibility','catalog_admin_actions']
  for (const table of tables) for (const role of ['anon','authenticated','service_role']) {
    await denied(`set role ${role}; select * from public.${table};`)
    await denied(`set role ${role}; insert into public.${table} default values;`)
    for (const privilege of ['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER']) {
      assert.equal((await rows(`select has_table_privilege('${role}','public.${table}','${privilege}') as allowed`))[0].allowed, false)
    }
  }
  const routines = await rows(`select p.oid::regprocedure::text as signature,p.prosecdef,p.proconfig
    from pg_proc p where p.pronamespace='public'::regnamespace and p.proname like 'catalog_%'`)
  assert.equal(routines.length, 11)
  assert.equal((await rows(`select count(*)::int as n from pg_class where relnamespace='public'::regnamespace
    and relname in (${tables.map(quote).join(',')}) and relrowsecurity and relforcerowsecurity`))[0].n, 8)
  assert.equal((await rows(`select count(*)::int as n from pg_proc where pronamespace='public'::regnamespace
    and proname like 'catalog_%' and pg_get_userbyid(proowner)<>${quote(maintenance)}`))[0].n, 0)
  for (const routine of routines) {
    assert.deepEqual(routine.proconfig, ['search_path=pg_catalog'])
    for (const role of ['anon','authenticated','service_role']) {
      assert.equal((await rows(`select has_function_privilege('${role}',${quote(routine.signature)},'EXECUTE') as allowed`))[0].allowed, false)
    }
  }
  await denied(`${actor(manager)} ${mutation(0,fixture.draft)}`)
  await denied(`set role service_role; select public.catalog_locked_actor();`)
  await denied(`${actor(ordinary)} insert into public.subscription_admin_permissions values (${quote(ordinary)},'subscriptions.manage',1,true,${quote(ordinary)},'self promote');`)
  passed('all table/function privileges closed including service_role; no self promotion or private reads')

  await db.exec(`insert into public.catalog_plans values (${quote(plan)},'synthetic-test');
    insert into public.subscription_admin_permissions values (${quote(manager)},'subscriptions.manage',1,true,${quote(manager)},'synthetic maintenance only');`)
  // Isolated verification grants ONLY. Never part of the shipped migration.
  // Exercise the actual permission function, not a replacement/mock resolver.
  await db.exec(`grant execute on function public.catalog_save_draft(uuid,uuid,bigint,jsonb,text),public.catalog_retire_offer(uuid,bigint,text) to authenticated;`)
  await denied(`${actor(ordinary)} ${mutation(0,fixture.draft)}`)
  await denied(`set session authorization direct_login; set role authenticated;
    select set_config('request.jwt.claim.sub',${quote(manager)},false); ${mutation(0,fixture.draft)}`)
  await denied(`set role service_role; select set_config('request.jwt.claim.sub',${quote(manager)},false); ${mutation(0,fixture.draft)}`)
  await denied(`${actor(manager)} ${mutation(0,fixture.draft, '')}`)
  assert.equal((await rows('select count(*)::int as n from public.catalog_drafts'))[0].n, 0)
  assert.equal((await rows('select count(*)::int as n from public.catalog_draft_revisions'))[0].n, 0)
  assert.equal((await rows('select count(*)::int as n from public.catalog_admin_actions'))[0].n, 1)
  await db.exec(`${actor(manager)} ${mutation(0,fixture.draft)}; ${reset}`)
  assert.equal((await rows("select actor_subject,permission_revision::text as revision from public.catalog_admin_actions where operation='draft.create'"))[0].actor_subject, manager)
  const edited = structuredClone(fixture.draft)
  edited.revision = '2'; edited.internal_notes = 'synthetic new revision'
  await db.exec(`${actor(manager)} select set_config('request.jwt.claim.actor',${quote(ordinary)},false);
    ${mutation(1,edited)}; ${reset}`)
  assert.equal((await rows("select actor_subject from public.catalog_admin_actions where operation='draft.edit'"))[0].actor_subject, manager)
  await denied(`${actor(manager)} ${mutation(1,edited)}`)
  assert.equal((await rows('select count(*)::int as n from public.catalog_draft_revisions'))[0].n, 2)
  const rolledBack = structuredClone(edited); rolledBack.revision = '3'
  const auditBefore = await rows('select count(*)::int as n from public.catalog_admin_actions')
  await denied(`begin; ${actor(manager)} ${mutation(2,rolledBack)}; select 1/0; commit;`, /division by zero/)
  assert.equal((await rows('select revision::text as revision from public.catalog_drafts'))[0].revision, '2')
  assert.deepEqual(await rows('select count(*)::int as n from public.catalog_admin_actions'), auditBefore)
  passed('real permission checks, forged direct-SQL identity denial, audit rollback, sequential CAS/history')

  // Separate native connections when --pg-bin is supplied. WASM uses one backend
  // and can establish immediate rechecking only, not cross-worker lock semantics.
  await db.exec(`update public.subscription_admin_permissions set active=false,revision=2,reason='synthetic revoke' where subject_id=${quote(manager)};`)
  const third = structuredClone(edited); third.revision = '3'
  await denied(`${actor(manager)} ${mutation(2,third)}`)
  await db.exec(`update public.subscription_admin_permissions set active=true,revision=3,reason='synthetic regrant' where subject_id=${quote(manager)};`)
  await denied(`update public.subscription_admin_permissions set active=false where subject_id=${quote(manager)};`)
  passed(pgBin ? 'revocation observed from a new independent connection; revision enforced' : 'same-backend revocation rechecked; independent-connection proof still required')

  const saveOffer = (canonical, fingerprint = null, id = offer, version = 1, revision = 1) =>
    `insert into public.catalog_offer_versions values (${quote(id)},${quote(plan)},${version},${quote(draft)},${revision},${quote(canonical)},${quote(fingerprint)});`
  await denied(saveOffer(fixture.canonical, 'a'.repeat(64)))
  await db.exec(saveOffer(fixture.canonical))
  assert.equal((await rows('select fingerprint from public.catalog_offer_versions'))[0].fingerprint, fixture.fingerprint)
  assert.deepEqual((await rows('select canonical_json from public.catalog_offer_versions'))[0].canonical_json, fixture.canonical)
  assert.equal((await rows('select count(*)::int as n from public.catalog_price_versions'))[0].n, 1)
  assert.equal((await rows('select state from public.catalog_visibility'))[0].state, 'hidden')
  for (const role of ['anon','authenticated','service_role']) {
    for (const statement of [
      `update public.catalog_offer_versions set fingerprint='${'a'.repeat(64)}'`,
      'delete from public.catalog_offer_versions',
      'delete from public.catalog_plans',
      'truncate public.catalog_plans cascade',
      `update public.catalog_price_versions set document=document||'{"amount_minor":"1"}'::jsonb`,
      'delete from public.catalog_price_versions',
      `insert into public.catalog_price_versions(price_id,offer_version_id,document) values (${quote(price)},${quote(offer)},${json(JSON.parse(fixture.canonical).terms.prices[0])}) on conflict(price_id) do update set document=excluded.document`,
      `${saveOffer(fixture.canonical).slice(0,-1)} on conflict(offer_version_id) do update set fingerprint=excluded.fingerprint`,
      'update public.subscription_admin_permissions set active=true,revision=revision+1',
    ]) await denied(`set role ${role}; ${statement};`, /permission denied/)
  }
  for (const table of ['catalog_plans','catalog_draft_revisions','catalog_offer_versions','catalog_price_versions','catalog_admin_actions']) {
    await denied(`delete from public.${table};`)
    await denied(`truncate public.${table} cascade;`)
  }
  await denied('delete from public.catalog_drafts;')
  await denied(`update public.catalog_plans set code='changed';`)
  await denied(`update public.catalog_offer_versions set canonical_json='{}';`)
  await denied(`update public.catalog_price_versions set document=document||'{"amount_minor":"1"}'::jsonb;`)
  await denied(`update public.catalog_draft_revisions set document='{}';`)
  await denied(`update public.catalog_admin_actions set reason='changed';`)
  await denied(`insert into public.catalog_plans values (${quote(plan)},'changed') on conflict(plan_id) do update set code=excluded.code;`)
  await denied(`${saveOffer(fixture.canonical).slice(0,-1)} on conflict(offer_version_id) do update set fingerprint=excluded.fingerprint;`)
  const priceDoc = JSON.parse(fixture.canonical).terms.prices[0]
  await denied(`insert into public.catalog_price_versions(price_id,offer_version_id,document) values (${quote(price)},${quote(offer)},${json(priceDoc)}) on conflict(price_id) do update set document=excluded.document;`)
  await denied(`update public.catalog_visibility set state='visible',revision=2,valid_from=now();`)
  passed('canonical B byte/hash compatibility; automatic price children; immutable parent/history/child/upsert/truncate guards')

  const beforeTerms = await rows('select canonical_json,fingerprint from public.catalog_offer_versions')
  await denied(`${actor(manager)} select public.catalog_retire_offer(${quote(offer)},1,'');`)
  assert.equal((await rows('select state from public.catalog_visibility'))[0].state, 'hidden')
  await db.exec(`${actor(manager)} select public.catalog_retire_offer(${quote(offer)},1,'synthetic retire'); ${reset}`)
  await denied(`${actor(manager)} select public.catalog_retire_offer(${quote(offer)},1,'stale');`)
  assert.deepEqual(await rows('select canonical_json,fingerprint from public.catalog_offer_versions'), beforeTerms)
  assert.equal((await rows('select state from public.catalog_visibility'))[0].state, 'retired')
  passed('retirement/audit atomicity and historical terms unchanged')

  // Invalid new version must fail atomically, including auto-created prices.
  const nextId = '20000000-0000-4000-8000-000000000009'
  const invalidSnapshot = (change, sourceRevision = 2) => {
    const value = JSON.parse(fixture.canonical); value.offer_version_id = nextId; value.version = '2'
    value.terms.prices[0].price_id = '20000000-0000-4000-8000-000000000008'
    change(value)
    return saveOffer(JSON.stringify(value), null, nextId, 2, sourceRevision)
  }
  for (const amount of ['-1','1.5','9223372036854775808']) {
    await denied(invalidSnapshot(value => { value.terms.prices[0].amount_minor = amount }))
  }
  await denied(invalidSnapshot(value => { value.terms.prices[0].billing.count = '0' }))
  await denied(invalidSnapshot(value => { value.terms.prices[0].currency = 'EUR' }))
  await denied(invalidSnapshot(value => { value.terms.prices[0].exponent = '0' }))
  await denied(invalidSnapshot(() => {}, 999))
  await denied(invalidSnapshot(value => { value.plan.code = 'forged' }))
  await denied(invalidSnapshot(value => { value.terms.prices.push(structuredClone(value.terms.prices[0])) }))
  await denied(`insert into public.catalog_price_versions(price_id,offer_version_id,document) values ('20000000-0000-4000-8000-000000000007',${quote(offer)},${json({...priceDoc,amount_minor:'2'})});`)
  assert.equal((await rows('select count(*)::int as n from public.catalog_offer_versions'))[0].n, 1)
  assert.equal((await rows('select count(*)::int as n from public.catalog_price_versions'))[0].n, 1)
  assert.equal((await rows('select count(*)::int as n from public.catalog_visibility'))[0].n, 1)
  passed('invalid FK/numeric/currency/duplicate children rejected without partial rows')

  // BYPASSRLS still requires SQL privileges. Prove the distinction in rollback.
  await db.exec(`begin; grant select on public.catalog_plans to service_role; set role service_role;
    do $$begin if (select count(*) from public.catalog_plans)<>1 then raise exception 'bypass proof failed'; end if; end$$;
    reset role; rollback;`)
  await denied('set role service_role; select * from public.catalog_plans;')
  for (const role of ['anon','authenticated']) {
    await db.exec(`begin; grant select on public.catalog_plans to ${role}; set role ${role};
      do $$begin if (select count(*) from public.catalog_plans)<>0 then raise exception 'RLS leaked rows'; end if; end$$;
      reset role; rollback;`)
  }
  passed('service_role BYPASSRLS explicitly verified; privilege denial, not RLS, closes it')

  if (pgBin) {
    const children = new Set()
    const start = (sql, application, hold = false) => {
      const child = spawn(binary('psql'), pgArgs, { env: { ...pgEnv, PGAPPNAME: application }, windowsHide: true })
      children.add(child)
      let stderr = '', stdout = '', readySeen = false, resolveReady, rejectReady
      const ready = new Promise((resolve,reject) => { resolveReady=resolve; rejectReady=reject })
      // One-shot processes need no readiness barrier; still handle early errors.
      ready.catch(() => {})
      child.stderr.on('data', chunk => { stderr += chunk })
      child.stdout.on('data', chunk => {
        stdout += chunk
        if (stdout.includes('C112C_READY')) { readySeen=true; resolveReady() }
      })
      child.stdin.on('error', () => {})
      const timer = setTimeout(() => child.kill(), 25000)
      const done = new Promise(resolve => {
        child.on('error', error => { stderr+=error.message; rejectReady(error) })
        child.on('close', code => {
          clearTimeout(timer); children.delete(child)
          if (!readySeen) rejectReady(new Error(`session ended before barrier: ${stderr}`))
          resolve({code,stderr})
        })
      })
      if (hold) child.stdin.write(`${sql}\n\\echo C112C_READY\n`)
      else child.stdin.end(sql)
      return { ready, done, commit: () => child.stdin.end('commit;\n') }
    }
    const waitForBlocked = async (waiter, holder) => {
      const deadline = performance.now()+8000
      while (performance.now()<deadline) {
        const blocked = await rows(`select w.pid as waiter,h.pid as holder from pg_stat_activity w,pg_stat_activity h
          where w.application_name=${quote(waiter)} and h.application_name=${quote(holder)}
          and w.pid<>h.pid and h.pid=any(pg_blocking_pids(w.pid)) and w.wait_event_type='Lock'`)
        if (blocked.length) return
        // Poll an observed lock relationship; no delay creates the race ordering.
        await sleep(20)
      }
      throw new Error(`native lock barrier not reached: ${waiter} blocked by ${holder}`)
    }
    try {
      const beforeCas = (await rows('select count(*)::int as n from public.catalog_admin_actions'))[0].n
      const a = start(`begin; ${actor(manager)} ${mutation(2,third)};`, 'c112c-edit-a', true)
      await a.ready
      const b = start(`${actor(manager)} ${mutation(2,{...third,internal_notes:'losing edit must not persist'})};`, 'c112c-edit-b')
      await waitForBlocked('c112c-edit-b', 'c112c-edit-a')
      a.commit()
      assert.equal((await a.done).code, 0)
      const loser = await b.done
      assert.notEqual(loser.code, 0); assert.match(loser.stderr,/revision conflict/)
      assert.deepEqual((await rows('select document from public.catalog_drafts'))[0].document, third)
      assert.equal((await rows('select count(*)::int as n from public.catalog_draft_revisions'))[0].n, 3)
      assert.equal((await rows('select count(*)::int as n from public.catalog_admin_actions'))[0].n, beforeCas+1)
      passed('independent native CAS: observed lock barrier, one winner, loser leaves no data/history/audit')
      const fourth = {...third,revision:'4'}
      const writer = start(`begin; ${actor(manager)} ${mutation(3,fourth)};`, 'c112c-write-before-revoke', true)
      await writer.ready
      const revoke = start(`update public.subscription_admin_permissions set active=false,revision=4,reason='native revoke' where subject_id=${quote(manager)};`, 'c112c-revoke')
      await waitForBlocked('c112c-revoke', 'c112c-write-before-revoke')
      writer.commit()
      assert.equal((await writer.done).code, 0); assert.equal((await revoke.done).code, 0)
      const beforeDenied = await rows('select count(*)::int as n from public.catalog_admin_actions')
      await denied(`${actor(manager)} ${mutation(4,{...fourth,revision:'5'})}`)
      assert.deepEqual(await rows('select count(*)::int as n from public.catalog_admin_actions'), beforeDenied)
      passed('native writer-first ordering: revoke blocks until admitted write commits; new connection denied afterwards')
      await db.exec(`update public.subscription_admin_permissions set active=true,revision=5,reason='native race setup' where subject_id=${quote(manager)};`)
      const revokeFirst = start(`begin; update public.subscription_admin_permissions set active=false,revision=6,reason='native revoke first' where subject_id=${quote(manager)};`, 'c112c-revoke-first', true)
      await revokeFirst.ready
      const beforeStale = await rows('select count(*)::int as n from public.catalog_admin_actions')
      const staleWorker = start(`${actor(manager)} ${mutation(4,{...fourth,revision:'5'})};`, 'c112c-stale-worker')
      await waitForBlocked('c112c-stale-worker', 'c112c-revoke-first')
      revokeFirst.commit()
      assert.equal((await revokeFirst.done).code, 0)
      const rejectedWorker = await staleWorker.done
      assert.notEqual(rejectedWorker.code, 0); assert.match(rejectedWorker.stderr,/permission denied/)
      assert.equal((await rows('select revision::text as revision from public.catalog_drafts'))[0].revision, '4')
      assert.equal((await rows('select count(*)::int as n from public.catalog_draft_revisions'))[0].n, 4)
      assert.equal((await rows('select count(*)::int as n from public.catalog_admin_actions'))[0].n, beforeStale[0].n+1)
      assert.equal((await rows("select count(*)::int as n from public.catalog_admin_actions where operation='draft.edit' and actor_subject<>"+quote(manager)))[0].n, 0)
      passed('native revoke-first ordering: stale worker waits, then denies; no partial revision/audit or forged actor')
    } finally {
      const closed = [...children].map(child => new Promise(resolve => child.once('close', resolve)))
      for (const child of children) child.kill()
      await Promise.all(closed)
    }
  } else console.log('BLOCKED: independent-connection CAS/revocation races require native initdb/pg_ctl/psql; PGlite is single-backend.')

  // Undo verification grants; assert final function access matches shipped SQL.
  await db.exec('revoke execute on function public.catalog_save_draft(uuid,uuid,bigint,jsonb,text),public.catalog_retire_offer(uuid,bigint,text) from authenticated;')
  await denied(`${actor(manager)} ${mutation(2,third)}`)
  passed('isolated grants removed; shipped application mutation boundary remains closed')
  console.log(`${groups} SQL verification groups passed; production publication is not implemented.`)
} finally {
  if (pgBin && directory) {
    // Retain the directory if shutdown fails; never erase a possibly running DB.
    if (serverMayExist) pg('pg_ctl', ['-D',join(directory,'data'),'-m','fast','-w','stop'])
    // Only the exact fresh mkdtemp directory created by this process is removed.
    assert(resolve(directory).startsWith(resolve(tmpdir()) + '\\') || resolve(directory).startsWith(resolve(tmpdir()) + '/'))
    await rm(directory, { recursive:true, force:true })
  } else if (db) await db.close()
}

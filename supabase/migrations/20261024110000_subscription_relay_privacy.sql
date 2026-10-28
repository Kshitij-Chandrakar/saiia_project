-- Closed hosted coordination and reversible deletion barrier. No LOGIN/activation.
begin;
create table public.subscription_relay_frames (
 run_id uuid primary key references public.subscription_auto_runs(run_id) on delete restrict,
 account_id uuid not null references auth.users(id) on delete restrict,
 session_id uuid not null references public.interview_sessions(id) on delete restrict,
 source text not null check(source in ('microphone','system','both')),
 last_sequence bigint not null default 0,
 last_hash text,
 bytes_received bigint not null default 0,
 created_at timestamptz not null default clock_timestamp()
);
create table public.subscription_auth_handoffs (
 code_hash text primary key check(code_hash ~ '^[0-9a-f]{64}$'),
 account_id uuid not null references auth.users(id) on delete restrict,
 state_hash text not null check(state_hash ~ '^[0-9a-f]{64}$'),
 ciphertext text not null check(length(ciphertext) between 1 and 50000),
 created_at timestamptz not null default clock_timestamp(),
 expires_at timestamptz not null
);
create table public.subscription_deletion_jobs (
 account_id uuid primary key references auth.users(id) on delete restrict,
 request_id uuid not null unique,
 phase text not null default 'quiescing' check(phase in ('quiescing','policy_pending')),
 revision bigint not null default 1,
 created_at timestamptz not null default clock_timestamp()
);
create table public.subscription_handoff_limits (
 account_id uuid primary key references auth.users(id) on delete restrict,
 last_created_at timestamptz not null
);
alter table public.subscription_relay_frames enable row level security;
alter table public.subscription_relay_frames force row level security;
alter table public.subscription_auth_handoffs enable row level security;
alter table public.subscription_auth_handoffs force row level security;
alter table public.subscription_deletion_jobs enable row level security;
alter table public.subscription_deletion_jobs force row level security;
alter table public.subscription_handoff_limits enable row level security;
alter table public.subscription_handoff_limits force row level security;
revoke all on public.subscription_relay_frames,public.subscription_auth_handoffs,public.subscription_deletion_jobs from public,anon,authenticated,service_role,usage_executor,catalog_draft_executor,usage_binding_executor,usage_reconciler;
revoke all on public.subscription_handoff_limits from public,anon,authenticated,service_role,usage_executor,catalog_draft_executor,usage_binding_executor,usage_reconciler;

create function public.subscription_access_check(p_account uuid) returns boolean
language plpgsql security definer set search_path=pg_catalog as $$
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 -- Same Auth-row ordering as subscription_current; no new account lock ordering.
 perform 1 from auth.users where id=p_account for no key update;
 if exists(select 1 from public.subscription_deletion_jobs where account_id=p_account) then raise exception 'access denied' using errcode='42501'; end if;
 return true;
end $$;

-- Preserve OIDs: renaming an old function would leave cached callers able to
-- invoke its unguarded body. Add the guard to the existing authoritative bodies.
do $$
declare signature text; body text;
begin
 foreach signature in array array['public.subscription_current(uuid,boolean)','public.usage_account_read(uuid)'] loop
  body:=pg_get_functiondef(signature::regprocedure);
  if body not like '%subscription_access_check%' then
   body:=regexp_replace(body,'\mbegin\M',E'begin\n perform public.subscription_access_check(p_account);','i');
   execute body;
  end if;
 end loop;
end $$;

create function public.subscription_relay_frame(p_account uuid,p_run uuid,p_owner uuid,p_fence bigint,p_session uuid,p_source text,p_sequence bigint,p_hash text,p_bytes integer) returns boolean
language plpgsql security definer set search_path=pg_catalog as $$
declare r public.subscription_relay_frames; at_time timestamptz;
begin
 perform public.subscription_auto_authorize(p_account,p_run,p_owner,p_fence,p_source);
 perform public.subscription_session_read(p_account,p_session);
 if p_sequence<1 or p_sequence>9007199254740991 or p_hash !~ '^[0-9a-f]{64}$' or p_bytes not between 2 and 6400 or p_bytes%2<>0 then raise exception 'invalid frame' using errcode='22023'; end if;
 insert into public.subscription_relay_frames(run_id,account_id,session_id,source) values(p_run,p_account,p_session,p_source) on conflict do nothing;
 select * into strict r from public.subscription_relay_frames where run_id=p_run for update;
 if (r.account_id,r.session_id,r.source) is distinct from (p_account,p_session,p_source) then raise exception 'stream conflict' using errcode='P0003'; end if;
 if p_sequence=r.last_sequence and p_hash=r.last_hash then return false; end if;
 if p_sequence<>r.last_sequence+1 then raise exception 'frame conflict' using errcode='P0003'; end if;
 at_time:=clock_timestamp();
 -- At most 200ms PCM per frame; 200ms initial burst, then real-time throughput.
 if r.bytes_received+p_bytes>6400+floor(extract(epoch from at_time-r.created_at)*32000) then raise exception 'audio rate exceeded' using errcode='22023'; end if;
 update public.subscription_relay_frames set last_sequence=p_sequence,last_hash=p_hash,bytes_received=bytes_received+p_bytes where run_id=p_run;
 return true;
end $$;

create function public.subscription_handoff(p_action text,p_account uuid,p_code text,p_state text,p_ciphertext text default null) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare r public.subscription_auth_handoffs; at_time timestamptz:=clock_timestamp();
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 if p_code !~ '^[0-9a-f]{64}$' or p_state !~ '^[0-9a-f]{64}$' then raise exception 'invalid handoff' using errcode='22023'; end if;
 if p_action='create' then
  perform public.subscription_access_check(p_account);
  delete from public.subscription_auth_handoffs where account_id=p_account and expires_at<=at_time;
  if exists(select 1 from public.subscription_handoff_limits where account_id=p_account and last_created_at>at_time-interval '5 seconds') or
     (select count(*) from public.subscription_auth_handoffs where account_id=p_account)>=3 then raise exception 'handoff rate exceeded' using errcode='40001'; end if;
  insert into public.subscription_auth_handoffs values(p_code,p_account,p_state,p_ciphertext,at_time,at_time+interval '5 minutes');
  insert into public.subscription_handoff_limits values(p_account,at_time) on conflict(account_id) do update set last_created_at=excluded.last_created_at;
  return '{}'::jsonb;
 elsif p_action='exchange' then
  -- Find account without holding a handoff lock before the common Auth lock.
  select * into r from public.subscription_auth_handoffs where code_hash=p_code and state_hash=p_state and expires_at>at_time;
  if not found then raise exception 'handoff missing' using errcode='P0002'; end if;
  perform public.subscription_access_check(r.account_id);
  delete from public.subscription_auth_handoffs where code_hash=p_code and state_hash=p_state and expires_at>clock_timestamp() returning * into r;
  if not found then raise exception 'handoff missing' using errcode='P0002'; end if;
  return jsonb_build_object('account_id',r.account_id,'ciphertext',r.ciphertext);
 else raise exception 'invalid action' using errcode='22023'; end if;
end $$;

create function public.subscription_deletion_prepare(p_account uuid,p_request uuid) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare j public.subscription_deletion_jobs; r public.subscription_auto_runs;
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 perform 1 from auth.users where id=p_account for no key update;
 if not found then raise exception 'missing account' using errcode='P0002'; end if;
 perform 1 from public.account_plan_bindings where account_id=p_account for update;
 select * into j from public.subscription_deletion_jobs where account_id=p_account for update;
 if found and j.request_id<>p_request then raise exception 'request conflict' using errcode='P0003'; end if;
 if not found then
  insert into public.subscription_deletion_jobs(account_id,request_id) values(p_account,p_request) returning * into j;
  insert into public.usage_events(account_id,event,fence,actor_principal) select p_account,'privacy.prepare',revision,session_user from public.account_plan_bindings where account_id=p_account;
 end if;
 -- Closing capability works without granting terms access, including uncertain retries.
 for r in select * from public.subscription_auto_runs where account_id=p_account and active order by run_id for update loop
  perform public.subscription_auto_disconnect(p_account,r.run_id,r.owner_token,r.fence);
 end loop;
 delete from public.subscription_auth_handoffs where account_id=p_account;
 -- Never purge content/Auth/immutable ledgers without the reviewed retention contract.
 update public.subscription_deletion_jobs set phase='policy_pending',revision=case when phase='quiescing' then revision+1 else revision end where account_id=p_account returning * into j;
 return jsonb_build_object('request_id',j.request_id,'phase',j.phase,'revision',j.revision,'irreversible_enabled',false);
end $$;

revoke all on function public.subscription_access_check(uuid),public.subscription_current(uuid,boolean),public.subscription_relay_frame(uuid,uuid,uuid,bigint,uuid,text,bigint,text,integer),public.subscription_handoff(text,uuid,text,text,text),public.subscription_deletion_prepare(uuid,uuid) from public,anon,authenticated,service_role,usage_executor,usage_binding_executor,usage_reconciler,catalog_draft_executor;
grant execute on function public.subscription_access_check(uuid),public.subscription_current(uuid,boolean),public.subscription_relay_frame(uuid,uuid,uuid,bigint,uuid,text,bigint,text,integer),public.subscription_handoff(text,uuid,text,text,text),public.subscription_deletion_prepare(uuid,uuid) to usage_executor;

-- Block existing direct authenticated table/storage reads as well as application
-- APIs. Restrictive policies only intersect existing ownership policies; they
-- confer no SELECT/UPDATE/DELETE privilege and never defeat ledger immutability.
create function public.subscription_account_accessible() returns boolean
language sql stable security definer set search_path=pg_catalog as $$
 select auth.uid() is not null and not exists(
  select 1 from public.subscription_deletion_jobs where account_id=auth.uid())
$$;
revoke all on function public.subscription_account_accessible() from public,anon,service_role;
grant execute on function public.subscription_account_accessible() to authenticated;
do $$
declare target record;
begin
 for target in
  select distinct n.nspname,c.relname from pg_constraint f
  join pg_class c on c.oid=f.conrelid join pg_namespace n on n.oid=c.relnamespace
  where f.contype='f' and f.confrelid='auth.users'::regclass and n.nspname='public'
  union select 'storage','objects' where to_regclass('storage.objects') is not null
 loop
  execute format('create policy subscription_deletion_barrier on %I.%I as restrictive for all to authenticated using(public.subscription_account_accessible()) with check(public.subscription_account_accessible())',target.nspname,target.relname);
 end loop;
end $$;
commit;

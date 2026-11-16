-- Local additive candidate. No historical backfill, retirement, LOGIN or activation.
begin;
alter table public.subscription_auto_runs alter column owner_token drop not null;
alter table public.subscription_auto_runs add column owner_verifier bytea;
create function public.privacy_auto_owner(r public.subscription_auto_runs,p_owner uuid) returns boolean
language sql immutable set search_path=pg_catalog as $$
 select p_owner is not null and case when r.owner_verifier is not null then
 r.owner_verifier=sha256(convert_to(p_owner::text,'UTF8')) else r.owner_token=p_owner end is true
$$;
create function public.privacy_auto_new_credential() returns trigger language plpgsql set search_path=pg_catalog as $$
begin
 if new.owner_token is null then raise exception 'missing run credential' using errcode='22023'; end if;
 new.owner_verifier:=sha256(convert_to(new.owner_token::text,'UTF8'));
 new.owner_token:=null;
 return new;
end $$;
create trigger privacy_auto_credential_split before insert on public.subscription_auto_runs
for each row execute function public.privacy_auto_new_credential();

-- Checked substitutions retain authoritative OIDs, locking, fencing and ledger SQL.
do $$ declare d text; signature text; begin
 d:=pg_get_functiondef('public.subscription_auto_call(uuid,text,jsonb)'::regprocedure);
 if strpos(d,'declare b public.account_plan_bindings;')=0 or strpos(d,'values((p_doc->>''run_id'')::uuid,p_account,p_doc->>''request_id'',p_doc->>''semantic_hash'') returning * into r;')=0 or strpos(d,'if r.owner_token<>(p_doc->>''owner_token'')::uuid')=0 then raise exception 'unsupported Auto credential writer'; end if;
 d:=replace(d,'declare b public.account_plan_bindings;','declare wire_owner uuid; b public.account_plan_bindings;');
 d:=replace(d,'insert into public.subscription_auto_runs(run_id,account_id,request_id,semantic_hash)', 'wire_owner:=gen_random_uuid(); insert into public.subscription_auto_runs(run_id,account_id,request_id,semantic_hash,owner_token)');
 d:=replace(d,'values((p_doc->>''run_id'')::uuid,p_account,p_doc->>''request_id'',p_doc->>''semantic_hash'') returning * into r;', 'values((p_doc->>''run_id'')::uuid,p_account,p_doc->>''request_id'',p_doc->>''semantic_hash'',wire_owner) returning * into r;');
 d:=replace(d,'if r.owner_token<>(p_doc->>''owner_token'')::uuid','wire_owner:=(p_doc->>''owner_token'')::uuid; if not public.privacy_auto_owner(r,wire_owner)');
 d:=replace(d,'''owner_token'',r.owner_token','''owner_token'',wire_owner');
 execute d;
 foreach signature in array array['public.subscription_auto_authorize(uuid,uuid,uuid,bigint,text)','public.subscription_auto_disconnect(uuid,uuid,uuid,bigint)'] loop
  d:=pg_get_functiondef(signature::regprocedure);
  if strpos(d,'r.owner_token<>p_owner')=0 then raise exception 'unsupported credential consumer'; end if;
  execute replace(d,'r.owner_token<>p_owner','not public.privacy_auto_owner(r,p_owner)');
 end loop;
 d:=pg_get_functiondef('public.privacy_auto_payload_decode(public.privacy_auto_reply_payloads,public.subscription_auto_runs,bigint)'::regprocedure);
 if strpos(d,'(private.response->>''owner_token'')::uuid<>r.owner_token')=0 then raise exception 'unsupported replay consumer'; end if;
 execute replace(d,'(private.response->>''owner_token'')::uuid<>r.owner_token','not public.privacy_auto_owner(r,(private.response->>''owner_token'')::uuid)');
 -- Internal deletion already owns the subject and run locks. It must settle,
 -- not recover/reconstruct a caller capability from a one-way verifier.
 d:=pg_get_functiondef('public.subscription_deletion_prepare(uuid,uuid)'::regprocedure);
 if strpos(d,'perform public.subscription_auto_disconnect(p_account,r.run_id,r.owner_token,r.fence);')=0 then raise exception 'unsupported deletion settlement'; end if;
 execute replace(d,'perform public.subscription_auto_disconnect(p_account,r.run_id,r.owner_token,r.fence);',
 'perform public.subscription_auto_finish_slice(r.run_id,clock_timestamp()); update public.subscription_auto_runs set active=false,fence=fence+1 where run_id=r.run_id;');
end $$;

-- Separate NOLOGIN function owner, no role memberships and fixed capabilities.
create role privacy_payload_owner nologin nosuperuser nocreatedb nocreaterole noinherit;
create role privacy_cleanup_executor nologin nosuperuser nocreatedb nocreaterole noinherit;
grant usage on schema public to privacy_payload_owner,privacy_cleanup_executor;
grant select on public.privacy_content_jobs,public.privacy_deletion_requests,
 public.subscription_auto_runs,public.privacy_auto_reply_payloads to privacy_payload_owner;
grant update(lease_id) on public.privacy_content_jobs to privacy_payload_owner;
grant update(owner_token,owner_verifier) on public.subscription_auto_runs to privacy_payload_owner;
grant update(response,private_checksum,state,erasure_job) on public.privacy_auto_reply_payloads to privacy_payload_owner;
create policy privacy_payload_owner_jobs on public.privacy_content_jobs to privacy_payload_owner using(true) with check(true);
create policy privacy_payload_owner_requests on public.privacy_deletion_requests for select to privacy_payload_owner using(true);
create policy privacy_payload_owner_runs on public.subscription_auto_runs to privacy_payload_owner using(true) with check(true);
create policy privacy_payload_owner_payloads on public.privacy_auto_reply_payloads to privacy_payload_owner using(true) with check(true);
grant execute on function public.privacy_auto_payload_erase(uuid,uuid) to privacy_payload_owner;
create function public.privacy_auto_credentials_erase(p_job uuid,p_lease uuid) returns integer
language plpgsql security definer set search_path=pg_catalog as $$
declare account uuid; removed integer; begin
 if session_user<>'privacy_cleanup_executor' or current_setting('role',true)<>'none' then raise exception 'cleanup principal denied' using errcode='42501'; end if;
 select j.account_id into account from public.privacy_content_jobs j join public.privacy_deletion_requests r on r.request_id=j.id and r.account_id=j.account_id
 where j.id=p_job and j.kind='account' and j.lease_id=p_lease and j.state='running' and j.lease_until>clock_timestamp() and r.state='accepted_restricted' for update of j;
 if not found then raise exception 'stale cleanup scope' using errcode='40001'; end if;
 -- Account acceptance settles every active run before issuing this durable task.
 if exists(select 1 from public.subscription_auto_runs where account_id=account and active) then raise exception 'active credential still required' using errcode='55000'; end if;
 removed:=public.privacy_auto_payload_erase(p_job,p_lease);
 update public.subscription_auto_runs set owner_token=null,owner_verifier=null where account_id=account and not active;
 if exists(select 1 from public.subscription_auto_runs where account_id=account and (owner_token is not null or owner_verifier is not null)) or exists(select 1 from public.privacy_auto_reply_payloads where account_id=account and state='available') then raise exception 'credential absence unverified' using errcode='55000'; end if;
 return removed;
end $$;
alter function public.privacy_auto_credentials_erase(uuid,uuid) owner to privacy_payload_owner;
revoke all on function public.privacy_auto_credentials_erase(uuid,uuid),public.privacy_auto_owner(public.subscription_auto_runs,uuid),public.privacy_auto_new_credential() from public,anon,authenticated,service_role,usage_executor,privacy_preparation_executor;
grant execute on function public.privacy_auto_credentials_erase(uuid,uuid) to privacy_cleanup_executor;
-- No table grants, role memberships, arbitrary predicates or retirement privilege.
commit;

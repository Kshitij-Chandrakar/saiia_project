-- Local-only stage candidate. No activation, destructive scheduler or grants.
begin;
create table public.privacy_content_jobs (
 id uuid primary key,
 account_id uuid not null references auth.users(id) on delete restrict,
 kind text not null check(kind in ('export','session','history','account')),
 resource_id uuid,
 registry_version text not null,
 state text not null default 'pending' check(state in ('pending','running','ready','blocked','failed','primary_verified','expired')),
 revision bigint not null default 1,
 created_at timestamptz not null default clock_timestamp(),
 cutoff_at timestamptz,
 ready_at timestamptz,
 expires_at timestamptz,
 lease_id uuid,
 lease_until timestamptz,
 attempts integer not null default 0,
 retry_at timestamptz not null default clock_timestamp(),
 artifact_key text,
 capability_hash text,
 capability_expires_at timestamptz,
 progress jsonb not null default '{}',
 blockers jsonb not null default '[]',
 unique(account_id,id)
);
create unique index privacy_one_active_export on public.privacy_content_jobs(account_id)
 where kind='export' and state in ('pending','running','ready');
create table public.privacy_erased_sessions (
 account_id uuid not null references auth.users(id) on delete restrict,
 session_id uuid not null,
 job_id uuid not null references public.privacy_content_jobs(id) on delete restrict,
 primary key(account_id,session_id)
);
create table public.privacy_erased_session_keys (
 account_id uuid not null references auth.users(id) on delete restrict,
 key_version integer not null references public.privacy_matching_keys(version) on delete restrict,
 digest bytea not null,
 job_id uuid not null references public.privacy_content_jobs(id) on delete restrict,
 primary key(account_id,key_version,digest)
);
create table public.privacy_export_rows (
 job_id uuid not null references public.privacy_content_jobs(id) on delete cascade,
 ordinal bigint generated always as identity,
 category text not null,
 document jsonb not null,
 primary key(job_id,ordinal)
);
create table public.privacy_content_objects (
 job_id uuid not null references public.privacy_content_jobs(id) on delete restrict,
 bucket text not null check(bucket in ('resumes','exports')),
 object_key text not null,
 source_id uuid,
 original_name text,
 version text,
 state text not null default 'pending' check(state in ('pending','verified','blocked')),
 primary key(job_id,bucket,object_key)
);
create table public.privacy_export_proofs (
 request_id uuid primary key,
 account_id uuid not null references auth.users(id) on delete restrict,
 session_id uuid not null,
 started_at timestamptz not null default clock_timestamp(),
 expires_at timestamptz not null default clock_timestamp()+interval '5 minutes',
 otp_hash text,
 otp_version text,
 email_fingerprint text,
 sent_at timestamptz,
 attempts integer not null default 0,
 verified_at timestamptz,
 consumed_at timestamptz
);
create table public.privacy_export_otp_sends (
 account_id uuid not null references auth.users(id) on delete restrict,
 sent_at timestamptz not null default clock_timestamp()
);
do $$ declare t text; begin
 foreach t in array array['privacy_content_jobs','privacy_erased_sessions','privacy_erased_session_keys','privacy_export_rows','privacy_content_objects','privacy_export_proofs','privacy_export_otp_sends'] loop
  execute format('alter table public.%I enable row level security',t);
  execute format('alter table public.%I force row level security',t);
  execute format('revoke all on public.%I from public,anon,authenticated,service_role,usage_executor,usage_binding_executor,usage_reconciler,catalog_draft_executor',t);
 end loop;
end $$;
-- Session fences supplement, rather than replace, the existing account fence.
do $$ declare t text; begin
 foreach t in array array['marketing_unsubscribe_tokens','subscription_auth_handoffs'] loop
  if to_regclass('public.'||t) is not null then
   execute format('create trigger privacy_private_credential_fence before insert or update on public.%I for each row execute function public.privacy_content_write_guard()',t);
  end if;
 end loop;
end $$;
create function public.privacy_session_erasure_fence() returns trigger
language plpgsql security definer set search_path=pg_catalog,extensions,public as $$
declare subject uuid; sid uuid; begin
 subject:=coalesce((to_jsonb(new)->>'user_id')::uuid,(to_jsonb(new)->>'account_id')::uuid);
 sid:=coalesce((to_jsonb(new)->>'session_id')::uuid,(to_jsonb(new)->>'interview_session_id')::uuid);
 if tg_table_name='interview_sessions' then sid:=(to_jsonb(new)->>'id')::uuid; end if;
 if subject is null then raise exception 'owner missing' using errcode='42501'; end if;
 perform 1 from auth.users where id=subject for no key update;
 if tg_table_name='interview_session_idempotency_keys' and exists(
  select 1 from public.privacy_erased_session_keys e join public.privacy_matching_keys k on k.version=e.key_version
  where e.account_id=subject and e.digest=hmac(convert_to(jsonb_build_array('c15.session-key.v1',subject,to_jsonb(new)->>'idempotency_key')::text,'UTF8'),k.secret,'sha256')) then
  raise exception 'privacy replay denied' using errcode='42501';
 end if;
 if exists(select 1 from public.privacy_erased_sessions e where e.account_id=subject and e.session_id=sid) then
  raise exception 'privacy scope restricted' using errcode='42501';
 end if;
 return new;
end $$;
do $$ declare t text; begin
 foreach t in array array['interview_sessions','interview_session_idempotency_keys','interview_session_transcript_entries','interview_session_ai_notes',
 'interview_session_ask_ai_messages','interview_session_ask_ai_request_keys','interview_session_my_answers',
 'session_generation_turns','interview_answer_sources','interview_answer_diagrams','subscription_screen_threads','subscription_screen_results'] loop
  if to_regclass('public.'||t) is not null then
   execute format('create trigger privacy_session_erasure before insert or update on public.%I for each row execute function public.privacy_session_erasure_fence()',t);
  end if;
 end loop;
end $$;
revoke all on function public.privacy_session_erasure_fence() from public,anon,authenticated,service_role;
create function public.privacy_capture_erasure_keys(p_account uuid,p_job uuid) returns void
language plpgsql security definer set search_path=pg_catalog,extensions,public as $$
begin
 if not exists(select 1 from public.privacy_matching_keys where current_key) then raise exception 'matching unavailable' using errcode='42501'; end if;
 insert into public.privacy_erased_session_keys(account_id,key_version,digest,job_id)
 select p_account,k.version,hmac(convert_to(jsonb_build_array('c15.session-key.v1',p_account,i.idempotency_key)::text,'UTF8'),k.secret,'sha256'),p_job
 from public.interview_session_idempotency_keys i join public.privacy_erased_sessions e on e.session_id=i.interview_session_id and e.account_id=i.user_id
 cross join public.privacy_matching_keys k where i.user_id=p_account and e.job_id=p_job and k.current_key on conflict do nothing;
end $$;
revoke all on function public.privacy_capture_erasure_keys(uuid,uuid) from public,anon,authenticated,service_role,usage_executor;
create function public.privacy_content_status(p_request uuid) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 return coalesce((select jsonb_build_object('cleanup_state',j.state,'cleanup_progress',j.progress,
  'cleanup_blockers',j.blockers,'primary_content_verified',j.state='primary_verified',
  'retention_obligations','pending','content_erased',false)
  from public.privacy_content_jobs j where j.id=p_request and j.kind='account'),
  jsonb_build_object('cleanup_state','pending','primary_content_verified',false,'content_erased',false));
end $$;
revoke all on function public.privacy_content_status(uuid) from public,anon,authenticated,service_role;
grant execute on function public.privacy_content_status(uuid) to usage_executor;
commit;

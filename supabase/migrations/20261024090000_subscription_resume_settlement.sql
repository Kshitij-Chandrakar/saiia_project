begin;
-- A permanent successful-upload marker is independent of deletable files.
create table public.subscription_resume_history (
 account_id uuid primary key references auth.users(id) on delete cascade,
 first_ready_at timestamptz not null default clock_timestamp()
);
create table public.subscription_resume_jobs (
 account_id uuid not null references auth.users(id) on delete cascade,
 resume_id uuid not null references public.resumes(id) on delete cascade,
 semantic_hash text not null,
 replacement_of uuid,
 usage_id uuid references public.usage_operations(operation_id),
 primary key(account_id,resume_id)
);
create table public.subscription_resume_active_sets (
 account_id uuid primary key references auth.users(id) on delete cascade,
 binding_revision bigint not null,
 resume_ids uuid[] not null
);

create function public.subscription_resume_call(p_account uuid,p_action text,p_doc jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare r public.resumes; n public.resumes; j public.subscription_resume_jobs; terms jsonb; a jsonb; cap bigint; stored bigint; pending bigint; operation jsonb; replacing uuid; patch jsonb; selected uuid[]; revision bigint;
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 if p_action not in ('list','read','capacity') then
   perform public.subscription_current(p_account,false);
   select c.canonical_json::jsonb->'terms' into terms from public.account_plan_bindings b join public.catalog_offer_versions c using(offer_version_id) where b.account_id=p_account;
   if not exists(select 1 from jsonb_array_elements(terms->'entitlements') e where e->>'feature'=case when p_action='use' then 'resume.grounding' else 'resume.upload' end and e->>'allowed'='true') then raise exception 'denied' using errcode='42501'; end if;
   if p_action='update' and p_doc->'payload'->>'status'='extracting' and not exists(select 1 from jsonb_array_elements(terms->'entitlements') e where e->>'feature'='resume.extract' and e->>'allowed'='true') then raise exception 'extraction denied' using errcode='42501'; end if;
 else perform 1 from public.account_plan_bindings where account_id=p_account for update;
 end if;
 if p_action='list' then return jsonb_build_object('items',coalesce((select jsonb_agg(to_jsonb(x) order by updated_at desc,id) from public.resumes x where user_id=p_account and status<>'deleted'),'[]')); end if;
 if p_action='capacity' then return jsonb_build_object('used',(select count(*) from public.resumes where user_id=p_account and status='ready'),'reserved',(select count(*) from public.resumes file join public.subscription_resume_jobs job on job.account_id=file.user_id and job.resume_id=file.id where file.user_id=p_account and file.status in ('uploaded','extracting','needs_review','indexing') and job.replacement_of is null)); end if;
 select * into r from public.resumes where user_id=p_account and id=(p_doc->>'resume_id')::uuid for update;
 if p_action='read' then
   if not found then raise exception 'not found' using errcode='P0002'; end if;
   return to_jsonb(r);
 end if;
 select x into a from jsonb_array_elements(terms->'storage_allowances') x where x->>'meter'='resume.stored_files';
 if a is null then select jsonb_build_object('mode','limited','amount',x->'amount') into a from jsonb_array_elements(terms->'limits') x where x->>'meter'='resume.stored_files' and x->>'kind'='storage'; end if;
 if a is null or a->>'mode' not in ('limited','unlimited') then raise exception 'missing capacity' using errcode='55000'; end if;
 cap:=case when a->>'mode'='unlimited' then null else (a->>'amount')::bigint end;
 select count(*) into stored from public.resumes where user_id=p_account and status='ready';
 if p_action='select' then
   select array_agg(value::uuid) into selected from jsonb_array_elements_text(p_doc->'resume_ids');
   if cardinality(selected) is null or cardinality(selected)<1 or cap is not null and cardinality(selected)>cap or cardinality(selected)<>(select count(distinct x) from unnest(selected) x) or cardinality(selected)<>(select count(*) from public.resumes where user_id=p_account and status='ready' and id=any(selected)) then raise exception 'invalid active set' using errcode='22023'; end if;
   select b.revision into revision from public.account_plan_bindings b where b.account_id=p_account;
   insert into public.subscription_resume_active_sets values(p_account,revision,selected) on conflict(account_id) do update set binding_revision=excluded.binding_revision,resume_ids=excluded.resume_ids;
   update public.resumes set is_active=false where user_id=p_account and is_active;
   update public.resumes set is_active=true where id=selected[1] and user_id=p_account returning * into r;
   return to_jsonb(r);
 end if;
 if p_action='insert' then
   if r.id is not null then
     select * into j from public.subscription_resume_jobs where account_id=p_account and resume_id=r.id;
     if j.semantic_hash is distinct from p_doc->>'semantic_hash' then raise exception 'identity conflict' using errcode='P0003'; end if;
     return to_jsonb(r);
   end if;
   if cap is not null and stored>cap then raise exception 'select permitted active set' using errcode='42501'; end if;
   select count(*) into pending from public.resumes where user_id=p_account and status in ('uploaded','extracting','needs_review','indexing');
   if cap is not null and pending>=greatest(1,cap-stored) then raise exception 'upload pending' using errcode='40001'; end if;
   -- Existing single-current-resume UI chooses its current usable file as the
   -- replacement only when no stored slot remains. It is retained on failure.
   if cap is not null and stored=cap then
     select id into replacing from public.resumes where user_id=p_account and is_active and status='ready';
     if replacing is null then raise exception 'active set required' using errcode='42501'; end if;
   end if;
   if exists(select 1 from public.subscription_resume_history where account_id=p_account) and (stored=0 or replacing is not null) then
     select x into operation from jsonb_array_elements(public.subscription_account_usage(p_account)) x where x->>'meter'='resume.replacements';
     if operation is null then raise exception 'replacement allowance missing' using errcode='55000'; end if;
     if operation->>'mode'='limited' and (operation->>'used')::bigint+(operation->>'reserved')::bigint>=(operation->>'allowance')::bigint then raise exception 'replacement exhausted' using errcode='P0004'; end if;
     operation:=null;
   end if;
   n:=jsonb_populate_record(null::public.resumes,p_doc->'payload');
   if n.id<>(p_doc->>'resume_id')::uuid or n.user_id<>p_account or n.status<>'uploaded' or n.is_active or n.storage_path not like p_account::text||'/'||n.id::text||'/%' then raise exception 'invalid metadata' using errcode='22023'; end if;
   insert into public.resumes(id,user_id,storage_path,original_filename,mime_type,file_size,status,is_active) values(n.id,p_account,n.storage_path,n.original_filename,n.mime_type,n.file_size,'uploaded',false) returning * into r;
   insert into public.subscription_resume_jobs values(p_account,r.id,p_doc->>'semantic_hash',replacing,(operation->>'operation_id')::uuid);
   return to_jsonb(r);
 end if;
 if r.id is null then raise exception 'not found' using errcode='P0002'; end if;
 if p_action='rebuild' then
   if r.status<>'ready' or r.active_chunk_generation<>(p_doc->>'expected_generation')::uuid or not exists(select 1 from public.resume_chunks where user_id=p_account and resume_id=r.id and generation_id=(p_doc->>'generation')::uuid) then raise exception 'stale generation' using errcode='40001'; end if;
   if cap is not null and stored>cap and not exists(select 1 from public.subscription_resume_active_sets s join public.account_plan_bindings b using(account_id) where s.account_id=p_account and s.binding_revision=b.revision and r.id=any(s.resume_ids)) then raise exception 'select active set' using errcode='42501'; end if;
   update public.resumes set active_chunk_generation=(p_doc->>'generation')::uuid,index_status='indexed',failure_code=null,failure_message=null,failed_at=null,last_error_at=null where id=r.id returning * into r;
   return to_jsonb(r);
 end if;
 select * into j from public.subscription_resume_jobs where account_id=p_account and resume_id=r.id for update;
 if p_action='activate' then
   if r.status='ready' and r.confirmed_profile=p_doc->'profile' and r.extraction_attempt=(p_doc->>'attempt')::integer then return to_jsonb(r); end if;
   if r.status='ready' then raise exception 'conflicting activation identity' using errcode='P0003'; end if;
   if cap is not null and stored-(case when j.replacement_of is not null and exists(select 1 from public.resumes where id=j.replacement_of and user_id=p_account and status='ready') then 1 else 0 end)>=cap then raise exception 'capacity exhausted' using errcode='P0004'; end if;
   if exists(select 1 from public.subscription_resume_history where account_id=p_account) and (stored=0 or j.replacement_of is not null) then
     -- Successful activation owns the allowance period. A candidate may remain
     -- in review across midnight/month end without charging the upload period.
     operation:=public.usage_call(p_account,'reserve',jsonb_build_object('operation','resume.replace','resource_id',r.id,'request_id',r.id::text,'semantic_hash',j.semantic_hash,'meter','resume.replacements','requested',1,'policy_version','subscriptions.approved.2026-10-24','lease_seconds',60));
     j.usage_id:=(operation->>'operation_id')::uuid;
     update public.subscription_resume_jobs set usage_id=j.usage_id where account_id=p_account and resume_id=r.id;
   end if;
   select * into strict n from public.activate_cloud_resume(p_account,r.id,(p_doc->>'attempt')::integer,(p_doc->>'generation')::uuid,p_doc->'profile');
   if j.replacement_of is not null then update public.resumes set status='deleted',is_active=false where id=j.replacement_of and user_id=p_account; end if;
   if j.usage_id is not null then perform public.subscription_result_finish(p_account,j.usage_id,1,r.id); end if;
   insert into public.subscription_resume_history(account_id) values(p_account) on conflict do nothing;
   return to_jsonb(n);
 end if;
 if p_action='update' then
   if p_doc ? 'statuses' and not (p_doc->'statuses' ? r.status) or p_doc ? 'attempt' and r.extraction_attempt<>(p_doc->>'attempt')::integer then raise exception 'state changed' using errcode='40001'; end if;
   patch:=p_doc->'payload';
   if exists(select 1 from jsonb_object_keys(patch) k where k not in ('status','is_active','confirmed_at','extraction_attempt','confirmed_profile','active_chunk_generation','failure_code','failure_message','failed_at','last_error_at','parser_provider','parser_status','extraction_status','index_status','review_required')) then raise exception 'invalid update' using errcode='22023'; end if;
   if patch->>'status'='ready' or patch->>'is_active'='true' or patch ? 'active_chunk_generation' and patch->'active_chunk_generation'<>'null' then raise exception 'activation required' using errcode='42501'; end if;
   n:=jsonb_populate_record(r,patch);
   update public.resumes set status=n.status,is_active=n.is_active,confirmed_at=n.confirmed_at,extraction_attempt=n.extraction_attempt,confirmed_profile=n.confirmed_profile,active_chunk_generation=n.active_chunk_generation,failure_code=n.failure_code,failure_message=n.failure_message,failed_at=n.failed_at,last_error_at=n.last_error_at,parser_provider=n.parser_provider,parser_status=n.parser_status,extraction_status=n.extraction_status,index_status=n.index_status,review_required=n.review_required where id=r.id returning * into r;
   if r.status in ('failed','timeout','cancelled','deleted') and j.usage_id is not null and exists(select 1 from public.usage_operations where operation_id=j.usage_id and state='reserved') then perform public.subscription_result_finish(p_account,j.usage_id,0,null); end if;
   return to_jsonb(r);
 end if;
 if p_action='use' then
   if r.status<>'ready' or cap is not null and stored>cap and not exists(select 1 from public.subscription_resume_active_sets s join public.account_plan_bindings b using(account_id) where s.account_id=p_account and s.binding_revision=b.revision and r.id=any(s.resume_ids)) then raise exception 'select permitted active set' using errcode='42501'; end if;
   return to_jsonb(r);
 end if;
 raise exception 'invalid operation' using errcode='22023';
end $$;
alter table public.subscription_resume_history enable row level security;
alter table public.subscription_resume_history force row level security;
alter table public.subscription_resume_jobs enable row level security;
alter table public.subscription_resume_jobs force row level security;
alter table public.subscription_resume_active_sets enable row level security;
alter table public.subscription_resume_active_sets force row level security;
revoke all on public.subscription_resume_history,public.subscription_resume_jobs,public.subscription_resume_active_sets from public,anon,authenticated,service_role,usage_executor;
revoke all on function public.subscription_resume_call(uuid,text,jsonb) from public,anon,authenticated,service_role;
grant execute on function public.subscription_resume_call(uuid,text,jsonb) to usage_executor;
commit;

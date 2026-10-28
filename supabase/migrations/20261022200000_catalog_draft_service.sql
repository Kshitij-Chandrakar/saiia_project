-- C11.3B: closed server-only validation channel and durable draft retries.
-- NOLOGIN, no members/login provisioning: not a PostgREST/customer role.
begin;
create role catalog_draft_executor nologin noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls;

create table public.catalog_draft_requests (
  actor_subject uuid not null references auth.users(id) on delete restrict,
  request_id uuid not null,
  operation text not null check (operation in ('draft.create','draft.edit')),
  draft_id uuid not null,
  expected_revision bigint not null check (expected_revision >= 0),
  resulting_revision bigint not null check (resulting_revision = expected_revision + 1),
  semantic_hash text not null check (semantic_hash ~ '^[0-9a-f]{64}$'),
  recorded_at timestamptz not null default clock_timestamp(),
  primary key(actor_subject,request_id),
  foreign key(draft_id,resulting_revision) references public.catalog_draft_revisions(draft_id,revision) on delete restrict,
  check ((operation='draft.create') = (expected_revision=0))
);
alter table public.catalog_draft_requests enable row level security;
alter table public.catalog_draft_requests force row level security;
revoke all on public.catalog_draft_requests from public,anon,authenticated,service_role,catalog_draft_executor;
create trigger immutable_rows before update or delete on public.catalog_draft_requests
  for each row execute function public.catalog_reject_mutation();
create trigger immutable_truncate before truncate on public.catalog_draft_requests
  for each statement execute function public.catalog_reject_mutation();

-- Preserve C's gateway path and revocation ordering. The extra path is usable
-- only by an isolated server principal, never authenticator/service_role.
-- Its identity is installed only inside the private entry point below.
create or replace function public.catalog_locked_actor() returns public.subscription_admin_permissions
language plpgsql security definer set search_path=pg_catalog as $$
declare g public.subscription_admin_permissions; subject uuid;
begin
  if session_user='authenticator' and current_setting('role',true)='authenticated' then
    subject:=auth.uid();
  elsif session_user='catalog_draft_executor' and current_setting('role',true)='none' then
    subject:=nullif(current_setting('catalog.draft_actor',true),'')::uuid;
  else
    raise exception 'catalog identity gateway denied' using errcode='42501';
  end if;
  select * into g from public.subscription_admin_permissions
    where subject_id=subject and permission='subscriptions.manage' and active for share;
  if not found then raise exception 'catalog permission denied' using errcode='42501'; end if;
  return g;
end;
$$;

-- This is trusted infrastructure, NOT a JWT/public RPC. Caller UUID is accepted
-- only from a server connection whose service verifies the original JWT and
-- validates/normalizes B documents before dispatch. No EXECUTE for clients.
create function public.catalog_draft_service_call(p_actor uuid,p_operation text,p_id uuid,
  p_key uuid,p_expected bigint,p_document jsonb,p_reason text) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare prior public.catalog_draft_requests; h text; result jsonb; old_actor text;
begin
  if session_user<>'catalog_draft_executor' or current_setting('role',true)<>'none' then
    raise exception 'server channel required' using errcode='42501';
  end if;
  old_actor:=current_setting('catalog.draft_actor',true);
  perform set_config('catalog.draft_actor',p_actor::text,true);
  -- Always lock/recheck before any lookup/replay, including protected results.
  perform public.catalog_locked_actor();
  if p_operation='draft.read' then
    if p_key is not null or p_expected is not null or p_document is not null or p_reason is not null then
      raise exception 'invalid read' using errcode='23514';
    end if;
    result:=public.catalog_adapter_load_draft(p_id);
  else
    if p_operation not in ('draft.create','draft.edit') or p_operation is null
      or p_key is null or p_expected is null or p_expected<0
      or (p_operation='draft.create') is distinct from (p_expected=0)
      or p_document is null or p_reason is null then
      raise exception 'invalid operation' using errcode='23514';
    end if;
    -- JSONB semantic encoding is versioned here. Never trust a supplied digest.
    h:=encode(sha256(convert_to(jsonb_build_object('protocol','draft.request.v1',
      'actor',p_actor,'operation',p_operation,'target',p_id,'expected',p_expected,
      'document',p_document,'reason',p_reason)::text,'UTF8')),'hex');
    -- Hash collisions serialize unrelated keys only; PK enforces exact identity.
    perform pg_advisory_xact_lock(hashtextextended(p_actor::text||':'||p_key::text,0));
    select * into prior from public.catalog_draft_requests where actor_subject=p_actor and request_id=p_key;
    if found then
      if prior.semantic_hash<>h then raise exception 'request identity conflict' using errcode='P0003'; end if;
      select jsonb_build_object('storage_version','catalog.store.v1','draft_id',r.draft_id,
        'plan_id',r.plan_id,'revision',r.revision::text,'document',r.document) into result
        from public.catalog_draft_revisions r where r.draft_id=prior.draft_id and r.revision=prior.resulting_revision;
    else
      if p_expected=0 then
        insert into public.catalog_plans(plan_id,code)
          values((p_document->'plan'->>'plan_id')::uuid,p_document->'plan'->>'code')
          on conflict(plan_id) do nothing;
      end if;
      result:=public.catalog_adapter_save_draft(p_id,(p_document->'plan'->>'plan_id')::uuid,p_expected,p_document,p_reason);
      insert into public.catalog_draft_requests(actor_subject,request_id,operation,draft_id,expected_revision,resulting_revision,semantic_hash)
        values(p_actor,p_key,p_operation,p_id,p_expected,p_expected+1,h);
    end if;
  end if;
  perform set_config('catalog.draft_actor',coalesce(old_actor,''),true);
  return result;
end;
$$;
revoke all on function public.catalog_draft_service_call(uuid,text,uuid,uuid,bigint,jsonb,text)
  from public,anon,authenticated,service_role;
grant usage on schema public to catalog_draft_executor;
grant execute on function public.catalog_draft_service_call(uuid,text,uuid,uuid,bigint,jsonb,text) to catalog_draft_executor;
-- No memberships, direct tables, old RPC grants or real permission assignments.
commit;

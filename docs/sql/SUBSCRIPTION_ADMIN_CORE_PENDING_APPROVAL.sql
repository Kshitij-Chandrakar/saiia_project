-- PREPARED ONLY. Requires approval before running in rbmxfazjbldmkomdpyzl.
-- Core current v1/v2/v3 admin catalog; NO human grant, LOGIN, offers or activation.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='60s';
DO $$ BEGIN IF to_regclass('public.subscription_admin_permissions') IS NOT NULL OR to_regclass('public.catalog_plans') IS NOT NULL OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname='catalog_draft_executor') THEN RAISE EXCEPTION 'Baseline changed: stop and inspect before applying'; END IF; END $$;

-- SOURCE: 20261022120000_catalog_storage_foundation.sql
-- SHA256: 9ecb1e5edfa99085ae553b4ca2821b09565f79be6354d123e4f38d25167483a3
-- C11.2C: additive, closed catalog storage. No offers, subjects or runtime grants.
-- Prepare only; apply solely to an explicitly disposable database in this slice.
-- C11.3 must supply domain-validated publication and verified ingress before grants.

create table public.subscription_admin_permissions (
  subject_id uuid not null references auth.users(id) on delete restrict,
  permission text not null check (permission = 'subscriptions.manage'),
  revision bigint not null default 1 check (revision > 0),
  active boolean not null,
  approved_by uuid not null,
  reason text not null check (length(btrim(reason)) between 1 and 2000),
  primary key (subject_id, permission)
);

create table public.catalog_plans (
  plan_id uuid primary key,
  code text not null unique check (code ~ '^[a-z][a-z0-9._:-]{0,119}$')
);

create table public.catalog_drafts (
  draft_id uuid primary key,
  plan_id uuid not null references public.catalog_plans(plan_id) on delete restrict,
  revision bigint not null check (revision > 0),
  document jsonb not null check (jsonb_typeof(document) = 'object'),
  check ((document->>'draft_id') is not null and (document->>'draft_id')::uuid = draft_id),
  check (coalesce(document->>'revision','') ~ '^[1-9][0-9]*$' and (document->>'revision')::bigint = revision),
  check ((document->'plan'->>'plan_id') is not null and (document->'plan'->>'plan_id')::uuid = plan_id),
  check (coalesce(document->>'state','') in ('draft','previewed','published','abandoned')),
  check (coalesce(document->>'contract_version','') = 'catalog.v1'),
  check (coalesce(document->>'registry_version','') = 'catalog.features.v1')
);

create table public.catalog_draft_revisions (
  draft_id uuid not null references public.catalog_drafts(draft_id) on delete restrict,
  revision bigint not null check (revision > 0),
  plan_id uuid not null references public.catalog_plans(plan_id) on delete restrict,
  document jsonb not null,
  primary key (draft_id, revision),
  unique (draft_id, revision, plan_id)
);

create table public.catalog_offer_versions (
  offer_version_id uuid primary key,
  plan_id uuid not null references public.catalog_plans(plan_id) on delete restrict,
  version bigint not null check (version > 0),
  source_draft_id uuid not null,
  source_revision bigint not null,
  -- Exact B canonical bytes; JSONB serialization must never replace these bytes.
  canonical_json text not null,
  -- Derived in the insert trigger, never a validation attestation/signature.
  fingerprint text not null check (fingerprint ~ '^[0-9a-f]{64}$'),
  unique (plan_id, version),
  unique (source_draft_id, source_revision),
  foreign key (source_draft_id, source_revision, plan_id)
    references public.catalog_draft_revisions(draft_id, revision, plan_id) on delete restrict
);

create table public.catalog_price_versions (
  price_id uuid primary key,
  offer_version_id uuid not null references public.catalog_offer_versions(offer_version_id) on delete restrict,
  document jsonb not null,
  currency text generated always as (document->>'currency') stored not null,
  exponent bigint generated always as ((document->>'exponent')::bigint) stored not null,
  amount_minor bigint generated always as ((document->>'amount_minor')::bigint) stored not null,
  billing_unit text generated always as (document->'billing'->>'unit') stored not null,
  billing_count bigint generated always as ((document->'billing'->>'count')::bigint) stored not null,
  unique (offer_version_id, currency, billing_unit, billing_count),
  check ((document->>'price_id') is not null and (document->>'price_id')::uuid = price_id),
  check (coalesce(document->>'currency_version','') = 'catalog.currency.v1'),
  check ((currency in ('INR','USD') and exponent=2) or (currency='JPY' and exponent=0) or (currency='KWD' and exponent=3)),
  check ((document->>'amount_minor') ~ '^(0|[1-9][0-9]*)$' and amount_minor >= 0),
  check ((document->>'exponent') ~ '^(0|[1-9][0-9]*)$'),
  check (billing_unit in ('month','year') and billing_count > 0),
  check ((document->'billing'->>'count') ~ '^[1-9][0-9]*$')
);

create table public.catalog_visibility (
  offer_version_id uuid primary key references public.catalog_offer_versions(offer_version_id) on delete restrict,
  revision bigint not null default 1 check (revision > 0),
  state text not null default 'hidden' check (state in ('hidden','visible','retired')),
  valid_from timestamptz,
  valid_until timestamptz,
  check (valid_until is null or (valid_from is not null and valid_until > valid_from)),
  check (state <> 'visible' or valid_from is not null)
);

create table public.catalog_admin_actions (
  action_id uuid primary key default gen_random_uuid(),
  actor_subject uuid not null,
  permission_revision bigint not null check (permission_revision > 0),
  operation text not null check (operation in ('draft.create','draft.edit','offer.retire','permission.change')),
  resource_id uuid not null,
  resulting_revision bigint not null check (resulting_revision > 0),
  reason text not null check (length(btrim(reason)) between 1 and 2000),
  recorded_at timestamptz not null default clock_timestamp()
);

create function public.catalog_reject_mutation() returns trigger
language plpgsql set search_path = pg_catalog as $$
begin raise exception 'catalog immutable history' using errcode='55000'; end;
$$;

-- No delete, truncate, upsert-update or parent cascade may erase historical rows.
do $$
declare t text;
begin
  foreach t in array array['catalog_plans','catalog_draft_revisions','catalog_offer_versions','catalog_price_versions','catalog_admin_actions'] loop
    execute format('create trigger immutable_rows before update or delete on public.%I for each row execute function public.catalog_reject_mutation()',t);
    execute format('create trigger immutable_truncate before truncate on public.%I for each statement execute function public.catalog_reject_mutation()',t);
  end loop;
end;
$$;

-- Shared membership authority, deliberately not wired to the current Python probe.
-- Membership provisioning/revocation is maintenance-only, with no grant RPC.
create function public.catalog_permission_change() returns trigger
language plpgsql security definer set search_path = pg_catalog as $$
begin
  if tg_op='UPDATE' then
    if new.subject_id<>old.subject_id or new.permission<>old.permission or new.revision<>old.revision+1 then
      raise exception 'permission revision conflict' using errcode='40001';
    end if;
  elsif new.revision<>1 then
    raise exception 'initial permission revision must be one' using errcode='23514';
  end if;
  insert into public.catalog_admin_actions(actor_subject,permission_revision,operation,resource_id,resulting_revision,reason)
    values(new.approved_by,new.revision,'permission.change',new.subject_id,new.revision,new.reason);
  return new;
end;
$$;
create trigger permission_change before insert or update on public.subscription_admin_permissions
  for each row execute function public.catalog_permission_change();
create trigger permission_delete before delete on public.subscription_admin_permissions
  for each row execute function public.catalog_reject_mutation();
create trigger permission_truncate before truncate on public.subscription_admin_permissions
  for each statement execute function public.catalog_reject_mutation();

create function public.catalog_locked_actor() returns public.subscription_admin_permissions
language plpgsql security definer set search_path = pg_catalog as $$
declare g public.subscription_admin_permissions;
begin
  -- auth.uid() is trustworthy only behind JWT-verifying PostgREST, not arbitrary
  -- SQL GUCs or a service-role request. No actor UUID override is accepted.
  if session_user <> 'authenticator' or current_setting('role',true) <> 'authenticated' then
    raise exception 'catalog identity gateway denied' using errcode='42501';
  end if;
  select * into g from public.subscription_admin_permissions
    where subject_id=auth.uid() and permission='subscriptions.manage' and active for share;
  if not found then raise exception 'catalog permission denied' using errcode='42501'; end if;
  -- FOR SHARE conflicts with revocation UPDATE until transaction end. No cache.
  return g;
end;
$$;

create function public.catalog_draft_guard() returns trigger
language plpgsql security definer set search_path = pg_catalog as $$
begin
  if tg_op='UPDATE' then
    if new.draft_id<>old.draft_id or new.plan_id<>old.plan_id or new.revision<>old.revision+1
       or old.document->>'state' in ('published','abandoned') then
      raise exception 'draft revision conflict' using errcode='40001';
    end if;
  elsif new.revision<>1 then
    raise exception 'initial draft revision must be one' using errcode='23514';
  end if;
  if new.document->'plan'->>'code' is distinct from (select code from public.catalog_plans where plan_id=new.plan_id) then
    raise exception 'plan identity mismatch' using errcode='23514';
  end if;
  return new;
end;
$$;
create trigger draft_guard before insert or update on public.catalog_drafts for each row execute function public.catalog_draft_guard();
create trigger draft_delete before delete on public.catalog_drafts for each row execute function public.catalog_reject_mutation();
create trigger draft_truncate before truncate on public.catalog_drafts for each statement execute function public.catalog_reject_mutation();

create function public.catalog_record_revision() returns trigger
language plpgsql security definer set search_path = pg_catalog as $$
begin
  insert into public.catalog_draft_revisions values(new.draft_id,new.revision,new.plan_id,new.document);
  return new;
end;
$$;
create trigger record_revision after insert or update on public.catalog_drafts for each row execute function public.catalog_record_revision();

-- Only a storage primitive. Domain validation/approval/preview is still required
-- in the future trusted adapter, even for incomplete drafts. No publish here.
create function public.catalog_save_draft(p_id uuid,p_plan uuid,p_expected bigint,p_document jsonb,p_reason text)
returns bigint language plpgsql security definer set search_path = pg_catalog as $$
declare g public.subscription_admin_permissions; r bigint;
begin
  g:=public.catalog_locked_actor();
  if p_expected is null or p_expected<0 or p_document->>'state' is distinct from 'draft' then
    raise exception 'invalid draft edit' using errcode='23514';
  end if;
  if p_expected=0 then
    insert into public.catalog_drafts values(p_id,p_plan,1,p_document) returning revision into r;
  else
    update public.catalog_drafts set revision=revision+1,document=p_document
      where draft_id=p_id and plan_id=p_plan and revision=p_expected returning revision into r;
    if not found then raise exception 'draft revision conflict' using errcode='40001'; end if;
  end if;
  insert into public.catalog_admin_actions(actor_subject,permission_revision,operation,resource_id,resulting_revision,reason)
    values(g.subject_id,g.revision,case when p_expected=0 then 'draft.create' else 'draft.edit' end,p_id,r,p_reason);
  return r;
end;
$$;

create function public.catalog_offer_guard() returns trigger
language plpgsql security definer set search_path = pg_catalog as $$
declare d jsonb; derived text; n bigint;
begin
  d:=new.canonical_json::jsonb;
  if d->>'contract_version' is distinct from 'catalog.v1' or d->>'registry_version' is distinct from 'catalog.features.v1'
     or (d->>'offer_version_id')::uuid is distinct from new.offer_version_id
     or (d->>'version')::bigint is distinct from new.version
     or (d->'plan'->>'plan_id')::uuid is distinct from new.plan_id
     or d->'plan'->>'code' is distinct from (select code from public.catalog_plans where plan_id=new.plan_id)
     or jsonb_typeof(d->'terms'->'prices') is distinct from 'array' or jsonb_array_length(d->'terms'->'prices')=0 then
    raise exception 'snapshot identity mismatch' using errcode='23514';
  end if;
  -- Serialize version allocation per stable identity; no gapless promise.
  perform 1 from public.catalog_plans where plan_id=new.plan_id for update;
  select coalesce(max(version),0) into n from public.catalog_offer_versions where plan_id=new.plan_id;
  if new.version<=n then raise exception 'offer version must increase' using errcode='23514'; end if;
  derived:=encode(sha256(convert_to(new.canonical_json,'UTF8')),'hex');
  if new.fingerprint is not null and new.fingerprint<>derived then
    raise exception 'snapshot fingerprint mismatch' using errcode='23514';
  end if;
  new.fingerprint:=derived;
  return new;
end;
$$;
create trigger offer_guard before insert on public.catalog_offer_versions for each row execute function public.catalog_offer_guard();

create function public.catalog_price_guard() returns trigger
language plpgsql security definer set search_path = pg_catalog as $$
begin
  if not exists(select 1 from public.catalog_offer_versions o,
      lateral jsonb_array_elements(o.canonical_json::jsonb->'terms'->'prices') p
      where o.offer_version_id=new.offer_version_id and p=new.document) then
    raise exception 'price must match immutable snapshot' using errcode='23514';
  end if;
  return new;
end;
$$;
create trigger price_guard before insert on public.catalog_price_versions for each row execute function public.catalog_price_guard();

create function public.catalog_offer_children() returns trigger
language plpgsql security definer set search_path = pg_catalog as $$
declare p jsonb;
begin
  for p in select * from jsonb_array_elements(new.canonical_json::jsonb->'terms'->'prices') loop
    insert into public.catalog_price_versions(price_id,offer_version_id,document) values((p->>'price_id')::uuid,new.offer_version_id,p);
  end loop;
  insert into public.catalog_visibility(offer_version_id) values(new.offer_version_id);
  return new;
end;
$$;
create trigger offer_children after insert on public.catalog_offer_versions for each row execute function public.catalog_offer_children();

create function public.catalog_visibility_guard() returns trigger
language plpgsql set search_path = pg_catalog as $$
begin
  if tg_op='INSERT' then
    if new.state<>'hidden' or new.revision<>1 then raise exception 'initial visibility must be hidden' using errcode='23514'; end if;
  elsif new.offer_version_id<>old.offer_version_id or new.revision<>old.revision+1
      or old.state='retired' or new.state<>'retired' then
    -- Publication/visibility scheduling requires later reviewed C11.3 functions.
    raise exception 'unsupported visibility transition' using errcode='23514';
  end if;
  return new;
end;
$$;
create trigger visibility_guard before insert or update on public.catalog_visibility for each row execute function public.catalog_visibility_guard();
create trigger visibility_delete before delete on public.catalog_visibility for each row execute function public.catalog_reject_mutation();
create trigger visibility_truncate before truncate on public.catalog_visibility for each statement execute function public.catalog_reject_mutation();

create function public.catalog_retire_offer(p_id uuid,p_expected bigint,p_reason text)
returns bigint language plpgsql security definer set search_path = pg_catalog as $$
declare g public.subscription_admin_permissions; r bigint;
begin
  g:=public.catalog_locked_actor();
  update public.catalog_visibility set state='retired',revision=revision+1
    where offer_version_id=p_id and revision=p_expected and state<>'retired' returning revision into r;
  if not found then raise exception 'visibility revision conflict' using errcode='40001'; end if;
  insert into public.catalog_admin_actions(actor_subject,permission_revision,operation,resource_id,resulting_revision,reason)
    values(g.subject_id,g.revision,'offer.retire',p_id,r,p_reason);
  return r;
end;
$$;

-- Supabase defaults may grant more than PUBLIC. Explicitly remove all three
-- application roles, including BYPASSRLS service_role: RLS alone is insufficient.
do $$
declare t text; f record;
begin
  foreach t in array array['subscription_admin_permissions','catalog_plans','catalog_drafts','catalog_draft_revisions','catalog_offer_versions','catalog_price_versions','catalog_visibility','catalog_admin_actions'] loop
    execute format('alter table public.%I enable row level security',t);
    execute format('alter table public.%I force row level security',t);
    execute format('revoke all on table public.%I from public,anon,authenticated,service_role',t);
  end loop;
  for f in select oid::regprocedure as signature from pg_proc where pronamespace='public'::regnamespace
    and proname = any(array['catalog_reject_mutation','catalog_permission_change','catalog_locked_actor',
      'catalog_draft_guard','catalog_record_revision','catalog_save_draft','catalog_offer_guard',
      'catalog_price_guard','catalog_offer_children','catalog_visibility_guard','catalog_retire_offer']) loop
    execute format('revoke all on function %s from public,anon,authenticated,service_role',f.signature);
  end loop;
end;
$$;
INSERT INTO supabase_migrations.schema_migrations(version) VALUES ('20261022120000');

-- SOURCE: 20261022150000_catalog_adapter_primitives.sql
-- SHA256: 9b011afd17ce6a686f3def4f9835f3561e28c6d312ed14d1e184148a6b5109c7
-- C11.2D: closed private adapter primitives, not publication or public reads.
-- Requires C11.2C. No application EXECUTE/table grants or live subjects.
alter table public.catalog_admin_actions drop constraint catalog_admin_actions_operation_check;
alter table public.catalog_admin_actions add constraint catalog_admin_actions_operation_check
  check (operation in ('draft.create','draft.edit','offer.retire','permission.change','snapshot.archive'));

create function public.catalog_adapter_load_draft(p_id uuid) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare d public.catalog_drafts;
begin
  perform public.catalog_locked_actor();
  select * into d from public.catalog_drafts where draft_id=p_id;
  if not found then raise exception 'catalog record not found' using errcode='P0002'; end if;
  return jsonb_build_object('storage_version','catalog.store.v1','draft_id',d.draft_id,
    'plan_id',d.plan_id,'revision',d.revision::text,'document',d.document);
end;
$$;

create function public.catalog_adapter_save_draft(p_id uuid,p_plan uuid,p_expected bigint,p_document jsonb,p_reason text)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
begin
  perform public.catalog_locked_actor();
  if p_expected>0 then
    perform 1 from public.catalog_drafts where draft_id=p_id for update;
    if not found then raise exception 'catalog record not found' using errcode='P0002'; end if;
  end if;
  -- Reuse accepted CAS/history/audit; return its readback in the same transaction.
  perform public.catalog_save_draft(p_id,p_plan,p_expected,p_document,p_reason);
  return public.catalog_adapter_load_draft(p_id);
end;
$$;

create function public.catalog_adapter_load_snapshot(p_id uuid) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare o public.catalog_offer_versions; prices jsonb;
begin
  perform public.catalog_locked_actor();
  select * into o from public.catalog_offer_versions where offer_version_id=p_id;
  if not found then raise exception 'catalog record not found' using errcode='P0002'; end if;
  select coalesce(jsonb_agg(document order by price_id),'[]'::jsonb) into prices
    from public.catalog_price_versions where offer_version_id=p_id;
  return jsonb_build_object('storage_version','catalog.store.v1','offer_version_id',o.offer_version_id,
    'plan_id',o.plan_id,'version',o.version::text,'source_draft_id',o.source_draft_id,
    'source_revision',o.source_revision::text,'canonical_json',o.canonical_json,
    'fingerprint',o.fingerprint,'prices',prices);
end;
$$;

-- Backend validation boundary ONLY; SQL cannot attest Python domain validation.
-- Keep EXECUTE closed until a reviewed server-only transport is composed. Never
-- expose this primitive directly to clients or treat a submitted hash as proof.
create function public.catalog_adapter_archive_snapshot(p_draft_id uuid,p_expected bigint,
  p_offer_id uuid,p_version bigint,p_canonical_json text,p_reason text) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare g public.subscription_admin_permissions; d public.catalog_drafts;
begin
  g:=public.catalog_locked_actor();
  select * into d from public.catalog_drafts where draft_id=p_draft_id for update;
  if not found then raise exception 'catalog record not found' using errcode='P0002'; end if;
  if d.revision is distinct from p_expected then
    raise exception 'draft revision conflict' using errcode='40001';
  end if;
  if d.document->>'state' is distinct from 'draft' then
    raise exception 'unsupported archive source' using errcode='23514';
  end if;
  insert into public.catalog_offer_versions(offer_version_id,plan_id,version,source_draft_id,source_revision,canonical_json)
    values(p_offer_id,d.plan_id,p_version,d.draft_id,d.revision,p_canonical_json);
  insert into public.catalog_admin_actions(actor_subject,permission_revision,operation,resource_id,resulting_revision,reason)
    values(g.subject_id,g.revision,'snapshot.archive',p_offer_id,p_version,p_reason);
  -- Initial hidden visibility is created by C's trigger; no published state,
  -- preview approval, catalog revision or customer visibility is activated.
  return public.catalog_adapter_load_snapshot(p_offer_id);
end;
$$;

revoke all on function public.catalog_adapter_load_draft(uuid),
  public.catalog_adapter_save_draft(uuid,uuid,bigint,jsonb,text),
  public.catalog_adapter_load_snapshot(uuid),
  public.catalog_adapter_archive_snapshot(uuid,bigint,uuid,bigint,text,text)
  from public,anon,authenticated,service_role;
INSERT INTO supabase_migrations.schema_migrations(version) VALUES ('20261022150000');

-- SOURCE: 20261022180000_subscription_admin_self_probe.sql
-- SHA256: 536dcf4b6a7add22c94fb199aa7c114963d12765842ad66f887b6794d9b1f407
-- C11.3A: caller-only, read-only membership probe. No mutation grants/subjects.
create function public.subscription_admin_self_probe() returns jsonb
language plpgsql stable security definer set search_path=pg_catalog as $$
declare subject uuid; r bigint;
begin
  if session_user <> 'authenticator' or current_setting('role',true) <> 'authenticated' then
    raise exception 'identity gateway denied' using errcode='42501';
  end if;
  subject:=auth.uid();
  if subject is null then raise exception 'identity required' using errcode='42501'; end if;
  select revision into r from public.subscription_admin_permissions
    where subject_id=subject and permission='subscriptions.manage' and active;
  return jsonb_build_object('contract_version','admin.access.v1','subject_id',subject,
    'permissions',case when r is null then '[]'::jsonb else '["subscriptions.manage"]'::jsonb end,
    'permission_revision',r::text);
end;
$$;
revoke all on function public.subscription_admin_self_probe() from public,anon,authenticated,service_role;
-- Deliberate narrow access: only caller's safe permission facts, no actor input.
grant execute on function public.subscription_admin_self_probe() to authenticated;
INSERT INTO supabase_migrations.schema_migrations(version) VALUES ('20261022180000');

-- SOURCE: 20261022200000_catalog_draft_service.sql
-- SHA256: 526314e4e5a756242a52294073d26281dc975cabed0c55425266a18796875086
-- C11.3B: closed server-only validation channel and durable draft retries.
-- NOLOGIN, no members/login provisioning: not a PostgREST/customer role.
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
INSERT INTO supabase_migrations.schema_migrations(version) VALUES ('20261022200000');

-- SOURCE: 20261022210000_catalog_publication_reviews.sql
-- SHA256: d8c661c75b4932805c85e8fd762586abda8129fdfc3789eed6a1e996efbda885
-- C11.3F1: closed review evidence ONLY. No publishing or production grants.
-- Apply solely to task-owned disposable PostgreSQL during this slice.

alter table public.catalog_admin_actions drop constraint catalog_admin_actions_operation_check;
alter table public.catalog_admin_actions add constraint catalog_admin_actions_operation_check
  check(operation in ('draft.create','draft.edit','offer.retire','permission.change','snapshot.archive','review.create'));

create table public.catalog_publication_reviews (
  review_id uuid primary key default gen_random_uuid(),
  draft_id uuid not null,
  source_revision bigint not null check(source_revision>0),
  plan_id uuid not null,
  reviewer_subject uuid not null references auth.users(id) on delete restrict,
  permission_revision bigint not null check(permission_revision>0),
  recorded_at timestamptz not null default clock_timestamp(),
  metadata jsonb not null check(jsonb_typeof(metadata)='object'),
  metadata_hash text not null check(metadata_hash ~ '^[0-9a-f]{64}$'),
  foreign key(draft_id,source_revision,plan_id)
    references public.catalog_draft_revisions(draft_id,revision,plan_id) on delete restrict,
  check(metadata->>'protocol' is not distinct from 'catalog.review.v1'),
  check(metadata->>'contract_version' is not distinct from 'catalog.v1'),
  check(metadata->>'registry_version' is not distinct from 'catalog.features.v1'),
  check(metadata->>'validation_policy_version' is not distinct from 'catalog.validation.v1'),
  check(metadata->>'draft_id' is not null and (metadata->>'draft_id')::uuid=draft_id),
  check(metadata->>'plan_id' is not null and (metadata->>'plan_id')::uuid=plan_id),
  check(coalesce(metadata->>'revision','') ~ '^[1-9][0-9]*$' and (metadata->>'revision')::bigint=source_revision),
  check(coalesce(metadata->>'source_hash','') ~ '^[0-9a-f]{64}$'),
  check(coalesce(metadata->>'terms_fingerprint','') ~ '^[0-9a-f]{64}$')
);

create table public.catalog_lifecycle_requests (
  actor_subject uuid not null references auth.users(id) on delete restrict,
  request_id uuid not null,
  operation text not null check(operation='review.create'),
  draft_id uuid not null references public.catalog_drafts(draft_id) on delete restrict,
  semantic_hash text not null check(semantic_hash ~ '^[0-9a-f]{64}$'),
  review_id uuid not null unique references public.catalog_publication_reviews(review_id) on delete restrict,
  action_id uuid not null unique references public.catalog_admin_actions(action_id) on delete restrict,
  primary key(actor_subject,request_id)
);

do $$
declare t text;
begin
  foreach t in array array['catalog_publication_reviews','catalog_lifecycle_requests'] loop
    execute format('alter table public.%I enable row level security',t);
    execute format('alter table public.%I force row level security',t);
    execute format('revoke all on public.%I from public,anon,authenticated,service_role,catalog_draft_executor',t);
    execute format('create trigger immutable_rows before update or delete on public.%I for each row execute function public.catalog_reject_mutation()',t);
    execute format('create trigger immutable_truncate before truncate on public.%I for each statement execute function public.catalog_reject_mutation()',t);
  end loop;
end;
$$;

-- Private helpers; only the gateway owner may invoke them. Python domain
-- readiness/approval cannot be attested by an arbitrary SQL metadata hash.
create function public.catalog_review_context(p_id uuid) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare d public.catalog_drafts; plan uuid; heads jsonb; archive jsonb;
begin
  perform public.catalog_locked_actor();
  select plan_id into plan from public.catalog_drafts where draft_id=p_id;
  if not found then raise exception 'missing draft' using errcode='P0002'; end if;
  perform 1 from public.catalog_plans where plan_id=plan for share;
  select * into d from public.catalog_drafts where draft_id=p_id for share;
  select coalesce(jsonb_agg(jsonb_build_object('offer_version_id',o.offer_version_id,
    'visibility_revision',v.revision::text,'fingerprint',o.fingerprint) order by o.offer_version_id),'[]')
    into heads from public.catalog_offer_versions o join public.catalog_visibility v using(offer_version_id)
    where o.plan_id=plan and v.state='visible';
  select jsonb_build_object('reference',jsonb_build_object('offer_version_id',o.offer_version_id,
      'visibility_revision',v.revision::text,'fingerprint',o.fingerprint),
      'state',v.state,'snapshot',public.catalog_adapter_load_snapshot(o.offer_version_id))
    into archive from public.catalog_offer_versions o join public.catalog_visibility v using(offer_version_id)
    where o.source_draft_id=d.draft_id and o.source_revision=d.revision;
  return jsonb_build_object('document',d.document,
    'source_hash',encode(sha256(convert_to(d.document::text,'UTF8')),'hex'),
    'heads',heads,'archive',archive,'now',clock_timestamp());
end;
$$;

create function public.catalog_review_read(p_id uuid) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare r public.catalog_publication_reviews; d public.catalog_draft_revisions;
begin
  perform public.catalog_locked_actor();
  select * into r from public.catalog_publication_reviews where review_id=p_id;
  if not found then raise exception 'missing review' using errcode='P0002'; end if;
  select * into d from public.catalog_draft_revisions where draft_id=r.draft_id and revision=r.source_revision;
  return jsonb_build_object('receipt',jsonb_build_object('storage_version','catalog.review.store.v1',
    'review_id',r.review_id,'reviewer_subject',r.reviewer_subject,
    'permission_revision',r.permission_revision::text,'recorded_at',r.recorded_at,'basis',r.metadata),
    'intact',r.metadata_hash=encode(sha256(convert_to(r.metadata::text,'UTF8')),'hex'),
    'source_document',d.document,'source_hash',encode(sha256(convert_to(d.document::text,'UTF8')),'hex'),
    'now',clock_timestamp());
end;
$$;

create function public.catalog_review_service_call(p_actor uuid,p_operation text,p_id uuid,
  p_key uuid,p_request jsonb,p_metadata jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare g public.subscription_admin_permissions; prior public.catalog_lifecycle_requests;
  old_actor text; result jsonb; h text; ctx jsonb; r uuid; audit_id uuid;
begin
  if session_user<>'catalog_draft_executor' or current_setting('role',true)<>'none' then
    raise exception 'server channel required' using errcode='42501';
  end if;
  old_actor:=current_setting('catalog.draft_actor',true);
  perform set_config('catalog.draft_actor',p_actor::text,true);
  g:=public.catalog_locked_actor(); -- permission first, including historical replay
  if p_operation in ('prepare','record') then
    if p_key is null or p_request is null or jsonb_typeof(p_request)<>'object'
      or (select count(*) from jsonb_object_keys(p_request))<>2
      or not(p_request ? 'basis' and p_request ? 'reason')
      or jsonb_typeof(p_request->'reason')<>'string'
      or length(btrim(p_request->>'reason')) not between 1 and 2000
      or p_request->'basis'->>'draft_id' is distinct from p_id::text then
      raise exception 'invalid review request' using errcode='23514';
    end if;
    h:=encode(sha256(convert_to(jsonb_build_object('protocol','catalog.lifecycle.request.v1',
      'actor',p_actor,'operation','review.create','target',p_id,'request',p_request)::text,'UTF8')),'hex');
    perform pg_advisory_xact_lock(hashtextextended('catalog.lifecycle.request.v1:'||p_actor::text||':'||p_key::text,0));
    select * into prior from public.catalog_lifecycle_requests where actor_subject=p_actor and request_id=p_key;
    if found then
      if prior.semantic_hash<>h then raise exception 'request conflict' using errcode='P0003'; end if;
      result:=public.catalog_review_read(prior.review_id);
    elsif p_operation='prepare' then
      if p_metadata is not null then raise exception 'invalid prepare' using errcode='23514'; end if;
      result:=null;
    else
      if p_metadata is distinct from p_request->'basis' then
        raise exception 'invalid review basis' using errcode='23514';
      end if;
      ctx:=public.catalog_review_context(p_id);
      if p_metadata->>'revision' is distinct from ctx->'document'->>'revision'
        or ctx->'document'->>'state' is distinct from 'draft'
        or p_metadata->>'source_hash' is distinct from ctx->>'source_hash' then
        raise exception 'stale review' using errcode='40001';
      end if;
      if (p_metadata->'authority'->>'valid_from')::timestamptz>clock_timestamp()
        or (p_metadata->'authority'->>'valid_until')::timestamptz<=clock_timestamp()
        or p_metadata->'authority'->>'valid_from' is null
        or p_metadata->'authority'->>'valid_until' is null then
        raise exception 'expired review authority' using errcode='40001';
      end if;
      insert into public.catalog_publication_reviews(draft_id,source_revision,plan_id,reviewer_subject,
        permission_revision,metadata,metadata_hash) values(p_id,(p_metadata->>'revision')::bigint,
        (p_metadata->>'plan_id')::uuid,g.subject_id,g.revision,p_metadata,
        encode(sha256(convert_to(p_metadata::text,'UTF8')),'hex')) returning review_id into r;
      insert into public.catalog_admin_actions(actor_subject,permission_revision,operation,resource_id,resulting_revision,reason)
        values(g.subject_id,g.revision,'review.create',r,(p_metadata->>'revision')::bigint,p_request->>'reason')
        returning action_id into audit_id;
      insert into public.catalog_lifecycle_requests values(p_actor,p_key,'review.create',p_id,h,r,audit_id);
      result:=public.catalog_review_read(r);
    end if;
  elsif p_key is not null or p_request is not null or p_metadata is not null then
    raise exception 'invalid review read' using errcode='23514';
  elsif p_operation='peek' then
    result:=public.catalog_adapter_load_draft(p_id);
  elsif p_operation='context' then
    result:=public.catalog_review_context(p_id);
  elsif p_operation='read' then
    result:=public.catalog_review_read(p_id);
  else
    raise exception 'unsupported review operation' using errcode='23514';
  end if;
  perform set_config('catalog.draft_actor',coalesce(old_actor,''),true);
  return result;
end;
$$;

revoke all on function public.catalog_review_context(uuid),public.catalog_review_read(uuid),
  public.catalog_review_service_call(uuid,text,uuid,uuid,jsonb,jsonb)
  from public,anon,authenticated,service_role,catalog_draft_executor;
-- Intentionally NO application EXECUTE grant/composition. Native fixtures grant
-- only this exact entry point to their disposable restricted LOGIN. C's existing
-- pool ACL policy is unchanged and will reject an unreviewed extra grant.
INSERT INTO supabase_migrations.schema_migrations(version) VALUES ('20261022210000');

-- SOURCE: 20261022220000_catalog_lifecycle_transactions.sql
-- SHA256: 0f80aa49a6555208c370760465e5f711329a21441525a7255f276888559f6220
-- C11.3F2: closed trusted-server transactions, no EXECUTE grants or public reads.
-- Apply only in task-owned disposable PostgreSQL for acceptance. No real offers.

alter table public.catalog_offer_versions add unique(offer_version_id,plan_id);
alter table public.catalog_visibility add column plan_id uuid;
alter table public.catalog_visibility add column retired_at timestamptz;
-- Locked owner-only backfill. Never invent a historical retirement timestamp.
drop trigger visibility_guard on public.catalog_visibility;
update public.catalog_visibility v set plan_id=o.plan_id from public.catalog_offer_versions o
  where o.offer_version_id=v.offer_version_id;
update public.catalog_visibility v set retired_at=(select max(a.recorded_at)
  from public.catalog_admin_actions a where a.operation='offer.retire'
  and a.resource_id=v.offer_version_id and a.resulting_revision=v.revision) where v.state='retired';
alter table public.catalog_visibility alter column plan_id set not null;
alter table public.catalog_visibility add foreign key(offer_version_id,plan_id)
  references public.catalog_offer_versions(offer_version_id,plan_id) on delete restrict;
alter table public.catalog_visibility add check((state='retired')=(retired_at is not null));
create unique index catalog_one_visible_plan on public.catalog_visibility(plan_id) where state='visible';

create or replace function public.catalog_visibility_guard() returns trigger
language plpgsql security definer set search_path=pg_catalog as $$
begin
  if tg_op='INSERT' then
    new.plan_id:=(select plan_id from public.catalog_offer_versions where offer_version_id=new.offer_version_id);
    if new.state<>'hidden' or new.revision<>1 or new.retired_at is not null then
      raise exception 'invalid initial visibility' using errcode='23514'; end if;
  else
    if new.offer_version_id<>old.offer_version_id or new.plan_id<>old.plan_id
      or new.revision<>old.revision+1 or old.state='retired'
      or not ((old.state='hidden' and new.state in ('visible','retired'))
           or (old.state='visible' and new.state='retired'))
      or (old.state='visible' and (new.valid_from is distinct from old.valid_from
           or new.valid_until is distinct from old.valid_until)) then
      raise exception 'invalid visibility transition' using errcode='40001'; end if;
    if new.state='retired' then new.retired_at:=clock_timestamp();
    elsif new.retired_at is not null then raise exception 'invalid retirement' using errcode='23514'; end if;
  end if;
  return new;
end;
$$;
create trigger visibility_guard before insert or update on public.catalog_visibility
  for each row execute function public.catalog_visibility_guard();

-- Avoid plan-lock upgrades: FK KEY SHARE remains compatible with this lock.
create or replace function public.catalog_offer_guard() returns trigger
language plpgsql security definer set search_path = pg_catalog as $$
declare d jsonb; derived text; n bigint;
begin
  d:=new.canonical_json::jsonb;
  if d->>'contract_version' is distinct from 'catalog.v1' or d->>'registry_version' is distinct from 'catalog.features.v1'
     or (d->>'offer_version_id')::uuid is distinct from new.offer_version_id
     or (d->>'version')::bigint is distinct from new.version
     or (d->'plan'->>'plan_id')::uuid is distinct from new.plan_id
     or d->'plan'->>'code' is distinct from (select code from public.catalog_plans where plan_id=new.plan_id)
     or jsonb_typeof(d->'terms'->'prices') is distinct from 'array' or jsonb_array_length(d->'terms'->'prices')=0 then
    raise exception 'snapshot identity mismatch' using errcode='23514';
  end if;
  -- Serialize version allocation per stable identity; no gapless promise.
  perform 1 from public.catalog_plans where plan_id=new.plan_id for no key update;
  select coalesce(max(version),0) into n from public.catalog_offer_versions where plan_id=new.plan_id;
  if new.version<=n then raise exception 'offer version must increase' using errcode='23514'; end if;
  derived:=encode(sha256(convert_to(new.canonical_json,'UTF8')),'hex');
  if new.fingerprint is not null and new.fingerprint<>derived then
    raise exception 'snapshot fingerprint mismatch' using errcode='23514';
  end if;
  new.fingerprint:=derived;
  return new;
end;
$$;

create table public.catalog_public_state (
  singleton boolean primary key default true check(singleton),
  revision bigint not null check(revision>0)
);
insert into public.catalog_public_state values(true,1); -- technical epoch, no commercial seed
create trigger state_delete before delete on public.catalog_public_state for each row execute function public.catalog_reject_mutation();
create trigger state_truncate before truncate on public.catalog_public_state for each statement execute function public.catalog_reject_mutation();

create table public.catalog_publications (
  offer_version_id uuid primary key references public.catalog_offer_versions on delete restrict,
  review_id uuid not null unique references public.catalog_publication_reviews on delete restrict,
  draft_id uuid not null,
  source_revision bigint not null check(source_revision>0),
  terminal_revision bigint not null check(terminal_revision=source_revision+1),
  plan_id uuid not null,
  fingerprint text not null check(fingerprint ~ '^[0-9a-f]{64}$'),
  actor_subject uuid not null references auth.users on delete restrict,
  permission_revision bigint not null check(permission_revision>0),
  catalog_revision bigint not null check(catalog_revision>0),
  recorded_at timestamptz not null default clock_timestamp(),
  foreign key(draft_id,source_revision,plan_id) references public.catalog_draft_revisions(draft_id,revision,plan_id) on delete restrict,
  foreign key(draft_id,terminal_revision,plan_id) references public.catalog_draft_revisions(draft_id,revision,plan_id) on delete restrict,
  foreign key(offer_version_id,plan_id) references public.catalog_offer_versions(offer_version_id,plan_id) on delete restrict
);

alter table public.catalog_lifecycle_requests drop constraint catalog_lifecycle_requests_operation_check;
alter table public.catalog_lifecycle_requests alter column draft_id drop not null;
alter table public.catalog_lifecycle_requests alter column review_id drop not null;
alter table public.catalog_lifecycle_requests add column offer_version_id uuid references public.catalog_offer_versions on delete restrict;
alter table public.catalog_lifecycle_requests add column result jsonb;
alter table public.catalog_lifecycle_requests add check(
 (operation='review.create' and draft_id is not null and review_id is not null and offer_version_id is null and result is null)
 or (operation in ('offer.publish','offer.replace','offer.retire') and review_id is null
     and offer_version_id is not null and result is not null and jsonb_typeof(result)='object'
     and result->>'operation' is not distinct from operation
     and (result->>'actor_subject')::uuid is not distinct from actor_subject
     and (result->>'request_id')::uuid is not distinct from request_id
     and (result->>'offer_version_id')::uuid is not distinct from offer_version_id
     and result->>'protocol' is not distinct from 'catalog.lifecycle.result.v1'));
-- F1 positional INSERT continues to use the original leading columns; the
-- new trailing fields default NULL. Existing review rows remain unchanged.
alter table public.catalog_admin_actions drop constraint catalog_admin_actions_operation_check;
alter table public.catalog_admin_actions add constraint catalog_admin_actions_operation_check
 check(operation in ('draft.create','draft.edit','offer.retire','permission.change','snapshot.archive','review.create','offer.publish','offer.replace'));

do $$ declare t text; begin
 foreach t in array array['catalog_publications','catalog_public_state'] loop
  execute format('alter table public.%I enable row level security',t);
  execute format('alter table public.%I force row level security',t);
  execute format('revoke all on public.%I from public,anon,authenticated,service_role,catalog_draft_executor',t);
 end loop;
end; $$;
create trigger immutable_rows before update or delete on public.catalog_publications for each row execute function public.catalog_reject_mutation();
create trigger immutable_truncate before truncate on public.catalog_publications for each statement execute function public.catalog_reject_mutation();

-- Future caller-scoped operation status can reuse this; no public API here.
create function public.catalog_lifecycle_result(p_actor uuid,p_key uuid) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare result jsonb;
begin
 perform public.catalog_locked_actor();
 -- One READ COMMITTED statement snapshot: historical result, current visibility
 -- and epoch cannot be read from mutually inconsistent commits.
 select jsonb_build_object('receipt',r.result,'current',jsonb_build_object(
   'offer_version_id',v.offer_version_id,'revision',v.revision::text,'state',v.state,
   'valid_from',v.valid_from,'valid_until',v.valid_until,'retired_at',v.retired_at),
   'current_catalog_revision',e.revision::text,'publication_enabled',false) into result
 from public.catalog_lifecycle_requests r join public.catalog_visibility v using(offer_version_id)
 cross join public.catalog_public_state e
 where r.actor_subject=p_actor and r.request_id=p_key and r.result is not null and e.singleton;
 if result is null then raise exception 'missing operation' using errcode='P0002'; end if;
 return result;
end; $$;

create function public.catalog_lifecycle_service_call(p_actor uuid,p_stage text,p_request jsonb,p_validated jsonb)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare g public.subscription_admin_permissions; prior public.catalog_lifecycle_requests;
 req uuid; op text; target uuid; review uuid; expected bigint; reason text; h text;
 old_actor text; result jsonb; envelope jsonb; ctx jsonb; b jsonb; snapshot jsonb;
 rr public.catalog_publication_reviews; d public.catalog_drafts; plan uuid;
 v public.catalog_visibility; predecessor public.catalog_visibility; archive public.catalog_offer_versions;
 oid uuid; ver bigint; epoch bigint; action uuid; terminal jsonb; retired_action uuid;
begin
 if session_user<>'catalog_draft_executor' or current_setting('role',true)<>'none' then
  raise exception 'server channel required' using errcode='42501'; end if;
 old_actor:=current_setting('catalog.draft_actor',true);
 perform set_config('catalog.draft_actor',p_actor::text,true);
 g:=public.catalog_locked_actor(); -- always before protected lookup/replay
 op:=p_request->>'operation'; req:=(p_request->>'request_id')::uuid;
 expected:=(p_request->>'expected_revision')::bigint; reason:=p_request->>'reason';
 if p_request is null or jsonb_typeof(p_request)<>'object' or
   (select count(*) from jsonb_object_keys(p_request))<>5 or req is null or expected is null or expected<1
   or jsonb_typeof(p_request->'reason') is distinct from 'string' or length(btrim(reason)) not between 1 and 2000
   or op is null or op not in ('offer.publish','offer.replace','offer.retire') then
  raise exception 'invalid lifecycle request' using errcode='23514'; end if;
 if op='offer.retire' then target:=(p_request->>'offer_version_id')::uuid;
 else review:=(p_request->>'review_id')::uuid; target:=review; end if;
 if target is null then raise exception 'missing target' using errcode='23514'; end if;
 h:=encode(sha256(convert_to(jsonb_build_object('protocol','catalog.lifecycle.request.v1',
   'actor',p_actor,'operation',op,'target',target,'request',p_request)::text,'UTF8')),'hex');
 perform pg_advisory_xact_lock(hashtextextended('catalog.lifecycle.request.v1:'||p_actor::text||':'||req::text,0));
 select * into prior from public.catalog_lifecycle_requests where actor_subject=p_actor and request_id=req;
 if found then
  if prior.semantic_hash<>h then raise exception 'request identity conflict' using errcode='P0003'; end if;
  result:=public.catalog_lifecycle_result(p_actor,req);
 elsif p_stage='prepare' and op<>'offer.retire' and p_validated is null then result:=null;
 else
  if op='offer.retire' then
   if p_stage<>'retire' or p_validated is not null then raise exception 'invalid stage' using errcode='23514'; end if;
   select plan_id into plan from public.catalog_offer_versions where offer_version_id=target;
   if not found then raise exception 'missing offer' using errcode='P0002'; end if;
   perform 1 from public.catalog_plans where plan_id=plan for no key update;
   select * into v from public.catalog_visibility where offer_version_id=target for update;
   if v.revision<>expected or v.state='retired' then raise exception 'stale visibility' using errcode='40001'; end if;
   update public.catalog_visibility set state='retired',revision=revision+1 where offer_version_id=target returning * into v;
   oid:=target;
  else
   envelope:=public.catalog_review_read(review);
   select * into rr from public.catalog_publication_reviews where review_id=review;
   if p_stage='review' and p_validated is null then result:=envelope;
   elsif p_stage='peek' and p_validated is null then result:=public.catalog_adapter_load_draft(rr.draft_id);
   elsif p_stage in ('context','commit') then
    -- All writers take exclusive plan BEFORE draft/review/visibility, no lock upgrade.
    perform 1 from public.catalog_plans where plan_id=rr.plan_id for no key update;
    select * into d from public.catalog_drafts where draft_id=rr.draft_id for update;
    perform 1 from public.catalog_publication_reviews where review_id=review for share;
    perform 1 from public.catalog_visibility where plan_id=rr.plan_id order by offer_version_id for update;
    ctx:=public.catalog_review_context(rr.draft_id);
    select coalesce(max(version),0)+1 into ver from public.catalog_offer_versions where plan_id=rr.plan_id;
    if p_stage='context' and p_validated is null then result:=ctx||jsonb_build_object('next_version',ver::text);
    elsif p_stage='commit' then
     b:=rr.metadata;
     if p_validated is null or (select count(*) from jsonb_object_keys(p_validated))<>2
       or p_validated->'basis' is distinct from b or envelope->>'intact'<>'true'
       or b->>'validation_policy_version' is distinct from 'catalog.validation.v1'
       or b->>'contract_version' is distinct from 'catalog.v1'
       or b->>'registry_version' is distinct from 'catalog.features.v1'
       or b->>'protocol' is distinct from 'catalog.review.v1'
       or d.revision<>expected or d.revision<>rr.source_revision or d.document->>'state'<>'draft'
       or ctx->>'source_hash' is distinct from b->>'source_hash'
       or b->'intent'->>'action' is distinct from substring(op from 7)
       or not ((b->'authority'->>'valid_from')::timestamptz<=clock_timestamp()
           and (b->'authority'->>'valid_until')::timestamptz>clock_timestamp())
       or exists(select 1 from public.catalog_publications where review_id=review) then
      raise exception 'stale review' using errcode='40001'; end if;
     if coalesce(ctx->'heads'->0,'null'::jsonb) is distinct from b->'current_offer'
       or coalesce(ctx->'archive'->'reference','null'::jsonb) is distinct from b->'archived_offer'
       or (op='offer.replace') is distinct from (jsonb_array_length(ctx->'heads')=1) then
      raise exception 'changed catalog head' using errcode='40001'; end if;
     snapshot:=(p_validated->>'canonical_json')::jsonb;
     oid:=(snapshot->>'offer_version_id')::uuid;
     if snapshot->'plan' is distinct from d.document->'plan'
       or snapshot->'terms' is distinct from d.document->'terms' then
      raise exception 'source snapshot mismatch' using errcode='23514'; end if;
     if b->'archived_offer'<>'null'::jsonb then
      select * into archive from public.catalog_offer_versions where offer_version_id=(b->'archived_offer'->>'offer_version_id')::uuid;
      if archive.offer_version_id is distinct from oid or archive.canonical_json is distinct from p_validated->>'canonical_json'
        or ctx->'archive'->>'state' is distinct from 'hidden' then
       raise exception 'archive mismatch' using errcode='40001'; end if;
     else
      if (snapshot->>'version')::bigint is distinct from ver then raise exception 'version mismatch' using errcode='40001'; end if;
      -- Reuse the accepted archive primitive under the unified plan/draft locks.
      perform public.catalog_adapter_archive_snapshot(d.draft_id,d.revision,oid,ver,p_validated->>'canonical_json',reason);
     end if;
     if op='offer.replace' then
      select * into predecessor from public.catalog_visibility where offer_version_id=(b->'current_offer'->>'offer_version_id')::uuid;
      update public.catalog_visibility set state='retired',revision=revision+1 where offer_version_id=predecessor.offer_version_id;
      insert into public.catalog_admin_actions(actor_subject,permission_revision,operation,resource_id,resulting_revision,reason)
       values(g.subject_id,g.revision,'offer.retire',predecessor.offer_version_id,predecessor.revision+1,reason);
     end if;
     update public.catalog_visibility set state='visible',revision=revision+1,
       valid_from=(b->'intent'->>'valid_from')::timestamptz,valid_until=(b->'intent'->>'valid_until')::timestamptz
       where offer_version_id=oid and state='hidden' returning * into v;
     if not found then raise exception 'invalid visibility' using errcode='40001'; end if;
     terminal:=jsonb_set(jsonb_set(d.document,'{state}','"published"'),'{revision}',to_jsonb(d.revision+1));
     update public.catalog_drafts set revision=revision+1,document=terminal where draft_id=d.draft_id;
    else raise exception 'invalid commit' using errcode='23514'; end if;
   else raise exception 'invalid stage' using errcode='23514'; end if;
  end if;
  if result is null then
   -- Global epoch last; independent plans do not lock it until all their work is ready.
   update public.catalog_public_state set revision=revision+1 where singleton returning revision into epoch;
   if epoch is null then raise exception 'missing epoch' using errcode='55000'; end if;
   if op<>'offer.retire' then
    insert into public.catalog_publications(offer_version_id,review_id,draft_id,source_revision,terminal_revision,
      plan_id,fingerprint,actor_subject,permission_revision,catalog_revision)
     select oid,review,d.draft_id,d.revision,d.revision+1,d.plan_id,o.fingerprint,g.subject_id,g.revision,epoch
      from public.catalog_offer_versions o where o.offer_version_id=oid;
   end if;
   insert into public.catalog_admin_actions(actor_subject,permission_revision,operation,resource_id,resulting_revision,reason)
    values(g.subject_id,g.revision,op,oid,v.revision,reason) returning action_id into action;
   result:=jsonb_build_object('protocol','catalog.lifecycle.result.v1','request_id',req,'actor_subject',g.subject_id,
     'permission_revision',g.revision::text,'operation',op,'offer_version_id',oid,'review_id',review,
     'visibility_revision',v.revision::text,'catalog_revision',epoch::text,'recorded_at',clock_timestamp());
   insert into public.catalog_lifecycle_requests(actor_subject,request_id,operation,draft_id,semantic_hash,action_id,offer_version_id,result)
    values(p_actor,req,op,d.draft_id,h,action,oid,result);
   result:=public.catalog_lifecycle_result(p_actor,req);
  end if;
 end if;
 perform set_config('catalog.draft_actor',coalesce(old_actor,''),true);
 return result;
end; $$;

-- The older retirement primitive has no durable result/epoch. It remains closed
-- and cannot be composed as an alternate lifecycle write path after F2.
create or replace function public.catalog_retire_offer(p_id uuid,p_expected bigint,p_reason text)
returns bigint language plpgsql security definer set search_path=pg_catalog as $$
begin raise exception 'use lifecycle boundary' using errcode='42501'; end; $$;

revoke all on function public.catalog_lifecycle_result(uuid,uuid),
 public.catalog_lifecycle_service_call(uuid,text,jsonb,jsonb)
 from public,anon,authenticated,service_role,catalog_draft_executor;
-- NO EXECUTE grant. Existing composition/ACL allowlist deliberately unchanged.
INSERT INTO supabase_migrations.schema_migrations(version) VALUES ('20261022220000');

-- SOURCE: 20261023010000_catalog_lifecycle_transport.sql
-- SHA256: 7dc20ec15639f6bfc630cc280adc2bf0f62a8fd3d356a4c2d4e4c88e3f27850c
-- C11.3F3: exact backend-only grants/read primitives. No public/PostgREST RPC,
-- table access, LOGIN/member provisioning, policy approval or admin assignments.
-- Prepared and applied only in task-owned disposable PostgreSQL in this slice.

create function public.catalog_lifecycle_read_call(p_actor uuid,p_operation text,p_id uuid)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare old_actor text; result jsonb; r public.catalog_lifecycle_requests;
begin
 if session_user<>'catalog_draft_executor' or current_setting('role',true)<>'none' then
  raise exception 'server channel required' using errcode='42501'; end if;
 old_actor:=current_setting('catalog.draft_actor',true);
 perform set_config('catalog.draft_actor',p_actor::text,true);
 perform public.catalog_locked_actor();
 if p_operation='operation' then
  select * into r from public.catalog_lifecycle_requests where actor_subject=p_actor and request_id=p_id;
  if not found then raise exception 'missing operation' using errcode='P0002'; end if;
  if r.operation='review.create' then
   result:=jsonb_build_object('kind','review','review',public.catalog_review_read(r.review_id));
  else
   result:=jsonb_build_object('kind','lifecycle','result',public.catalog_lifecycle_result(p_actor,p_id));
  end if;
 elsif p_operation='offer' then
  -- A single statement snapshot binds immutable terms, provenance, terminal
  -- source, current visibility and epoch. No unprotected listing/direct tables.
  select jsonb_build_object('snapshot',public.catalog_adapter_load_snapshot(o.offer_version_id),
    'current',jsonb_build_object('offer_version_id',v.offer_version_id,'revision',v.revision::text,
      'state',v.state,'valid_from',v.valid_from,'valid_until',v.valid_until,'retired_at',v.retired_at),
    'publication',case when p.offer_version_id is null then null else jsonb_build_object(
      'review_id',p.review_id,'source_revision',p.source_revision::text,
      'terminal_revision',p.terminal_revision::text,'fingerprint',p.fingerprint,
      'catalog_revision',p.catalog_revision::text,'recorded_at',p.recorded_at) end,
    'source',d.document,'catalog_revision',e.revision::text) into result
   from public.catalog_offer_versions o join public.catalog_visibility v using(offer_version_id)
   left join public.catalog_publications p using(offer_version_id)
   left join public.catalog_draft_revisions d on d.draft_id=p.draft_id and d.revision=p.terminal_revision
   cross join public.catalog_public_state e where o.offer_version_id=p_id and e.singleton;
  if result is null then raise exception 'missing offer' using errcode='P0002'; end if;
 else raise exception 'unsupported read' using errcode='23514'; end if;
 perform set_config('catalog.draft_actor',coalesce(old_actor,''),true);
 return result;
end; $$;

revoke all on function public.catalog_lifecycle_read_call(uuid,text,uuid)
 from public,anon,authenticated,service_role,catalog_draft_executor;
-- Exact server session required by ALL gateways; no helper/table grants.
grant execute on function public.catalog_review_service_call(uuid,text,uuid,uuid,jsonb,jsonb),
 public.catalog_lifecycle_service_call(uuid,text,jsonb,jsonb),
 public.catalog_lifecycle_read_call(uuid,text,uuid) to catalog_draft_executor;
INSERT INTO supabase_migrations.schema_migrations(version) VALUES ('20261023010000');

-- SOURCE: 20261023120000_catalog_v2_drafts.sql
-- SHA256: e917376a9c1972032deb9a6e2e709a36de81cd510b76d7289b1169aedcc696a9
-- Additive draft version acceptance only. No permissions, publication or seeds.
do $$ declare item record; begin
 for item in select conname from pg_constraint
 where conrelid='public.catalog_drafts'::regclass and contype='c'
 and (pg_get_constraintdef(oid) like '%contract_version%' or pg_get_constraintdef(oid) like '%registry_version%') loop
 execute format('alter table public.catalog_drafts drop constraint %I',item.conname);
 end loop;
end $$;
alter table public.catalog_drafts add constraint catalog_document_version_pair check (
 (coalesce(document->>'contract_version',''),coalesce(document->>'registry_version',''))
 in (('catalog.v1','catalog.features.v1'),('catalog.v2','catalog.features.v2')));
INSERT INTO supabase_migrations.schema_migrations(version) VALUES ('20261023120000');

-- SOURCE: 20261023130000_catalog_v2_review_binding.sql
-- SHA256: c924ffa6476ee77966fa84300c4fbc943709691b68f9a00ecf831a19c4da5d29
-- Additive v2 review/version compatibility. No new roles, grants or offers.
do $$ declare item record; begin
 for item in select conname from pg_constraint where conrelid='public.catalog_publication_reviews'::regclass and contype='c'
 and (pg_get_constraintdef(oid) like '%contract_version%' or pg_get_constraintdef(oid) like '%registry_version%' or pg_get_constraintdef(oid) like '%validation_policy_version%') loop
 execute format('alter table public.catalog_publication_reviews drop constraint %I',item.conname);
 end loop;
end $$;
alter table public.catalog_publication_reviews add constraint catalog_review_version_triple check (
 (coalesce(metadata->>'contract_version',''),coalesce(metadata->>'registry_version',''),coalesce(metadata->>'validation_policy_version',''))
 in (('catalog.v1','catalog.features.v1','catalog.validation.v1'),('catalog.v2','catalog.features.v2','catalog.validation.v2')));
create or replace function public.catalog_offer_guard() returns trigger
language plpgsql security definer set search_path = pg_catalog as $$
declare d jsonb; derived text; n bigint;
begin
  d:=new.canonical_json::jsonb;
  if (coalesce(d->>'contract_version',''),coalesce(d->>'registry_version','')) not in (('catalog.v1','catalog.features.v1'),('catalog.v2','catalog.features.v2'))
     or (d->>'offer_version_id')::uuid is distinct from new.offer_version_id
     or (d->>'version')::bigint is distinct from new.version
     or (d->'plan'->>'plan_id')::uuid is distinct from new.plan_id
     or d->'plan'->>'code' is distinct from (select code from public.catalog_plans where plan_id=new.plan_id)
     or jsonb_typeof(d->'terms'->'prices') is distinct from 'array' or (jsonb_array_length(d->'terms'->'prices')=0 and not (d->>'contract_version'='catalog.v2' and d->'terms'->>'pricing_mode'='free')) then
    raise exception 'snapshot identity mismatch' using errcode='23514';
  end if;
  -- Serialize version allocation per stable identity; no gapless promise.
  perform 1 from public.catalog_plans where plan_id=new.plan_id for no key update;
  select coalesce(max(version),0) into n from public.catalog_offer_versions where plan_id=new.plan_id;
  if new.version<=n then raise exception 'offer version must increase' using errcode='23514'; end if;
  derived:=encode(sha256(convert_to(new.canonical_json,'UTF8')),'hex');
  if new.fingerprint is not null and new.fingerprint<>derived then
    raise exception 'snapshot fingerprint mismatch' using errcode='23514';
  end if;
  new.fingerprint:=derived;
  return new;
end;
$$;

create or replace function public.catalog_lifecycle_service_call(p_actor uuid,p_stage text,p_request jsonb,p_validated jsonb)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare g public.subscription_admin_permissions; prior public.catalog_lifecycle_requests;
 req uuid; op text; target uuid; review uuid; expected bigint; reason text; h text;
 old_actor text; result jsonb; envelope jsonb; ctx jsonb; b jsonb; snapshot jsonb;
 rr public.catalog_publication_reviews; d public.catalog_drafts; plan uuid;
 v public.catalog_visibility; predecessor public.catalog_visibility; archive public.catalog_offer_versions;
 oid uuid; ver bigint; epoch bigint; action uuid; terminal jsonb; retired_action uuid;
begin
 if session_user<>'catalog_draft_executor' or current_setting('role',true)<>'none' then
  raise exception 'server channel required' using errcode='42501'; end if;
 old_actor:=current_setting('catalog.draft_actor',true);
 perform set_config('catalog.draft_actor',p_actor::text,true);
 g:=public.catalog_locked_actor(); -- always before protected lookup/replay
 op:=p_request->>'operation'; req:=(p_request->>'request_id')::uuid;
 expected:=(p_request->>'expected_revision')::bigint; reason:=p_request->>'reason';
 if p_request is null or jsonb_typeof(p_request)<>'object' or
   (select count(*) from jsonb_object_keys(p_request))<>5 or req is null or expected is null or expected<1
   or jsonb_typeof(p_request->'reason') is distinct from 'string' or length(btrim(reason)) not between 1 and 2000
   or op is null or op not in ('offer.publish','offer.replace','offer.retire') then
  raise exception 'invalid lifecycle request' using errcode='23514'; end if;
 if op='offer.retire' then target:=(p_request->>'offer_version_id')::uuid;
 else review:=(p_request->>'review_id')::uuid; target:=review; end if;
 if target is null then raise exception 'missing target' using errcode='23514'; end if;
 h:=encode(sha256(convert_to(jsonb_build_object('protocol','catalog.lifecycle.request.v1',
   'actor',p_actor,'operation',op,'target',target,'request',p_request)::text,'UTF8')),'hex');
 perform pg_advisory_xact_lock(hashtextextended('catalog.lifecycle.request.v1:'||p_actor::text||':'||req::text,0));
 select * into prior from public.catalog_lifecycle_requests where actor_subject=p_actor and request_id=req;
 if found then
  if prior.semantic_hash<>h then raise exception 'request identity conflict' using errcode='P0003'; end if;
  result:=public.catalog_lifecycle_result(p_actor,req);
 elsif p_stage='prepare' and op<>'offer.retire' and p_validated is null then result:=null;
 else
  if op='offer.retire' then
   if p_stage<>'retire' or p_validated is not null then raise exception 'invalid stage' using errcode='23514'; end if;
   select plan_id into plan from public.catalog_offer_versions where offer_version_id=target;
   if not found then raise exception 'missing offer' using errcode='P0002'; end if;
   perform 1 from public.catalog_plans where plan_id=plan for no key update;
   select * into v from public.catalog_visibility where offer_version_id=target for update;
   if v.revision<>expected or v.state='retired' then raise exception 'stale visibility' using errcode='40001'; end if;
   update public.catalog_visibility set state='retired',revision=revision+1 where offer_version_id=target returning * into v;
   oid:=target;
  else
   envelope:=public.catalog_review_read(review);
   select * into rr from public.catalog_publication_reviews where review_id=review;
   if p_stage='review' and p_validated is null then result:=envelope;
   elsif p_stage='peek' and p_validated is null then result:=public.catalog_adapter_load_draft(rr.draft_id);
   elsif p_stage in ('context','commit') then
    -- All writers take exclusive plan BEFORE draft/review/visibility, no lock upgrade.
    perform 1 from public.catalog_plans where plan_id=rr.plan_id for no key update;
    select * into d from public.catalog_drafts where draft_id=rr.draft_id for update;
    perform 1 from public.catalog_publication_reviews where review_id=review for share;
    perform 1 from public.catalog_visibility where plan_id=rr.plan_id order by offer_version_id for update;
    ctx:=public.catalog_review_context(rr.draft_id);
    select coalesce(max(version),0)+1 into ver from public.catalog_offer_versions where plan_id=rr.plan_id;
    if p_stage='context' and p_validated is null then result:=ctx||jsonb_build_object('next_version',ver::text);
    elsif p_stage='commit' then
     b:=rr.metadata;
     if p_validated is null or (select count(*) from jsonb_object_keys(p_validated))<>2
       or p_validated->'basis' is distinct from b or envelope->>'intact'<>'true'
       or (coalesce(b->>'contract_version',''),coalesce(b->>'registry_version',''),coalesce(b->>'validation_policy_version','')) not in (('catalog.v1','catalog.features.v1','catalog.validation.v1'),('catalog.v2','catalog.features.v2','catalog.validation.v2'))
       or b->>'contract_version' is distinct from d.document->>'contract_version'
       or b->>'registry_version' is distinct from d.document->>'registry_version'
       or b->>'protocol' is distinct from 'catalog.review.v1'
       or d.revision<>expected or d.revision<>rr.source_revision or d.document->>'state'<>'draft'
       or ctx->>'source_hash' is distinct from b->>'source_hash'
       or b->'intent'->>'action' is distinct from substring(op from 7)
       or not ((b->'authority'->>'valid_from')::timestamptz<=clock_timestamp()
           and (b->'authority'->>'valid_until')::timestamptz>clock_timestamp())
       or exists(select 1 from public.catalog_publications where review_id=review) then
      raise exception 'stale review' using errcode='40001'; end if;
     if coalesce(ctx->'heads'->0,'null'::jsonb) is distinct from b->'current_offer'
       or coalesce(ctx->'archive'->'reference','null'::jsonb) is distinct from b->'archived_offer'
       or (op='offer.replace') is distinct from (jsonb_array_length(ctx->'heads')=1) then
      raise exception 'changed catalog head' using errcode='40001'; end if;
     snapshot:=(p_validated->>'canonical_json')::jsonb;
     oid:=(snapshot->>'offer_version_id')::uuid;
     if snapshot->'plan' is distinct from d.document->'plan'
       or snapshot->'terms' is distinct from d.document->'terms' then
      raise exception 'source snapshot mismatch' using errcode='23514'; end if;
     if b->'archived_offer'<>'null'::jsonb then
      select * into archive from public.catalog_offer_versions where offer_version_id=(b->'archived_offer'->>'offer_version_id')::uuid;
      if archive.offer_version_id is distinct from oid or archive.canonical_json is distinct from p_validated->>'canonical_json'
        or ctx->'archive'->>'state' is distinct from 'hidden' then
       raise exception 'archive mismatch' using errcode='40001'; end if;
     else
      if (snapshot->>'version')::bigint is distinct from ver then raise exception 'version mismatch' using errcode='40001'; end if;
      -- Reuse the accepted archive primitive under the unified plan/draft locks.
      perform public.catalog_adapter_archive_snapshot(d.draft_id,d.revision,oid,ver,p_validated->>'canonical_json',reason);
     end if;
     if op='offer.replace' then
      select * into predecessor from public.catalog_visibility where offer_version_id=(b->'current_offer'->>'offer_version_id')::uuid;
      update public.catalog_visibility set state='retired',revision=revision+1 where offer_version_id=predecessor.offer_version_id;
      insert into public.catalog_admin_actions(actor_subject,permission_revision,operation,resource_id,resulting_revision,reason)
       values(g.subject_id,g.revision,'offer.retire',predecessor.offer_version_id,predecessor.revision+1,reason);
     end if;
     update public.catalog_visibility set state='visible',revision=revision+1,
       valid_from=(b->'intent'->>'valid_from')::timestamptz,valid_until=(b->'intent'->>'valid_until')::timestamptz
       where offer_version_id=oid and state='hidden' returning * into v;
     if not found then raise exception 'invalid visibility' using errcode='40001'; end if;
     terminal:=jsonb_set(jsonb_set(d.document,'{state}','"published"'),'{revision}',to_jsonb(d.revision+1));
     update public.catalog_drafts set revision=revision+1,document=terminal where draft_id=d.draft_id;
    else raise exception 'invalid commit' using errcode='23514'; end if;
   else raise exception 'invalid stage' using errcode='23514'; end if;
  end if;
  if result is null then
   -- Global epoch last; independent plans do not lock it until all their work is ready.
   update public.catalog_public_state set revision=revision+1 where singleton returning revision into epoch;
   if epoch is null then raise exception 'missing epoch' using errcode='55000'; end if;
   if op<>'offer.retire' then
    insert into public.catalog_publications(offer_version_id,review_id,draft_id,source_revision,terminal_revision,
      plan_id,fingerprint,actor_subject,permission_revision,catalog_revision)
     select oid,review,d.draft_id,d.revision,d.revision+1,d.plan_id,o.fingerprint,g.subject_id,g.revision,epoch
      from public.catalog_offer_versions o where o.offer_version_id=oid;
   end if;
   insert into public.catalog_admin_actions(actor_subject,permission_revision,operation,resource_id,resulting_revision,reason)
    values(g.subject_id,g.revision,op,oid,v.revision,reason) returning action_id into action;
   result:=jsonb_build_object('protocol','catalog.lifecycle.result.v1','request_id',req,'actor_subject',g.subject_id,
     'permission_revision',g.revision::text,'operation',op,'offer_version_id',oid,'review_id',review,
     'visibility_revision',v.revision::text,'catalog_revision',epoch::text,'recorded_at',clock_timestamp());
   insert into public.catalog_lifecycle_requests(actor_subject,request_id,operation,draft_id,semantic_hash,action_id,offer_version_id,result)
    values(p_actor,req,op,d.draft_id,h,action,oid,result);
   result:=public.catalog_lifecycle_result(p_actor,req);
  end if;
 end if;
 perform set_config('catalog.draft_actor',coalesce(old_actor,''),true);
 return result;
end; $$;
INSERT INTO supabase_migrations.schema_migrations(version) VALUES ('20261023130000');

-- SOURCE: 20261023140000_catalog_v3_terms.sql
-- SHA256: fb16dcc62d0a7afada600886ad44aeb42f2f5d341332abcba7e91fefc1051d74
-- V3 additive compatibility. Existing rows/canonical snapshots are untouched.
-- Additive draft version acceptance only. No permissions, publication or seeds.

do $$ declare item record; begin
 for item in select conname from pg_constraint
 where conrelid='public.catalog_drafts'::regclass and contype='c'
 and (pg_get_constraintdef(oid) like '%contract_version%' or pg_get_constraintdef(oid) like '%registry_version%') loop
 execute format('alter table public.catalog_drafts drop constraint %I',item.conname);
 end loop;
end $$;
alter table public.catalog_drafts add constraint catalog_document_version_pair check (
 (coalesce(document->>'contract_version',''),coalesce(document->>'registry_version',''))
 in (('catalog.v1','catalog.features.v1'),('catalog.v2','catalog.features.v2'),('catalog.v3','catalog.features.v3')));

-- Additive v2 review/version compatibility. No new roles, grants or offers.

do $$ declare item record; begin
 for item in select conname from pg_constraint where conrelid='public.catalog_publication_reviews'::regclass and contype='c'
 and (pg_get_constraintdef(oid) like '%contract_version%' or pg_get_constraintdef(oid) like '%registry_version%' or pg_get_constraintdef(oid) like '%validation_policy_version%') loop
 execute format('alter table public.catalog_publication_reviews drop constraint %I',item.conname);
 end loop;
end $$;
alter table public.catalog_publication_reviews add constraint catalog_review_version_triple check (
 (coalesce(metadata->>'contract_version',''),coalesce(metadata->>'registry_version',''),coalesce(metadata->>'validation_policy_version',''))
 in (('catalog.v1','catalog.features.v1','catalog.validation.v1'),('catalog.v2','catalog.features.v2','catalog.validation.v2'),('catalog.v3','catalog.features.v3','catalog.validation.v3')));
create or replace function public.catalog_offer_guard() returns trigger
language plpgsql security definer set search_path = pg_catalog as $$
declare d jsonb; derived text; n bigint;
begin
  d:=new.canonical_json::jsonb;
  if (coalesce(d->>'contract_version',''),coalesce(d->>'registry_version','')) not in (('catalog.v1','catalog.features.v1'),('catalog.v2','catalog.features.v2'),('catalog.v3','catalog.features.v3'))
     or (d->>'offer_version_id')::uuid is distinct from new.offer_version_id
     or (d->>'version')::bigint is distinct from new.version
     or (d->'plan'->>'plan_id')::uuid is distinct from new.plan_id
     or d->'plan'->>'code' is distinct from (select code from public.catalog_plans where plan_id=new.plan_id)
     or jsonb_typeof(d->'terms'->'prices') is distinct from 'array' or (jsonb_array_length(d->'terms'->'prices')=0 and not (d->>'contract_version' in ('catalog.v2','catalog.v3') and d->'terms'->>'pricing_mode'='free')) then
    raise exception 'snapshot identity mismatch' using errcode='23514';
  end if;
  -- Serialize version allocation per stable identity; no gapless promise.
  perform 1 from public.catalog_plans where plan_id=new.plan_id for no key update;
  select coalesce(max(version),0) into n from public.catalog_offer_versions where plan_id=new.plan_id;
  if new.version<=n then raise exception 'offer version must increase' using errcode='23514'; end if;
  derived:=encode(sha256(convert_to(new.canonical_json,'UTF8')),'hex');
  if new.fingerprint is not null and new.fingerprint<>derived then
    raise exception 'snapshot fingerprint mismatch' using errcode='23514';
  end if;
  new.fingerprint:=derived;
  return new;
end;
$$;

create or replace function public.catalog_lifecycle_service_call(p_actor uuid,p_stage text,p_request jsonb,p_validated jsonb)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare g public.subscription_admin_permissions; prior public.catalog_lifecycle_requests;
 req uuid; op text; target uuid; review uuid; expected bigint; reason text; h text;
 old_actor text; result jsonb; envelope jsonb; ctx jsonb; b jsonb; snapshot jsonb;
 rr public.catalog_publication_reviews; d public.catalog_drafts; plan uuid;
 v public.catalog_visibility; predecessor public.catalog_visibility; archive public.catalog_offer_versions;
 oid uuid; ver bigint; epoch bigint; action uuid; terminal jsonb; retired_action uuid;
begin
 if session_user<>'catalog_draft_executor' or current_setting('role',true)<>'none' then
  raise exception 'server channel required' using errcode='42501'; end if;
 old_actor:=current_setting('catalog.draft_actor',true);
 perform set_config('catalog.draft_actor',p_actor::text,true);
 g:=public.catalog_locked_actor(); -- always before protected lookup/replay
 op:=p_request->>'operation'; req:=(p_request->>'request_id')::uuid;
 expected:=(p_request->>'expected_revision')::bigint; reason:=p_request->>'reason';
 if p_request is null or jsonb_typeof(p_request)<>'object' or
   (select count(*) from jsonb_object_keys(p_request))<>5 or req is null or expected is null or expected<1
   or jsonb_typeof(p_request->'reason') is distinct from 'string' or length(btrim(reason)) not between 1 and 2000
   or op is null or op not in ('offer.publish','offer.replace','offer.retire') then
  raise exception 'invalid lifecycle request' using errcode='23514'; end if;
 if op='offer.retire' then target:=(p_request->>'offer_version_id')::uuid;
 else review:=(p_request->>'review_id')::uuid; target:=review; end if;
 if target is null then raise exception 'missing target' using errcode='23514'; end if;
 h:=encode(sha256(convert_to(jsonb_build_object('protocol','catalog.lifecycle.request.v1',
   'actor',p_actor,'operation',op,'target',target,'request',p_request)::text,'UTF8')),'hex');
 perform pg_advisory_xact_lock(hashtextextended('catalog.lifecycle.request.v1:'||p_actor::text||':'||req::text,0));
 select * into prior from public.catalog_lifecycle_requests where actor_subject=p_actor and request_id=req;
 if found then
  if prior.semantic_hash<>h then raise exception 'request identity conflict' using errcode='P0003'; end if;
  result:=public.catalog_lifecycle_result(p_actor,req);
 elsif p_stage='prepare' and op<>'offer.retire' and p_validated is null then result:=null;
 else
  if op='offer.retire' then
   if p_stage<>'retire' or p_validated is not null then raise exception 'invalid stage' using errcode='23514'; end if;
   select plan_id into plan from public.catalog_offer_versions where offer_version_id=target;
   if not found then raise exception 'missing offer' using errcode='P0002'; end if;
   perform 1 from public.catalog_plans where plan_id=plan for no key update;
   select * into v from public.catalog_visibility where offer_version_id=target for update;
   if v.revision<>expected or v.state='retired' then raise exception 'stale visibility' using errcode='40001'; end if;
   update public.catalog_visibility set state='retired',revision=revision+1 where offer_version_id=target returning * into v;
   oid:=target;
  else
   envelope:=public.catalog_review_read(review);
   select * into rr from public.catalog_publication_reviews where review_id=review;
   if p_stage='review' and p_validated is null then result:=envelope;
   elsif p_stage='peek' and p_validated is null then result:=public.catalog_adapter_load_draft(rr.draft_id);
   elsif p_stage in ('context','commit') then
    -- All writers take exclusive plan BEFORE draft/review/visibility, no lock upgrade.
    perform 1 from public.catalog_plans where plan_id=rr.plan_id for no key update;
    select * into d from public.catalog_drafts where draft_id=rr.draft_id for update;
    perform 1 from public.catalog_publication_reviews where review_id=review for share;
    perform 1 from public.catalog_visibility where plan_id=rr.plan_id order by offer_version_id for update;
    ctx:=public.catalog_review_context(rr.draft_id);
    select coalesce(max(version),0)+1 into ver from public.catalog_offer_versions where plan_id=rr.plan_id;
    if p_stage='context' and p_validated is null then result:=ctx||jsonb_build_object('next_version',ver::text);
    elsif p_stage='commit' then
     b:=rr.metadata;
     if p_validated is null or (select count(*) from jsonb_object_keys(p_validated))<>2
       or p_validated->'basis' is distinct from b or envelope->>'intact'<>'true'
       or (coalesce(b->>'contract_version',''),coalesce(b->>'registry_version',''),coalesce(b->>'validation_policy_version','')) not in (('catalog.v1','catalog.features.v1','catalog.validation.v1'),('catalog.v2','catalog.features.v2','catalog.validation.v2'),('catalog.v3','catalog.features.v3','catalog.validation.v3'))
       or b->>'contract_version' is distinct from d.document->>'contract_version'
       or b->>'registry_version' is distinct from d.document->>'registry_version'
       or b->>'protocol' is distinct from 'catalog.review.v1'
       or d.revision<>expected or d.revision<>rr.source_revision or d.document->>'state'<>'draft'
       or ctx->>'source_hash' is distinct from b->>'source_hash'
       or b->'intent'->>'action' is distinct from substring(op from 7)
       or not ((b->'authority'->>'valid_from')::timestamptz<=clock_timestamp()
           and (b->'authority'->>'valid_until')::timestamptz>clock_timestamp())
       or exists(select 1 from public.catalog_publications where review_id=review) then
      raise exception 'stale review' using errcode='40001'; end if;
     if coalesce(ctx->'heads'->0,'null'::jsonb) is distinct from b->'current_offer'
       or coalesce(ctx->'archive'->'reference','null'::jsonb) is distinct from b->'archived_offer'
       or (op='offer.replace') is distinct from (jsonb_array_length(ctx->'heads')=1) then
      raise exception 'changed catalog head' using errcode='40001'; end if;
     snapshot:=(p_validated->>'canonical_json')::jsonb;
     oid:=(snapshot->>'offer_version_id')::uuid;
     if snapshot->'plan' is distinct from d.document->'plan'
       or snapshot->'terms' is distinct from d.document->'terms' then
      raise exception 'source snapshot mismatch' using errcode='23514'; end if;
     if b->'archived_offer'<>'null'::jsonb then
      select * into archive from public.catalog_offer_versions where offer_version_id=(b->'archived_offer'->>'offer_version_id')::uuid;
      if archive.offer_version_id is distinct from oid or archive.canonical_json is distinct from p_validated->>'canonical_json'
        or ctx->'archive'->>'state' is distinct from 'hidden' then
       raise exception 'archive mismatch' using errcode='40001'; end if;
     else
      if (snapshot->>'version')::bigint is distinct from ver then raise exception 'version mismatch' using errcode='40001'; end if;
      -- Reuse the accepted archive primitive under the unified plan/draft locks.
      perform public.catalog_adapter_archive_snapshot(d.draft_id,d.revision,oid,ver,p_validated->>'canonical_json',reason);
     end if;
     if op='offer.replace' then
      select * into predecessor from public.catalog_visibility where offer_version_id=(b->'current_offer'->>'offer_version_id')::uuid;
      update public.catalog_visibility set state='retired',revision=revision+1 where offer_version_id=predecessor.offer_version_id;
      insert into public.catalog_admin_actions(actor_subject,permission_revision,operation,resource_id,resulting_revision,reason)
       values(g.subject_id,g.revision,'offer.retire',predecessor.offer_version_id,predecessor.revision+1,reason);
     end if;
     update public.catalog_visibility set state='visible',revision=revision+1,
       valid_from=(b->'intent'->>'valid_from')::timestamptz,valid_until=(b->'intent'->>'valid_until')::timestamptz
       where offer_version_id=oid and state='hidden' returning * into v;
     if not found then raise exception 'invalid visibility' using errcode='40001'; end if;
     terminal:=jsonb_set(jsonb_set(d.document,'{state}','"published"'),'{revision}',to_jsonb(d.revision+1));
     update public.catalog_drafts set revision=revision+1,document=terminal where draft_id=d.draft_id;
    else raise exception 'invalid commit' using errcode='23514'; end if;
   else raise exception 'invalid stage' using errcode='23514'; end if;
  end if;
  if result is null then
   -- Global epoch last; independent plans do not lock it until all their work is ready.
   update public.catalog_public_state set revision=revision+1 where singleton returning revision into epoch;
   if epoch is null then raise exception 'missing epoch' using errcode='55000'; end if;
   if op<>'offer.retire' then
    insert into public.catalog_publications(offer_version_id,review_id,draft_id,source_revision,terminal_revision,
      plan_id,fingerprint,actor_subject,permission_revision,catalog_revision)
     select oid,review,d.draft_id,d.revision,d.revision+1,d.plan_id,o.fingerprint,g.subject_id,g.revision,epoch
      from public.catalog_offer_versions o where o.offer_version_id=oid;
   end if;
   insert into public.catalog_admin_actions(actor_subject,permission_revision,operation,resource_id,resulting_revision,reason)
    values(g.subject_id,g.revision,op,oid,v.revision,reason) returning action_id into action;
   result:=jsonb_build_object('protocol','catalog.lifecycle.result.v1','request_id',req,'actor_subject',g.subject_id,
     'permission_revision',g.revision::text,'operation',op,'offer_version_id',oid,'review_id',review,
     'visibility_revision',v.revision::text,'catalog_revision',epoch::text,'recorded_at',clock_timestamp());
   insert into public.catalog_lifecycle_requests(actor_subject,request_id,operation,draft_id,semantic_hash,action_id,offer_version_id,result)
    values(p_actor,req,op,d.draft_id,h,action,oid,result);
   result:=public.catalog_lifecycle_result(p_actor,req);
  end if;
 end if;
 perform set_config('catalog.draft_actor',coalesce(old_actor,''),true);
 return result;
end; $$;

INSERT INTO supabase_migrations.schema_migrations(version) VALUES ('20261023140000');
COMMIT;

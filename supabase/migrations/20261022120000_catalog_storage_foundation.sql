-- C11.2C: additive, closed catalog storage. No offers, subjects or runtime grants.
-- Prepare only; apply solely to an explicitly disposable database in this slice.
-- C11.3 must supply domain-validated publication and verified ingress before grants.
begin;

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
commit;

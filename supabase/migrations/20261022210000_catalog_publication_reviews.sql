-- C11.3F1: closed review evidence ONLY. No publishing or production grants.
-- Apply solely to task-owned disposable PostgreSQL during this slice.
begin;

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
commit;

-- C11.2D: closed private adapter primitives, not publication or public reads.
-- Requires C11.2C. No application EXECUTE/table grants or live subjects.
begin;
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
commit;

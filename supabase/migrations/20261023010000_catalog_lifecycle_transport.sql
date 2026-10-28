-- C11.3F3: exact backend-only grants/read primitives. No public/PostgREST RPC,
-- table access, LOGIN/member provisioning, policy approval or admin assignments.
-- Prepared and applied only in task-owned disposable PostgreSQL in this slice.
begin;

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
commit;

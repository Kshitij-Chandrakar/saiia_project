-- V3 additive compatibility. Existing rows/canonical snapshots are untouched.
begin;
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

commit;

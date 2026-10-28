-- C11.3F2: closed trusted-server transactions, no EXECUTE grants or public reads.
-- Apply only in task-owned disposable PostgreSQL for acceptance. No real offers.
begin;

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
commit;

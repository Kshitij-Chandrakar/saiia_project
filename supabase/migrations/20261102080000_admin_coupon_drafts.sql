-- Inert Super-admin configuration only. No redemption/publication entry point.
begin;
create table administration.coupon_drafts (
 id uuid primary key, code text not null unique check(code ~ '^[A-Z0-9_-]{1,64}$'),
 revision bigint not null check(revision>0), source_discount_id uuid,
 updated_at timestamptz not null default clock_timestamp()
);
create table administration.coupon_requests (
 id uuid primary key, actor uuid not null, coupon_id uuid not null,
 expected bigint not null, code text not null, source_discount_id uuid,
 resulting_revision bigint not null, recorded_at timestamptz not null default clock_timestamp()
);
alter table administration.coupon_drafts enable row level security;
alter table administration.coupon_requests enable row level security;
revoke all on administration.coupon_drafts,administration.coupon_requests from public,anon,authenticated,service_role,admin_executor,admin_bootstrap_executor;
create function public.administration_coupon(p_actor uuid,p_session uuid,p_presence timestamptz,p_action text,p_doc jsonb default '{}')
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare admission jsonb; draft administration.coupon_drafts; prior administration.coupon_requests;
 target uuid; operation uuid; expected bigint; definition uuid; next_revision bigint; page jsonb;
begin
 if session_user<>'admin_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 admission:=public.administration_call(p_actor,null,null,'me','{}');
 if admission ? 'error' then return admission; end if;
 if admission->>'role'<>'super_admin' then
  perform administration.audit_action(p_actor,admission->>'role',null,'coupon','denied',null,gen_random_uuid());
  return jsonb_build_object('error','not_found');
 end if;
 if p_action='list' then
  if p_doc-array['after']<>'{}'::jsonb then return jsonb_build_object('error','invalid'); end if;
  perform administration.audit_action(p_actor,admission->>'role',null,'coupon.read','confirmed',null,gen_random_uuid());
  select coalesce((select jsonb_agg(jsonb_build_object('id',id,'code',code,
   'revision',revision::text,'source_discount_id',source_discount_id,'updated_at',updated_at,
   'eligibility',null,'stacking',null,'redemption_limits',null,'timing_duration',null,'quote_provider_policy',null,
   'redemption_available',false) order by id) from (select * from administration.coupon_drafts
   where id>coalesce((p_doc->>'after')::uuid,'00000000-0000-0000-0000-000000000000'::uuid) order by id limit 101) q),'[]') into page;
  return jsonb_build_object('items',jsonb_path_query_array(page,'$[0 to 99]'),'has_more',jsonb_array_length(page)>100,
   'next_cursor',case when jsonb_array_length(page)>100 then page->99->>'id' else null end,
   'redemption_available',false,'coverage','inert_configuration_only');
 end if;
 if p_action<>'save' or p_doc-array['id','operation_id','expected','code','source_discount_id']<>'{}'::jsonb then return jsonb_build_object('error','invalid'); end if;
 if p_session is null or p_presence is null or p_presence>clock_timestamp() or p_presence<clock_timestamp()-interval '5 minutes'
  or not administration.authenticator_ready(p_actor) then return jsonb_build_object('error','reauthentication_required'); end if;
 if coalesce(p_doc->>'code','') !~ '^[A-Z0-9_-]{1,64}$' or coalesce(p_doc->>'expected','') !~ '^(0|[1-9][0-9]{0,17})$'
  or not(p_doc ? 'source_discount_id') then return jsonb_build_object('error','invalid'); end if;
 target:=(p_doc->>'id')::uuid; operation:=(p_doc->>'operation_id')::uuid; expected:=(p_doc->>'expected')::bigint;
 definition:=(p_doc->>'source_discount_id')::uuid;
 if target is null or operation is null then return jsonb_build_object('error','invalid'); end if;
 -- A reference can only point at an existing Discount; its terms are not copied or inferred.
 if definition is not null and not exists(select 1 from public.catalog_drafts d,
  lateral jsonb_array_elements(coalesce(d.document->'terms'->'discounts','[]')) discount
  where discount->>'discount_id'=definition::text) then return jsonb_build_object('error','invalid'); end if;
 select * into prior from administration.coupon_requests where id=operation;
 if found then
  if prior.actor<>p_actor or prior.coupon_id<>target or prior.expected<>expected or prior.code<>p_doc->>'code'
   or prior.source_discount_id is distinct from definition then return jsonb_build_object('error','conflict'); end if;
  return jsonb_build_object('id',target,'revision',prior.resulting_revision::text,'redemption_available',false);
 end if;
 select * into draft from administration.coupon_drafts where id=target for update;
 if coalesce(draft.revision,0)<>expected then return jsonb_build_object('error','conflict'); end if;
 if exists(select 1 from administration.coupon_drafts where code=p_doc->>'code' and id<>target) then return jsonb_build_object('error','conflict'); end if;
 insert into administration.coupon_drafts(id,code,revision,source_discount_id) values(target,p_doc->>'code',1,definition)
 on conflict(id) do update set code=excluded.code,revision=administration.coupon_drafts.revision+1,source_discount_id=excluded.source_discount_id,updated_at=clock_timestamp()
 returning administration.coupon_drafts.revision into next_revision;
 insert into administration.coupon_requests values(operation,p_actor,target,expected,p_doc->>'code',definition,next_revision,clock_timestamp());
 perform administration.audit_action(p_actor,admission->>'role',target,'coupon.draft','confirmed','commercial',operation);
 return jsonb_build_object('id',target,'revision',next_revision::text,'redemption_available',false);
end$$;
revoke all on function public.administration_coupon(uuid,uuid,timestamptz,text,jsonb) from public,anon,authenticated,service_role,admin_bootstrap_executor;
grant execute on function public.administration_coupon(uuid,uuid,timestamptz,text,jsonb) to admin_executor;
commit;

-- Separate staff restriction axis: no cancellation, suppression, deletion or entitlement extension.
begin;
create table administration.customer_access (
 subject uuid primary key, restricted boolean not null, revision bigint not null check(revision>0),
 changed_at timestamptz not null default clock_timestamp()
);
create table administration.access_reviews (
 id uuid primary key default gen_random_uuid(), actor uuid not null, session_id uuid not null,
 actor_revision bigint not null, target uuid not null, target_revision bigint not null,
 restricted boolean not null, reason text not null check(reason in ('support','security')),
 operation_id uuid not null, expires_at timestamptz not null default clock_timestamp()+interval '5 minutes',
 consumed_at timestamptz, unique(actor,operation_id)
);
alter table administration.customer_access enable row level security;
alter table administration.access_reviews enable row level security;
revoke all on administration.customer_access,administration.access_reviews from public,anon,authenticated,service_role,admin_executor,admin_bootstrap_executor;
create function administration.restricted(p_subject uuid) returns boolean
language sql stable security definer set search_path=pg_catalog as $$
 select exists(select 1 from administration.customer_access where subject=p_subject and restricted)
$$;
revoke all on function administration.restricted(uuid) from public,anon,authenticated,service_role,admin_executor,admin_bootstrap_executor;
create function public.administration_product_access(p_subject uuid) returns boolean
language plpgsql security definer set search_path=pg_catalog as $$
begin
 if session_user<>'admin_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 if not exists(select 1 from administration.configuration where singleton and enabled) then raise exception 'unavailable' using errcode='P0005'; end if;
 return not administration.restricted(p_subject) and not exists(select 1 from public.subscription_deletion_jobs where account_id=p_subject) and not exists(select 1 from public.privacy_restored_subjects where account_id=p_subject) and public.privacy_restore_accessible() and not public.privacy_email_denied((select email from auth.users where id=p_subject));
end$$;
revoke all on function public.administration_product_access(uuid) from public,anon,authenticated,service_role,admin_bootstrap_executor;
grant execute on function public.administration_product_access(uuid) to admin_executor;
create function public.administration_access(p_actor uuid,p_session uuid,p_presence timestamptz,p_action text,p_doc jsonb)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare admission jsonb; m administration.memberships; v administration.access_reviews;
 current_revision bigint; result administration.receipts; target uuid; wanted boolean; operation uuid;
begin
 if session_user<>'admin_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 -- Same authority lock as membership changes prevents promotion/support-target races.
 admission:=public.administration_call(p_actor,null,null,'me','{}');
 if admission ? 'error' then return admission; end if;
 m:=administration.member(p_actor);
 if p_action not in ('review','confirm') or jsonb_typeof(p_doc)<>'object' then return jsonb_build_object('error','invalid'); end if;
 if p_session is null or p_presence is null or p_presence>clock_timestamp() or p_presence<clock_timestamp()-interval '5 minutes' or not administration.authenticator_ready(p_actor) then return jsonb_build_object('error','reauthentication_required'); end if;
 if p_action='review' then
  if not p_doc ?& array['target','restricted','reason','operation_id'] or p_doc-array['target','restricted','reason','operation_id']<>'{}'::jsonb
   or jsonb_typeof(p_doc->'restricted')<>'boolean' or coalesce(p_doc->>'reason','') not in ('support','security') then return jsonb_build_object('error','invalid'); end if;
  target:=(p_doc->>'target')::uuid; wanted:=(p_doc->>'restricted')::boolean; operation:=(p_doc->>'operation_id')::uuid;
  if not wanted and m.role<>'super_admin' then
   perform administration.audit_action(p_actor,m.role,target,'access.restore','denied',p_doc->>'reason',operation);
   return jsonb_build_object('error','not_found'); end if;
  perform 1 from auth.users where id=target for no key update;
  if not found or exists(select 1 from administration.memberships where subject=target) then return jsonb_build_object('error','not_found'); end if;
  select revision into current_revision from administration.customer_access where subject=target;
  select * into v from administration.access_reviews where actor=p_actor and operation_id=operation;
  if found then
   if v.target<>target or v.session_id<>p_session or v.restricted<>wanted or v.reason<>p_doc->>'reason' then return jsonb_build_object('error','conflict'); end if;
  else
  if exists(select 1 from administration.receipts where id=operation) then return jsonb_build_object('error','conflict'); end if;
   insert into administration.access_reviews(actor,session_id,actor_revision,target,target_revision,restricted,reason,operation_id)
   values(p_actor,p_session,m.revision,target,coalesce(current_revision,0),wanted,p_doc->>'reason',operation) returning * into v;
  end if;
  return jsonb_build_object('review_id',v.id,'target',v.target,'restricted',v.restricted,'expires_at',v.expires_at,'operation_id',v.operation_id);
 end if;
 if not p_doc ?& array['review_id','confirm'] or p_doc-array['review_id','confirm']<>'{}'::jsonb or p_doc->'confirm'<>'true'::jsonb then return jsonb_build_object('error','invalid'); end if;
 select * into v from administration.access_reviews where id=(p_doc->>'review_id')::uuid and actor=p_actor and session_id=p_session for update;
 if not found then return jsonb_build_object('error','conflict'); end if;
 if not v.restricted and m.role<>'super_admin' then return jsonb_build_object('error','not_found'); end if;
 select * into result from administration.receipts where id=v.operation_id;
 if found then
  if result.actor<>p_actor or result.review_id<>v.id or result.action<>(case when v.restricted then 'access.restrict' else 'access.restore' end) then return jsonb_build_object('error','conflict'); end if;
  return jsonb_build_object('operation_id',result.id,'state',result.state,'revision',result.revision::text,'restricted',v.restricted,'billing_changed',false); end if;
 if v.actor_revision<>m.revision or v.expires_at<=clock_timestamp() or v.consumed_at is not null then return jsonb_build_object('error','conflict'); end if;
 perform 1 from auth.users where id=v.target for no key update;
 if not found or exists(select 1 from administration.memberships where subject=v.target) then return jsonb_build_object('error','not_found'); end if;
 select revision into current_revision from administration.customer_access where subject=v.target for update;
 if coalesce(current_revision,0)<>v.target_revision then return jsonb_build_object('error','conflict'); end if;
 insert into administration.customer_access(subject,restricted,revision) values(v.target,v.restricted,1)
 on conflict(subject) do update set restricted=excluded.restricted,revision=administration.customer_access.revision+1,changed_at=clock_timestamp()
 returning revision into current_revision;
 insert into administration.receipts(id,actor,review_id,action,target,revision,state)
 values(v.operation_id,p_actor,v.id,case when v.restricted then 'access.restrict' else 'access.restore' end,v.target,current_revision,'confirmed');
 update administration.access_reviews set consumed_at=clock_timestamp() where id=v.id;
 perform administration.audit_action(p_actor,m.role,v.target,case when v.restricted then 'access.restrict' else 'access.restore' end,'confirmed',v.reason,v.operation_id);
 -- No alteration of C15 barriers, provider mandates, paid expiry or customer data.
 return jsonb_build_object('operation_id',v.operation_id,'state','confirmed','revision',current_revision::text,'restricted',v.restricted,'billing_changed',false);
end$$;
revoke all on function public.administration_access(uuid,uuid,timestamptz,text,jsonb) from public,anon,authenticated,service_role,admin_bootstrap_executor;
grant execute on function public.administration_access(uuid,uuid,timestamptz,text,jsonb) to admin_executor;
-- Keep original OIDs and grants: cached callers must see the additional guard.
do $$ declare signature text; definition text; begin
 foreach signature in array array['public.subscription_access_check(uuid)','public.privacy_content_write_guard()','public.privacy_storage_write_guard()'] loop
  definition:=pg_get_functiondef(signature::regprocedure);
  if signature='public.subscription_access_check(uuid)' then
   definition:=replace(definition,'return true;', 'if administration.restricted(p_account) then raise exception ''account restricted'' using errcode=''42501''; end if; return true;');
  else
   definition:=replace(definition,'return new;', 'if administration.restricted(subject) then raise exception ''account restricted'' using errcode=''42501''; end if; return new;');
  end if;
  if definition not like '%administration.restricted%' then raise exception 'guard integration mismatch'; end if;
  execute definition;
 end loop;
 definition:=pg_get_functiondef('public.subscription_account_accessible()'::regprocedure);
 definition:=replace(definition,'if subject is null or', 'if administration.restricted(subject) then return false; end if; if subject is null or');
 if definition not like '%administration.restricted%' then raise exception 'rls integration mismatch'; end if;
 execute definition;
 definition:=pg_get_functiondef('administration.eligible(uuid)'::regprocedure);
 definition:=replace(definition,'select exists(', 'select not administration.restricted(p_subject) and exists(');
 if position('administration.restricted(p_subject)' in definition)=0 then raise exception 'eligible restriction patch mismatch'; end if;
 execute definition;
end$$;
create function public.administration_content_allowed(p_subject uuid) returns boolean
language sql stable security definer set search_path=pg_catalog as $$select not administration.restricted(p_subject)$$;
revoke all on function public.administration_content_allowed(uuid) from public,anon,authenticated,service_role,admin_executor,admin_bootstrap_executor;
grant execute on function public.administration_content_allowed(uuid) to privacy_runtime_owner;
insert into public.privacy_runtime_operations values('3bc813c4ce8441a1a9ca9cb44e44169113ca8bffa46377859cee14d2c123266c','select jsonb_build_array(jsonb_build_array(public.administration_content_allowed(($1->>0)::uuid)))',1,'rows',false,false);
insert into public.privacy_runtime_operations values('96db93374f08084f435951098a92b4607f550ec7843c00435d525540244468f8','select jsonb_build_array(jsonb_build_array(to_regprocedure(''public.administration_content_allowed(uuid)'') is not null))',0,'rows',false,false);
commit;

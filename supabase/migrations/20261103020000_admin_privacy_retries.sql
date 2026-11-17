-- Exact-task retry only. No deletion initiation, changed scope or mark-complete action.
begin;
create table administration.privacy_reviews (
 id uuid primary key default gen_random_uuid(), actor uuid not null, session_id uuid not null,
 actor_revision bigint not null, task_id uuid not null, account_id uuid not null,
 task_revision bigint not null, operation_id uuid not null, reason text not null check(reason in ('support','security')),
 expires_at timestamptz not null default clock_timestamp()+interval '5 minutes', consumed_at timestamptz,
 unique(actor,operation_id)
);
alter table administration.privacy_reviews enable row level security;
revoke all on administration.privacy_reviews from public,anon,authenticated,service_role,admin_executor,admin_bootstrap_executor;
create function administration.retry_eligible(p_task uuid) returns boolean
language sql stable security definer set search_path=pg_catalog as $$
 select exists(select 1 from public.privacy_content_jobs j where j.id=p_task
 and j.kind in ('account','session','history') and j.state in ('blocked','failed') and j.attempts<5
 and (j.lease_id is null or j.lease_until<=statement_timestamp())
 and j.blockers <@ '["storage_forbidden_not_absence","storage_unavailable"]'::jsonb
 and not exists(select 1 from administration.memberships where subject=j.account_id)
 and (j.kind<>'account' or exists(select 1 from public.privacy_deletion_requests r
  where r.account_id=j.account_id and r.request_id=j.id and r.accepted_at is not null and r.scope='whole_account'))
 and not exists(select 1 from public.privacy_retirement_units u join public.privacy_retirement_holds h using(unit_id) where u.account_id=j.account_id and h.active))
$$;
revoke all on function administration.retry_eligible(uuid) from public,anon,authenticated,service_role,admin_executor,admin_bootstrap_executor;
create function public.administration_privacy_retry(p_actor uuid,p_session uuid,p_presence timestamptz,p_action text,p_doc jsonb)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare admission jsonb; m administration.memberships; v administration.privacy_reviews;
 j public.privacy_content_jobs; receipt administration.receipts; target uuid; operation uuid;
begin
 if session_user<>'admin_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 admission:=public.administration_call(p_actor,null,null,'me','{}');
 if admission ? 'error' then return admission; end if;
 m:=administration.member(p_actor);
 if p_action not in ('review','confirm') or jsonb_typeof(p_doc)<>'object' then return jsonb_build_object('error','invalid'); end if;
 if p_session is null or p_presence is null or p_presence>clock_timestamp() or p_presence<clock_timestamp()-interval '5 minutes' or not administration.authenticator_ready(p_actor) then return jsonb_build_object('error','reauthentication_required'); end if;
 if p_action='review' then
  if not p_doc ?& array['task_id','revision','reason','operation_id'] or p_doc-array['task_id','revision','reason','operation_id']<>'{}'::jsonb or coalesce(p_doc->>'reason','') not in ('support','security') then return jsonb_build_object('error','invalid'); end if;
  target:=(p_doc->>'task_id')::uuid; operation:=(p_doc->>'operation_id')::uuid;
  select * into j from public.privacy_content_jobs where id=target;
  if not found or not administration.retry_eligible(target) or j.revision::text<>p_doc->>'revision' then return jsonb_build_object('error','retry_unavailable'); end if;
  select * into v from administration.privacy_reviews where actor=p_actor and operation_id=operation;
  if found then
   if v.task_id<>target or v.task_revision<>j.revision or v.session_id<>p_session or v.reason<>p_doc->>'reason' then return jsonb_build_object('error','conflict'); end if;
  else
   insert into administration.privacy_reviews(actor,session_id,actor_revision,task_id,account_id,task_revision,operation_id,reason)
   values(p_actor,p_session,m.revision,j.id,j.account_id,j.revision,operation,p_doc->>'reason') returning * into v;
  end if;
  return jsonb_build_object('review_id',v.id,'task_id',v.task_id,'revision',v.task_revision::text,'expires_at',v.expires_at);
 end if;
 if not p_doc ?& array['review_id','confirm'] or p_doc-array['review_id','confirm']<>'{}'::jsonb or p_doc->'confirm'<>'true'::jsonb then return jsonb_build_object('error','invalid'); end if;
 select * into v from administration.privacy_reviews where id=(p_doc->>'review_id')::uuid and actor=p_actor and session_id=p_session for update;
 if not found then return jsonb_build_object('error','not_found'); end if;
 select * into receipt from administration.receipts where id=v.operation_id and actor=p_actor;
 if found then return jsonb_build_object('state',receipt.state,'operation_id',receipt.id,'revision',receipt.revision::text); end if;
 if v.actor_revision<>m.revision or v.expires_at<=clock_timestamp() or v.consumed_at is not null then return jsonb_build_object('error','conflict'); end if;
 -- Preserve worker lock order: authority -> account -> task. No active lease is reset.
 perform 1 from auth.users where id=v.account_id for no key update;
 select * into j from public.privacy_content_jobs where id=v.task_id and account_id=v.account_id for update;
 if not found or j.revision<>v.task_revision or not administration.retry_eligible(j.id) then return jsonb_build_object('error','retry_unavailable'); end if;
 update public.privacy_content_jobs set state='pending',retry_at=clock_timestamp(),lease_id=null,lease_until=null,revision=revision+1 where id=j.id returning * into j;
 insert into administration.receipts(id,actor,review_id,action,target,revision,state) values(v.operation_id,p_actor,v.id,'privacy.retry',j.account_id,j.revision,'queued');
 update administration.privacy_reviews set consumed_at=clock_timestamp() where id=v.id;
 perform administration.audit_action(p_actor,m.role,j.account_id,'privacy.retry','queued',v.reason,v.operation_id);
 return jsonb_build_object('state','queued','operation_id',v.operation_id,'revision',j.revision::text);
end$$;
revoke all on function public.administration_privacy_retry(uuid,uuid,timestamptz,text,jsonb) from public,anon,authenticated,service_role,admin_bootstrap_executor;
grant execute on function public.administration_privacy_retry(uuid,uuid,timestamptz,text,jsonb) to admin_executor;
do $$ declare definition text; old text; new text; begin
 definition:=pg_get_functiondef('public.administration_read(uuid,text,uuid,uuid,text)'::regprocedure);
 old:='''as_of'',statement_timestamp()) into result from public.privacy_deletion_requests where account_id=p_target;';
 new:='''as_of'',statement_timestamp(),''tasks'',(select coalesce(jsonb_agg(jsonb_build_object(''task_id'',q.id,''kind'',q.kind,''state'',q.state,''revision'',q.revision::text,''attempts'',q.attempts,''retry_available'',administration.retry_eligible(q.id))),''[]'') from (select id,kind,state,revision,attempts from public.privacy_content_jobs where account_id=p_target and kind<>''export'' order by created_at desc limit 100) q)) into result from public.privacy_deletion_requests where account_id=p_target;';
 if position(old in definition)=0 then raise exception 'privacy projection mismatch'; end if;
 execute replace(definition,old,new);
end$$;
commit;

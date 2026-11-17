begin;
create role admin_dispatch_executor nologin nosuperuser nocreatedb nocreaterole noinherit nobypassrls;
create table administration.command_reviews (
 id uuid primary key default gen_random_uuid(), actor uuid not null, session_id uuid not null,
 actor_revision bigint not null, target uuid not null, operation_id uuid not null,
 billing_id uuid not null, snapshot text not null, reason text not null check(reason in ('support','security')),
 expires_at timestamptz not null default clock_timestamp()+interval '5 minutes', consumed_at timestamptz,
 unique(actor,operation_id)
);
create table administration.commands (
 id uuid primary key, actor uuid not null, actor_revision bigint not null, target uuid not null,
 billing_id uuid not null, reason text not null, state text not null default 'pending'
 check(state in ('pending','running','unknown','confirmed','failed','blocked')),
 lease uuid, lease_until timestamptz, attempts integer not null default 0,
 dispatched boolean not null default false, created_at timestamptz not null default clock_timestamp(),
 updated_at timestamptz not null default clock_timestamp()
);
alter table administration.command_reviews enable row level security;
alter table administration.commands enable row level security;
revoke all on administration.command_reviews,administration.commands from public,anon,authenticated,service_role,admin_executor,admin_bootstrap_executor,admin_retention_executor,admin_dispatch_executor;
create function administration.billing_snapshot(p_id uuid) returns text language sql stable security definer set search_path=pg_catalog as $$
 select encode(sha256(convert_to(jsonb_build_array(o.operation_id,o.account_id,o.state,o.cancel_requested,o.provider_state,b.revision)::text,'UTF8')),'hex') from public.billing_operations o join public.account_plan_bindings b on b.account_id=o.account_id where o.operation_id=p_id
$$;
revoke all on function administration.billing_snapshot(uuid) from public,anon,authenticated,service_role,admin_executor,admin_dispatch_executor;
create function public.administration_cancel(p_actor uuid,p_session uuid,p_presence timestamptz,p_action text,p_doc jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare access jsonb; member administration.memberships; v administration.command_reviews; o public.billing_operations; prior administration.receipts;
begin
 if session_user<>'admin_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 access:=public.administration_call(p_actor,null,null,'me','{}'); if access ? 'error' then return access; end if;
 member:=administration.member(p_actor);
 if p_action='status' then
  return coalesce((select jsonb_build_object('operation_id',id,'state',state,'updated_at',updated_at,'billing_cancelled',state='confirmed','access_revoked',false) from administration.commands where id=(p_doc->>'operation_id')::uuid and actor=p_actor),jsonb_build_object('error','not_found'));
 end if;
 if p_session is null or p_presence is null or p_presence>clock_timestamp() or p_presence<clock_timestamp()-interval '5 minutes' or not administration.authenticator_ready(p_actor) then return jsonb_build_object('error','reauthentication_required'); end if;
 if p_action='review' then
  if not p_doc ?& array['target','billing_id','operation_id','reason'] or p_doc-array['target','billing_id','operation_id','reason']<>'{}'::jsonb or coalesce(p_doc->>'reason','') not in ('support','security') then return jsonb_build_object('error','invalid'); end if;
  perform 1 from auth.users where id=(p_doc->>'target')::uuid for no key update;
  if not found or exists(select 1 from administration.memberships where subject=(p_doc->>'target')::uuid) then return jsonb_build_object('error','not_found'); end if;
  select * into o from public.billing_operations where operation_id=(p_doc->>'billing_id')::uuid and account_id=(p_doc->>'target')::uuid;
  if not found or o.provider_id is null or o.provider_state in ('cancelled','completed','expired') then return jsonb_build_object('error','cancellation_unavailable'); end if;
  select * into v from administration.command_reviews where actor=p_actor and operation_id=(p_doc->>'operation_id')::uuid;
  if found then
   if v.target<>o.account_id or v.billing_id<>o.operation_id or v.session_id<>p_session or v.reason<>p_doc->>'reason' then return jsonb_build_object('error','conflict'); end if;
  else
   insert into administration.command_reviews(actor,session_id,actor_revision,target,operation_id,billing_id,snapshot,reason)
   values(p_actor,p_session,member.revision,o.account_id,(p_doc->>'operation_id')::uuid,o.operation_id,administration.billing_snapshot(o.operation_id),p_doc->>'reason') returning * into v;
  end if;
  return jsonb_build_object('review_id',v.id,'operation_id',v.operation_id,'expires_at',v.expires_at,'paid_access_preserved',true,'refund_initiated',false);
 elsif p_action='confirm' then
  if not p_doc ?& array['review_id','confirm'] or p_doc-array['review_id','confirm']<>'{}'::jsonb or p_doc->'confirm'<>'true'::jsonb then return jsonb_build_object('error','invalid'); end if;
  select * into prior from administration.receipts where actor=p_actor and review_id=(p_doc->>'review_id')::uuid and action='renewal.cancel';
  if found then return jsonb_build_object('operation_id',prior.id,'state',prior.state); end if;
  select * into v from administration.command_reviews where id=(p_doc->>'review_id')::uuid and actor=p_actor and session_id=p_session for update;
  if not found or v.expires_at<=clock_timestamp() or v.consumed_at is not null or v.actor_revision<>member.revision then return jsonb_build_object('error','conflict'); end if;
  perform 1 from auth.users where id=v.target for no key update;
  if exists(select 1 from administration.memberships where subject=v.target) or v.snapshot is distinct from administration.billing_snapshot(v.billing_id) then return jsonb_build_object('error','conflict'); end if;
  insert into administration.commands(id,actor,actor_revision,target,billing_id,reason) values(v.operation_id,p_actor,member.revision,v.target,v.billing_id,v.reason);
  insert into administration.receipts(id,actor,review_id,action,target,revision,state) values(v.operation_id,p_actor,v.id,'renewal.cancel',v.target,1,'queued');
  update administration.command_reviews set consumed_at=clock_timestamp() where id=v.id;
  perform administration.audit_action(p_actor,member.role,v.target,'renewal.cancel','queued',v.reason,v.operation_id);
  return jsonb_build_object('operation_id',v.operation_id,'state','queued');
 end if;
 return jsonb_build_object('error','invalid');
end$$;
revoke all on function public.administration_cancel(uuid,uuid,timestamptz,text,jsonb) from public,anon,authenticated,service_role,admin_bootstrap_executor,admin_dispatch_executor;
grant execute on function public.administration_cancel(uuid,uuid,timestamptz,text,jsonb) to admin_executor;
create function public.administration_command(p_action text,p_doc jsonb) returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare command administration.commands; member administration.memberships; begin
 if session_user<>'admin_dispatch_executor' or current_setting('role',true)<>'none' or jsonb_typeof(p_doc)<>'object' then raise exception 'denied' using errcode='42501'; end if;
 perform 1 from administration.configuration where singleton and enabled for update; if not found then return null; end if;
 if p_action='claim' then
  select * into command from administration.commands where (state='pending' or state in ('running','unknown') and lease_until<=clock_timestamp()) and attempts<5 order by created_at for update skip locked limit 1;
  if not found then return null; end if;
  member:=administration.member(command.actor);
  if member.subject is null or member.revision<>command.actor_revision or exists(select 1 from administration.memberships where subject=command.target) then
   update administration.commands set state='blocked',updated_at=clock_timestamp() where id=command.id;
   perform administration.audit_action(command.actor,member.role,command.target,'renewal.cancel','authority_changed',command.reason,command.id); return null;
  end if;
  update administration.commands set state='running',lease=gen_random_uuid(),lease_until=clock_timestamp()+interval '30 seconds',attempts=attempts+1,updated_at=clock_timestamp() where id=command.id returning * into command;
  return jsonb_build_object('id',command.id,'account_id',command.target,'billing_id',command.billing_id,'lease',command.lease,'reconcile_only',command.dispatched);
 end if;
 select * into command from administration.commands where id=(p_doc->>'id')::uuid and lease=(p_doc->>'lease')::uuid and state='running' and lease_until>clock_timestamp() for update;
 if not found then raise exception 'stale command' using errcode='40001'; end if;
 member:=administration.member(command.actor);
 if member.subject is null or member.revision<>command.actor_revision or exists(select 1 from administration.memberships where subject=command.target) then
  update administration.commands set state='blocked',lease=null,lease_until=null,updated_at=clock_timestamp() where id=command.id; return jsonb_build_object('allowed',false);
 end if;
 if p_action='dispatch' then
  update administration.commands set dispatched=true where id=command.id;
  return jsonb_build_object('allowed',true);
 elsif p_action='finish' then
  if coalesce(p_doc->>'outcome','') not in ('confirmed','unknown','failed') then raise exception 'invalid outcome' using errcode='22023'; end if;
  update administration.commands set state=p_doc->>'outcome',lease=null,lease_until=clock_timestamp()+interval '30 seconds',updated_at=clock_timestamp() where id=command.id;
  perform administration.audit_action(command.actor,member.role,command.target,'renewal.cancel',p_doc->>'outcome',command.reason,command.id);
  return jsonb_build_object('state',p_doc->>'outcome');
 end if;
 raise exception 'invalid command' using errcode='22023';
end$$;
revoke all on function public.administration_command(text,jsonb) from public,anon,authenticated,service_role,admin_executor,admin_bootstrap_executor,admin_retention_executor;
grant execute on function public.administration_command(text,jsonb) to admin_dispatch_executor;
commit;
